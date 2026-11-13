"""Local-only acceptance tests; never use a real VPN or remote endpoint."""
import copy
from contextlib import redirect_stdout
import io
import json
import os
import signal
from pathlib import Path
import socket
import stat
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest import mock

ROOT = Path(__file__).absolute().parent

import probe


def outbound():
    return {"type": "vless", "server": "192.0.2.10", "server_port": 443,
            "uuid": "00000000-0000-4000-8000-000000000001",
            "tls": {"enabled": True, "server_name": "example.com",
                    "reality": {"enabled": True, "public_key": "PLACEHOLDER"}}}


class IsolationTests(unittest.TestCase):
    def test_single_encrypted_outbound_is_copied_and_isolated(self):
        original = outbound()
        original.update(routing_mark=123, domain_resolver="system",
                        protect_path="/tmp/protect", bind_interface="tun0")
        saved = copy.deepcopy(original)
        config = probe.build_config(original, "wlo1", 23456)
        self.assertEqual(original, saved)
        self.assertEqual(config["inbounds"], [{"type": "mixed", "tag": "probe",
                                              "listen": "127.0.0.1", "listen_port": 23456}])
        node = config["outbounds"][0]
        self.assertEqual(node["tag"], "node")
        self.assertEqual(node["bind_interface"], "wlo1")
        for key in ("routing_mark", "domain_resolver", "protect_path", "detour"):
            self.assertNotIn(key, node)
        self.assertEqual(node["multiplex"], {"enabled": False})
        self.assertEqual(config["route"], {"final": "node", "auto_detect_interface": False})


    def test_rejects_unsafe_outbounds(self):
        for change in ({"type": "direct"}, {"server": "host.example"},
                       {"detour": "existing-vpn"}, {"type": "tun"},
                       {"tls": {"enabled": True, "insecure": True}},
                       {"bind_address": "127.0.0.1"}):
            with self.subTest(change=change):
                bad = outbound()
                bad.update(change)
                with self.assertRaises(probe.ProbeError):
                    probe.build_config(bad, "wlo1", 23456)


    def test_manifest_bounds_names_and_encryption(self):
        node = {"name": "safe", "expected_exit_ipv4": "198.51.100.2", "outbound": outbound()}
        self.assertEqual(probe.validate_manifest({"nodes": [node]}, "wlo1")["nodes"], [node])
        for manifest in ({"nodes": []}, {"nodes": [node] * 9}, {"nodes": [node, node]},
                         {"nodes": [dict(node, expected_exit_ipv4=True)]},
                         {"nodes": [dict(node, expected_http_exit_ipv4="198.51.100.2")]},
                         {"nodes": [node], "inbounds": [{"type": "tun"}]},
                         {"nodes": [node], "binary": "sing-box"}):
            with self.subTest(manifest=manifest):
                with self.assertRaises(probe.ProbeError):
                    probe.validate_manifest(manifest, "wlo1")

    def test_trojan_requires_verified_tls_and_reconnect_safe_transport(self):
        trojan = {"type": "trojan", "server": "192.0.2.11", "server_port": 443,
                  "password": "PRIVATE", "tls": {"enabled": True, "server_name": "example.com"},
                  "tcp_multi_path": True, "multiplex": {"enabled": True}}
        config = probe.build_config(trojan, "wlo1", 23456)
        self.assertNotIn("tcp_multi_path", config["outbounds"][0])
        self.assertFalse(config["outbounds"][0]["multiplex"]["enabled"])
        for extra in ({"transport": {"type": "grpc"}}, {"server": "::ffff:127.0.0.1"},
                      {"server": 123}, {"tls": {"enabled": False}},
                      {"tls": {"enabled": True, "server_name": "example.com", "certificate_path": "/private"}}):
            with self.assertRaises(probe.ProbeError):
                probe.build_config(dict(trojan, **extra), "wlo1", 23456)


class DnsTests(unittest.TestCase):
    def test_dns_a_answer_and_compressed_name(self):
        query = probe.dns_query(0x1234)
        answer = (b"\x12\x34\x81\x80\x00\x01\x00\x01\x00\x00\x00\x00" +
                  query[12:] + b"\xc0\x0c\x00\x01\x00\x01\x00\x00\x00\x3c\x00\x04\x5d\xb8\xd8\x22")
        self.assertEqual(probe.parse_dns(answer, 0x1234),
                         {"rcode": 0, "answers": ["93.184.216.34"]})
        for bad in (b"", answer[:15], answer[:-1],
                    b"\xff\xff" + answer[2:],
                    answer[:3] + b"\x82" + answer[4:12],
                    answer[:12] + b"\xc0\x0c" + answer[14:]):
            with self.subTest(packet=bad):
                with self.assertRaises(probe.ProbeError):
                    probe.parse_dns(bad, 0x1234)

    def test_socks_udp_frame_bounds_and_target(self):
        packet = b"\x00\x00\x00\x01\x01\x01\x01\x01\x00\x35payload"
        self.assertEqual(probe.parse_udp_frame(packet), b"payload")
        for bad in (b"", packet[:9], b"\x00\x00\x01" + packet[3:],
                    packet[:4] + b"\x08\x08\x08\x08" + packet[8:]):
            with self.assertRaises(probe.ProbeError):
                probe.parse_udp_frame(bad)


    def test_dns_rcode_and_unrelated_answers_are_not_successful_a_evidence(self):
        query = probe.dns_query(0x1234)
        nxdomain = b"\x12\x34\x81\x83\x00\x01\x00\x00\x00\x00\x00\x00" + query[12:]
        self.assertEqual(probe.parse_dns(nxdomain, 0x1234), {"rcode": 3, "answers": []})
        unrelated = (b"\x12\x34\x81\x80\x00\x01\x00\x01\x00\x00\x00\x00" + query[12:] +
                     b"\x04evil\x03com\x00\x00\x01\x00\x01\x00\x00\x00\x3c\x00\x04\xc0\x00\x02\x01")
        self.assertEqual(probe.parse_dns(unrelated, 0x1234)["answers"], [])
        for index in range(64):
            with self.assertRaises(probe.ProbeError):
                probe.parse_dns(bytes([index]) * (index + 1), 0x1234)

    def test_socks_reply_rejects_nonlocal_relay_and_reports_unsupported(self):
        for reply, code in ((b"\x05\x07\x00\x01", "udp_unsupported"),
                            (b"\x04\x00\x00\x01", "socks_reply_invalid"),
                            (b"\x05\x00\x00\x01\x01\x01\x01\x01\x00\x35", "socks_nonlocal_relay_forbidden"),
                            (b"\x05\x00", "socks_truncated")):
            with self.subTest(code=code):
                client, server = socket.socketpair()
                client.settimeout(1)
                server.settimeout(1)
                def respond():
                    with server:
                        probe.recv_exact(server, 3)
                        server.sendall(b"\x05\x00")
                        probe.recv_exact(server, 10)
                        server.sendall(reply)
                thread = threading.Thread(target=respond)
                thread.start()
                try:
                    with self.assertRaisesRegex(probe.ProbeError, "^" + code + "$"):
                        probe.socks_udp_relay(client)
                finally:
                    client.close()
                    thread.join(2)
                self.assertFalse(thread.is_alive())


class PrivateFilesTests(unittest.TestCase):
    def test_output_is_private_exclusive_and_symlink_safe(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            target = Path(directory) / "result.json"
            with probe.open_output(str(target)) as output:
                output.write('{"status":"pass"}')
            self.assertEqual(stat.S_IMODE(target.stat().st_mode), 0o600)
            with self.assertRaises(probe.ProbeError):
                probe.open_output(str(target))
            alias = Path(directory) / "alias"
            alias.symlink_to(target)
            with self.assertRaises(probe.ProbeError):
                probe.open_output(str(alias))
            linked = Path(directory) / "linked"
            linked.symlink_to(directory, target_is_directory=True)
            with self.assertRaises(probe.ProbeError):
                probe.open_output(str(linked / "new.json"))
            os.chmod(directory, 0o755)
            with self.assertRaises(probe.ProbeError):
                probe.open_output(str(Path(directory) / "other.json"))

    def test_cleanup_reports_changed_owned_file_without_deleting_it(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            workspace = probe.Workspace(directory)
            path = workspace.create("config.json", b"secret")
            os.unlink(path)
            os.symlink("/dev/null", path)
            result = workspace.cleanup()
            self.assertFalse(result["files_removed"])
            self.assertTrue(Path(path).is_symlink())
            os.unlink(path)
            os.rmdir(workspace.path)

    def test_process_timeout_stops_only_owned_process_group(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            workspace = probe.Workspace(directory)
            try:
                result = probe.command([sys.executable, "-c", "import time; time.sleep(30)"],
                                       workspace, "timeout", 0.05)
                self.assertEqual(result["error"], "process_timeout")
                self.assertTrue(result["process_group_stopped"])
            finally:
                self.assertTrue(workspace.cleanup()["files_removed"])


    def test_manifest_permissions_symlinks_and_fifo_fail_closed(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            manifest = Path(directory) / "manifest.json"
            manifest.write_text(json.dumps({"nodes": [{"name": "safe", "expected_exit_ipv4": "198.51.100.2",
                                                         "outbound": outbound()}]}))
            manifest.chmod(0o644)
            with self.assertRaises(probe.ProbeError):
                probe.load_manifest(str(manifest), "wlo1")
            manifest.chmod(0o600)
            self.assertEqual(len(probe.load_manifest(str(manifest), "wlo1")["nodes"]), 1)
            link = Path(directory) / "link.json"
            link.symlink_to(manifest)
            with self.assertRaises(probe.ProbeError):
                probe.load_manifest(str(link), "wlo1")
            fifo = Path(directory) / "fifo.json"
            os.mkfifo(fifo, 0o600)
            with self.assertRaises(probe.ProbeError):
                probe.load_manifest(str(fifo), "wlo1")

    def test_child_file_size_hard_limit(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            work = probe.Workspace(directory)
            try:
                result = probe.command([sys.executable, "-c",
                    "import sys; sys.stdout.buffer.write(b'x'*2097152); sys.stdout.flush()"],
                    work, "limit", 2)
                self.assertNotEqual(result["returncode"], 0)
                self.assertLessEqual(os.stat(result["stdout"]).st_size, 1048576)
                self.assertTrue(result["process_group_stopped"])
            finally:
                self.assertTrue(work.cleanup()["files_removed"])

    def test_timeout_kills_descendants_but_not_an_unrelated_process(self):
        sentinel = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"],
                                    start_new_session=True)
        try:
            with tempfile.TemporaryDirectory(dir=ROOT) as directory:
                work = probe.Workspace(directory)
                try:
                    script = ("import subprocess,sys,time; subprocess.Popen([sys.executable,'-c',"
                              "'import signal,time; signal.signal(signal.SIGTERM,signal.SIG_IGN); time.sleep(30)']);"
                              "time.sleep(30)")
                    result = probe.command([sys.executable, "-c", script], work, "tree", 0.3)
                    self.assertTrue(result["process_group_stopped"], result)
                    self.assertIsNone(sentinel.poll())
                finally:
                    self.assertTrue(work.cleanup()["files_removed"])
        finally:
            sentinel.terminate()
            sentinel.wait(timeout=2)


class CurlTests(unittest.TestCase):
    def test_curl_is_fresh_socks5h_and_ignores_all_environment_proxies(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            workspace = probe.Workspace(directory)
            def fake_command(argv, work, label, timeout):
                self.assertEqual(argv[:2], ["/usr/bin/curl", "--disable"])
                self.assertIn("socks5h://127.0.0.1:23456", argv)
                self.assertEqual(argv[argv.index("--noproxy") + 1], "")
                self.assertNotIn("--next", argv)
                self.assertEqual(argv.count(probe.IPIFY), 1)
                self.assertIn("--max-filesize", argv)
                self.assertNotIn("--location", argv)
                body = argv[argv.index("--output") + 1]
                with open(body, "wb") as stream:
                    stream.write(b'{"ip":"192.0.2.7"}')
                out = work.create(label + ".stdout", b"200 18 0.01\n")
                return {"returncode": 0, "stdout": out, "process_group_stopped": True}
            try:
                with mock.patch.object(probe, "command", side_effect=fake_command):
                    result, body = probe.curl_request("/usr/bin/curl", 23456, probe.IPIFY,
                                                      workspace, "exit")
                self.assertEqual(result["status"], "pass")
                self.assertEqual(result["http_code"], 200)
                self.assertEqual(json.loads(body)["ip"], "192.0.2.7")
                self.assertFalse(any("proxy" in key.lower() for key in probe.child_env()))
            finally:
                self.assertTrue(workspace.cleanup()["files_removed"])


    @unittest.skipUnless(probe.shutil.which("curl"), "curl not installed")
    def test_real_curl_flags_and_remote_dns_against_local_rejecting_socks_server(self):
        observed = []
        errors = []
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            listener.listen(1)
            listener.settimeout(4)
            port = listener.getsockname()[1]
            def fake_server():
                try:
                    with listener.accept()[0] as stream:
                        stream.settimeout(4)
                        head = probe.recv_exact(stream, 2)
                        self.assertEqual(head[0], 5)
                        methods = probe.recv_exact(stream, head[1])
                        self.assertIn(0, methods)
                        stream.sendall(b"\x05\x00")
                        head = probe.recv_exact(stream, 4)
                        self.assertEqual(head, b"\x05\x01\x00\x03")
                        size = probe.recv_exact(stream, 1)[0]
                        observed.append(probe.recv_exact(stream, size))
                        probe.recv_exact(stream, 2)
                        # Reject CONNECT: there is no DNS lookup or remote socket.
                        stream.sendall(b"\x05\x05\x00\x01\x00\x00\x00\x00\x00\x00")
                except BaseException as exc:
                    errors.append(exc)
            thread = threading.Thread(target=fake_server)
            thread.start()
            try:
                with tempfile.TemporaryDirectory(dir=ROOT) as directory:
                    work = probe.Workspace(directory)
                    try:
                        result, _ = probe.curl_request(probe.shutil.which("curl"), port,
                                                       probe.IPIFY, work, "real-curl")
                        self.assertEqual(result["returncode"], 97, result)
                        self.assertEqual(result["status"], "fail")
                    finally:
                        self.assertTrue(work.cleanup()["files_removed"])
            finally:
                thread.join(5)
            self.assertFalse(thread.is_alive())
            self.assertEqual(errors, [])
            self.assertEqual(observed, [b"api.ipify.org"])


class LocalHarnessTests(unittest.TestCase):
    def node(self):
        return {"name": "documentation-node", "expected_exit_ipv4": "192.0.2.7",
                "outbound": outbound()}

    def test_owned_proxy_full_synthetic_run_and_negative_canary(self):
        fixture = str(ROOT / "fake_process.py")
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            result = probe.run_node(self.node(), fixture, fixture, "lo", directory, True)
            self.assertEqual(result["status"], "pass", result)
            self.assertEqual(result["checks"]["udp_dns"]["answers"], ["192.0.2.80"])
            self.assertEqual(result["checks"]["reconnect_exit"]["exit_ipv4"], "192.0.2.7")
            self.assertEqual(result["checks"]["download"]["bytes"], 1048576)
            self.assertEqual(result["checks"]["negative_canary"]["status"], "pass")
            self.assertTrue(result["cleanup"]["process_group_stopped"])
            self.assertTrue(result["cleanup"]["files_removed"])
            self.assertEqual(list(Path(directory).iterdir()), [])
            rendered = json.dumps(result)
            for secret in ("PLACEHOLDER", "00000000-0000-4000-8000-000000000001", "NOT-RETAINED"):
                self.assertNotIn(secret, rendered)

    def test_cleanup_failure_is_reported_and_overrides_pass(self):
        original = probe.Workspace.cleanup
        def report_failure(work):
            result = original(work)
            result["files_removed"] = False
            return result
        fixture = str(ROOT / "fake_process.py")
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            with mock.patch.object(probe.Workspace, "cleanup", report_failure):
                result = probe.run_node(self.node(), fixture, fixture, "lo", directory, False)
            self.assertEqual(result["status"], "fail")
            self.assertEqual(result["error"], "cleanup_failed")

    def test_udp_unsupported_is_partial_not_pass(self):
        fixture = str(ROOT / "fake_process.py")
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            with mock.patch.object(probe, "udp_dns", return_value={
                    "status": "partial", "error": "udp_unsupported"}):
                result = probe.run_node(self.node(), fixture, fixture, "lo", directory, False)
            self.assertEqual(result["status"], "partial")

    def test_preflight_failure_is_redacted_and_cleans_private_files(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            result = probe.run_node(self.node(), "/usr/bin/false", "/usr/bin/false", "lo", directory, False)
            self.assertEqual(result["status"], "fail")
            self.assertEqual(result["error"], "config_check_failed")
            self.assertTrue(result["cleanup"]["files_removed"])
            self.assertEqual(list(Path(directory).iterdir()), [])


class CliTests(unittest.TestCase):
    def run_main(self, directory, interrupt=False):
        fixture = str(ROOT / "fake_process.py")
        manifest = Path(directory) / "manifest.json"
        manifest.write_text(json.dumps({"binary": fixture, "nodes": [{
            "name": "synthetic", "expected_exit_ipv4": "192.0.2.7", "outbound": outbound()}]}))
        manifest.chmod(0o600)
        output = Path(directory) / "result.json"
        summary = io.StringIO()
        with mock.patch.object(probe, "verify_interface"), \
                mock.patch.object(probe.shutil, "which", return_value=fixture), redirect_stdout(summary):
            if interrupt:
                def terminate(*args):
                    os.kill(os.getpid(), signal.SIGTERM)
                with mock.patch.object(probe, "exit_check", side_effect=terminate):
                    code = probe.main(["--manifest", str(manifest), "--output", str(output),
                                       "--interface", "lo"])
            else:
                code = probe.main(["--manifest", str(manifest), "--output", str(output),
                                   "--interface", "lo", "--negative-canary"])
        return code, json.loads(output.read_text()), json.loads(summary.getvalue())

    def test_cli_private_manifest_to_private_report_local_fixtures_only(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            code, report, summary = self.run_main(directory)
            self.assertEqual(code, 0, report)
            self.assertEqual(summary, {"status": "pass", "node_count": 1})
            self.assertEqual(stat.S_IMODE((Path(directory) / "result.json").stat().st_mode), 0o600)
            self.assertIn("No mobile/cellular certification", report["limitations"])
            self.assertEqual(sorted(x.name for x in Path(directory).iterdir()), ["manifest.json", "result.json"])

    def test_sigterm_reports_interruption_and_removes_only_owned_resources(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            code, report, summary = self.run_main(directory, interrupt=True)
            self.assertEqual(code, 1)
            result = report["nodes"][0]
            self.assertTrue(result["interrupted"])
            self.assertEqual(result["cleanup"], {"process_group_stopped": True, "files_removed": True})
            self.assertEqual(sorted(x.name for x in Path(directory).iterdir()), ["manifest.json", "result.json"])
        probe._STOP_REQUESTED = False  # Reset cancellation state between independent API tests.


if __name__ == "__main__":
    unittest.main()
