"""Offline runner-callpath tests. All real sockets are loopback, no VPN credentials."""
import asyncio
import copy
from contextlib import redirect_stdout
import io
import ipaddress
import json
import os
from pathlib import Path
import shutil
import signal
import socket
import stat
import struct
import sys
import tempfile
import unittest
from unittest import mock

import pool_probe as pool


def manifest():
    return {"binary": "/not/a/live/core", "nodes": {
        role: {"server": "93.184.216." + str(30 + i), "server_port": 443,
               "expected_exit_ipv4": "93.184.216." + str(40 + i)}
        for i, role in enumerate(pool.ROLES)},
        "targets": {"api.ipify.org": "104.26.12.205", "www.wikipedia.org": "185.15.59.224"}}


def profile():
    """Sanitized production shape, not a renderer or deployable configuration."""
    data = manifest()
    return {"log": {"level": "warn", "timestamp": True},
        "inbounds": [{"type": "tun", "tag": "tun-in", "auto_route": True, "strict_route": True}],
        "outbounds": [copy.deepcopy(pool.POOL)] + [
            {"type": "vless", "tag": role, "server": node["server"], "server_port": 443,
             "uuid": "00000000-0000-4000-8000-000000000001", "flow": "xtls-rprx-vision",
             "domain_resolver": "bootstrap", "tls": {"enabled": True, "server_name": "example.com",
                "utls": {"enabled": True, "fingerprint": "firefox"}, "reality": {
                    "enabled": True, "public_key": "A" * 43, "short_id": "abcd"}}}
            for role, node in data["nodes"].items()] + [
                {"type": "direct", "tag": "direct", "domain_resolver": "bootstrap"}],
        "dns": {"strategy": "ipv4_only", "final": "remote", "servers": [
            {"type": "https", "tag": "bootstrap", "server": "1.1.1.1", "server_port": 443,
             "path": "/dns-query", "detour": "direct"},
            {"type": "https", "tag": "remote", "server": "8.8.8.8", "server_port": 443,
             "path": "/dns-query", "detour": "proxy"}, {"type": "local", "tag": "local"}],
            "rules": [{"domain_suffix": ["local", "lan", "home.arpa"], "action": "route", "server": "local"},
                      {"query_type": ["AAAA"], "action": "predefined", "rcode": "NOERROR"},
                      {"domain": ["config.nikcode.xyz"], "action": "route", "server": "bootstrap"},
                      {"domain_suffix": ["ru", "su", "xn--p1ai"], "action": "route", "server": "bootstrap"}]},
        "route": {"auto_detect_interface": True, "default_domain_resolver": "remote", "final": "proxy",
                  "rule_set": [{"type": "inline", "tag": "geoip-ru", "rules": [{"ip_cidr": ["5.128.0.0/14"]}]}],
                  "rules": [{"action": "sniff", "inbound": ["tun-in"]},
                            {"protocol": "dns", "action": "hijack-dns"},
                            {"ip_is_private": True, "action": "route", "outbound": "direct"},
                            {"ip_cidr": ["ff00::/8"], "action": "route", "outbound": "direct"},
                            {"ip_version": 6, "action": "reject", "method": "default", "no_drop": True},
                            {"domain": ["config.nikcode.xyz"], "network": "tcp", "port": [443],
                             "action": "route", "outbound": "direct"},
                            {"domain_suffix": ["local", "lan", "home.arpa", "ru", "su", "xn--p1ai"],
                             "action": "route", "outbound": "direct"},
                            {"rule_set": ["geoip-ru"], "action": "route", "outbound": "direct"}]},
        "experimental": {"cache_file": {"enabled": True, "cache_id": "test-only"}}}


def write_private(path, value):
    path.write_text(json.dumps(value))
    path.chmod(0o600)


async def exact_gate_refusal(gate):
    """Real authenticated local SOCKS attempt; never opens an upstream socket."""
    reader, writer = await asyncio.open_connection("127.0.0.1", gate.port)
    try:
        writer.write(b"\x05\x01\x02")
        await writer.drain()
        assert await reader.readexactly(2) == b"\x05\x02"
        user, password = gate.username.encode(), gate.password.encode()
        writer.write(b"\x01" + bytes([len(user)]) + user + bytes([len(password)]) + password)
        await writer.drain()
        assert await reader.readexactly(2) == b"\x01\x00"
        ip = ipaddress.ip_address(gate.address)
        writer.write(bytes([5, 1, 0, 1 if ip.version == 4 else 4]) + ip.packed
                     + struct.pack("!H", gate.target_port))
        await writer.drain()
        assert (await reader.readexactly(10))[:2] == b"\x05\x02"
    finally:
        writer.close()
        await writer.wait_closed()


class ProfileTests(unittest.TestCase):
    def test_actual_clone_retains_rules_dns_and_original_identity(self):
        original = profile()
        original["outbounds"][1]["bind_interface"] = "wlo1"
        saved = copy.deepcopy(original)
        gates = {r: mock.Mock(port=23000 + i, username="test", password="test")
                 for i, r in enumerate(pool.ROLES)}
        clone = pool.clone_profile(original, manifest(), 22000,
                                   {"username": "local", "password": "secret"}, gates)
        self.assertEqual(original, saved)
        self.assertEqual(clone["dns"], original["dns"])
        self.assertEqual(clone["route"]["rules"], original["route"]["rules"])
        self.assertEqual(clone["route"]["rule_set"], original["route"]["rule_set"])
        self.assertEqual(clone["outbounds"][0], original["outbounds"][0])
        for i, role in enumerate(pool.ROLES, 1):
            node = clone["outbounds"][i]
            self.assertNotIn("bind_interface", node)
            self.assertEqual(node["detour"], "gate-" + role)
            for key in ("tls", "uuid", "server", "server_port", "flow"):
                self.assertEqual(node[key], original["outbounds"][i][key])
        self.assertEqual(clone["inbounds"][0]["tag"], "tun-in")
        self.assertEqual(clone["inbounds"][0]["listen"], "127.0.0.1")
        self.assertFalse(clone["inbounds"][0]["set_system_proxy"])
        self.assertEqual(clone["experimental"], {"cache_file": {"enabled": False}})
        self.assertEqual(clone["outbounds"][5]["bind_interface"], "wlo1")
        self.assertTrue(all("bind_interface" not in o for o in clone["outbounds"][6:]))

    def test_strict_flat_membership_and_production_options(self):
        changes = [{"interval": "1s"}, {"tolerance": 0}, {"tolerance": True},
                   {"interrupt_exist_connections": True}, {"url": "http://example.com"},
                   {"outbounds": ["france", "frankfurt"]},
                   {"outbounds": ["france", "frankfurt", "poland", "direct"]},
                   {"outbounds": ["france", "frankfurt", "poland", "poland"]},
                   {"type": "selector"}, {"idle_timeout": "5s"}]
        for change in changes:
            with self.subTest(change=change):
                value = profile()
                value["outbounds"][0].update(change)
                with self.assertRaises(pool.Error):
                    pool.validate_profile(value, manifest())
        value = profile()
        value["outbounds"][0]["outbounds"].reverse()
        pool.validate_profile(value, manifest())  # Equal membership, no artificial order constraint.

    def test_rejects_unsupported_profiles_instead_of_changing_semantics(self):
        for mutation in (
            lambda p: p.update(endpoints=[{"type": "tailscale"}]),
            lambda p: p.update(services=[{"type": "resolved"}]),
            lambda p: p["route"].update(final="direct"),
            lambda p: p["outbounds"].append({"type": "selector", "tag": "fallback"}),
            lambda p: p["outbounds"][1].update(detour="existing-vpn"),
            lambda p: p["outbounds"][1].update(bind_address="1.2.3.4"),
            lambda p: p["outbounds"][1].update(multiplex={"enabled": True}),
            lambda p: p["outbounds"][1]["tls"].update(certificate_path="/secret"),
            lambda p: p["outbounds"][1].update(server="93.184.216.99"),
            lambda p: p["dns"]["servers"][0].update(detour="proxy"),
            lambda p: p["dns"]["servers"][0].update(bind_interface="tun0"),
            lambda p: p["route"]["rule_set"][0].update(type="local", path="/shared/rules"),
            lambda p: p["route"]["rule_set"][0]["rules"][0].update(ip_cidr=["0.0.0.0/0"]),
            lambda p: p["route"]["rules"][0].update(inbound=["other"]),
            lambda p: p["experimental"].update(clash_api={"default_mode": "direct"}),
            lambda p: p["experimental"].update(clash_api={"default_mode": "global"}),
        ):
            with self.subTest(mutation=mutation):
                value = profile()
                mutation(value)
                with self.assertRaises(pool.Error):
                    pool.validate_profile(value, manifest())

    def test_remote_mode_retained_not_forced_inline(self):
        value = profile()
        value["route"]["rule_set"] = [{"type": "remote", "tag": "geoip-ru", "format": "binary",
            "url": "https://subscriptions.nikcode.xyz/rules/geoip-test.srs",
            "http_client": {"engine": "go", "detour": "direct"}, "update_interval": "168h"}]
        self.assertEqual(pool.validate_profile(value, manifest()), value)

    @unittest.skipUnless(shutil.which("node"), "local node unavailable")
    def test_real_production_renderer_shapes_inline_and_remote_offline(self):
        config = {"schema": 1, "nodes": [
            {"id": role, "enabled": True, "protocol": "vless", "host": node["server"],
             "port": node["server_port"], "server_name": "example.com", "public_key": "A" * 43,
             "short_id": "abcd"} for role, node in manifest()["nodes"].items()],
            "ru_rules": [{"ip_cidr": ["5.128.0.0/14"]}], "devices": [{
                "id": "test-only", "hash": "0" * 64, "enabled": True, "tailscale": False,
                "credentials": {role: {"uuid": "00000000-0000-4000-8000-%012d" % (i + 1)}
                                for i, role in enumerate(pool.ROLES)}}]}
        script = ("import {singBoxPilot,validPilot,OWN_RULES_URL} from './tools/nikcode-network/src/worker.js';"
                  "let s='';for await(const c of process.stdin)s+=c;const p=JSON.parse(s);"
                  "p.rules_url=OWN_RULES_URL;if(!validPilot(p))process.exit(1);"
                  "process.stdout.write(JSON.stringify(singBoxPilot(p,p.devices[0])));")
        for mode in ("inline", "remote"):
            with self.subTest(mode=mode):
                config["devices"][0]["rule_set_mode"] = mode
                rendered = pool.probe.subprocess.run([shutil.which("node"), "--input-type=module", "-e", script],
                    input=json.dumps(config).encode(), cwd=str(pool.REPO), stdout=pool.probe.subprocess.PIPE,
                    stderr=pool.probe.subprocess.PIPE, timeout=5, env=pool.probe.child_env())
                self.assertEqual(rendered.returncode, 0)
                actual = json.loads(rendered.stdout)
                pool.validate_profile(actual, manifest())
                self.assertEqual(actual["route"]["rule_set"][0]["type"], mode)
                gates = {role: mock.Mock(port=23000 + i, username="u", password="p")
                         for i, role in enumerate(pool.ROLES)}
                cloned = pool.clone_profile(actual, manifest(), 22000, {"username": "u", "password": "p"}, gates)
                self.assertEqual(cloned["route"]["rule_set"], actual["route"]["rule_set"])
                self.assertEqual(cloned["route"]["rules"], actual["route"]["rules"])
                self.assertEqual(cloned["dns"], actual["dns"])
                if mode == "inline":
                    pool.validate_foreign_routes(actual, manifest())
                else:
                    with self.assertRaisesRegex(pool.Error, "foreign_cut_requires_inline_rules"):
                        pool.validate_foreign_routes(actual, manifest())

    def test_foreign_cut_rejects_matching_or_ambiguous_exception_rules(self):
        for rule in (
            {"domain": ["API.IPIFY.ORG."]}, {"domain_suffix": ["org"]},
            {"domain": [manifest()["targets"][pool.HOSTS[0]]]},
            {"ip_cidr": [manifest()["targets"][pool.HOSTS[1]] + "/32"]},
            {"domain": ["api.ipify.org"], "domain_suffix": ["ru"]},
            {"ip_cidr": ["0.0.0.0/0"], "ip_is_private": True},
            {"domain_suffix": []}, {"domain": []}, {"ip_cidr": []},
            {"domain_suffix": ["."]}, {"port": [443]}, {},
        ):
            with self.subTest(rule=rule):
                value = profile()
                value["route"]["rules"].append(dict(rule, action="route", outbound="direct"))
                pool.validate_profile(value, manifest())
                with self.assertRaisesRegex(pool.Error, "foreign_cut_route_not_proven"):
                    pool.validate_foreign_routes(value, manifest())
        value = profile()
        value["route"]["rule_set"][0]["rules"].append({"ip_cidr": []})
        with self.assertRaisesRegex(pool.Error, "unsupported_inline_ru_rule"):
            pool.validate_profile(value, manifest())

    def test_manifest_exact_nodes_exits_and_targets(self):
        pool.validate_manifest(manifest())
        for mutation in (
            lambda m: m["nodes"].pop("italy"),
            lambda m: m["nodes"]["poland"].update(expected_exit_ipv4=m["nodes"]["france"]["expected_exit_ipv4"]),
            lambda m: m["nodes"]["italy"].update(server="localhost"),
            lambda m: m["nodes"]["italy"].update(server="::ffff:127.0.0.1"),
            lambda m: m["nodes"]["italy"].update(server_port=True),
            lambda m: m.update(targets={"example.ru": "1.1.1.1"}),
            lambda m: m["targets"].update({"api.ipify.org": "127.0.0.1"}),
            lambda m: m.update(credential="do-not-echo"),
        ):
            value = manifest()
            mutation(value)
            with self.assertRaises(pool.Error):
                pool.validate_manifest(value)


class GateTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.gate = await pool.Gate("93.184.216.30", 443).start()
        self.clients = []

    async def asyncTearDown(self):
        await self.gate.close()
        for writer in self.clients:
            writer.close()
            try:
                await writer.wait_closed()
            except OSError:
                pass
        self.assertFalse(self.gate.tasks)
        self.assertFalse(self.gate.writers)

    async def connect(self, address=None, port=443, command=1, auth=True, domain=False):
        reader, writer = await asyncio.open_connection("127.0.0.1", self.gate.port)
        self.clients.append(writer)
        writer.write(b"\x05\x01" + (b"\x02" if auth else b"\x00"))
        await writer.drain()
        if not auth:
            return reader, writer
        self.assertEqual(await reader.readexactly(2), b"\x05\x02")
        user, password = self.gate.username.encode(), self.gate.password.encode()
        writer.write(b"\x01" + bytes([len(user)]) + user + bytes([len(password)]) + password)
        await writer.drain()
        self.assertEqual(await reader.readexactly(2), b"\x01\x00")
        if domain:
            destination = b"\x03\x09localhost"
        else:
            ip = ipaddress.ip_address(address or self.gate.address)
            destination = bytes([1 if ip.version == 4 else 4]) + ip.packed
        writer.write(bytes([5, command, 0]) + destination + struct.pack("!H", port))
        await writer.drain()
        return reader, writer

    async def test_target_allowlist_udp_domain_and_unauthenticated_refusal(self):
        with mock.patch.object(self.gate, "dial", new=mock.AsyncMock()) as dial:
            for kwargs in ({"address": "127.0.0.1"}, {"port": 80}, {"command": 3},
                           {"domain": True}, {"auth": False}, {"address": "::1"}):
                reader, _ = await self.connect(**kwargs)
                response = await asyncio.wait_for(reader.read(20), 1)
                self.assertNotEqual(response[:2], b"\x05\x00")
            dial.assert_not_awaited()

    async def test_only_authenticated_exact_unavailable_target_counts(self):
        await self.gate.set_available(False)
        with mock.patch.object(self.gate, 'dial', new=mock.AsyncMock()) as dial:
            for kwargs in ({'address': '127.0.0.1'}, {'port': 80}, {'auth': False}):
                reader, _ = await self.connect(**kwargs)
                await asyncio.wait_for(reader.read(20), 1)
            self.assertEqual(self.gate.unavailable_refusals, 0)
            for _ in range(2):
                reader, _ = await self.connect()
                self.assertNotEqual((await asyncio.wait_for(reader.read(20), 1))[:2], b'\x05\x00')
            self.assertEqual(self.gate.unavailable_refusals, 2)
            self.assertEqual(self.gate.dial_attempts, 0)
            self.assertEqual(self.gate.connected, 0)
            dial.assert_not_awaited()

    async def test_wrong_password_and_truncated_parse_are_closed(self):
        await self.gate.set_available(False)
        with mock.patch.object(self.gate, "dial", new=mock.AsyncMock()) as dial:
            for raw in (b"\x04\x01\x02", b"\x05\x00", b"\x05\x01\x02\x01\x01x\x01y"):
                reader, writer = await asyncio.open_connection("127.0.0.1", self.gate.port)
                self.clients.append(writer)
                writer.write(raw)
                await writer.drain()
                writer.write_eof()
                await asyncio.wait_for(reader.read(30), 1)
            self.assertEqual(self.gate.unavailable_refusals, 0)
            dial.assert_not_awaited()

    async def test_real_loopback_stream_cleanup_and_restoration(self):
        upstreams = []
        async def echo(reader, writer):
            upstreams.append(writer)
            try:
                while data := await reader.read(32768):
                    writer.write(data)
                    await writer.drain()
            finally:
                writer.close()
                await writer.wait_closed()
        server = await asyncio.start_server(echo, "127.0.0.1", 0)
        port = server.sockets[0].getsockname()[1]
        try:
            with mock.patch.object(self.gate, "dial", new=lambda: asyncio.open_connection("127.0.0.1", port)):
                reader, writer = await self.connect()
                self.assertEqual((await reader.readexactly(10))[:2], b"\x05\x00")
                writer.write(b"only-owned-stream")
                await writer.drain()
                self.assertEqual(await reader.readexactly(17), b"only-owned-stream")
                await self.gate.set_available(False)
                self.assertEqual(await asyncio.wait_for(reader.read(), 1), b"")
                self.assertFalse(self.gate.tasks)
                self.assertFalse(self.gate.writers)
                self.assertEqual((self.gate.pending_dials, self.gate.upstream_streams), (0, 0))
                reader, _ = await self.connect()
                self.assertNotEqual((await reader.read(20))[:2], b"\x05\x00")
                await self.gate.set_available(True)
                reader, _ = await self.connect()
                self.assertEqual((await reader.readexactly(10))[:2], b"\x05\x00")
        finally:
            await self.gate.close()
            server.close()
            await server.wait_closed()
            for writer in upstreams:
                writer.close()

    async def test_pending_upstream_dial_cancelled_on_disable(self):
        started, cancelled = asyncio.Event(), asyncio.Event()
        async def pending():
            started.set()
            try:
                await asyncio.Future()
            finally:
                cancelled.set()
        with mock.patch.object(self.gate, "dial", new=pending):
            reader, _ = await self.connect()
            await asyncio.wait_for(started.wait(), 1)
            await self.gate.set_available(False)
            self.assertTrue(cancelled.is_set())
            self.assertEqual(await reader.read(), b"")
            self.assertEqual((self.gate.pending_dials, self.gate.upstream_streams), (0, 0))
            self.assertFalse(self.gate.tasks)
            self.assertFalse(self.gate.writers)

    async def test_real_gate_dial_failure_is_not_an_unavailable_refusal(self):
        with mock.patch.object(self.gate, "dial", new=mock.AsyncMock(side_effect=OSError())):
            reader, _ = await self.connect()
            self.assertNotEqual((await reader.read(20))[:2], b"\x05\x00")
            self.assertEqual(self.gate.dial_attempts, 1)
            self.assertEqual((self.gate.connected, self.gate.unavailable_refusals,
                              self.gate.pending_dials, self.gate.upstream_streams), (0, 0, 0, 0))

    async def test_physical_bind_permission_failure_sets_fatal(self):
        with mock.patch.object(pool, "bound_socket", side_effect=pool.Error("physical_socket_bind_unavailable")):
            reader, _ = await self.connect()
            self.assertNotEqual((await reader.read(20))[:2], b"\x05\x00")
            self.assertTrue(self.gate.fatal)


class CallpathTests(unittest.TestCase):
    def setUp(self):
        pool.STOP = False
        self.temp = tempfile.TemporaryDirectory(prefix="pool-probe-offline-")
        self.root = Path(self.temp.name)
        self.addCleanup(self.temp.cleanup)
        self.manifest = self.root / "manifest.json"
        self.profile = self.root / "profile.json"
        self.output = self.root / "result.json"
        write_private(self.manifest, manifest())
        write_private(self.profile, profile())

    def invoke(self):
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            code = pool.main(["--manifest", str(self.manifest), "--profile", str(self.profile),
                              "--output", str(self.output)])
        return code, json.loads(stdout.getvalue())

    def test_private_exclusive_output_and_secret_free_validation_error(self):
        self.manifest.chmod(0o644)
        code, summary = self.invoke()
        self.assertEqual(code, 1)
        self.assertEqual(summary, {"status": "fail", "stages": 0})
        self.assertEqual(stat.S_IMODE(self.output.stat().st_mode), 0o600)
        report = json.loads(self.output.read_text())
        self.assertEqual(report["error"], "private_input_required")
        saved = self.output.read_bytes()
        self.invoke()
        self.assertEqual(self.output.read_bytes(), saved)
        self.assertNotIn("00000000", saved.decode())
        self.assertNotIn(str(self.root), saved.decode())

    def test_unsafe_paths_symlinks_duplicates_and_inside_repo_refused(self):
        symlink = self.root / "link.json"
        symlink.symlink_to(self.profile)
        with self.assertRaises(pool.Error):
            pool.load_private(str(symlink))
        self.profile.write_text('{"secret":"do-not-echo","secret":2}')
        with self.assertRaisesRegex(pool.Error, "duplicate_json_key"):
            pool.load_private(str(self.profile))
        with self.assertRaises(pool.Error):
            pool.load_private(str(Path(pool.__file__)))
        self.root.chmod(0o755)
        with self.assertRaises(pool.Error):
            pool.load_private(str(self.manifest))
        self.root.chmod(0o700)

    def test_bad_profile_never_starts_or_uses_interface(self):
        value = profile()
        value["outbounds"][0]["interval"] = "1s"
        write_private(self.profile, value)
        with mock.patch.object(pool.probe, "verify_interface") as interface, \
             mock.patch.object(pool.probe.subprocess, "Popen") as popen:
            code, _ = self.invoke()
        self.assertEqual(code, 1)
        interface.assert_not_called()
        popen.assert_not_called()
        self.assertTrue(all(json.loads(self.output.read_text())["cleanup"].values()))

    def test_foreign_exception_or_remote_cut_fails_before_interface_and_core(self):
        for remote in (False, True):
            value = profile()
            if remote:
                value["route"]["rule_set"] = [{"type": "remote", "tag": "geoip-ru", "format": "binary",
                    "url": "https://subscriptions.nikcode.xyz/rules/test.srs",
                    "http_client": {"engine": "go", "detour": "direct"}, "update_interval": "168h"}]
            else:
                value["route"]["rules"].append({"domain_suffix": ["org"], "action": "route", "outbound": "direct"})
            report = {"stages": []}
            with mock.patch.object(pool.probe, "verify_interface") as interface, \
                 mock.patch.object(pool.probe.subprocess, "Popen") as popen:
                asyncio.run(pool.run(manifest(), value, str(self.root), report))
            self.assertEqual(report["status"], "fail")
            self.assertEqual(report["error"], "foreign_cut_requires_inline_rules" if remote
                             else "foreign_cut_route_not_proven")
            interface.assert_not_called()
            popen.assert_not_called()

    def test_bind_permission_failure_starts_no_core(self):
        with mock.patch.object(pool.probe, "verify_interface"), \
             mock.patch.object(pool, "bound_socket", side_effect=pool.Error("physical_socket_bind_unavailable")), \
             mock.patch.object(pool.probe.subprocess, "Popen") as popen:
            code, _ = self.invoke()
        self.assertEqual(code, 1)
        popen.assert_not_called()
        self.assertEqual(json.loads(self.output.read_text())["error"], "physical_socket_bind_unavailable")

    def test_actual_run_callpath_native_check_failure_cleans_gates_and_files(self):
        command = mock.AsyncMock(return_value=(1, b"PRIVATE RAW CORE ERROR"))
        with mock.patch.object(pool.probe, "verify_interface"), \
             mock.patch.object(pool, "bound_socket", return_value=mock.Mock()), \
             mock.patch.object(pool, "verify_binary", new=mock.AsyncMock()), \
             mock.patch.object(pool, "command", new=command), \
             mock.patch.object(pool.probe.subprocess, "Popen") as popen:
            code, _ = self.invoke()
        self.assertEqual(code, 1)
        popen.assert_not_called()
        self.assertIn("check", command.call_args.args[0])
        report = json.loads(self.output.read_text())
        self.assertEqual(report["error"], "native_config_check_failed")
        self.assertTrue(all(report["cleanup"].values()))
        self.assertEqual(set(p.name for p in self.root.iterdir()), {"manifest.json", "profile.json", "result.json"})
        self.assertNotIn("PRIVATE", self.output.read_text())

    def mocked_full_run(self, interrupt=False, restore_failure=False):
        gates = {}
        configs = []
        saw_all_down = False
        clone = pool.clone_profile
        original_sleep = asyncio.sleep
        async def fast_sleep(_):
            await original_sleep(0)
        def capture(profile, data, port, auth, actual_gates):
            gates.update(actual_gates)
            return clone(profile, data, port, auth, actual_gates)
        async def ready(process, port, auth):
            directory = Path(process.argv[-1])
            configs.append(json.loads((directory / "core.json").read_text()))
            self.assertTrue(all(stat.S_IMODE(p.stat().st_mode) == 0o600 for p in directory.iterdir()))
            if interrupt:
                os.kill(os.getpid(), signal.SIGTERM)  # Actual installed CLI handler, no child/network.
        async def command(argv, work, label, timeout, capture=True):
            nonlocal saw_all_down
            # Fake native/curl execution is a UNIT SEAM, not live acceptance.
            # request(), observe(), clone topology and all Gate state remain real.
            if "check" in argv:
                return 0, b""
            active = [r for r, gate in gates.items() if gate.available]
            if not active:
                saw_all_down = True
                await exact_gate_refusal(gates["france"])  # May equally represent concurrent URLTest.
                self.assertTrue(all(not g.pending_dials and not g.upstream_streams
                                    and not g.dial_attempts and not g.connected for g in gates.values()))
                return 35, b"000"
            if restore_failure and saw_all_down:
                return 35, b"000"
            body = Path(argv[argv.index("--output") + 1])
            body.write_text(json.dumps({"ip": manifest()["nodes"][active[0]]["expected_exit_ipv4"]}))
            return 0, b"200"
        process = mock.Mock(poll=lambda: None)
        def popen(argv, **kwargs):
            process.argv = argv
            self.assertEqual(kwargs["stdout"], pool.probe.subprocess.DEVNULL)
            self.assertEqual(kwargs["stderr"], pool.probe.subprocess.DEVNULL)
            self.assertTrue(kwargs["start_new_session"])
            return process
        with mock.patch.object(pool.probe, "verify_interface"), \
             mock.patch.object(pool, "bound_socket", return_value=mock.Mock()), \
             mock.patch.object(pool, "verify_binary", new=mock.AsyncMock()), \
             mock.patch.object(pool, "command", new=command), \
             mock.patch.object(pool, "clone_profile", new=capture), \
             mock.patch.object(pool, "ready", new=ready), \
             mock.patch.object(pool.asyncio, "sleep", new=fast_sleep), \
             mock.patch.object(pool.probe, "owns_listener", return_value=True), \
             mock.patch.object(pool.probe.subprocess, "Popen", side_effect=popen), \
             mock.patch.object(pool.probe, "stop_process", return_value=True) as stop:
            result = self.invoke()
        stop.assert_called_once_with(process)
        self.assertTrue(configs)
        self.assertTrue(all(not gate.tasks and not gate.writers and not gate.available for gate in gates.values()))
        self.assertEqual(set(p.name for p in self.root.iterdir()), {"manifest.json", "profile.json", "result.json"})
        report = json.loads(self.output.read_text())
        self.assertTrue(all(report["cleanup"].values()))
        return result, report

    def test_actual_main_all_eight_with_real_cut_state_fake_core_unit_seam(self):
        (code, summary), report = self.mocked_full_run()
        self.assertEqual(code, 0)
        self.assertEqual(summary, {"status": "pass", "stages": 8})
        self.assertNotIn("error", report)
        self.assertEqual(len(report["stages"]), 8)
        self.assertTrue(all(s["status"] == "pass" for s in report["stages"]))
        for private in ("00000000", "93.184.", str(self.root), "public_key"):
            self.assertNotIn(private, self.output.read_text())

    def test_all_down_cut_without_restoration_cannot_complete_acceptance(self):
        (code, summary), report = self.mocked_full_run(restore_failure=True)
        self.assertEqual((code, summary), (1, {"status": "fail", "stages": 8}))
        self.assertEqual(report["stages"][6]["status"], "pass")
        self.assertEqual(report["stages"][7]["status"], "fail")
        self.assertEqual(report["error"], "stage_attempt_limit")

    def test_actual_sigterm_handler_cleans_owned_resources_and_restores_handler(self):
        handler = signal.getsignal(signal.SIGTERM)
        (code, summary), report = self.mocked_full_run(interrupt=True)
        self.assertEqual(code, 1)
        self.assertEqual(report["error"], "interrupted")
        self.assertEqual(summary["status"], "fail")
        self.assertEqual(signal.getsignal(signal.SIGTERM), handler)
        pool.STOP = False

    def test_owned_process_and_descendant_cleanup_on_timeout(self):
        async def execute():
            work = pool.probe.Workspace(str(self.root))
            pid_file = work.create("descendant.pid")
            script = ("import os,time; p=os.fork(); "
                      "open(" + repr(pid_file) + ",'w').write(str(p if p else os.getpid())); time.sleep(60)")
            try:
                with self.assertRaisesRegex(pool.Error, "command_timeout"):
                    await pool.command([sys.executable, "-c", script], work, "owned-child", 0.3)
                pid = int(work.read(pid_file, 30))
                path = Path("/proc") / str(pid) / "stat"
                if path.exists():
                    self.assertEqual(path.read_text().rsplit(")", 1)[1].split()[0], "Z")
                self.assertTrue(work.process_cleanup_ok)
            finally:
                self.assertTrue(work.cleanup()["files_removed"])
        asyncio.run(execute())

    def test_binary_digest_and_version_are_both_required(self):
        async def execute():
            work = pool.probe.Workspace(str(self.root))
            try:
                with self.assertRaisesRegex(pool.Error, "binary_sha256_mismatch"):
                    await pool.verify_binary(sys.executable, work)
                digest = pool.hashlib.sha256(Path(sys.executable).read_bytes()).hexdigest()
                with mock.patch.object(pool, "SHA256", digest), \
                     mock.patch.object(pool, "command", new=mock.AsyncMock(return_value=(0, b"sing-box version 1.14.3\n"))):
                    with self.assertRaisesRegex(pool.Error, "binary_version_mismatch"):
                        await pool.verify_binary(sys.executable, work)
            finally:
                work.cleanup()
        asyncio.run(execute())


class ObservationTests(unittest.IsolatedAsyncioTestCase):
    async def cut_fixture(self):
        gates = {}
        for role, node in manifest()["nodes"].items():
            gate = await pool.Gate(node["server"], node["server_port"]).start()
            self.addAsyncCleanup(gate.close)
            gates[role] = gate
        credential = {"username": "unit-only", "password": "not-a-live-secret"}
        config = pool.clone_profile(profile(), manifest(), 12345, credential, gates)
        return gates, credential, config

    async def test_real_authenticated_mixed_health_good_bad_auth_and_dead_core(self):
        writers, tasks = [], set()
        credential = {"username": "local-user", "password": "local-password"}
        accepted = []
        bad = False
        async def auth(reader, writer):
            tasks.add(asyncio.current_task())
            writers.append(writer)
            try:
                self.assertEqual(await reader.readexactly(3), b"\x05\x01\x02")
                writer.write(b"\x05\x02")
                await writer.drain()
                head = await reader.readexactly(2)
                user = await reader.readexactly(head[1])
                size = (await reader.readexactly(1))[0]
                password = await reader.readexactly(size)
                accepted.append((user.decode(), password.decode()))
                writer.write(b"\x01\x01" if bad else b"\x01\x00")
                await writer.drain()
            finally:
                writer.close()
                await writer.wait_closed()
                tasks.discard(asyncio.current_task())
        server = await asyncio.start_server(auth, "127.0.0.1", 0)
        port = server.sockets[0].getsockname()[1]
        try:
            with mock.patch.object(pool.probe, "owns_listener", return_value=True):
                await pool.ready(mock.Mock(poll=lambda: None), port, credential)
                bad = True
                with self.assertRaisesRegex(pool.Error, "mixed_auth_failed"):
                    await pool.ready(mock.Mock(poll=lambda: None), port, credential)
                with self.assertRaisesRegex(pool.Error, "core_exited"):
                    await pool.ready(mock.Mock(poll=lambda: 1), port, credential)
            self.assertEqual(accepted, [(credential["username"], credential["password"])] * 2)
        finally:
            server.close()
            for writer in writers:
                writer.close()
            await asyncio.gather(*list(tasks), return_exceptions=True)
            await server.wait_closed()

    async def test_actual_clone_cut_rejects_bypass_gate_or_identity_changes(self):
        gates, credential, config = await self.cut_fixture()
        pool.validate_cut(config, manifest(), gates, 12345, credential)
        for mutate in (
            lambda c: c["outbounds"][1].pop("detour"),
            lambda c: c["outbounds"][-1].update(server_port=1),
            lambda c: c["outbounds"][-1].update(password="wrong"),
            lambda c: c["outbounds"].append({"type": "direct", "tag": "bypass"}),
            lambda c: c["inbounds"][0].update(listen="0.0.0.0"),
            lambda c: c["route"].update(final="direct"),
            lambda c: c["route"]["rules"].append({"domain": [pool.HOSTS[0]], "action": "route", "outbound": "direct"}),
        ):
            changed = copy.deepcopy(config)
            mutate(changed)
            with self.assertRaises(pool.Error):
                pool.validate_cut(changed, manifest(), gates, 12345, credential)
        gates["france"].target_port = 80
        with self.assertRaisesRegex(pool.Error, "foreign_cut_gate"):
            pool.validate_cut(config, manifest(), gates, 12345, credential)

    async def test_command_request_observe_rejects_http_unknown_failure_and_timeout(self):
        for response in ((35, b"503"), (0, b"200"), (6, b"000"), (35, b"not-status"),
                         pool.Error("command_timeout")):
            with self.subTest(response=str(response)), tempfile.TemporaryDirectory() as directory:
                work = pool.probe.Workspace(directory)
                gates, credential, config = await self.cut_fixture()
                command = mock.AsyncMock(side_effect=response) if isinstance(response, Exception) else mock.AsyncMock(return_value=response)
                try:
                    with mock.patch.object(pool, "STAGES", (("all_down", ()),)), \
                         mock.patch.object(pool, "ready", new=mock.AsyncMock()), \
                         mock.patch.object(pool, "command", new=command), \
                         mock.patch.object(pool.probe, "owns_listener", return_value=True):
                        report = {"stages": []}
                        with self.assertRaisesRegex(pool.Error, "all_down_not_closed"):
                            await pool.observe(manifest(), gates, mock.Mock(poll=lambda: None), 12345,
                                "/mock/curl", "/private/config", work, report, credential, config)
                        command.assert_awaited_once()
                        self.assertEqual(report["stages"][0]["status"], "fail")
                finally:
                    self.assertTrue(work.cleanup()["files_removed"])

    async def test_concurrent_urltest_refusal_neither_supplies_nor_invalidates_cut(self):
        for with_cut in (False, True):
            gates, credential, config = await self.cut_fixture()
            for gate in gates.values():
                await gate.set_available(False)
            # Actual independent authenticated denial, not attributed to a curl.
            await exact_gate_refusal(gates["italy"])
            async def command(*args):
                await exact_gate_refusal(gates["france"])
                return 35, b"000"
            async def fast_sleep(_):
                pass
            with tempfile.TemporaryDirectory() as directory:
                work = pool.probe.Workspace(directory)
                try:
                    with mock.patch.object(pool, "STAGES", (("all_down", ()),)), \
                         mock.patch.object(pool, "ready", new=mock.AsyncMock()), \
                         mock.patch.object(pool, "command", new=command), \
                         mock.patch.object(pool.asyncio, "sleep", new=fast_sleep), \
                         mock.patch.object(pool.probe, "owns_listener", return_value=True):
                        report = {"stages": []}
                        invocation = pool.observe(manifest(), gates, mock.Mock(poll=lambda: None), 12345,
                            "/mock/curl", "/private/config", work, report, credential, config if with_cut else None)
                        if with_cut:
                            await invocation
                            self.assertEqual(report["stages"][0]["proof"], "validated_four_edge_cut")
                            self.assertEqual(report["stages"][0]["status"], "pass")
                        else:
                            with self.assertRaisesRegex(pool.Error, "foreign_cut_missing"):
                                await invocation
                        self.assertTrue(all(not g.dial_attempts and not g.connected
                                            and not g.pending_dials and not g.upstream_streams for g in gates.values()))
                finally:
                    self.assertTrue(work.cleanup()["files_removed"])

    async def test_curl_transport_errors_alone_cannot_prove_all_down(self):
        for code in (7, 28, 35, 52, 55, 56, 97):
            with self.subTest(curl_code=code), tempfile.TemporaryDirectory() as directory:
                work = pool.probe.Workspace(directory)
                gates = {role: pool.Gate('93.184.216.30', 443) for role in pool.ROLES}
                async def fast_sleep(_):
                    pass
                try:
                    with mock.patch.object(pool, 'STAGES', (("all_down", ()),)), \
                         mock.patch.object(pool, 'command', new=mock.AsyncMock(return_value=(code, b'000'))), \
                         mock.patch.object(pool, 'ready', new=mock.AsyncMock()), \
                         mock.patch.object(pool.probe, 'owns_listener', return_value=True), \
                         mock.patch.object(pool.asyncio, 'sleep', new=fast_sleep):
                        # Exercise the auditor's actual command → request classification,
                        # then prove that result alone cannot satisfy observe's cut guard.
                        result = await pool.request('/mock/curl', '/private/config', manifest(),
                                                    pool.HOSTS[0], work, 0, pool.time.monotonic() + 5)
                        self.assertTrue(result['transport_failed'])
                        self.assertEqual(result['http_code'], 0)
                        report = {'stages': []}
                        with self.assertRaisesRegex(pool.Error, 'foreign_cut_missing'):
                            await pool.observe(manifest(), gates, mock.Mock(poll=lambda: None), 12345,
                                               '/mock/curl', '/private/config', work, report)
                        self.assertNotEqual(report['stages'][0]['status'], 'pass')
                finally:
                    work.cleanup()

    async def test_all_down_activity_and_health_guards_with_real_cut(self):
        for mode in ('dial', 'connected', 'pending', 'stream', 'unhealthy', 'enabled', 'success', 'http', 'dns_error'):
            with self.subTest(mode=mode):
                gates, credential, config = await self.cut_fixture()
                gate = gates['france']
                async def request(*args):
                    gate.unavailable_refusals += 1
                    if mode == 'dial':
                        gate.dial_attempts += 1
                    elif mode == 'connected':
                        gate.connected += 1
                    elif mode == 'pending':
                        gate.pending_dials += 1
                    elif mode == 'stream':
                        gate.upstream_streams += 1
                    elif mode == 'enabled':
                        gate.available = True
                    return {'ok': mode == 'success', 'http_code': 503 if mode == 'http' else 0,
                            'transport_failed': mode != 'dns_error'}
                health = mock.AsyncMock(side_effect=[None, pool.Error('mixed_auth_failed')]
                                        if mode == 'unhealthy' else None)
                with mock.patch.object(pool, 'STAGES', (("all_down", ()),)), \
                     mock.patch.object(pool, 'request', new=request), \
                     mock.patch.object(pool, 'ready', new=health), \
                     mock.patch.object(pool.probe, 'owns_listener', return_value=True):
                    report = {'stages': []}
                    with self.assertRaises(pool.Error) as failure:
                        await pool.observe(manifest(), gates, mock.Mock(poll=lambda: None), 12345,
                                           '/mock/curl', '/private/config', None, report, credential, config)
                    expected = {'dial': 'all_down_upstream_activity', 'connected': 'all_down_upstream_activity',
                                'pending': 'all_down_gate_not_quiescent', 'stream': 'all_down_gate_not_quiescent',
                                'unhealthy': 'mixed_auth_failed', 'enabled': 'all_down_gate_not_quiescent',
                                'success': 'all_down_not_closed', 'http': 'all_down_not_closed',
                                'dns_error': 'all_down_not_closed'}
                    self.assertEqual(str(failure.exception), expected[mode])
                    self.assertNotEqual(report['stages'][0]['status'], 'pass')

    async def run_observation(self, mode="success"):
        gates, credential, config = await self.cut_fixture()
        observed = []
        calls = []
        async def request(curl, config, data, host, work, serial, deadline):
            active = tuple(r for r, g in gates.items() if g.available)
            calls.append((host, active))
            if not active:
                if mode == "leak":
                    return {"ok": True, "http_code": 200, "transport_failed": False}
                if mode == "dns_error":
                    return {"ok": False, "http_code": 0, "transport_failed": False}
                return {"ok": False, "http_code": 0, "transport_failed": True}
            return {"ok": True, "http_code": 200, "transport_failed": False,
                    "exit": "unexpected" if mode == "unexpected" else active[0]}
        real_sleep = asyncio.sleep
        async def fast_sleep(_):
            await real_sleep(0)
        with mock.patch.object(pool, 'ready', new=mock.AsyncMock()), \
             mock.patch.object(pool, "request", new=request), \
             mock.patch.object(pool.probe, "owns_listener", return_value=True), \
             mock.patch.object(pool.asyncio, "sleep", new=fast_sleep):
            report = {"stages": observed}
            await pool.observe(manifest(), gates, mock.Mock(poll=lambda: None), 12345,
                               "/mock/curl", "/private/config", None, report, credential, config)
        return report, calls

    async def test_all_eight_schedule_real_cut_state_fake_requests_unit_seam(self):
        report, calls = await self.run_observation()
        self.assertEqual([s["stage"] for s in report["stages"]],
                         [name for name, _ in pool.STAGES])
        self.assertTrue(all(s["status"] == "pass" and s["attempts"] == 2 for s in report["stages"]))
        self.assertEqual(report["stages"][2]["observed_exit"], "italy")
        self.assertEqual(report["stages"][3]["observed_exit"], "poland")
        self.assertEqual(report["stages"][5]["observed_exit"], "frankfurt")
        self.assertEqual(len([c for c in calls if not c[1]]), 4)
        self.assertEqual(report["stages"][6]["proof"], "validated_four_edge_cut")
        self.assertEqual(calls[-1][1], pool.ROLES)

    async def test_all_down_success_or_dns_only_failure_never_passes(self):
        for mode in ("leak", "dns_error", "unexpected"):
            with self.subTest(mode=mode), self.assertRaises(pool.Error):
                await self.run_observation(mode)

    @unittest.skipUnless(shutil.which("curl"), "local curl unavailable")
    async def test_real_curl_sends_pinned_numeric_socks_connect_no_external_call(self):
        captured = []
        async def socks(reader, writer):
            try:
                greeting = await reader.readexactly(2)
                self.assertEqual(greeting[0], 5)
                self.assertIn(2, await reader.readexactly(greeting[1]))
                writer.write(b"\x05\x02")
                await writer.drain()
                head = await reader.readexactly(2)
                await reader.readexactly(head[1])
                size = (await reader.readexactly(1))[0]
                await reader.readexactly(size)
                writer.write(b"\x01\x00")
                await writer.drain()
                head = await reader.readexactly(4)
                self.assertEqual(head, b"\x05\x01\x00\x01")
                address = str(ipaddress.ip_address(await reader.readexactly(4)))
                port = struct.unpack("!H", await reader.readexactly(2))[0]
                captured.append((address, port))
                writer.write(b"\x05\x02\x00\x01" + b"\x00" * 6)
                await writer.drain()
            finally:
                writer.close()
                await writer.wait_closed()
        server = await asyncio.start_server(socks, "127.0.0.1", 0)
        try:
            with tempfile.TemporaryDirectory(prefix="pool-request-offline-") as directory:
                work = pool.probe.Workspace(directory)
                try:
                    config = work.create("curl.conf", ("proxy = \"socks5h://127.0.0.1:"
                        + str(server.sockets[0].getsockname()[1]) + "\"\nproxy-user = \"user:password\"\n").encode())
                    result = await pool.request(shutil.which("curl"), config, manifest(), pool.HOSTS[0],
                                                work, 1, pool.time.monotonic() + 5)
                    self.assertTrue(result["transport_failed"])
                    self.assertFalse(result["ok"])
                    self.assertEqual(captured, [(manifest()["targets"][pool.HOSTS[0]], 443)])
                finally:
                    self.assertTrue(work.cleanup()["files_removed"])
        finally:
            server.close()
            await server.wait_closed()


if __name__ == "__main__":
    unittest.main()
