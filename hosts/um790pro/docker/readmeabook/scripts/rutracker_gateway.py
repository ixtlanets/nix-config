#!/usr/bin/env python3

"""Internal RuTracker-to-FlareSolverr compatibility gateway.

Prowlarr's FlareSolverr integration replays solved requests with its own HTTP
client. Modern Cloudflare clearance can be bound to the browser fingerprint,
so the replay is rejected. This gateway returns FlareSolverr's browser response
directly and deliberately supports only the RuTracker endpoints Prowlarr needs.
"""

from __future__ import annotations

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

        self.flaresolverr_url = flaresolverr_url
        self.listen_host = listen_host
        self.listen_port = listen_port
        self.max_body_bytes = max_body_bytes
        self.max_upstream_response_bytes = max_upstream_response_bytes
        self.max_timeout_ms = max_timeout_ms
        self.timeout_seconds = timeout_seconds


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
    server_version = "ReadMeABook-RuTracker-Gateway"
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

            cookies = self._request_cookies()
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

    def _call_flaresolverr(self, payload: dict[str, Any]) -> dict[str, Any]:
        request = urllib.request.Request(
            self.config.flaresolverr_url,
            data=json.dumps(payload, separators=(",", ":")).encode(),
            headers={"Content-Type": "application/json"},
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
