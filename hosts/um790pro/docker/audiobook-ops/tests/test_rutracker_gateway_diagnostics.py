"""Authentication diagnostics through the real, socket-free HTTP handler."""

import json
import unittest
import urllib.error
from unittest.mock import patch

import test_rutracker_gateway_memory as memory


class GatewayDiagnosticsTest(unittest.TestCase):
    setUp = memory.GatewayMemoryTest.setUp
    upstream = memory.GatewayMemoryTest.upstream
    exchange = memory.GatewayMemoryTest.exchange

    def assert_diagnostic(self, *, status="2xx", target="true", marker="false", category="unverified"):
        logged = self.logs.getvalue()
        self.assertEqual(logged, (
            "rutracker-gateway auth verification failed: "
            f"status_class={status} final_target_match={target} "
            f"login_marker={marker} category={category}\n"
        ))
        self.assertLessEqual(len(logged), 200)
        self.assertEqual(len(logged.splitlines()), 1)
        self.assertNotIn("SENTINEL", logged)

    def assert_failure(self, response, message="RuTracker authentication unverified"):
        self.assertEqual(response.status, 502)
        self.assertEqual(json.loads(self.body), {"error": message})
        self.assertIsNone(response.headers.get_all("Set-Cookie"))
        self.assertEqual(self.config.session_cookies, memory.SESSION_COOKIES)

    def test_absent_canonical_marker_logs_only_safe_observations(self):
        self.config.session_cookies = dict(memory.SESSION_COOKIES)
        self.config.session_cookies["OPERATOR_NAME_SENTINEL"] = "OPERATOR_VALUE_SENTINEL"
        before = dict(self.config.session_cookies)
        self.solution["response"] = "<html>UPSTREAM_BODY_SENTINEL\n</html>"
        self.solution["cookies"] = [{"name": "RETURNED_NAME_SENTINEL", "value": "RETURNED_VALUE_SENTINEL"}]
        with patch.object(self.module.os, "environ", {"PROWLARR_GATEWAY_BASIC": "OPERATOR_AUTH_SENTINEL"}):
            response = self.exchange(
                target="/forum/login.php?QUERY_SENTINEL",
                headers={"Cookie": "CLIENT_NAME_SENTINEL=CLIENT_VALUE_SENTINEL"},
            )
        self.assertEqual(response.status, 502)
        self.assertEqual(json.loads(self.body), {"error": "RuTracker authentication unverified"})
        self.assertIsNone(response.headers.get_all("Set-Cookie"))
        self.assertEqual(self.config.session_cookies, before)
        self.assert_diagnostic()

    def test_status_classes_require_strict_observed_http_integers(self):
        for status, expected in (
            (100, "1xx"), (199, "1xx"), (300, "3xx"), (399, "3xx"),
            (400, "4xx"), (499, "4xx"), (500, "5xx"), (599, "5xx"),
            (True, "unknown"), (False, "unknown"), ("200", "unknown"),
            (None, "unknown"), (200.0, "unknown"), ([], "unknown"),
            ({"STATUS_SENTINEL": "x"}, "unknown"), (99, "unknown"),
            (600, "unknown"), (-200, "unknown"),
        ):
            with self.subTest(status=status):
                self.logs.seek(0)
                self.logs.truncate()
                self.solution["status"] = status
                self.assert_failure(self.exchange())
                self.assert_diagnostic(status=expected, marker="not_observed")
        self.logs.seek(0)
        self.logs.truncate()
        self.solution.pop("status")
        self.assert_failure(self.exchange())
        self.assert_diagnostic(status="not_observed", marker="not_observed")

    def test_transport_failures_use_fixed_categories_without_exception_data(self):
        hostile = type("HOSTILE_CLASS_SENTINEL\nforged-log", (Exception,), {})
        for error, category, public in (
            (urllib.error.HTTPError("https://URL_SENTINEL", 403, "MESSAGE_SENTINEL", {}, None), "http_error", "FlareSolverr unavailable"),
            (urllib.error.URLError("REASON_SENTINEL"), "url_error", "FlareSolverr unavailable"),
            (TimeoutError("TIMEOUT_SENTINEL"), "timeout", "FlareSolverr unavailable"),
            (hostile("EXCEPTION_SENTINEL\nAuthorization: VALUE_SENTINEL"), "exception", "upstream request failed"),
        ):
            with self.subTest(category=category):
                if isinstance(error, urllib.error.HTTPError):
                    self.addCleanup(error.close)
                self.logs.seek(0)
                self.logs.truncate()
                self.upstream_error = error
                self.assert_failure(self.exchange(), public)
                self.assert_diagnostic(status="not_observed", target="unknown", marker="not_observed", category=category)

    def test_invalid_html_shape_retains_safe_fields_without_claiming_marker_absence(self):
        for response in (None, [], {"BODY_SENTINEL": "x"}, 123):
            with self.subTest(response=response):
                self.logs.seek(0)
                self.logs.truncate()
                self.solution.update(status=403, response=response)
                self.assert_failure(self.exchange(), "invalid FlareSolverr solution")
                self.assert_diagnostic(status="4xx", marker="not_observed", category="invalid_solution")

    def test_canonical_parser_evidence_does_not_credit_spoofed_markers(self):
        for html in (
            '<!-- <span id="logged-in-username">BODY_SENTINEL -->',
            '<script><span id="logged-in-username">BODY_SENTINEL</script>',
            '<template><span id="logged-in-username">BODY_SENTINEL</template>',
            '<span id="other" id="logged-in-username">BODY_SENTINEL</span>',
            '&lt;span id="logged-in-username"&gt;BODY_SENTINEL',
        ):
            with self.subTest(html=html):
                self.logs.seek(0)
                self.logs.truncate()
                self.solution["response"] = html
                self.assert_failure(self.exchange())
                self.assert_diagnostic()

    def test_success_and_pass_through_remain_quiet(self):
        for status in (200, 204, 299):
            self.solution["status"] = status
            self.assertEqual(self.exchange().status, 200)
            self.assertEqual(self.logs.getvalue(), "")
        self.config.session_cookies = {}
        self.assertEqual(self.exchange().status, 200)
        payload = json.loads(self.calls[-1][0].data)
        self.assertEqual(payload["cmd"], "request.post")
        self.assertEqual(payload["postData"], "login_username=USER_SENTINEL&login_password=PASSWORD_SENTINEL")
        self.assertEqual(self.logs.getvalue(), "")
        self.serialized = b'not JSON BODY_SENTINEL'
        self.assertEqual(self.exchange().status, 502)
        self.assertEqual(json.loads(self.body), {"error": "invalid FlareSolverr response"})
        self.assertEqual(self.logs.getvalue(), "")

    def test_existing_generic_fallback_does_not_disclose_dynamic_exception_name(self):
        self.config.session_cookies = {}
        self.upstream_error = type("HOSTILE_CLASS_SENTINEL\nforged-log", (Exception,), {})("TEXT_SENTINEL")
        response = self.exchange()
        self.assertEqual(response.status, 502)
        self.assertEqual(json.loads(self.body), {"error": "upstream request failed"})
        self.assertIsNone(response.headers.get_all("Set-Cookie"))
        self.assertEqual(self.config.session_cookies, {})
        # Preserve the existing fallback log, with a fixed category; no auth log.
        self.assertEqual(self.logs.getvalue(), "rutracker-gateway upstream failure: exception\n")

    def test_request_validation_failures_do_not_log_upstream_auth_failure(self):
        for kwargs, status in (
            ({"headers": {"Content-Type": "text/plain"}}, 415),
            ({"headers": {"Transfer-Encoding": "chunked"}}, 400),
            ({"body": b"x" * 129}, 413),
            ({"target": "https://TARGET_SENTINEL.invalid/forum/login.php"}, 400),
            ({"target": "/forum/tracker.php?QUERY_SENTINEL"}, 405),
        ):
            with self.subTest(kwargs=kwargs):
                self.assertEqual(self.exchange(**kwargs).status, status)
                self.assertEqual(self.logs.getvalue(), "")
                self.assertEqual(self.calls, [])

    def test_sequential_requests_do_not_reuse_prior_observations(self):
        self.solution["response"] = "<html>BODY_SENTINEL</html>"
        self.assert_failure(self.exchange())
        self.assert_diagnostic()
        self.logs.seek(0)
        self.logs.truncate()
        self.upstream_error = TimeoutError("TIMEOUT_SENTINEL")
        self.assert_failure(self.exchange(), "FlareSolverr unavailable")
        self.assert_diagnostic(status="not_observed", target="unknown", marker="not_observed", category="timeout")
        self.logs.seek(0)
        self.logs.truncate()
        self.upstream_error = None
        self.solution["response"] = '<SPAN ID="logged-in-username">session</SPAN>'
        self.assertEqual(self.exchange().status, 200)
        self.assertEqual(self.logs.getvalue(), "")

    def test_same_keepalive_handler_does_not_reuse_success_observations_on_timeout(self):
        original_upstream = self.upstream

        def sequential_upstream(request, timeout):
            if self.calls:
                raise TimeoutError("TIMEOUT_SENTINEL")
            return original_upstream(request, timeout)

        self.upstream = sequential_upstream
        response = self.exchange(
            headers={"Connection": "keep-alive"},
            following=(
                b"POST /forum/login.php HTTP/1.1\r\nHost: gateway.invalid\r\n"
                b"Connection: close\r\nContent-Type: application/x-www-form-urlencoded\r\n"
                b"Content-Length: 22\r\n\r\npassword=FORM_SENTINEL"
            ),
        )
        self.assertEqual(response.status, 200)
        self.assertEqual(self.wire.count(b"HTTP/1.1 200 OK"), 1)
        self.assertEqual(self.wire.count(b"HTTP/1.1 502 Bad Gateway"), 1)
        self.assertTrue(self.wire.endswith(b'{"error":"FlareSolverr unavailable"}'))
        self.assert_diagnostic(status="not_observed", target="unknown", marker="not_observed", category="timeout")

    def test_rejected_solution_targets_retain_observations_without_relaxing_validation(self):
        for url, target, category, public in (
            ("https://rutracker.org/forum/index.php?QUERY_SENTINEL", "false", "unverified", "RuTracker authentication unverified"),
            ("https://rutracker.org/forum/login.php#FRAGMENT_SENTINEL", "false", "unverified", "RuTracker authentication unverified"),
            ("https://FOREIGN_SENTINEL.invalid/forum/index.php", "false", "unexpected_target", "unexpected FlareSolverr target"),
            ("http://rutracker.org/forum/index.php", "false", "unexpected_target", "unexpected FlareSolverr target"),
            ("https://USER_SENTINEL:PASS_SENTINEL@rutracker.org/forum/index.php", "false", "unexpected_target", "unexpected FlareSolverr target"),
            ("https://rutracker.org:444/forum/index.php", "false", "unexpected_target", "unexpected FlareSolverr target"),
            ("https://rutracker.org:PORT_SENTINEL/forum/index.php", "false", "exception", "upstream request failed"),
            ("https://[URL_SENTINEL", "false", "exception", "upstream request failed"),
            (None, "unknown", "unexpected_target", "unexpected FlareSolverr target"),
            ([], "unknown", "unexpected_target", "unexpected FlareSolverr target"),
            ({"URL_SENTINEL": "x"}, "unknown", "unexpected_target", "unexpected FlareSolverr target"),
        ):
            with self.subTest(url=url):
                self.logs.seek(0)
                self.logs.truncate()
                self.solution["url"] = url
                self.assert_failure(self.exchange(), public)
                self.assert_diagnostic(target=target, marker="not_observed", category=category)

    def test_unusable_upstream_envelopes_log_only_fixed_failure_categories(self):
        for serialized, category, public in (
            (b"not JSON BODY_SENTINEL\n", "invalid_json", "invalid FlareSolverr response"),
            (b"\xff", "invalid_json", "invalid FlareSolverr response"),
            (b"x" * 4097, "oversized_response", "FlareSolverr response too large"),
            (b'[]', "flaresolverr_failure", "FlareSolverr failed"),
            (b'{"status":"error","message":"MESSAGE_SENTINEL"}', "flaresolverr_failure", "FlareSolverr failed"),
            (b'{"status":"ok","solution":null}', "invalid_solution", "invalid FlareSolverr solution"),
            (b'{"status":"ok","solution":[]}', "invalid_solution", "invalid FlareSolverr solution"),
        ):
            with self.subTest(category=category, serialized=serialized[:30]):
                self.logs.seek(0)
                self.logs.truncate()
                self.serialized = serialized
                self.assert_failure(self.exchange(), public)
                self.assert_diagnostic(status="not_observed", target="unknown", marker="not_observed", category=category)


if __name__ == "__main__":
    unittest.main()
