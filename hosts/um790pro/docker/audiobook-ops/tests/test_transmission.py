from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import threading
import unittest

from audiobook_ops.interface import OperationError
from audiobook_ops.transmission import TransmissionAdapter, TransmissionHTTPRPC


class FakeRPC:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, object]]] = []
        self.torrents: list[dict[str, object]] = []

    def call(self, method: str, arguments: dict[str, object]) -> dict[str, object]:
        self.calls.append((method, arguments))
        if method == "torrent-get":
            return {"torrents": [dict(torrent) for torrent in self.torrents]}
        if method == "torrent-add":
            torrent = {
                "hashString": "a" * 40,
                "id": 7,
                "labels": list(arguments["labels"]),
                "status": 4,
                "percentDone": 0.0,
                "leftUntilDone": 1234,
                "rateDownload": 42,
                "activityDate": 100,
                "downloadDir": "/downloads",
                "name": "Кроткая",
                "error": 0,
                "errorString": "",
                "isFinished": False,
            }
            self.torrents.append(torrent)
            return {"torrent-added": dict(torrent)}
        if method == "torrent-remove":
            return {}
        raise AssertionError(method)


class TransmissionAdapterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.rpc = FakeRPC()
        self.adapter = TransmissionAdapter(self.rpc, download_dir="/downloads")

    def test_submit_is_replay_safe_and_never_returns_resolution_material(self) -> None:
        resolution = {
            "magnet_uri": "magnet:?xt=urn:btih:" + "a" * 40 + "&dn=secret-title",
            "download_url": None,
            "infohash": "a" * 40,
        }

        first = self.adapter.submit(resolution, "task-key-one")
        replay = self.adapter.submit(resolution, "task-key-one")

        self.assertEqual(first, "a" * 40)
        self.assertEqual(replay, first)
        additions = [call for call in self.rpc.calls if call[0] == "torrent-add"]
        self.assertEqual(len(additions), 1)
        self.assertEqual(additions[0][1]["labels"], ["audiobook-ops:task-key-one"])
        self.assertNotIn("magnet", json.dumps({"first": first, "replay": replay}))

    def test_observe_and_remove_use_only_the_exact_internal_hash(self) -> None:
        self.adapter.submit(
            {"magnet_uri": "magnet:?xt=urn:btih:" + "a" * 40},
            "task-key-one",
        )

        observed = self.adapter.observe("a" * 40)
        self.adapter.remove("a" * 40)

        self.assertEqual(observed["torrent_hash"], "a" * 40)
        self.assertEqual(observed["status"], "downloading")
        self.assertEqual(observed["download_root"], "/downloads/Кроткая")
        removal = [call for call in self.rpc.calls if call[0] == "torrent-remove"][-1]
        self.assertEqual(
            removal[1], {"delete-local-data": True, "ids": ["a" * 40]}
        )

    def test_arbitrary_source_and_hash_values_fail_closed(self) -> None:
        with self.assertRaisesRegex(OperationError, "unsafe release resolution"):
            self.adapter.submit({"download_url": "https://evil.example/payload"}, "key")
        with self.assertRaisesRegex(OperationError, "invalid torrent identity"):
            self.adapter.observe("not-a-hash")
        with self.assertRaisesRegex(OperationError, "invalid torrent identity"):
            self.adapter.remove("not-a-hash")

    def test_http_rpc_negotiates_a_session_without_exposing_credentials(self) -> None:
        requests: list[dict[str, object]] = []

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:
                if self.headers.get("X-Transmission-Session-Id") != "session-one":
                    self.send_response(409)
                    self.send_header("X-Transmission-Session-Id", "session-one")
                    self.end_headers()
                    return
                length = int(self.headers.get("Content-Length", "0"))
                requests.append(json.loads(self.rfile.read(length)))
                body = json.dumps(
                    {"arguments": {"torrents": []}, "result": "success"}
                ).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, _format: str, *_args: object) -> None:
                return

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        host, port = server.server_address
        try:
            rpc = TransmissionHTTPRPC(
                f"http://{host}:{port}/transmission/rpc",
                "audiobook-ops",
                "test-password",
            )
            result = rpc.call("torrent-get", {"fields": ["hashString"]})
        finally:
            server.shutdown()
            server.server_close()

        self.assertEqual(result, {"torrents": []})
        self.assertEqual(requests[0]["method"], "torrent-get")
        self.assertNotIn("test-password", json.dumps({"result": result, "requests": requests}))


if __name__ == "__main__":
    unittest.main()
