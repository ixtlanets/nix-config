"""Synthetic HTTP boundary only: never resolve or contact the provider.

The adapter deliberately maps fixed canonical URLs to an ephemeral loopback
fixture. It is test code, never a launcher option or a real browser substitute.
"""
from __future__ import annotations

import contextlib
import http.client
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import importlib.util
import json
import os
from pathlib import Path
import select
import struct
import sys
import tempfile
import threading
import unittest
from urllib.parse import parse_qs, urlencode
import zlib


BUNDLE = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "owner_helper_http_test", BUNDLE / "scripts/owner_rutracker_helper.py")
HELPER = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = HELPER
SPEC.loader.exec_module(HELPER)
def png_chunk(kind: bytes, data: bytes) -> bytes:
    return (struct.pack("!I", len(data)) + kind + data
            + struct.pack("!I", zlib.crc32(kind + data) & 0xffffffff))


PNG = (b"\x89PNG\r\n\x1a\n"
       + png_chunk(b"IHDR", struct.pack("!IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
       + png_chunk(b"IDAT", zlib.compress(b"\x00\xff\xff\xff"))
       + png_chunk(b"IEND", b""))
LOGIN = ("<form method='post' action='login.php'>"
         "<input name='login_username'><input name='login_password' type='password'>"
         "<input name='cap_sid' type='hidden' value='fixture123'>"
         "<input name='cap_code_fixture123'></form>")


class FixtureServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self):
        super().__init__(("127.0.0.1", 0), FixtureHandler)
        self.events = []
        self.marker = "<span id='logged-in-username'>fixture</span>"


class FixtureHandler(BaseHTTPRequestHandler):
    def log_message(self, *_args):
        pass

    def reply(self, body, *, cookie=None, status=200):
        data = body.encode("utf-8") if isinstance(body, str) else body
        self.send_response(status)
        self.send_header("Content-Length", str(len(data)))
        if cookie:
            self.send_header("Set-Cookie", cookie)
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        self.server.events.append(("GET", self.path))
        if self.path == "/forum/login.php":
            self.reply(LOGIN)
        elif self.path == "/fixture-captcha.png":
            self.reply(PNG)
        elif self.path == "/forum/index.php":
            if self.headers.get("Cookie") == "bb_session=fixture-login":
                self.reply(self.server.marker,
                           cookie="bb_session=fixture-rotated; Path=/forum/; Secure")
            else:
                self.reply("<p>login required</p>")
        else:
            self.reply("", status=404)

    def do_POST(self):
        if self.path != "/forum/login.php":
            self.reply("", status=404)
            return
        size = int(self.headers.get("Content-Length", "0"))
        if size > 4096:
            self.reply("", status=413)
            return
        fields = parse_qs(self.rfile.read(size).decode("utf-8"))
        # Store only synthetic fixture values; never reusable against a provider.
        self.server.events.append(("POST", self.path, fields))
        expected = {"login_username": ["fixture"],
                    "login_password": ["synthetic-password"],
                    "cap_sid": ["fixture123"],
                    "cap_code_fixture123": ["synthetic-answer"]}
        if all(fields.get(key) == value for key, value in expected.items()):
            self.reply("<p>submitted</p>",
                       cookie="bb_session=fixture-login; Path=/forum/; Secure")
        else:
            self.reply("<p>denied</p>")


@contextlib.contextmanager
def fixture():
    server = FixtureServer()  # A denied bind is a setup ERROR, never behavioral RED.
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        yield server
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=2)
        if worker.is_alive():
            raise AssertionError("fixture cleanup failed")


class FixtureBrowser:
    """Typed helper Browser adapter over actual synthetic loopback HTTP."""

    def __init__(self, server: FixtureServer):
        self.port = server.server_port
        self.cookie = ""
        self.closed = False

    def request(self, method: str, path: str, fields=None) -> bytes:
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=2)
        headers = {"Cookie": self.cookie} if self.cookie else {}
        body = None
        if fields is not None:
            body = urlencode(fields)
            headers["Content-Type"] = "application/x-www-form-urlencoded"
        try:
            connection.request(method, path, body, headers)
            response = connection.getresponse()
            if response.status != 200:
                raise RuntimeError("synthetic-http-status")
            raw = response.read(128 * 1024 + 1)
            if len(raw) > 128 * 1024:
                raise RuntimeError("synthetic-http-size")
            value = response.getheader("Set-Cookie")
            if value:
                cookies = SimpleCookie()
                cookies.load(value)
                self.cookie = "bb_session=" + cookies["bb_session"].value
            return raw
        finally:
            connection.close()

    def open_login(self) -> tuple[str, str, bytes]:
        page = self.request("GET", "/forum/login.php").decode("utf-8")
        png = self.request("GET", "/fixture-captcha.png")
        return HELPER.LOGIN_URL, page, png

    def submit_login(self, fields: dict[str, str]) -> None:
        self.request("POST", "/forum/login.php", fields)

    def verify_index(self) -> tuple[str, str]:
        return HELPER.INDEX_URL, self.request("GET", "/forum/index.php").decode("utf-8")

    def cookies(self) -> list[dict]:
        return [{"name": "bb_session", "value": self.cookie.removeprefix("bb_session="),
                 "domain": "rutracker.org", "path": "/forum/", "secure": True,
                 "expiry": 4102444800}]

    def close(self) -> None:
        self.closed = True


class FixtureChannel:
    def __init__(self):
        self.messages = []
        self.login = {"kind": "login", "username": "fixture",
                      "password": "synthetic-password", "captcha": "synthetic-answer"}

    def send(self, value: dict) -> None:
        self.messages.append(value)

    def receive(self) -> dict:
        return self.login


class FramedFixtureTransport:
    """Real anonymous-pipe frames and HTTP; only browser execution is adapted."""

    def __init__(self, server: FixtureServer):
        self.browser = FixtureBrowser(server)
        self.worker = None
        self.reader = self.writer = None
        self.error = None
        self.checks = 0

    def start(self) -> None:
        read_worker, write_host = os.pipe()
        read_host, write_worker = os.pipe()
        self.reader = os.fdopen(read_host, "rb", buffering=0)
        self.writer = os.fdopen(write_host, "wb", buffering=0)

        def run():
            with os.fdopen(read_worker, "rb", buffering=0) as reader, \
                    os.fdopen(write_worker, "wb", buffering=0) as writer:
                class Channel:
                    def send(_self, value):
                        HELPER.write_frame(writer, value)

                    def receive(_self):
                        return HELPER.read_frame(reader)

                try:
                    HELPER.run(self.browser, Channel())
                except HELPER.SafeError as error:
                    self.error = error.code
                    HELPER.write_frame(writer, {"kind": "error", "code": error.code})

        self.worker = threading.Thread(target=run, daemon=True)
        self.worker.start()

    def receive(self) -> dict:
        if not select.select([self.reader], [], [], 3)[0]:
            raise RuntimeError("synthetic-frame-timeout")
        return HELPER.read_frame(self.reader)

    def send(self, value: dict) -> None:
        HELPER.write_frame(self.writer, value)

    def recheck(self) -> None:
        self.checks += 1

    def finish(self) -> None:
        self.worker.join(timeout=3)
        if self.worker.is_alive() or self.error or self.reader.read(1) != b"":
            raise RuntimeError("synthetic-helper-incomplete")
        self.reader.close()
        self.writer.close()

    def abort(self) -> None:
        if self.writer is not None:
            self.writer.close()
        if self.worker is not None:
            self.worker.join(timeout=3)
            if self.worker.is_alive():
                raise RuntimeError("synthetic-helper-cleanup")
        if self.reader is not None:
            self.reader.close()


class FixtureTerminal:
    def __init__(self):
        self.answers = iter(("synthetic-answer", "fixture", "synthetic-password"))
        self.image_seen = False

    def confirm_private_image(self, path: str) -> bool:
        self.image_seen = Path(path).read_bytes() == PNG
        return self.image_seen

    def read_secret(self, _prompt: str) -> str:
        return next(self.answers)


class SyntheticHTTPTests(unittest.TestCase):
    def test_framed_http_refresh_stages_image_and_atomically_publishes_rotation(self):
        host_spec = importlib.util.spec_from_file_location(
            "owner_host_http_test", BUNDLE / "scripts/owner_rutracker_refresh.py")
        host = importlib.util.module_from_spec(host_spec)
        sys.modules[host_spec.name] = host
        host_spec.loader.exec_module(host)
        with fixture() as server, tempfile.TemporaryDirectory(
                dir=os.environ["TMPDIR"]) as scratch:
            image_dir, secret_dir = Path(scratch) / "images", Path(scratch) / "secrets"
            image_dir.mkdir(mode=0o710)
            secret_dir.mkdir(mode=0o750)
            image_dir.chmod(0o710)
            secret_dir.chmod(0o750)
            secret = secret_dir / "gateway-session-cookie"
            secret.write_text('{"bb_session":"fixture-previous"}')
            secret.chmod(0o640)
            images = host.Directory(str(image_dir), os.getuid(), 0o710, anchor=scratch)
            secrets_dir = host.Directory(str(secret_dir), os.getuid(), 0o750, anchor=scratch)
            transport, terminal = FramedFixtureTransport(server), FixtureTerminal()
            try:
                host.refresh(terminal, transport,
                             host.Stage(images, os.getuid(), os.getgid()),
                             host.Publisher(secrets_dir, os.getgid()))
                self.assertTrue(terminal.image_seen)
                self.assertTrue(transport.browser.closed)
                self.assertEqual(transport.checks, 3)
                self.assertEqual(json.loads(secret.read_text()),
                                 {"bb_session": "fixture-rotated"})
                self.assertEqual(secret.stat().st_mode & 0o777, 0o640)
                backups = list(secret_dir.glob(".gateway-session-cookie.rollback-*"))
                self.assertEqual(len(backups), 1)
                self.assertEqual(json.loads(backups[0].read_text()),
                                 {"bb_session": "fixture-previous"})
                self.assertEqual(backups[0].stat().st_mode & 0o777, 0o600)
                self.assertEqual(list(image_dir.iterdir()), [])
            finally:
                transport.abort()
                images.close()
                secrets_dir.close()

    def test_retained_http_state_verifies_then_persists_rotation(self):
        with fixture() as server:
            browser, channel = FixtureBrowser(server), FixtureChannel()
            HELPER.run(browser, channel)
            self.assertTrue(browser.closed)
            self.assertEqual(channel.messages[-1], {
                "kind": "verified", "cookies": {"bb_session": "fixture-rotated"}})
            self.assertEqual([event[:2] for event in server.events], [
                ("GET", "/forum/login.php"), ("GET", "/fixture-captcha.png"),
                ("POST", "/forum/login.php"), ("GET", "/forum/index.php")])

    def test_wrong_captcha_or_password_never_produces_verified_cookie(self):
        for field in ("captcha", "password"):
            with self.subTest(field=field), fixture() as server:
                browser, channel = FixtureBrowser(server), FixtureChannel()
                channel.login[field] = "synthetic-wrong"
                with self.assertRaises(HELPER.SafeError) as caught:
                    HELPER.run(browser, channel)
                self.assertEqual(caught.exception.code, "authentication")
                self.assertTrue(browser.closed)
                self.assertFalse(any(frame["kind"] == "verified" for frame in channel.messages))

    def test_http_marker_in_inert_document_never_proves_authentication(self):
        for marker in ("", "<!-- <span id='logged-in-username'>fixture</span> -->",
                       "<script><span id='logged-in-username'>fixture</span></script>",
                       "<template><span id='logged-in-username'>fixture</span></template>"):
            with self.subTest(marker=marker), fixture() as server:
                server.marker = marker
                browser, channel = FixtureBrowser(server), FixtureChannel()
                with self.assertRaises(HELPER.SafeError) as caught:
                    HELPER.run(browser, channel)
                self.assertEqual(caught.exception.code, "authentication")
                self.assertTrue(browser.closed)
                self.assertFalse(any(frame["kind"] == "verified" for frame in channel.messages))


if __name__ == "__main__":
    unittest.main()
