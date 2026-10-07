#!/usr/bin/env python3

"""Internal RuTracker-to-FlareSolverr compatibility gateway.

Prowlarr's FlareSolverr integration replays solved requests with its own HTTP
client. Modern Cloudflare clearance can be bound to the browser fingerprint,
so the replay is rejected. This gateway returns FlareSolverr's browser response
directly and deliberately supports only the RuTracker endpoints Prowlarr needs.

RuTracker now challenges the login form with an image captcha, which Prowlarr
cannot solve. The operator performs one interactive login through the same
egress path and stores the resulting session cookies as a root-only secret.
This gateway injects those cookies into every upstream request and answers the
login POST with a minimal "already authenticated" page so Prowlarr can take
over the session without ever solving a captcha. When no session is available
the previous pass-through behaviour is preserved.
"""

from __future__ import annotations

import base64
import json
import os
import re
import sys
import urllib.error
import urllib.request
from http.cookies import CookieError, SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import urlsplit, urlunsplit

TARGET_ORIGIN = "https://rutracker.org"
COOKIE_NAME = re.compile(r"[A-Za-z0-9_!#$%&'*+.^`|~-]+")
DEFAULT_LOGGED_IN_MARKER = 'id="logged-in-username"'

class GatewayConfig:
    def __init__(
        self,
        *,
        flaresolverr_url: str,
        listen_host: str,
        listen_port: int,
        max_body_bytes: int,
        max_upstream_response_bytes: int,
        max_timeout_ms: int,
        timeout_seconds: int,
        session_cookies_file: str = "",
        logged_in_marker: str = DEFAULT_LOGGED_IN_MARKER,
    ) -> None:
        flare_url = urlsplit(flaresolverr_url)
        if (
            flare_url.scheme not in {"http", "https"}
            or not flare_url.hostname
            or flare_url.username
            or flare_url.password
            or flare_url.fragment
        ):
            raise ValueError("invalid FlareSolverr URL")
        if not 0 <= listen_port <= 65535:
            raise ValueError("listen_port is out of range")
        for name, value in (
            ("max_body_bytes", max_body_bytes),
            ("max_upstream_response_bytes", max_upstream_response_bytes),
            ("max_timeout_ms", max_timeout_ms),
            ("timeout_seconds", timeout_seconds),
        ):
            if value < 1:
                raise ValueError(f"{name} must be positive")
        if not logged_in_marker:
            raise ValueError("logged_in_marker must not be empty")

        self.flaresolverr_url = flaresolverr_url
        self.listen_host = listen_host
        self.listen_port = listen_port
        self.max_body_bytes = max_body_bytes
        self.max_upstream_response_bytes = max_upstream_response_bytes
        self.max_timeout_ms = max_timeout_ms
        self.timeout_seconds = timeout_seconds
        self.session_cookies_file = session_cookies_file
        self.logged_in_marker = logged_in_marker
        self.session_cookies = self._load_session_cookies()

    def _load_session_cookies(self) -> dict[str, str]:
        """Load the operator-provided RuTracker session cookies.

        The file is a flat JSON object of cookie name to value. Absence or a
        malformed file degrades to an empty session, which keeps the gateway in
        its historical pass-through mode instead of failing to start.
        """

        if not self.session_cookies_file:
            return {}
        try:
            with open(self.session_cookies_file, encoding="utf-8") as handle:
                raw = json.load(handle)
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            return {}
        if not isinstance(raw, dict):
            return {}
        cookies: dict[str, str] = {}
        for name, value in raw.items():
            if (
                isinstance(name, str)
                and isinstance(value, str)
                and COOKIE_NAME.fullmatch(name)
                and not any(character in value for character in "\r\n;")
            ):
                cookies[name] = value
        return cookies

    def session_payload_cookies(self) -> list[dict[str, str]]:
        return [{"name": name, "value": value} for name, value in self.session_cookies.items()]

class GatewayRequestError(Exception):
    def __init__(self, status: int, public_message: str) -> None:
        super().__init__(public_message)
        self.status = status
        self.public_message = public_message

class GatewayHTTPServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address: tuple[str, int], config: GatewayConfig) -> None:
        super().__init__(address, RuTrackerGatewayHandler)
        self.config = config

class RuTrackerGatewayHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "AudiobookOps-RuTracker-Gateway"
    sys_version = ""

    @property
    def config(self) -> GatewayConfig:
        return self.server.config  # type: ignore[attr-defined,no-any-return]

    def do_GET(self) -> None:
        if self.path == "/health":
            self._send_json(200, {"status": "ok"})
            return
        self._handle_upstream("GET")

    def do_POST(self) -> None:
        self._handle_upstream("POST")

    def do_HEAD(self) -> None:
        self._send_json(405, {"error": "method not allowed"}, include_body=False)

    def do_CONNECT(self) -> None:
        self._send_json(405, {"error": "method not allowed"})

    def log_message(self, _format: str, *_args: object) -> None:
        # BaseHTTPRequestHandler logs full request targets. Search terms and POST
        # failures do not belong in production logs.
        return

    def _handle_upstream(self, method: str) -> None:
        try:
            target_url, target_path = self._target_url()
            if method == "POST" and target_path != "/forum/login.php":
                raise GatewayRequestError(405, "method not allowed")

            if method == "POST" and self.config.session_cookies:
                # Drain and validate the form body so HTTP keep-alive stays
                # usable; the credentials themselves are deliberately ignored.
                self._read_form_body()
                self._send_session_login()
                return

            cookies = self._merged_cookies()
            flare_payload: dict[str, Any] = {
                "cmd": "request.get" if method == "GET" else "request.post",
                "url": target_url,
                "maxTimeout": self.config.max_timeout_ms,
            }
            if cookies:
                flare_payload["cookies"] = cookies
            if method == "POST":
                flare_payload["postData"] = self._read_form_body()

            solution = self._call_flaresolverr(flare_payload)
            self._send_solution(solution)
        except GatewayRequestError as error:
            self._send_json(error.status, {"error": error.public_message})
        except Exception as error:  # fail closed without request or credential data
            print(
                f"rutracker-gateway upstream failure: {type(error).__name__}",
                file=sys.stderr,
                flush=True,
            )
            self._send_json(502, {"error": "upstream request failed"})

    def _target_url(self) -> tuple[str, str]:
        parsed = urlsplit(self.path)
        if parsed.scheme or parsed.netloc or parsed.fragment or self.path.startswith("//"):
            raise GatewayRequestError(400, "invalid request target")
        if parsed.path != "/" and not parsed.path.startswith("/forum/"):
            raise GatewayRequestError(404, "path not allowed")
        relative = urlunsplit(("", "", parsed.path, parsed.query, ""))
        return TARGET_ORIGIN + relative, parsed.path

    def _request_cookies(self) -> list[dict[str, str]]:
        header = self.headers.get("Cookie")
        if not header:
            return []
        parsed = SimpleCookie()
        try:
            parsed.load(header)
        except CookieError as error:
            raise GatewayRequestError(400, "invalid cookie header") from error
        return [{"name": name, "value": morsel.value} for name, morsel in parsed.items()]

    def _merged_cookies(self) -> list[dict[str, str]]:
        """Session cookies take precedence over client-supplied cookies."""

        session = self.config.session_cookies
        merged: dict[str, str] = {}
        for cookie in self._request_cookies():
            merged[cookie["name"]] = cookie["value"]
        for name, value in session.items():
            merged[name] = value
        return [{"name": name, "value": value} for name, value in merged.items()]

    def _read_form_body(self) -> str:
        if self.headers.get("Transfer-Encoding"):
            raise GatewayRequestError(400, "transfer encoding not supported")
        content_type = self.headers.get_content_type().lower()
        if content_type != "application/x-www-form-urlencoded":
            raise GatewayRequestError(415, "unsupported content type")
        raw_length = self.headers.get("Content-Length")
        if raw_length is None:
            raise GatewayRequestError(411, "content length required")
        try:
            length = int(raw_length)
        except ValueError as error:
            raise GatewayRequestError(400, "invalid content length") from error
        if length < 0:
            raise GatewayRequestError(400, "invalid content length")
        if length > self.config.max_body_bytes:
            raise GatewayRequestError(413, "request body too large")
        body = self.rfile.read(length)
        if len(body) != length:
            raise GatewayRequestError(400, "incomplete request body")
        try:
            return body.decode("ascii")
        except UnicodeDecodeError as error:
            raise GatewayRequestError(400, "form body must be URL encoded") from error

    def _authorization_header(self) -> str | None:
        """Reconstruct the Basic header Prowlarr configured for this indexer.

        Prowlarr's FlareSolverr integration drops the indexer's Authorization
        header from the replayed login POST, which would make the gateway
        unreachable. The gateway re-adds it from the PROWLARR_GATEWAY_BASIC
        environment secret when it is present.
        """

        raw = os.environ.get("PROWLARR_GATEWAY_BASIC", "").strip()
        if not raw:
            return None
        return "Basic " + base64.b64encode(raw.encode("utf-8")).decode("ascii")

    def _send_session_login(self) -> None:
        """Answer the login POST with a minimal authenticated page.

        The session cookies come from an operator-run interactive login, so the
        gateway can report success without reaching RuTracker. Prowlarr only
        checks for ``id="logged-in-username"`` and then stores the Set-Cookie
        values it receives here.
        """

        marker = self.config.logged_in_marker
        html = (
            "<!DOCTYPE html><html><head><meta charset=\"windows-1251\">"
            "<title>RuTracker.org</title></head><body>"
            f"<span {marker}>session</span>"
            "</body></html>"
        )
        body = html.encode("windows-1251", errors="xmlcharrefreplace")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=windows-1251")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        for name, value in self.config.session_cookies.items():
            self.send_header("Set-Cookie", f"{name}={value}; Path=/; HttpOnly; SameSite=Lax")
        self.end_headers()
        self.wfile.write(body)

    def _call_flaresolverr(self, payload: dict[str, Any]) -> dict[str, Any]:
        headers = {"Content-Type": "application/json"}
        authorization = self._authorization_header()
        if authorization:
            headers["Authorization"] = authorization
        request = urllib.request.Request(
            self.config.flaresolverr_url,
            data=json.dumps(payload, separators=(",", ":")).encode(),
            headers=headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(
                request, timeout=self.config.timeout_seconds
            ) as response:
                serialized = response.read(self.config.max_upstream_response_bytes + 1)
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as error:
            raise GatewayRequestError(502, "FlareSolverr unavailable") from error
        if len(serialized) > self.config.max_upstream_response_bytes:
            raise GatewayRequestError(502, "FlareSolverr response too large")
        try:
            result = json.loads(serialized)
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise GatewayRequestError(502, "invalid FlareSolverr response") from error
        if not isinstance(result, dict) or result.get("status") != "ok":
            raise GatewayRequestError(502, "FlareSolverr failed")
        solution = result.get("solution")
        if not isinstance(solution, dict) or not isinstance(solution.get("response"), str):
            raise GatewayRequestError(502, "invalid FlareSolverr solution")

        final_url = urlsplit(str(solution.get("url", "")))
        if (
            final_url.scheme != "https"
            or final_url.hostname != "rutracker.org"
            or final_url.username
            or final_url.password
            or final_url.port not in {None, 443}
        ):
            raise GatewayRequestError(502, "unexpected FlareSolverr target")
        return solution

    def _send_solution(self, solution: dict[str, Any]) -> None:
        body = solution["response"].encode("windows-1251", errors="xmlcharrefreplace")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=windows-1251")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        cookies = solution.get("cookies", [])
        if isinstance(cookies, list):
            for cookie in cookies:
                if not isinstance(cookie, dict):
                    continue
                name = cookie.get("name")
                value = cookie.get("value")
                if (
                    not isinstance(name, str)
                    or not COOKIE_NAME.fullmatch(name)
                    or not isinstance(value, str)
                    or any(character in value for character in "\r\n;")
                ):
                    continue
                self.send_header(
                    "Set-Cookie", f"{name}={value}; Path=/; HttpOnly; SameSite=Lax"
                )
        self.end_headers()
        self.wfile.write(body)

    def _send_json(
        self, status: int, payload: dict[str, str], *, include_body: bool = True
    ) -> None:
        body = json.dumps(payload, separators=(",", ":")).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body) if include_body else 0))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        if include_body:
            self.wfile.write(body)

def create_server(config: GatewayConfig) -> GatewayHTTPServer:
    return GatewayHTTPServer((config.listen_host, config.listen_port), config)

def config_from_environment() -> GatewayConfig:
    return GatewayConfig(
        flaresolverr_url=os.environ.get(
            "RUTRACKER_GATEWAY_FLARESOLVERR_URL", "http://flaresolverr:8191/v1"
        ),
        listen_host=os.environ.get("RUTRACKER_GATEWAY_LISTEN_HOST", "0.0.0.0"),
        listen_port=int(os.environ.get("RUTRACKER_GATEWAY_LISTEN_PORT", "8080")),
        max_body_bytes=int(os.environ.get("RUTRACKER_GATEWAY_MAX_BODY_BYTES", "65536")),
        max_upstream_response_bytes=int(
            os.environ.get("RUTRACKER_GATEWAY_MAX_RESPONSE_BYTES", str(16 * 1024 * 1024))
        ),
        max_timeout_ms=int(
            os.environ.get("RUTRACKER_GATEWAY_FLARESOLVERR_TIMEOUT_MS", "120000")
        ),
        timeout_seconds=int(
            os.environ.get("RUTRACKER_GATEWAY_HTTP_TIMEOUT_SECONDS", "130")
        ),
        session_cookies_file=os.environ.get("RUTRACKER_GATEWAY_SESSION_COOKIES", ""),
        logged_in_marker=os.environ.get(
            "RUTRACKER_GATEWAY_LOGGED_IN_MARKER", DEFAULT_LOGGED_IN_MARKER
        ),
    )

def main() -> int:
    server = create_server(config_from_environment())
    print(
        f"rutracker-gateway listening on {server.server_address[0]}:{server.server_address[1]}",
        flush=True,
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
