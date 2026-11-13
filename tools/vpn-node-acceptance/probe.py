#!/usr/bin/env python3
"""Bounded, userspace-only VPN acceptance. Stdlib orchestration; curl + sing-box."""
import argparse
import copy
from contextlib import contextmanager
import ipaddress
import json
import os
from pathlib import Path
import re
import resource
import secrets
import shutil
import signal
import socket
import stat
import struct
import subprocess
import sys
import tempfile
import time
import uuid

MAX_NODES = 8
MAX_JSON = 1024 * 1024
MAX_DOWNLOAD = 1048576
TIMEOUT = 18
_CLEANUP_DEPTH = 0
_STOP_REQUESTED = False


@contextmanager
def cleanup_guard():
    global _CLEANUP_DEPTH
    _CLEANUP_DEPTH += 1
    try:
        yield
    finally:
        _CLEANUP_DEPTH -= 1


def check_interrupted():
    if _STOP_REQUESTED:
        raise StopRequested()


FORBIDDEN = {"routing_mark", "detour", "domain_resolver", "protect_path"}
ALLOWED = {"type", "tag", "server", "server_port", "uuid", "flow", "password",
           "tls", "transport", "packet_encoding", "network", "multiplex",
           "bind_interface", "connect_timeout", "tcp_fast_open", "tcp_multi_path",
           "udp_fragment", "udp_over_tcp"} | FORBIDDEN
TARGETS = ("https://example.com/", "https://www.wikipedia.org/")
IPIFY = "https://api.ipify.org?format=json"
TRACE = "https://www.cloudflare.com/cdn-cgi/trace"
DOWNLOAD = "https://speed.cloudflare.com/__down?bytes=1048576"
LIMITATIONS = ["No mobile/cellular certification", "No TUN routing or leak certification",
               "No kill-switch, reboot, handoff, or long-term/speed certification",
               "Existing VPN baseline preservation must be verified separately by lead"]


class ProbeError(Exception):
    """Only fixed, non-secret codes may cross the report boundary."""


def require(condition, code):
    if not condition:
        raise ProbeError(code)


def ipv4(value):
    require(isinstance(value, str), "invalid_ipv4")
    try:
        return str(ipaddress.IPv4Address(value))
    except (ValueError, TypeError, ipaddress.AddressValueError):
        raise ProbeError("invalid_ipv4") from None


def build_config(outbound, interface, port):
    require(isinstance(outbound, dict), "invalid_outbound")
    require(isinstance(interface, str) and re.fullmatch(r"[a-zA-Z0-9_.:-]{1,15}", interface),
            "invalid_interface")
    require(isinstance(port, int) and 1 <= port <= 65535, "invalid_port")
    node = copy.deepcopy(outbound)
    require(not (set(node) - ALLOWED), "unsupported_outbound_field")
    require(not node.get("detour"), "proxy_detour_forbidden")
    require(node.get("type") in ("vless", "trojan"), "unsupported_encryption")
    require(isinstance(node.get("server"), str), "numeric_server_required")
    try:
        server = ipaddress.ip_address(node.get("server"))
    except (ValueError, TypeError):
        raise ProbeError("numeric_server_required") from None
    routed = getattr(server, "ipv4_mapped", None) or server
    require(not routed.is_unspecified and not routed.is_loopback and not routed.is_multicast
            and not routed.is_link_local and not getattr(server, "scope_id", None),
            "invalid_server_address")
    require(type(node.get("server_port")) is int and 1 <= node["server_port"] <= 65535,
            "invalid_server_port")
    tls = node.get("tls")
    require(isinstance(tls, dict) and tls.get("enabled") is True
            and not tls.get("insecure"), "verified_tls_required")
    require(not (set(tls) - {"enabled", "server_name", "insecure", "alpn", "min_version",
                            "max_version", "cipher_suites", "utls", "reality"}),
            "unsupported_tls_field")
    require(isinstance(tls.get("server_name"), str) and
            re.fullmatch(r"[a-zA-Z0-9.-]{1,253}", tls["server_name"]), "invalid_tls_name")
    if "utls" in tls:
        require(isinstance(tls["utls"], dict) and
                not (set(tls["utls"]) - {"enabled", "fingerprint"}), "invalid_utls")
    if node["type"] == "vless":
        reality = tls.get("reality")
        require(isinstance(reality, dict) and reality.get("enabled") is True and
                not (set(reality) - {"enabled", "public_key", "short_id"}) and
                isinstance(reality.get("public_key"), str) and reality["public_key"],
                "reality_required")
        try:
            uuid.UUID(node.get("uuid", ""))
        except (ValueError, TypeError, AttributeError):
            raise ProbeError("invalid_uuid") from None
    else:
        require(isinstance(node.get("password"), str) and node["password"], "password_required")
        require("reality" not in tls, "trojan_reality_unsupported")
    if "transport" in node:
        tr = node["transport"]
        # HTTP/2/gRPC pools can mask an upstream reconnect; reject them, do not guess.
        fields = {"ws": {"type", "path", "headers", "max_early_data", "early_data_header_name"},
                  "httpupgrade": {"type", "host", "path", "headers"}}
        require(isinstance(tr, dict) and tr.get("type") in fields and
                not (set(tr) - fields[tr["type"]]), "unsupported_transport")
    # Explicitly disable transport pooling: every curl opens a new encrypted upstream.
    node["multiplex"] = {"enabled": False}
    node.pop("udp_over_tcp", None)
    node.pop("tcp_multi_path", None)  # Multipath subflows must not select another uplink.
    for key in FORBIDDEN:
        node.pop(key, None)
    node.update(tag="node", bind_interface=interface, server=str(server), connect_timeout="8s")
    return {"log": {"disabled": True},
            "inbounds": [{"type": "mixed", "tag": "probe", "listen": "127.0.0.1",
                          "listen_port": port}],
            "outbounds": [node],
            "route": {"final": "node", "auto_detect_interface": False}}


def validate_manifest(data, interface):
    require(isinstance(data, dict) and not (set(data) - {"nodes", "binary"}), "invalid_manifest")
    nodes = data.get("nodes")
    require(isinstance(nodes, list) and 1 <= len(nodes) <= MAX_NODES, "invalid_node_count")
    binary = data.get("binary", "/usr/bin/sing-box")
    require(isinstance(binary, str) and os.path.isabs(binary) and "\x00" not in binary,
            "invalid_binary")
    names = set()
    for node in nodes:
        require(isinstance(node, dict) and not (set(node) - {
            "name", "expected_exit_ipv4", "outbound", "expected_http_exit_ipv4"}), "invalid_node")
        name = node.get("name")
        require(isinstance(name, str) and re.fullmatch(r"[A-Za-z0-9_.-]{1,64}", name)
                and name not in names, "invalid_node_name")
        names.add(name)
        ipv4(node.get("expected_exit_ipv4"))
        extra = node.get("expected_http_exit_ipv4", [])
        require(isinstance(extra, list) and len(extra) <= 16, "invalid_http_exit_allowlist")
        for address in extra:
            ipv4(address)
        build_config(node.get("outbound"), interface, 12345)
    return data


def dns_query(qid):
    return struct.pack("!6H", qid, 0x0100, 1, 0, 0, 0) + b"\x07example\x03com\x00\x00\x01\x00\x01"


def dns_name(data, offset):
    labels, seen, end = [], set(), None
    for _ in range(64):
        require(0 <= offset < len(data) and offset not in seen, "dns_name_bounds")
        seen.add(offset)
        size = data[offset]
        if size & 0xc0 == 0xc0:
            require(offset + 1 < len(data), "dns_pointer_bounds")
            if end is None:
                end = offset + 2
            offset = ((size & 0x3f) << 8) | data[offset + 1]
            continue
        require(size <= 63, "dns_label_invalid")
        offset += 1
        if size == 0:
            require(sum(len(x) + 1 for x in labels) <= 254, "dns_name_too_long")
            return b".".join(labels).lower(), end if end is not None else offset
        require(offset + size <= len(data), "dns_label_bounds")
        labels.append(data[offset:offset + size])
        offset += size
    raise ProbeError("dns_pointer_loop")


def parse_dns(data, qid):
    require(12 <= len(data) <= 4096, "dns_packet_size")
    ident, flags, qd, an, ns, ar = struct.unpack("!6H", data[:12])
    require(ident == qid and flags & 0x8000 and not flags & 0x7a40,
            "dns_header_invalid")  # QR=1, opcode=0, TC=0; AD/CD allowed.
    rcode = flags & 15
    require(qd == 1 and an + ns + ar <= 64, "dns_counts_invalid")
    name, pos = dns_name(data, 12)
    require(pos + 4 <= len(data) and name == b"example.com" and
            data[pos:pos + 4] == b"\x00\x01\x00\x01", "dns_question_invalid")
    pos += 4
    answers, aliases = [], {}
    for index in range(an + ns + ar):
        name, pos = dns_name(data, pos)
        require(pos + 10 <= len(data), "dns_record_bounds")
        kind, cls, ttl, size = struct.unpack("!HHIH", data[pos:pos + 10])
        pos += 10
        require(pos + size <= len(data), "dns_rdata_bounds")
        if index < an and kind == 1 and cls == 1:
            require(size == 4, "dns_a_length")
            answers.append((name, str(ipaddress.IPv4Address(data[pos:pos + 4]))))
        if kind in (2, 5, 12):
            target, end = dns_name(data, pos)
            require(end == pos + size, "dns_name_rdata_bounds")
            if kind == 5 and cls == 1 and index < an:
                aliases[name] = target
        pos += size
    require(pos == len(data), "dns_trailing_data")
    accepted, name = {b"example.com"}, b"example.com"
    for _ in range(64):
        if name not in aliases:
            break
        name = aliases[name]
        require(name not in accepted, "dns_cname_loop")
        accepted.add(name)
    return {"rcode": rcode, "answers": sorted({ip for host, ip in answers if host in accepted})}


def recv_exact(sock, size, deadline=None):
    if deadline is None:
        deadline = time.monotonic() + (sock.gettimeout() or 4)
    result = bytearray()
    while len(result) < size:
        remaining = deadline - time.monotonic()
        require(remaining > 0, "socks_read_timeout")
        sock.settimeout(remaining)
        chunk = sock.recv(size - len(result))
        require(chunk, "socks_truncated")
        result.extend(chunk)
    return bytes(result)


def socks_greeting(control, deadline=None):
    control.sendall(b"\x05\x01\x00")
    require(recv_exact(control, 2, deadline) == b"\x05\x00", "socks_auth_invalid")


def socks_udp_relay(control):
    deadline = time.monotonic() + 4
    socks_greeting(control, deadline)
    control.sendall(b"\x05\x03\x00\x01\x00\x00\x00\x00\x00\x00")
    header = recv_exact(control, 4, deadline)
    require(header[0] == 5 and header[2] == 0, "socks_reply_invalid")
    if header[1] in (1, 7, 8):
        raise ProbeError("udp_unsupported")
    require(header[1] == 0 and header[3] == 1, "socks_udp_relay_invalid")
    host = ipaddress.IPv4Address(recv_exact(control, 4, deadline))
    port = struct.unpack("!H", recv_exact(control, 2, deadline))[0]
    require((host.is_loopback or host.is_unspecified) and port != 0,
            "socks_nonlocal_relay_forbidden")
    return "127.0.0.1" if host.is_unspecified else str(host), port


def parse_udp_frame(data):
    require(len(data) >= 10 and data[:4] == b"\x00\x00\x00\x01" and
            data[4:10] == b"\x01\x01\x01\x01\x00\x35", "socks_udp_frame_invalid")
    return data[10:]


def udp_dns(port):
    started = time.monotonic()
    try:
        # Both actual sockets connect/send ONLY to the dedicated loopback proxy.
        with socket.create_connection(("127.0.0.1", port), timeout=4) as control:
            relay = socks_udp_relay(control)
            qid = secrets.randbits(16)
            query = b"\x00\x00\x00\x01\x01\x01\x01\x01\x00\x35" + dns_query(qid)
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as udp:
                udp.settimeout(4)
                udp.bind(("127.0.0.1", 0))
                udp.connect(relay)
                udp.send(query)
                data = udp.recv(4096 + 11)
            parsed = parse_dns(parse_udp_frame(data), qid)
            parsed["status"] = "pass" if parsed["rcode"] == 0 and parsed["answers"] else "fail"
            if parsed["status"] == "fail":
                parsed["error"] = "dns_no_successful_a_answer"
            return dict(parsed, duration=round(time.monotonic() - started, 3))
    except ProbeError as exc:
        return {"status": "partial" if str(exc) == "udp_unsupported" else "fail",
                "error": str(exc), "duration": round(time.monotonic() - started, 3)}
    except (OSError, TimeoutError):
        # Failure to demonstrate UDP is never converted into a complete pass.
        return {"status": "partial", "error": "udp_unavailable_or_timeout",
                "duration": round(time.monotonic() - started, 3)}


def private_parent(path):
    """Walk with dirfds/O_NOFOLLOW: reject symlinks in every path component."""
    require(isinstance(path, str) and "\x00" not in path and ".." not in path.split("/"),
            "invalid_path")
    absolute = os.path.abspath(path)
    parts = Path(absolute).parts
    fd = os.open("/", os.O_RDONLY | os.O_DIRECTORY)
    try:
        for component in parts[1:-1]:
            next_fd = os.open(component, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = next_fd
        info = os.fstat(fd)
        require(info.st_uid == os.getuid() and stat.S_IMODE(info.st_mode) == 0o700,
                "private_parent_required")
        return fd, parts[-1], absolute
    except BaseException:
        os.close(fd)
        raise


def open_output(path):
    parent = None
    try:
        parent, name, _ = private_parent(path)
        fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600,
                     dir_fd=parent)
        os.fchmod(fd, 0o600)
        return os.fdopen(fd, "w", encoding="utf-8")
    except OSError:
        raise ProbeError("unsafe_or_existing_output") from None
    finally:
        if parent is not None:
            os.close(parent)


def load_manifest(path, interface):
    parent = None
    try:
        parent, name, _ = private_parent(path)
        fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
        with os.fdopen(fd, "rb") as stream:
            info = os.fstat(stream.fileno())
            require(stat.S_ISREG(info.st_mode) and info.st_uid == os.getuid() and
                    stat.S_IMODE(info.st_mode) == 0o600 and info.st_size <= MAX_JSON,
                    "private_manifest_required")
            raw = stream.read(MAX_JSON + 1)
            require(len(raw) <= MAX_JSON, "manifest_too_large")
        return validate_manifest(json.loads(raw), interface)
    except (OSError, ValueError, UnicodeError, RecursionError):
        raise ProbeError("invalid_or_unsafe_manifest") from None
    finally:
        if parent is not None:
            os.close(parent)


def identity(info):
    return info.st_dev, info.st_ino, info.st_uid


class Workspace:
    """Exact owned-file registry: never recursive-delete a directory tree."""
    def __init__(self, parent):
        self.path = tempfile.mkdtemp(prefix="vpn-probe-", dir=parent)
        os.chmod(self.path, 0o700)
        self.owner = identity(os.lstat(self.path))
        self.files = {}
        self.process_cleanup_ok = True

    def create(self, name, content=b""):
        require(re.fullmatch(r"[A-Za-z0-9_.-]+", name), "invalid_owned_filename")
        path = os.path.join(self.path, name)
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        try:
            os.fchmod(fd, 0o600)
            self.files[path] = identity(os.fstat(fd))
            with os.fdopen(fd, "wb", closefd=False) as stream:
                stream.write(content)
        finally:
            os.close(fd)
        return path

    def read(self, path, limit):
        require(path in self.files, "unowned_file")
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
        with os.fdopen(fd, "rb") as stream:
            require(identity(os.fstat(stream.fileno())) == self.files[path], "owned_file_changed")
            content = stream.read(limit + 1)
            require(len(content) <= limit, "owned_file_limit")
            return content

    def cleanup(self):
        removed = True
        try:
            require(identity(os.lstat(self.path)) == self.owner and
                    stat.S_ISDIR(os.lstat(self.path).st_mode), "owned_directory_changed")
            for path, owner in self.files.items():
                try:
                    info = os.lstat(path)
                    require(identity(info) == owner and stat.S_ISREG(info.st_mode), "owned_file_changed")
                    os.unlink(path)
                except (OSError, ProbeError):
                    removed = False
            if removed:
                os.rmdir(self.path)
        except (OSError, ProbeError):
            removed = False
        return {"process_group_stopped": self.process_cleanup_ok, "files_removed": removed}


def child_env():
    # No proxy vars (including ALL_PROXY/no_proxy), sing-box env overrides or curlrc.
    return {"PATH": os.defpath, "LANG": "C", "LC_ALL": "C", "GOMAXPROCS": "2",
            "GOMEMLIMIT": "128MiB"}


def child_limits():
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    resource.setrlimit(resource.RLIMIT_NOFILE, (128, 128))
    resource.setrlimit(resource.RLIMIT_FSIZE, (MAX_DOWNLOAD, MAX_DOWNLOAD))
    resource.setrlimit(resource.RLIMIT_CPU, (120, 120))


def start_process(argv, workspace, label):
    stdout = workspace.create(label + ".stdout")
    stderr = workspace.create(label + ".stderr")
    with open(stdout, "wb") as out, open(stderr, "wb") as err:
        process = subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=out, stderr=err,
                                   cwd=workspace.path, env=child_env(), start_new_session=True,
                                   preexec_fn=child_limits, close_fds=True)
    return process, stdout, stderr


def stop_process(process):
    """Defer cancellation during bounded cleanup; never abandon a half-stopped child."""
    with cleanup_guard():
        return _stop_process(process)


def _stop_process(process):
    """Signal only the session/process group we created, never names or services."""
    if process is None:
        return True
    try:
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            process.wait(timeout=1)
            return True
        try:
            process.wait(timeout=1)
        except subprocess.TimeoutExpired:
            pass
        # Also remove any still-running same-group descendants, even if leader exited.
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait(timeout=2)
        # Linux /proc: zombies have no sockets/resources and are awaiting reaping.
        for entry in os.scandir("/proc"):
            if not entry.name.isdigit():
                continue
            try:
                with open(entry.path + "/stat", encoding="ascii") as stream:
                    fields = stream.read(4096).rsplit(")", 1)[1].split()
                if int(fields[2]) == process.pid and fields[0] != "Z":
                    return False
            except (OSError, ValueError, IndexError):
                continue
        return True
    except (OSError, subprocess.TimeoutExpired):
        return False


def command(argv, workspace, label, timeout):
    process = None
    result = {}
    try:
        process, stdout, stderr = start_process(argv, workspace, label)
        result.update(stdout=stdout, stderr=stderr)
        try:
            result["returncode"] = process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            result["error"] = "process_timeout"
    except OSError:
        result["error"] = "process_start_failed"
    finally:
        stopped = stop_process(process)
        workspace.process_cleanup_ok &= stopped
        result["process_group_stopped"] = stopped
    return result


def curl_request(binary, port, url, workspace, label, limit=65536, capture=True):
    check_interrupted()
    started = time.monotonic()
    body_path = workspace.create(label + ".body")
    argv = [binary, "--disable", "--silent", "--show-error", "--ipv4",
            "--proxy", "socks5h://127.0.0.1:" + str(port), "--noproxy", "",
            "--proto", "=https", "--proto-redir", "=https", "--max-redirs", "0",
            "--connect-timeout", "8", "--max-time", str(TIMEOUT), "--retry", "0",
            "--no-keepalive", "--header", "Connection: close",
            "--max-filesize", str(limit), "--output", body_path,
            "--write-out", "%{http_code} %{size_download} %{time_total}\\n", url]
    executed = command(argv, workspace, label, TIMEOUT + 2)
    result = {"status": "fail", "duration": round(time.monotonic() - started, 3),
              "bytes": os.lstat(body_path).st_size}
    body = b""
    if "stdout" in executed:
        try:
            fields = workspace.read(executed["stdout"], 256).decode("ascii").strip().split()
            require(len(fields) == 3 and re.fullmatch(r"[0-9]{3}", fields[0]) and
                    re.fullmatch(r"[0-9]+", fields[1]) and
                    re.fullmatch(r"[0-9]+(?:\.[0-9]+)?", fields[2]), "curl_metrics_invalid")
            result["http_code"] = int(fields[0])
        except (ProbeError, UnicodeError, OSError):
            result["error"] = "curl_metrics_invalid"
    if executed.get("error"):
        result["error"] = executed["error"]
    elif executed.get("returncode") != 0:
        result["error"] = "curl_failed"
        result["returncode"] = executed.get("returncode")
    elif not executed.get("process_group_stopped"):
        result["error"] = "curl_cleanup_failed"
    elif not result.get("error"):
        if 200 <= result["http_code"] < 400 and result["bytes"] <= limit:
            result["status"] = "pass"
        else:
            result["error"] = "http_status_or_size_failed"
    if result["status"] == "pass" and capture:
        try:
            body = workspace.read(body_path, limit)
        except (ProbeError, OSError):
            result.update(status="fail", error="response_body_invalid")
    return result, body


def exit_check(binary, port, workspace, label, expected):
    result, body = curl_request(binary, port, IPIFY, workspace, label)
    if result["status"] == "pass":
        try:
            require(result["http_code"] == 200, "exit_http_status")
            address = ipv4(json.loads(body)["ip"])
            result["exit_ipv4"] = address
            require(address == expected, "unexpected_exit_ipv4")
        except ProbeError as exc:
            result.update(status="fail", error=str(exc))
        except (ValueError, TypeError, KeyError, UnicodeError, RecursionError):
            result.update(status="fail", error="exit_response_invalid")
    return result


def trace_check(binary, port, workspace, allowed):
    result, body = curl_request(binary, port, TRACE, workspace, "cloudflare-trace")
    if result["status"] == "pass":
        try:
            require(result["http_code"] == 200, "trace_http_status")
            # Never retain or print arbitrary trace fields (loc, colo, warp, etc.).
            fields = {}
            for line in body.decode("ascii").splitlines():
                key, sep, value = line.partition("=")
                if sep and key in ("ip", "h2", "tls"):
                    require(key not in fields, "trace_duplicate_field")
                    fields[key] = value
            address = ipv4(fields.get("ip"))
            result["exit_ipv4"] = address
            require(address in allowed, "unexpected_http_exit_ipv4")
            require(re.fullmatch(r"TLSv1\.[23]", fields.get("tls", "")), "trace_tls_invalid")
            result["tls"] = fields["tls"]
            if "h2" in fields:
                require(fields["h2"] in ("0", "1", "on", "off"), "trace_h2_invalid")
                result["h2"] = fields["h2"]
        except ProbeError as exc:
            result.update(status="fail", error=str(exc))
        except UnicodeError:
            result.update(status="fail", error="trace_response_invalid")
    return result


def reserve_port():
    for _ in range(10):
        tcp, udp = socket.socket(), socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            tcp.bind(("127.0.0.1", 0))
            port = tcp.getsockname()[1]
            udp.bind(("127.0.0.1", port))
            return port, (tcp, udp)
        except OSError:
            tcp.close()
            udp.close()
    raise ProbeError("local_port_unavailable")


def owns_listener(process, port):
    try:
        sockets = set()
        for fd in os.scandir("/proc/" + str(process.pid) + "/fd"):
            try:
                link = os.readlink(fd.path)
                if link.startswith("socket:["):
                    sockets.add(link[8:-1])
            except OSError:
                continue
        with open("/proc/net/tcp", encoding="ascii") as stream:
            for line in stream:
                fields = line.split()
                if len(fields) >= 10 and fields[1] == "0100007F:" + format(port, "04X") and fields[3] == "0A":
                    return fields[9] in sockets
    except OSError:
        pass
    return False


def wait_ready(process, port):
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        require(process.poll() is None, "proxy_exited_early")
        if owns_listener(process, port):
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=0.3) as control:
                    socks_greeting(control)
                require(process.poll() is None, "proxy_exited_early")
                return
            except (OSError, ProbeError):
                pass
        time.sleep(0.05)
    raise ProbeError("owned_proxy_not_ready")


class StopRequested(BaseException):
    pass


def combined_status(checks):
    statuses = [item["status"] for item in checks.values()]
    return "fail" if "fail" in statuses else "partial" if "partial" in statuses else "pass"


def run_node(node, binary, curl_binary, interface, parent, negative_canary=False):
    started = time.monotonic()
    result = {"name": node["name"], "status": "fail", "checks": {},
              "isolation": {"loopback_only_inbound": True, "single_encrypted_outbound": True,
                            "numeric_server": True, "bind_interface": interface,
                            "no_system_routing_changes": True, "proxy_environment_disabled": True,
                            "multiplex_disabled": True, "owned_listener_confirmed": False}}
    workspace, process, reserved = None, None, ()
    checks = result["checks"]
    try:
        check_interrupted()
        workspace = Workspace(parent)
        port, reserved = reserve_port()
        result["owned_resources"] = {"directory": workspace.path, "loopback_port": port}
        config = build_config(node["outbound"], interface, port)
        encoded = json.dumps(config).encode("utf-8")
        require(len(encoded) <= MAX_JSON, "config_too_large")
        config_path = workspace.create("config.json", encoded)
        checked = command([binary, "check", "-c", config_path, "-D", workspace.path],
                          workspace, "check", 8)
        checks["config_check"] = {"status": "pass" if checked.get("returncode") == 0 and
                                  checked.get("process_group_stopped") else "fail"}
        require(checks["config_check"]["status"] == "pass", "config_check_failed")
        check_interrupted()
        for sock in reserved:
            sock.close()
        reserved = ()
        process, _, _ = start_process([binary, "run", "-c", config_path, "-D", workspace.path],
                                     workspace, "proxy")
        result["owned_resources"]["process_group"] = process.pid
        wait_ready(process, port)
        result["isolation"]["owned_listener_confirmed"] = True
        checks["proxy_health"] = {"status": "pass"}
        expected = node["expected_exit_ipv4"]
        checks["initial_exit"] = exit_check(curl_binary, port, workspace, "initial-exit", expected)
        require(checks["initial_exit"]["status"] == "pass", "initial_exit_failed")
        allowed = {expected, *node.get("expected_http_exit_ipv4", [])}
        checks["cloudflare_exit"] = trace_check(curl_binary, port, workspace, allowed)
        for index, url in enumerate(TARGETS):
            outcome, _ = curl_request(curl_binary, port, url, workspace, "https-" + str(index),
                                      MAX_DOWNLOAD, capture=False)
            checks["https_" + ("example" if index == 0 else "wikipedia")] = outcome
        checks["download"], _ = curl_request(curl_binary, port, DOWNLOAD, workspace, "download",
                                             MAX_DOWNLOAD, capture=False)
        download = checks["download"]
        if download["status"] == "pass" and (download["bytes"] != MAX_DOWNLOAD or
                                               download["http_code"] != 200):
            download.update(status="fail", error="download_incomplete")
        checks["reconnect_exit"] = exit_check(curl_binary, port, workspace, "reconnect-exit", expected)
        check_interrupted()
        checks["udp_dns"] = udp_dns(port)
        require(process.poll() is None and owns_listener(process, port), "proxy_health_lost")
        stopped = stop_process(process)
        workspace.process_cleanup_ok &= stopped
        if stopped:
            process = None
        check_interrupted()
        if negative_canary:
            if stopped:
                canary, _ = curl_request(curl_binary, port, IPIFY, workspace, "negative-canary")
                passed = canary["status"] == "fail" and canary.get("returncode") == 7
                checks["negative_canary"] = {"status": "pass" if passed else "fail",
                                              "duration": canary["duration"],
                                              "curl_returncode": canary.get("returncode")}
                if not passed:
                    checks["negative_canary"]["error"] = "owned_proxy_failure_not_confirmed"
            else:
                checks["negative_canary"] = {"status": "fail", "error": "proxy_stop_failed"}
        result["status"] = combined_status(checks)
    except StopRequested:
        result.update(status="fail", error="interrupted", interrupted=True)
    except ProbeError as exc:
        result.update(status="fail", error=str(exc))
    except Exception:
        # Do not stringify external exceptions: they may contain credentials/config.
        result.update(status="fail", error="internal_or_os_error")
    finally:
        with cleanup_guard():
            for sock in reserved:
                sock.close()
            stopped = stop_process(process)
            if workspace is not None:
                workspace.process_cleanup_ok &= stopped
                # Do NOT delete live-process config/logs if process termination failed.
                if workspace.process_cleanup_ok:
                    try:
                        result["cleanup"] = workspace.cleanup()
                    except Exception:
                        result["cleanup"] = {"process_group_stopped": True, "files_removed": False}
                else:
                    result["cleanup"] = {"process_group_stopped": False, "files_removed": False}
            else:
                result["cleanup"] = {"process_group_stopped": stopped, "files_removed": True}
            if _STOP_REQUESTED:
                result.update(status="fail", error="interrupted", interrupted=True)
            if not all(result["cleanup"].values()):
                result.update(status="fail", error="cleanup_failed")
            result["duration"] = round(time.monotonic() - started, 3)
    return result


def verify_interface(interface):
    require(re.fullmatch(r"[A-Za-z0-9_.:-]{1,15}", interface), "invalid_interface")
    try:
        socket.if_nametoindex(interface)
    except OSError:
        raise ProbeError("interface_unavailable") from None
    require((Path("/sys/class/net") / interface / "device").exists(),
            "physical_interface_required")


def main(argv=None):
    global _STOP_REQUESTED
    _STOP_REQUESTED = False
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, help="existing private0600 JSON in private0700 dir")
    parser.add_argument("--output", required=True, help="new private JSON, parent must be private0700")
    parser.add_argument("--interface", required=True, help="physical interface, e.g. wlo1")
    parser.add_argument("--negative-canary", action="store_true", help="verify only our stopped proxy fails")
    args = parser.parse_args(argv)
    output, saved_handlers = None, {}
    report = {"status": "fail", "nodes": [], "limitations": LIMITATIONS,
              "vantage": "userspace proxy over explicitly bound physical uplink"}
    try:
        output = open_output(args.output)
        data = load_manifest(args.manifest, args.interface)
        verify_interface(args.interface)
        binary = data.get("binary", "/usr/bin/sing-box")
        require(os.path.isfile(binary) and os.access(binary, os.X_OK), "sing_box_unavailable")
        curl_binary = shutil.which("curl")
        require(curl_binary is not None, "curl_unavailable")
        def interrupted(signum, frame):
            global _STOP_REQUESTED
            _STOP_REQUESTED = True
            # Ignore repeats; first signal during cleanup is deferred until cleanup finishes.
            for sig in saved_handlers:
                signal.signal(sig, signal.SIG_IGN)
            if not _CLEANUP_DEPTH:
                raise StopRequested()
        for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
            saved_handlers[sig] = signal.signal(sig, interrupted)
        parent = os.path.dirname(os.path.abspath(args.output))
        for index, node in enumerate(data["nodes"]):
            result = run_node(node, binary, curl_binary, args.interface, parent, args.negative_canary)
            report["nodes"].append(result)
            if result.get("interrupted") or not all(result["cleanup"].values()):
                for skipped in data["nodes"][index + 1:]:
                    report["nodes"].append({"name": skipped["name"], "status": "partial",
                                             "error": "not_run_after_safety_stop"})
                break
        report["status"] = combined_status({str(i): n for i, n in enumerate(report["nodes"])})
    except StopRequested:
        report.update(status="fail", error="interrupted")
    except ProbeError as exc:
        report.update(status="fail", error=str(exc))
    except Exception:
        report.update(status="fail", error="internal_or_os_error")
    finally:
        for sig in saved_handlers:
            signal.signal(sig, signal.SIG_IGN)
        # Report writes are local only. They contain fixed error codes, not raw stderr.
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
            for sig, handler in saved_handlers.items():
                signal.signal(sig, handler)
    # No paths, credentials, configs, child stdout/stderr or response bodies on terminal.
    summary = {"status": report["status"], "node_count": len(report["nodes"])}
    if report.get("error"):
        summary["error"] = report["error"]
    print(json.dumps(summary, sort_keys=True))
    return {"pass": 0, "partial": 2, "fail": 1}[report["status"]]


if __name__ == "__main__":
    raise SystemExit(main())
