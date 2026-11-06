"""Socket-free HTTP parsing evidence; real loopback coverage lives alongside it."""

import contextlib
import http.client
import io
import json
import tempfile
import unittest
import urllib.error
from types import SimpleNamespace
from unittest.mock import patch

from test_rutracker_gateway import SESSION_COOKIES, load_gateway_module


class MemoryConnection:
    def __init__(self, request):
        self.input = io.BytesIO(request)
        self.output = io.BytesIO()

    def makefile(self, *args):
        return self.input

    def sendall(self, data):
        self.output.write(data)


class GatewayMemoryTest(unittest.TestCase):
    def setUp(self):
        self.module = load_gateway_module()
        self.config = self.module.GatewayConfig(
            flaresolverr_url="http://synthetic.invalid/v1",
            listen_host="127.0.0.1", listen_port=0,
            max_body_bytes=128, max_upstream_response_bytes=4096,
            max_timeout_ms=120000, timeout_seconds=5,
        )
        self.config.session_cookies = dict(SESSION_COOKIES)
        self.solution = {
            "url": "https://rutracker.org/forum/index.php", "status": 200,
            "response": '<html><span id="logged-in-username">тест</span></html>',
            "cookies": [],
        }
        self.calls = []
        self.logs = io.StringIO()
        self.serialized = None
        self.upstream_error = None

    def upstream(self, request, timeout):
        self.calls.append((request, timeout))
        if self.upstream_error:
            raise self.upstream_error
        serialized = self.serialized
        if serialized is None:
            serialized = json.dumps({"status": "ok", "solution": self.solution}).encode()
        return io.BytesIO(serialized)

    def exchange(self, *, method="POST", target="/forum/login.php", body=None, headers=None, following=b""):
        if body is None:
            body = b"login_username=USER_SENTINEL&login_password=PASSWORD_SENTINEL"
        fields = {
            "Host": "gateway.invalid", "Connection": "close",
            "Content-Type": "application/x-www-form-urlencoded",
            "Content-Length": str(len(body)),
            "Cookie": "bb_session=client-value; extra=client-extra",
            "Authorization": "Basic CLIENT_BASIC_SENTINEL",
            "X-Api-Key": "API_KEY_SENTINEL",
        }
        fields.update(headers or {})
        raw = f"{method} {target} HTTP/1.1\r\n".encode()
        raw += "".join(f"{name}: {value}\r\n" for name, value in fields.items()).encode()
        connection = MemoryConnection(raw + b"\r\n" + body + following)
        with patch.object(self.module.urllib.request, "urlopen", self.upstream), contextlib.redirect_stderr(self.logs):
            self.module.RuTrackerGatewayHandler(connection, ("127.0.0.1", 1), SimpleNamespace(config=self.config))
        self.wire = connection.output.getvalue()
        response = http.client.HTTPResponse(MemoryConnection(self.wire))
        response.begin()
        self.body = response.read()
        return response

    def test_verified_login_uses_fixed_get_without_credentials(self):
        response = self.exchange(target="/forum/login.php?SECRET_QUERY_SENTINEL")
        self.assertEqual(response.status, 200)
        self.assertEqual(response.headers["Cache-Control"], "no-store")
        self.assertEqual(response.headers["Content-Type"], "text/html; charset=windows-1251")
        self.assertIn(b'id="logged-in-username"', self.body)
        self.assertEqual(len(self.calls), 1)
        request, timeout = self.calls[0]
        self.assertEqual(timeout, 5)
        self.assertEqual(json.loads(request.data), {
            "cmd": "request.get", "url": "https://rutracker.org/forum/index.php",
            "maxTimeout": 120000,
            "cookies": [
                {"name": "bb_session", "value": "operator-session-value"},
                {"name": "extra", "value": "client-extra"},
                {"name": "cf_clearance", "value": "operator-clearance-value"},
                {"name": "bb_guid", "value": "operator-guid-value"},
            ],
        })
        sent = repr((request.data, request.header_items()))
        for secret in ("USER_SENTINEL", "PASSWORD_SENTINEL", "CLIENT_BASIC_SENTINEL", "API_KEY_SENTINEL", "SECRET_QUERY_SENTINEL"):
            self.assertNotIn(secret, sent + self.logs.getvalue() + self.body.decode())
        self.assertEqual(len(response.headers.get_all("Set-Cookie")), 3)

    def test_login_requires_canonical_actual_element(self):
        self.config.logged_in_marker = 'id="arbitrary-configured-marker"'
        for html in (
            "<html>guest UPSTREAM_BODY_SENTINEL</html>",
            '<!-- <span id="logged-in-username"> -->',
            '<script>const x = \'<span id="logged-in-username">\';</script>',
            '&lt;span id="logged-in-username"&gt;',
            '<textarea><span id="logged-in-username"></textarea>',
            '<template><span id="logged-in-username"></template>',
            '<script id="logged-in-username"></script>',
            '<script/><span id="logged-in-username">script text',
            '<plaintext></plaintext><span id="logged-in-username">text',
            '<select><option><span id="logged-in-username">option text</select>',
            '<span id="arbitrary-configured-marker">session</span>',
        ):
            with self.subTest(html=html):
                self.solution["response"] = html
                response = self.exchange()
                self.assertEqual(response.status, 502)
                self.assertEqual(json.loads(self.body), {"error": "RuTracker authentication unverified"})
                self.assertIsNone(response.headers.get_all("Set-Cookie"))
                self.assertNotIn("UPSTREAM_BODY_SENTINEL", self.logs.getvalue())
        self.solution["response"] = "<SPAN ID='logged-in-username'>тест</SPAN>"
        self.assertEqual(self.exchange().status, 200)
        self.assertIn(b'id="logged-in-username"', self.body)
        self.assertNotIn(b'arbitrary-configured-marker', self.body)

    def test_login_requires_success_status(self):
        for status in (None, True, "200", 0, 199, 300, 302, 401, 403, 500):
            with self.subTest(status=status):
                self.solution["status"] = status
                self.assertEqual(self.exchange().status, 502)
                self.assertNotIn(b'logged-in-username', self.body)
        self.solution.pop("status")
        self.assertEqual(self.exchange().status, 502)

    def test_login_requires_safe_final_page(self):
        for url in (
            "https://rutracker.org/forum/login.php",
            "https://rutracker.org/forum/tracker.php",
            "https://rutracker.org/forum/index.php?secret=URL_SENTINEL",
            "https://rutracker.org/forum/index.php#fragment",
            "https://example.invalid/forum/index.php",
            "http://rutracker.org/forum/index.php",
            "https://user:pass@rutracker.org/forum/index.php",
            "https://rutracker.org:444/forum/index.php", None, [],
        ):
            with self.subTest(url=url):
                self.solution["url"] = url
                response = self.exchange()
                self.assertEqual(response.status, 502)
                self.assertIsNone(response.headers.get_all("Set-Cookie"))
                self.assertNotIn(b'logged-in-username', self.body)
                self.assertNotIn("URL_SENTINEL", self.logs.getvalue())

    def test_verified_rotation_is_replayed_and_used_for_following_get(self):
        self.solution["cookies"] = [
            {"name": "bb_session", "value": "rotated", "domain": ".rutracker.org", "path": "/forum/"},
            {"name": "new_cookie", "value": "new-value"},
            {"name": "foreign", "value": "FOREIGN_SENTINEL", "domain": "other.invalid"},
            {"name": "narrow", "value": "NARROW_SENTINEL", "path": "/elsewhere"},
            {"name": "bad\r\nname", "value": "bad"},
            *[{"name": "unsafe", "value": value} for value in ("a\r\nb", "a;b", "a\x00b", "a\x1fb", "a\x7fb", "ю", 'a"b', "a\\b", "a,b", "a b")],
        ]
        response = self.exchange()
        self.assertEqual(response.status, 200)
        self.assertEqual(response.headers.get_all("Set-Cookie"), [
            "bb_session=rotated; Path=/; HttpOnly; SameSite=Lax",
            "cf_clearance=operator-clearance-value; Path=/; HttpOnly; SameSite=Lax",
            "bb_guid=operator-guid-value; Path=/; HttpOnly; SameSite=Lax",
            "new_cookie=new-value; Path=/; HttpOnly; SameSite=Lax",
        ])
        self.solution["cookies"] = []
        self.exchange(method="GET", target="/forum/tracker.php?nm=QUERY_SENTINEL", body=b"")
        cookies = {c["name"]: c["value"] for c in json.loads(self.calls[-1][0].data)["cookies"]}
        self.assertEqual(cookies["bb_session"], "rotated")
        self.assertEqual(cookies["new_cookie"], "new-value")

    def test_get_cookie_replay_rejects_unsafe_or_foreign_values(self):
        self.solution["cookies"] = [
            {"name": "valid", "value": "safe"},
            {"name": "unsafe", "value": "a\x00b"},
            {"name": "foreign", "value": "bad", "domain": "other.invalid"},
        ]
        response = self.exchange(method="GET", body=b"")
        self.assertEqual(response.headers.get_all("Set-Cookie"), [
            "valid=safe; Path=/; HttpOnly; SameSite=Lax",
        ])

    def test_rejected_form_closes_without_parsing_credentials_as_next_request(self):
        response = self.exchange(headers={"Content-Type": "text/plain", "Connection": "keep-alive"})
        self.assertEqual(response.status, 415)
        self.assertEqual(self.calls, [])
        self.assertNotIn(b"PASSWORD_SENTINEL", self.wire)
        self.assertEqual(self.wire.count(b"HTTP/1.1"), 1)

    def test_operator_cookie_file_rejects_unsafe_header_values(self):
        cookies = {"good": "safe-session", "bad\r\nname": "bad"}
        cookies.update({f"bad{index}": value for index, value in enumerate(
            ("a\x00b", "a\x1fb", "a\x7fb", "ю", 'a"b', "a\\b", "a,b", "a b", "a;b", "a\r\nb")
        )})
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8") as fixture:
            json.dump(cookies, fixture)
            fixture.flush()
            self.config = self.module.GatewayConfig(
                flaresolverr_url="http://synthetic.invalid/v1", listen_host="127.0.0.1",
                listen_port=0, max_body_bytes=128, max_upstream_response_bytes=4096,
                max_timeout_ms=120000, timeout_seconds=5, session_cookies_file=fixture.name,
            )
        self.assertEqual(self.config.session_cookies, {"good": "safe-session"})
        self.assertEqual(self.exchange().status, 200)
        self.assertEqual(json.loads(self.calls[0][0].data)["cookies"], [
            {"name": "bb_session", "value": "client-value"},
            {"name": "extra", "value": "client-extra"},
            {"name": "good", "value": "safe-session"},
        ])

    def test_upstream_failures_are_bounded_without_auth_or_cookie_changes(self):
        for serialized in (
            b"not JSON UPSTREAM_BODY_SENTINEL", b"\xff", b"[]",
            b'{"status":"error","message":"UPSTREAM_BODY_SENTINEL"}',
            b'{"status":"ok","solution":null}',
            b'{"status":"ok","solution":{"response":[]}}',
            b"x" * 4097,
        ):
            with self.subTest(serialized=serialized[:60]):
                self.serialized = serialized
                response = self.exchange()
                self.assertEqual(response.status, 502)
                self.assertIsNone(response.headers.get_all("Set-Cookie"))
                self.assertEqual(self.config.session_cookies, SESSION_COOKIES)
                self.assertLess(len(self.body), 100)
                self.assertNotIn(b"UPSTREAM_BODY_SENTINEL", self.body)
        self.serialized = None
        for error in (TimeoutError("EXCEPTION_SENTINEL"), urllib.error.URLError("EXCEPTION_SENTINEL"), RuntimeError("EXCEPTION_SENTINEL")):
            with self.subTest(error=type(error).__name__):
                self.upstream_error = error
                response = self.exchange()
                self.assertEqual(response.status, 502)
                self.assertIsNone(response.headers.get_all("Set-Cookie"))
                self.assertNotIn(b"EXCEPTION_SENTINEL", self.body)
        self.assertNotIn("SENTINEL", self.logs.getvalue())

    def test_form_validation_precedes_upstream_request(self):
        for headers, body, expected in (
            ({"Transfer-Encoding": "chunked"}, b"password=FORM_SENTINEL", 400),
            ({"Content-Length": "no"}, b"password=FORM_SENTINEL", 400),
            ({"Content-Length": "-1"}, b"password=FORM_SENTINEL", 400),
            ({}, b"x" * 129, 413),
            ({"Content-Length": "128"}, b"password=FORM_SENTINEL", 400),
            ({}, b"\xffFORM_SENTINEL", 400),
        ):
            with self.subTest(headers=headers, expected=expected):
                self.assertEqual(self.exchange(headers=headers, body=body).status, expected)
                self.assertEqual(self.calls, [])
                self.assertNotIn(b"FORM_SENTINEL", self.wire)

    def test_without_operator_session_login_remains_pass_through(self):
        self.config.session_cookies = {}
        response = self.exchange()
        self.assertEqual(response.status, 200)
        payload = json.loads(self.calls[0][0].data)
        self.assertEqual(payload["cmd"], "request.post")
        self.assertEqual(payload["url"], "https://rutracker.org/forum/login.php")
        self.assertEqual(payload["postData"], "login_username=USER_SENTINEL&login_password=PASSWORD_SENTINEL")
        self.assertIn("тест", self.body.decode("windows-1251"))
        self.assertEqual(self.logs.getvalue(), "")

    def test_valid_login_drains_form_before_keepalive_request(self):
        response = self.exchange(
            headers={"Connection": "keep-alive"},
            following=b"GET /health HTTP/1.1\r\nHost: gateway.invalid\r\nConnection: close\r\n\r\n",
        )
        self.assertEqual(response.status, 200)
        self.assertEqual(self.wire.count(b"HTTP/1.1 200 OK"), 2)
        self.assertTrue(self.wire.endswith(b'{"status":"ok"}'))
        self.assertNotIn(b"PASSWORD_SENTINEL", self.wire)
        self.assertEqual(len(self.calls), 1)
