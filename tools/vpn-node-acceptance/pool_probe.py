#!/usr/bin/env python3
"""Isolated four-node acceptance; explicit invocation performs real bounded traffic."""
import argparse
import asyncio
import copy
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import signal
import socket
import stat
import struct
import sys
import time

import probe  # Existing ownership, private-file and Linux process primitives; unchanged.

SHA256 = "1264361b5f8868c8768f7555d3e77e20118bf503c41ac08bb290a0d99056aa3a"
VERSION = "1.14.4"
ROLES = ("france", "frankfurt", "poland", "italy")
HOSTS = ("api.ipify.org", "www.wikipedia.org")
POOL = {"type": "urltest", "tag": "proxy", "outbounds": list(ROLES),
        "url": "https://www.gstatic.com/generate_204", "interval": "1m",
        "tolerance": 100, "interrupt_exist_connections": False}
REPO = Path(__file__).resolve().parents[2]
STAGE_SECONDS = 145
STOP = False
require = probe.require
Error = probe.ProbeError


def outside_repo(path):
    require(isinstance(path, str) and os.path.isabs(path), "absolute_path_required")
    require(not Path(path).resolve().is_relative_to(REPO), "artifacts_inside_repo_forbidden")


def load_private(path):
    outside_repo(path)
    parent = None
    try:
        parent, name, _ = probe.private_parent(path)
        fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
        with os.fdopen(fd, "rb") as stream:
            info = os.fstat(stream.fileno())
            require(stat.S_ISREG(info.st_mode) and info.st_uid == os.getuid()
                    and stat.S_IMODE(info.st_mode) == 0o600
                    and info.st_size <= probe.MAX_JSON, "private_input_required")
            raw = stream.read(probe.MAX_JSON + 1)
        require(len(raw) <= probe.MAX_JSON, "input_too_large")
        def unique(pairs):
            result = {}
            for key, value in pairs:
                require(key not in result, "duplicate_json_key")
                result[key] = value
            return result
        return json.loads(raw, object_pairs_hook=unique,
                          parse_constant=lambda _: (_ for _ in ()).throw(Error("invalid_json")))
    except (OSError, ValueError, UnicodeError, RecursionError):
        raise Error("invalid_or_unsafe_input") from None
    finally:
        if parent is not None:
            os.close(parent)


def public_ip(value, ipv4=False):
    try:
        address = ipaddress.ip_address(value) if isinstance(value, str) else None
        require(address is not None and address.is_global and not address.is_multicast
                and not getattr(address, "scope_id", None)
                and not getattr(address, "ipv4_mapped", None)
                and (not ipv4 or address.version == 4), "public_numeric_ip_required")
        return str(address)
    except ValueError:
        raise Error("public_numeric_ip_required") from None


def validate_manifest(data):
    require(isinstance(data, dict) and set(data) == {"binary", "nodes", "targets"},
            "invalid_manifest")
    require(isinstance(data["binary"], str) and os.path.isabs(data["binary"]), "invalid_binary")
    require(isinstance(data["nodes"], dict) and set(data["nodes"]) == set(ROLES),
            "exact_four_nodes_required")
    servers, exits = set(), set()
    for node in data["nodes"].values():
        require(isinstance(node, dict) and set(node) == {
            "server", "server_port", "expected_exit_ipv4"}, "invalid_expected_node")
        server = public_ip(node["server"])
        exit_ip = public_ip(node["expected_exit_ipv4"], True)
        require(type(node["server_port"]) is int and 1 <= node["server_port"] <= 65535,
                "invalid_node_port")
        require(server not in servers and exit_ip not in exits, "distinct_nodes_and_exits_required")
        servers.add(server)
        exits.add(exit_ip)
    require(isinstance(data["targets"], dict) and set(data["targets"]) == set(HOSTS),
            "exact_pinned_targets_required")
    for address in data["targets"].values():
        public_ip(address, True)
    return data


def fields(value, allowed, code):
    require(isinstance(value, dict) and not set(value) - set(allowed.split()), code)


def validate_profile(profile, manifest):
    """Accept only understood dial/control surfaces. Never repair unsupported semantics."""
    fields(profile, "log dns inbounds outbounds route experimental endpoints", "unsupported_profile_part")
    require(not profile.get("endpoints"), "unsupported_tailscale_or_other_endpoint")
    inbound = profile.get("inbounds")
    require(isinstance(inbound, list) and len(inbound) == 1
            and inbound[0].get("type") == "tun" and inbound[0].get("tag") == "tun-in",
            "production_tun_profile_required")
    outbounds = profile.get("outbounds")
    require(isinstance(outbounds, list) and len(outbounds) == 6
            and all(isinstance(o, dict) for o in outbounds), "exact_flat_pool_required")
    by_tag = {o.get("tag"): o for o in outbounds}
    require(len(by_tag) == 6 and set(by_tag) == {*ROLES, "proxy", "direct"},
            "exact_flat_pool_required")
    pool = by_tag["proxy"]
    require(set(pool) == set(POOL) and isinstance(pool.get("outbounds"), list)
            and len(pool["outbounds"]) == 4 and set(pool["outbounds"]) == set(ROLES)
            and all(pool[k] == v and type(pool[k]) is type(v)
                    for k, v in POOL.items() if k != "outbounds"),
            "production_urltest_options_required")
    for role in ROLES:
        node = by_tag[role]
        fields(node, "type tag server server_port uuid flow domain_resolver tls bind_interface "
               "connect_timeout tcp_fast_open multiplex network packet_encoding transport",
               "unsupported_node_dial_option")
        # Existing validator checks verified Reality, credentials and supported raw/ws transport.
        probe.build_config(node, "wlo1", 12345)
        require(node["type"] == "vless" and node["server"] == manifest["nodes"][role]["server"]
                and node["server_port"] == manifest["nodes"][role]["server_port"],
                "profile_node_mismatch")
        require(not node.get("multiplex", {}).get("enabled")
                and node.get("transport", {}).get("type") not in ("grpc", "http"),
                "pooled_transport_unsupported")
    direct = by_tag["direct"]
    fields(direct, "type tag domain_resolver bind_interface", "unsupported_direct_dial_option")
    require(direct.get("type") == "direct" and direct.get("domain_resolver") == "bootstrap",
            "bootstrap_direct_required")
    dns = profile.get("dns")
    fields(dns, "strategy final servers rules", "unsupported_dns_part")
    require(dns.get("strategy") == "ipv4_only" and dns.get("final") == "remote", "production_dns_required")
    servers = dns.get("servers")
    require(isinstance(servers, list) and len(servers) == 3, "unsupported_dns_servers")
    tags = set()
    for server in servers:
        fields(server, "type tag server server_port path detour", "unsupported_dns_dial_option")
        tag = server.get("tag")
        require(tag not in tags, "duplicate_dns_tag")
        tags.add(tag)
        if tag == "local":
            require(server == {"type": "local", "tag": "local"}, "unsupported_local_dns")
        else:
            require(tag in ("remote", "bootstrap") and server.get("type") == "https"
                    and server.get("server_port", 443) == 443
                    and server.get("path") == "/dns-query"
                    and server.get("detour") == ("proxy" if tag == "remote" else "direct"),
                    "unsupported_dns_server")
            public_ip(server.get("server"))
    require(tags == {"remote", "bootstrap", "local"}, "production_dns_required")
    require(isinstance(dns.get("rules"), list), "unsupported_dns_rules")
    for rule in dns["rules"]:
        fields(rule, "domain domain_suffix query_type action server disable_cache rcode", "unsupported_dns_rule")
        require(rule.get("action") in ("route", "predefined")
                and rule.get("server", "bootstrap") in tags, "unsupported_dns_rule")
    route = profile.get("route")
    fields(route, "auto_detect_interface final default_domain_resolver rule_set rules", "unsupported_route_part")
    require(route.get("final") == "proxy" and route.get("default_domain_resolver") == "remote",
            "vpn_final_required")
    require(isinstance(route.get("rules"), list), "unsupported_route_rules")
    for rule in route["rules"]:
        fields(rule, "action inbound protocol ip_is_private ip_cidr ip_version method no_drop "
               "network domain domain_suffix port rule_set outbound", "unsupported_route_rule")
        require(rule.get("action") in ("sniff", "hijack-dns", "route", "reject")
                and rule.get("outbound", "direct") in ("direct", "proxy"), "unsupported_route_rule")
        require("inbound" not in rule or rule["inbound"] == ["tun-in"], "unsupported_inbound_match")
    sets = route.get("rule_set")
    require(isinstance(sets, list) and len(sets) == 1 and sets[0].get("tag") == "geoip-ru",
            "production_ru_rules_required")
    ruleset = sets[0]
    if ruleset.get("type") == "inline":
        fields(ruleset, "tag type rules", "unsupported_inline_rule_set")
        require(isinstance(ruleset.get("rules"), list) and ruleset["rules"], "empty_ru_rules")
        for rule in ruleset["rules"]:
            fields(rule, "ip_cidr", "unsupported_inline_ru_rule")
            require(isinstance(rule.get("ip_cidr"), list) and rule["ip_cidr"], "unsupported_inline_ru_rule")
            for cidr in rule["ip_cidr"]:
                try:
                    network = ipaddress.ip_network(cidr)
                except (ValueError, TypeError):
                    raise Error("invalid_ru_cidr") from None
                require(not any(ipaddress.ip_address(ip) in network for ip in manifest["targets"].values()),
                        "foreign_target_is_exempt")
    else:
        fields(ruleset, "tag type format url http_client update_interval", "unsupported_remote_rule_set")
        from urllib.parse import urlsplit
        url = urlsplit(ruleset.get("url", ""))
        require(ruleset.get("type") == "remote" and ruleset.get("format") == "binary"
                and url.scheme == "https" and url.hostname in (
                    "subscriptions.nikcode.xyz", "raw.githubusercontent.com")
                and not url.username and not url.password and not url.query and not url.fragment,
                "unsupported_remote_rule_source")
        require(ruleset.get("http_client") in ({"engine": "go", "detour": "direct"},
                                               {"engine": "go", "detour": "proxy"}),
                "unsupported_rule_http_client")
    exp = profile.get("experimental", {})
    fields(exp, "cache_file clash_api", "unsupported_experimental_part")
    fields(exp.get("cache_file", {}), "enabled cache_id path store_fakeip store_rdrc", "unsupported_cache_option")
    # An existing controller is not preserved or exposed; all of its settings are test-only.
    fields(exp.get("clash_api", {}), "external_controller external_ui secret default_mode "
           "access_control_allow_origin access_control_allow_private_network", "unsupported_controller_option")
    require(exp.get("clash_api", {}).get("default_mode", "rule") == "rule",
            "unsupported_profile_mode")
    return profile


def clone_profile(profile, manifest, port, credential, gates):
    result = copy.deepcopy(validate_profile(profile, manifest))
    result.pop("endpoints", None)
    result["log"] = {"disabled": True}
    # Keep the original inbound tag so sniff/inbound-qualified rules remain meaningful.
    result["inbounds"] = [{"type": "mixed", "tag": "tun-in", "listen": "127.0.0.1",
                           "listen_port": port, "users": [credential], "set_system_proxy": False}]
    result["experimental"] = {"cache_file": {"enabled": False}}
    result["route"]["auto_detect_interface"] = False
    for outbound in result["outbounds"]:
        tag = outbound["tag"]
        if tag in ROLES:
            outbound.pop("bind_interface", None)  # Loopback detour must not bind wlo1.
            outbound["detour"] = "gate-" + tag
        elif tag == "direct":
            outbound["bind_interface"] = "wlo1"
    for role, gate in gates.items():
        result["outbounds"].append({"type": "socks", "tag": "gate-" + role,
                                    "server": "127.0.0.1", "server_port": gate.port,
                                    "version": "5", "username": gate.username,
                                    "password": gate.password})
    return result


def validate_foreign_routes(profile, manifest):
    """Conservative cut proof for TCP:443, both before and after TLS sniffing.

    Inline IP rules are inspectable. Opaque remote rule sets cannot certify a cut:
    preserving their mode is preferable to silently substituting an inline profile.
    Accept one destination matcher family per exception: native OR-group semantics
    must not be mistaken for AND. Network/port/inbound can only narrow that family;
    they are not used to prove exclusion. Unknown/combined families fail closed.
    """
    ruleset = profile["route"]["rule_set"][0]
    require(ruleset["type"] == "inline", "foreign_cut_requires_inline_rules")
    networks = [ipaddress.ip_network(cidr) for rule in ruleset["rules"] for cidr in rule["ip_cidr"]]
    def values(value):
        return value if isinstance(value, list) else [value]
    for host, address in manifest["targets"].items():
        ip = ipaddress.ip_address(address)
        for domain in (None, host, address):
            for rule in profile["route"]["rules"]:
                action = rule["action"]
                if action == "sniff" or (action == "route" and rule.get("outbound") == "proxy"):
                    continue
                matchers = set(rule) - {"action", "outbound", "method", "no_drop", "inbound", "network", "port"}
                require(len(matchers) == 1, "foreign_cut_route_not_proven")
                matcher = next(iter(matchers))
                candidates = values(rule[matcher])
                require(candidates, "foreign_cut_route_not_proven")
                if matcher in ("domain", "domain_suffix"):
                    require(all(isinstance(d, str) and re.fullmatch(r"[a-zA-Z0-9.-]+", d)
                                and d.strip(".") for d in candidates), "foreign_cut_route_not_proven")
                normalized = domain.lower().rstrip(".") if domain else None
                if matcher == "domain":
                    excluded = normalized not in [d.lower().rstrip(".") for d in candidates]
                elif matcher == "domain_suffix":
                    suffixes = [d.lower().strip(".") for d in candidates]
                    excluded = all(s and (normalized is None or (normalized != s
                                       and not normalized.endswith("." + s))) for s in suffixes)
                elif matcher == "ip_cidr":
                    excluded = not any(ip in ipaddress.ip_network(cidr) for cidr in candidates)
                elif matcher == "rule_set":
                    excluded = candidates == ["geoip-ru"] and not any(ip in n for n in networks)
                elif matcher == "ip_is_private":
                    excluded = rule[matcher] is True  # Manifest already requires global addresses.
                elif matcher == "ip_version":
                    excluded = type(rule[matcher]) is int and rule[matcher] == 6
                elif matcher == "protocol":
                    excluded = candidates == ["dns"]  # Numeric HTTPS TCP cannot be DNS.
                else:
                    excluded = False
                require(excluded, "foreign_cut_route_not_proven")


def validate_cut(config, manifest, gates, port, credential):
    """Check the actual config passed to the owned native core, not a caller flag."""
    require(config is not None and set(gates) == set(ROLES), "foreign_cut_missing")
    require(config["inbounds"] == [{"type": "mixed", "tag": "tun-in", "listen": "127.0.0.1",
            "listen_port": port, "users": [credential], "set_system_proxy": False}], "foreign_cut_inbound")
    require(len(config["outbounds"]) == 10, "foreign_cut_outbounds")
    by_tag = {o["tag"]: o for o in config["outbounds"]}
    source = copy.deepcopy(config)
    source["inbounds"] = [{"type": "tun", "tag": "tun-in"}]
    source["outbounds"] = [o for o in source["outbounds"] if o["tag"] in {*ROLES, "direct", "proxy"}]
    for node in source["outbounds"]:
        if node["tag"] in ROLES:
            require(node.pop("detour", None) == "gate-" + node["tag"], "foreign_cut_detour")
    validate_profile(source, manifest)
    validate_foreign_routes(source, manifest)
    for role, gate in gates.items():
        require(isinstance(gate, Gate) and gate.server is not None and gate.server.is_serving()
                and gate.address == manifest["nodes"][role]["server"]
                and gate.target_port == manifest["nodes"][role]["server_port"], "foreign_cut_gate")
        require(by_tag.get("gate-" + role) == {"type": "socks", "tag": "gate-" + role,
                "server": "127.0.0.1", "server_port": gate.port, "version": "5",
                "username": gate.username, "password": gate.password}, "foreign_cut_gate_config")


def bound_socket(address):
    sock = socket.socket(socket.AF_INET6 if ":" in address else socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BINDTODEVICE, b"wlo1\0")
        sock.setblocking(False)
        return sock
    except OSError:
        sock.close()
        raise Error("physical_socket_bind_unavailable") from None


class Gate:
    """Authenticated SOCKS CONNECT, one exact numeric destination; no DNS or UDP."""
    def __init__(self, address, port):
        self.address, self.target_port = address, port
        self.username, self.password = secrets.token_hex(16), secrets.token_hex(24)
        self.server, self.port, self.available = None, None, True
        self.tasks, self.writers = set(), set()
        self.denied, self.connected = 0, 0
        self.unavailable_refusals, self.dial_attempts, self.pending_dials = 0, 0, 0
        self.upstream_streams = 0
        self.fatal = False

    async def start(self):
        self.server = await asyncio.start_server(self.accept, "127.0.0.1", 0, limit=65536)
        self.port = self.server.sockets[0].getsockname()[1]
        return self

    def accept(self, reader, writer):
        if len(self.tasks) >= 64:
            writer.close()
            return
        # Register before scheduling: disabling can cancel a coroutine before its first step.
        self.writers.add(writer)
        task = asyncio.create_task(self.serve(reader, writer))
        self.tasks.add(task)
        def finished(done):
            self.tasks.discard(done)
            self.writers.discard(writer)
            writer.close()
            if not done.cancelled():
                done.exception()  # Consume task failures: no asyncio/raw socket diagnostics.
        task.add_done_callback(finished)

    async def dial(self):
        sock = bound_socket(self.address)
        try:
            await asyncio.wait_for(asyncio.get_running_loop().sock_connect(
                sock, (self.address, self.target_port)), 8)
            return await asyncio.open_connection(sock=sock, limit=65536)
        except BaseException:
            sock.close()
            raise

    async def handshake(self, reader, writer):
        head = await reader.readexactly(2)
        require(head[0] == 5 and 1 <= head[1] <= 16, "gate_protocol")
        methods = await reader.readexactly(head[1])
        require(2 in methods, "gate_auth_required")
        writer.write(b"\x05\x02")
        await writer.drain()
        head = await reader.readexactly(2)
        require(head[0] == 1 and head[1] != 0, "gate_auth_required")
        username = await reader.readexactly(head[1])
        size = (await reader.readexactly(1))[0]
        password = await reader.readexactly(size)
        require(secrets.compare_digest(username, self.username.encode())
                and secrets.compare_digest(password, self.password.encode()), "gate_auth_required")
        writer.write(b"\x01\x00")
        await writer.drain()
        head = await reader.readexactly(4)
        require(head[:3] == b"\x05\x01\x00" and head[3] in (1, 4), "gate_connect_only")
        raw = await reader.readexactly(4 if head[3] == 1 else 16)
        address = str(ipaddress.ip_address(raw))
        port = struct.unpack("!H", await reader.readexactly(2))[0]
        require(address == self.address and port == self.target_port, "gate_target")
        if not self.available:
            self.unavailable_refusals += 1
            raise Error("gate_unavailable")

    async def serve(self, reader, writer):
        upstream = None
        pipes = []
        self.writers.add(writer)
        try:
            await asyncio.wait_for(self.handshake(reader, writer), 4)
            self.dial_attempts += 1
            self.pending_dials += 1
            try:
                upstream_reader, upstream = await self.dial()
            finally:
                self.pending_dials -= 1
            self.upstream_streams += 1
            self.writers.add(upstream)
            require(self.available, "gate_unavailable")
            self.connected += 1
            writer.write(b"\x05\x00\x00\x01\x00\x00\x00\x00\x00\x00")
            await writer.drain()
            async def pipe(source, destination):
                while True:
                    data = await source.read(32768)
                    if not data:
                        break
                    destination.write(data)
                    await destination.drain()
            pipes = [asyncio.create_task(pipe(reader, upstream)),
                     asyncio.create_task(pipe(upstream_reader, writer))]
            await asyncio.wait(pipes, return_when=asyncio.FIRST_COMPLETED)
        except Error as exc:
            self.denied += 1
            if str(exc) == "physical_socket_bind_unavailable":
                self.fatal = True
            try:
                writer.write(b"\x05\x02\x00\x01\x00\x00\x00\x00\x00\x00")
            except OSError:
                pass
        except (OSError, asyncio.IncompleteReadError, asyncio.TimeoutError):
            self.denied += 1
        finally:
            for task in pipes:
                task.cancel()
            await asyncio.gather(*pipes, return_exceptions=True)
            if upstream is not None:
                self.upstream_streams -= 1
            for stream in (writer, upstream):
                if stream is not None:
                    self.writers.discard(stream)
                    stream.close()
                    try:
                        await asyncio.wait_for(stream.wait_closed(), 1)
                    except (OSError, asyncio.TimeoutError):
                        pass

    async def set_available(self, available):
        # Cancel pending handshakes/dials as well as established streams, before restoration.
        self.available = available
        if not available:
            tasks = list(self.tasks)
            for task in tasks:
                task.cancel()
            for writer in list(self.writers):
                writer.close()
            await asyncio.gather(*tasks, return_exceptions=True)

    async def close(self):
        self.available = False
        if self.server is not None:
            self.server.close()
        # Python 3.13+ wait_closed also waits for accepted transports: close those first.
        await self.set_available(False)
        if self.server is not None:
            await self.server.wait_closed()


async def command(argv, work, label, timeout, capture=True):
    """Poll only our child; keep gates servicing while curl/core runs. Never retain stderr."""
    process = None
    try:
        path = work.create(label + ".stdout")
        with open(path, "wb") as out:
            process = probe.subprocess.Popen(argv, stdin=probe.subprocess.DEVNULL,
                stdout=out if capture else probe.subprocess.DEVNULL,
                stderr=probe.subprocess.DEVNULL, cwd=work.path, env=probe.child_env(),
                start_new_session=True, preexec_fn=probe.child_limits, close_fds=True)
        deadline = time.monotonic() + timeout
        while process.poll() is None:
            require(not STOP, "interrupted")
            require(time.monotonic() < deadline, "command_timeout")
            await asyncio.sleep(0.05)
        return process.returncode, work.read(path, 4096) if capture else b""
    finally:
        work.process_cleanup_ok &= probe.stop_process(process)


async def verify_binary(binary, work):
    require(os.path.isfile(binary) and os.access(binary, os.X_OK), "binary_unavailable")
    with open(binary, "rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    require(digest == SHA256, "binary_sha256_mismatch")
    code, raw = await command([binary, "version"], work, "version", 5)
    require(code == 0 and re.search(rb"(?m)^sing-box version 1\.14\.4\r?$", raw) is not None,
            "binary_version_mismatch")


async def ready(process, port, credential):
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        require(not STOP, "interrupted")
        require(process.poll() is None, "core_exited")
        if probe.owns_listener(process, port):
            reader, writer = await asyncio.open_connection("127.0.0.1", port)
            try:
                writer.write(b"\x05\x01\x02")
                await writer.drain()
                require(await asyncio.wait_for(reader.readexactly(2), 1) == b"\x05\x02",
                        "mixed_auth_required")
                user, password = credential["username"].encode(), credential["password"].encode()
                writer.write(b"\x01" + bytes([len(user)]) + user + bytes([len(password)]) + password)
                await writer.drain()
                require(await asyncio.wait_for(reader.readexactly(2), 1) == b"\x01\x00",
                        "mixed_auth_failed")
                return
            finally:
                writer.close()
                await writer.wait_closed()
        await asyncio.sleep(0.05)
    raise Error("owned_core_not_ready")


async def request(curl, curl_config, manifest, host, work, serial, deadline):
    remaining = deadline - time.monotonic()
    require(remaining > 0.2, "stage_deadline")
    body = work.create("request-" + str(serial) + ".body")
    path = "/?format=json" if host == HOSTS[0] else "/"
    url = "https://" + host + path + ("&" if "?" in path else "?") + "pool_probe=" + secrets.token_hex(8)
    argv = [curl, "--disable", "--config", curl_config, "--silent", "--ipv4",
            "--noproxy", "", "--proto", "=https", "--proto-redir", "=https",
            "--max-redirs", "0", "--connect-timeout", "5", "--max-time", str(min(8, remaining)),
            "--retry", "0", "--no-keepalive", "--no-sessionid", "--header", "Connection: close",
            "--header", "Cache-Control: no-cache", "--max-filesize", "1048576", "--output", body,
            "--connect-to", host + ":443:" + manifest["targets"][host] + ":443",
            "--write-out", "%{http_code}", url]
    try:
        code, raw = await command(argv, work, "curl-" + str(serial), min(8, remaining) + 0.1)
    except Error as exc:
        if str(exc) not in ("command_timeout",):
            raise
        # A harness-killed process supplies no trustworthy completed HTTP-status record.
        return {"ok": False, "transport_failed": False, "http_code": 0}
    valid_status = re.fullmatch(rb"[0-9]{3}", raw) is not None
    http_code = int(raw) if valid_status else 0
    result = {"ok": code == 0 and 200 <= http_code < 400,
              "transport_failed": valid_status and code in (7, 28, 35, 52, 55, 56, 97) and http_code == 0,
              "http_code": http_code}
    if host == HOSTS[0] and result["ok"]:
        try:
            address = public_ip(json.loads(work.read(body, 65536))["ip"], True)
            result["exit"] = next((role for role, node in manifest["nodes"].items()
                                   if node["expected_exit_ipv4"] == address), "unexpected")
        except (Error, ValueError, KeyError, TypeError, UnicodeError):
            result["ok"] = False
    return result


STAGES = (
    ("baseline", ROLES),
    ("poland_only", ("poland",)),
    ("poland_to_italy", ("italy",)),
    ("italy_to_poland", ("poland",)),
    ("new_nodes_down", ("france", "frankfurt")),
    ("adminvps_down", ("frankfurt",)),
    ("all_down", ()),
    ("restored", ROLES),
)


async def observe(manifest, gates, process, port, curl, curl_config, work, report, credential=None, config=None):
    serial = 0
    for name, allowed in STAGES:
        started = time.monotonic()
        deadline = started + STAGE_SECONDS
        stage = {"stage": name, "status": "fail", "attempts": 0}
        report["stages"].append(stage)
        # Disable first: never briefly enable an unintended transition path.
        for role, gate in gates.items():
            if role not in allowed:
                await gate.set_available(False)
        for role in allowed:
            await gates[role].set_available(True)
        consecutive = 0
        while time.monotonic() + 0.3 < deadline:
            require(not STOP, "interrupted")
            require(process.poll() is None and probe.owns_listener(process, port), "owned_core_lost")
            require(not any(g.fatal for g in gates.values()), "physical_socket_bind_unavailable")
            stage["attempts"] += 1
            results = []
            for host in HOSTS:
                serial += 1
                if not allowed:
                    # Structural cut, not per-flow counter attribution. Native URLTest
                    # can race freely: every possible VLESS edge is still closed.
                    validate_cut(config, manifest, gates, port, credential)
                    require(all(not g.available and not g.pending_dials and not g.upstream_streams
                                for g in gates.values()), "all_down_gate_not_quiescent")
                    await ready(process, port, credential)
                    before = [(g.dial_attempts, g.connected) for g in gates.values()]
                result = await request(curl, curl_config, manifest, host, work, serial, deadline)
                if not allowed:
                    await ready(process, port, credential)
                    require(all(not g.available and not g.pending_dials and not g.upstream_streams
                                for g in gates.values()), "all_down_gate_not_quiescent")
                    validate_cut(config, manifest, gates, port, credential)
                    after = [(g.dial_attempts, g.connected) for g in gates.values()]
                    require(after == before, "all_down_upstream_activity")
                    require(not result["ok"] and not result["http_code"]
                            and result["transport_failed"], "all_down_not_closed")
                results.append(result)
            if allowed:
                require(results[0].get("exit") != "unexpected", "unexpected_exit")
                good = all(r["ok"] for r in results) and results[0].get("exit") in allowed
                if good:
                    stage["observed_exit"] = results[0]["exit"]
            else:
                good = all(r["transport_failed"] and not r["ok"] and not r["http_code"] for r in results)
                stage["proof"] = "validated_four_edge_cut"
            consecutive = consecutive + 1 if good else 0
            if consecutive >= 2:
                stage["status"] = "pass"
                break
            require(stage["attempts"] < 25, "stage_attempt_limit")
            await asyncio.sleep(min(5, max(0, deadline - time.monotonic() - 0.1)))
        stage["duration_seconds"] = round(time.monotonic() - started, 2)
        require(stage["status"] == "pass", "stage_acceptance_failed")


async def run(manifest, profile, parent, report):
    work, process, gates, reserved = None, None, {}, ()
    try:
        validate_profile(profile, manifest)
        validate_foreign_routes(profile, manifest)
        probe.verify_interface("wlo1")
        # Permission preflight does not connect anywhere; never grant capabilities or use sudo.
        for node in manifest["nodes"].values():
            bound_socket(node["server"]).close()
        work = probe.Workspace(parent)
        await verify_binary(manifest["binary"], work)
        curl = shutil.which("curl")
        require(curl is not None, "curl_unavailable")
        port, reserved = probe.reserve_port()
        for role, node in manifest["nodes"].items():
            gate = Gate(node["server"], node["server_port"])
            gates[role] = gate
            await gate.start()
        credential = {"username": secrets.token_hex(16), "password": secrets.token_hex(24)}
        config = clone_profile(profile, manifest, port, credential, gates)
        validate_cut(config, manifest, gates, port, credential)
        config_path = work.create("core.json", json.dumps(config).encode())
        curl_config = work.create("curl.conf", ("proxy = \"socks5h://127.0.0.1:" + str(port)
            + "\"\nproxy-user = \"" + credential["username"] + ":" + credential["password"] + "\"\n").encode())
        code, _ = await command([manifest["binary"], "check", "-c", config_path, "-D", work.path],
                                work, "check", 8, capture=False)
        require(code == 0, "native_config_check_failed")
        require(not STOP, "interrupted")
        for sock in reserved:
            sock.close()
        reserved = ()
        # No core stdout/stderr; no raw errors can reach terminal or result.
        process = probe.subprocess.Popen([manifest["binary"], "run", "-c", config_path, "-D", work.path],
            stdin=probe.subprocess.DEVNULL, stdout=probe.subprocess.DEVNULL, stderr=probe.subprocess.DEVNULL,
            cwd=work.path, env=probe.child_env(), start_new_session=True,
            preexec_fn=probe.child_limits, close_fds=True)
        await ready(process, port, credential)
        await observe(manifest, gates, process, port, curl, curl_config, work, report, credential, config)
        report["status"] = "pass"
    except Error as exc:
        report.update(status="fail", error=str(exc))
    except Exception:
        report.update(status="fail", error="internal_or_os_error")
    finally:
        # SIGINT/TERM/HUP handlers only set STOP; cleanup cannot be interrupted by repeats.
        for sock in reserved:
            sock.close()
        stopped = probe.stop_process(process)
        gates_closed = True
        for gate in gates.values():
            try:
                await gate.close()
            except Exception:
                gates_closed = False
        report["cleanup"] = {"process_groups_stopped": stopped and (work is None or work.process_cleanup_ok),
                             "gates_closed": gates_closed, "files_removed": True}
        if work is not None:
            work.process_cleanup_ok &= stopped
            report["cleanup"]["files_removed"] = (work.cleanup()["files_removed"]
                if work.process_cleanup_ok and gates_closed else False)
        if not all(report["cleanup"].values()):
            report.update(status="fail", error="owned_cleanup_failed")


def main(argv=None):
    global STOP
    STOP = False
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--profile", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    report = {"schema": 1, "status": "fail", "stages": [], "core_version": VERSION,
              "interface": "wlo1", "acceptance": "isolated_userspace_four_node_pool"}
    output, handlers = None, {}
    try:
        outside_repo(args.output)
        output = probe.open_output(args.output)
        manifest = validate_manifest(load_private(args.manifest))
        profile = load_private(args.profile)
        def interrupted(signum, frame):
            global STOP
            STOP = True
        for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
            handlers[sig] = signal.signal(sig, interrupted)
        asyncio.run(run(manifest, profile, os.path.dirname(args.output), report))
        if STOP:
            report.update(status="fail", error="interrupted")
    except Error as exc:
        report.update(status="fail", error=str(exc))
    except Exception:
        report.update(status="fail", error="internal_or_os_error")
    finally:
        try:
            if output is not None:
                json.dump(report, output, indent=2, sort_keys=True)
                output.write("\n")
                output.flush()
                os.fsync(output.fileno())
        except OSError:
            report.update(status="fail", error="output_write_failed")
        finally:
            if output is not None:
                try:
                    output.close()
                except OSError:
                    report.update(status="fail", error="output_write_failed")
            for sig, handler in handlers.items():
                signal.signal(sig, handler)
    print(json.dumps({"status": report["status"], "stages": len(report["stages"])}))
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
