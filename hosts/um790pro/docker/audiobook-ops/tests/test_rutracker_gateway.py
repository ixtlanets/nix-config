#!/usr/bin/env python3

import http.client
import importlib.util
import json
import threading
import unittest
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


BUNDLE_DIR = Path(__file__).resolve().parents[1]
GATEWAY_PATH = BUNDLE_DIR / "scripts" / "rutracker_gateway.py"


def load_gateway_module():
    spec = importlib.util.spec_from_file_location("rutracker_gateway", GATEWAY_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to load gateway module")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FakeFlareSolverrHandler(BaseHTTPRequestHandler):
    requests: list[dict] = []

    def do_POST(self) -> None:
        body = self.rfile.read(int(self.headers["Content-Length"]))
        payload = json.loads(body)
        self.__class__.requests.append(payload)
        response = {
            "status": "ok",
            "message": "Challenge solved!",
            "solution": {
                "url": payload["url"],
                "status": 200,
                "response": '<html><span id="logged-in-username">тест</span></html>',
                "cookies": [
                    {"name": "bb_session", "value": "session-value"},
                    {"name": "cf_clearance", "value": "clearance-value"},
                ],
            },
        }
        serialized = json.dumps(response).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(serialized)))
        self.end_headers()
        self.wfile.write(serialized)

    def log_message(self, _format: str, *_args: object) -> None:
        return


class RuTrackerGatewayTest(unittest.TestCase):
    def setUp(self) -> None:
        self.module = load_gateway_module()
        FakeFlareSolverrHandler.requests = []
        self.flare_server = ThreadingHTTPServer(("127.0.0.1", 0), FakeFlareSolverrHandler)
        self.flare_thread = threading.Thread(target=self.flare_server.serve_forever)
        self.flare_thread.start()
        config = self.module.GatewayConfig(
            flaresolverr_url=f"http://127.0.0.1:{self.flare_server.server_port}/v1",
            listen_host="127.0.0.1",
            listen_port=0,
            max_body_bytes=128,
            max_upstream_response_bytes=1024 * 1024,
            max_timeout_ms=120_000,
            timeout_seconds=5,
        )
        self.gateway_server = self.module.create_server(config)
        self.gateway_thread = threading.Thread(target=self.gateway_server.serve_forever)
        self.gateway_thread.start()
        self.gateway_url = f"http://127.0.0.1:{self.gateway_server.server_port}"

    def tearDown(self) -> None:
        self.gateway_server.shutdown()
        self.gateway_server.server_close()
        self.gateway_thread.join()
        self.flare_server.shutdown()
        self.flare_server.server_close()
        self.flare_thread.join()

    def test_health_is_local_and_does_not_call_flaresolverr(self) -> None:
        with urllib.request.urlopen(f"{self.gateway_url}/health") as response:
            self.assertEqual(response.status, 200)
            self.assertEqual(json.load(response), {"status": "ok"})

        self.assertEqual(FakeFlareSolverrHandler.requests, [])

    def test_post_is_forwarded_without_logging_or_persisting_credentials(self) -> None:
        form = b"login_username=user&login_password=secret"
        request = urllib.request.Request(
            f"{self.gateway_url}/forum/login.php",
            data=form,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            method="POST",
        )

        with urllib.request.urlopen(request) as response:
            body = response.read().decode("windows-1251")
            cookies = response.headers.get_all("Set-Cookie")

        self.assertIn("logged-in-username", body)
        self.assertIn("тест", body)
        self.assertEqual(
            FakeFlareSolverrHandler.requests[0],
            {
                "cmd": "request.post",
                "url": "https://rutracker.org/forum/login.php",
                "postData": form.decode(),
                "maxTimeout": 120_000,
            },
        )
        self.assertTrue(any(cookie.startswith("bb_session=session-value;") for cookie in cookies))
        self.assertTrue(any(cookie.startswith("cf_clearance=clearance-value;") for cookie in cookies))

    def test_get_passes_only_cookie_names_and_values_to_flaresolverr(self) -> None:
        request = urllib.request.Request(
            f"{self.gateway_url}/forum/tracker.php?nm=tolkien",
            headers={"Cookie": "bb_session=session-value; cf_clearance=clearance-value"},
        )

        with urllib.request.urlopen(request) as response:
            self.assertEqual(response.status, 200)
            response.read()

        self.assertEqual(
            FakeFlareSolverrHandler.requests[0],
            {
                "cmd": "request.get",
                "url": "https://rutracker.org/forum/tracker.php?nm=tolkien",
                "cookies": [
                    {"name": "bb_session", "value": "session-value"},
                    {"name": "cf_clearance", "value": "clearance-value"},
                ],
                "maxTimeout": 120_000,
            },
        )

    def test_rejects_proxy_targets_and_oversized_request_bodies(self) -> None:
        connection = http.client.HTTPConnection(
            "127.0.0.1", self.gateway_server.server_port, timeout=5
        )
        connection.request("GET", "https://example.com/forum/tracker.php")
        response = connection.getresponse()
        self.assertEqual(response.status, 400)
        response.read()
        connection.close()

        request = urllib.request.Request(
            f"{self.gateway_url}/forum/login.php",
            data=b"x" * 129,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            method="POST",
        )
        with self.assertRaises(urllib.error.HTTPError) as raised:
            urllib.request.urlopen(request)
        self.assertEqual(raised.exception.code, 413)
        raised.exception.close()
        self.assertEqual(FakeFlareSolverrHandler.requests, [])


if __name__ == "__main__":
    unittest.main()

