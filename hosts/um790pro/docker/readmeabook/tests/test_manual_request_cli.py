#!/usr/bin/env python3

import json
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse


BUNDLE_DIR = Path(__file__).resolve().parents[1]
MANUAL_REQUEST = BUNDLE_DIR / "scripts" / "manual-request.py"


class ManualRequestCliTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        self.requester_password_file = self.root / "requester-password"
        self.requester_password_file.write_text("requester-password\n", encoding="utf-8")
        self.admin_password_file = self.root / "admin-password"
        self.admin_password_file.write_text("admin-password\n", encoding="utf-8")

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def start_api(
        self,
        request_log: list[str] | None = None,
        global_auto_approve: bool = False,
        user_auto_approve: bool | None = None,
    ) -> tuple[ThreadingHTTPServer, str]:
        seen = request_log if request_log is not None else []

        class Handler(BaseHTTPRequestHandler):
            def send_json(self, status: int, value: object) -> None:
                payload = json.dumps(value).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def do_GET(self) -> None:
                path = urlparse(self.path).path
                seen.append(path)
                authorization = self.headers.get("Authorization")
                if path == "/api/auth/me" and authorization == "Bearer user-session-token":
                    self.send_json(
                        200,
                        {
                            "user": {
                                "id": "user-1",
                                "role": "user",
                                "username": "nik-requester",
                            }
                        },
                    )
                    return
                if authorization != "Bearer admin-session-token":
                    self.send_json(401, {"message": "Unauthorized"})
                    return
                if path == "/api/admin/settings/auto-approve":
                    self.send_json(
                        200, {"autoApproveRequests": global_auto_approve}
                    )
                    return
                if path == "/api/admin/users":
                    self.send_json(
                        200,
                        {
                            "users": [
                                {
                                    "autoApproveRequests": user_auto_approve,
                                    "id": "user-1",
                                    "plexUsername": "nik-requester",
                                    "role": "user",
                                }
                            ]
                        },
                    )
                    return
                self.send_json(404, {"message": "Not found"})

            def do_POST(self) -> None:
                path = urlparse(self.path).path
                seen.append(path)
                length = int(self.headers.get("Content-Length", "0"))
                body = json.loads(self.rfile.read(length))
                if path == "/api/auth/local/login":
                    if body == {"password": "admin-password", "username": "nik"}:
                        self.send_json(200, {"accessToken": "admin-session-token"})
                        return
                    if body == {
                        "password": "requester-password",
                        "username": "nik-requester",
                    }:
                        self.send_json(200, {"accessToken": "user-session-token"})
                        return
                    self.send_json(401, {"message": "Invalid credentials"})
                    return
                if self.headers.get("Authorization") != "Bearer user-session-token":
                    self.send_response(401)
                    self.end_headers()
                    return
                if path == "/api/audiobooks/request-with-torrent":
                    audiobook = body.get("audiobook", {})
                    torrent = body.get("torrent", {})
                    if audiobook != {
                        "asin": "manual:rutracker:6887881",
                        "author": "Конофальский Борис",
                        "title": "Кляксы",
                    } or torrent.get("guid") != "private-guid":
                        self.send_response(400)
                        self.end_headers()
                        return
                    payload = json.dumps(
                        {
                            "request": {
                                "id": "req-manual-1",
                                "status": (
                                    "downloading"
                                    if global_auto_approve
                                    else "awaiting_approval"
                                ),
                            },
                            "success": True,
                        }
                    ).encode()
                    self.send_response(201)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(payload)))
                    self.end_headers()
                    self.wfile.write(payload)
                    return
                if path != "/api/audiobooks/search-torrents":
                    self.send_response(404)
                    self.end_headers()
                    return
                if body != {"author": "Конофальский Борис", "title": "Кляксы"}:
                    self.send_response(400)
                    self.end_headers()
                    return
                payload = json.dumps(
                    {
                        "message": "Found 1 result",
                        "results": [
                            {
                                "downloadUrl": "http://prowlarr:9696/download?apikey=supersecret",
                                "finalScore": 40.5,
                                "format": "MP3",
                                "guid": "private-guid",
                                "indexer": "RuTracker",
                                "infoUrl": "http://rutracker-gateway:8080/forum/viewtopic.php?t=6887881",
                                "leechers": 7,
                                "protocol": "torrent",
                                "publishDate": "2026-09-10T12:00:00.000Z",
                                "rank": 1,
                                "seeders": 44,
                                "size": 572522496,
                                "title": "Конофальский Борис - Рейд 8, Глубокий рейд 4, Кляксы",
                            }
                        ],
                    }
                ).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def log_message(self, _format: str, *_args: object) -> None:
                return

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        host, port = server.server_address
        return server, f"http://{host}:{port}"

    def test_search_lists_safe_release_fields_without_creating_a_request(self) -> None:
        server, base_url = self.start_api()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        config = self.root / "manual-request.json"
        config.write_text(
            json.dumps(
                {
                    "admin_password_file": str(self.admin_password_file),
                    "admin_username": "nik",
                    "requester_password_file": str(self.requester_password_file),
                    "requester_username": "nik-requester",
                    "rmab_url": base_url,
                }
            ),
            encoding="utf-8",
        )

        result = subprocess.run(
            [
                sys.executable,
                str(MANUAL_REQUEST),
                "--config",
                str(config),
                "search",
                "--title",
                "Кляксы",
                "--author",
                "Конофальский Борис",
                "--json",
            ],
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            json.loads(result.stdout),
            {
                "results": [
                    {
                        "format": "MP3",
                        "indexer": "RuTracker",
                        "leechers": 7,
                        "protocol": "torrent",
                        "rank": 1,
                        "score": 40.5,
                        "seeders": 44,
                        "size_bytes": 572522496,
                        "title": "Конофальский Борис - Рейд 8, Глубокий рейд 4, Кляксы",
                        "topic_id": "6887881",
                    }
                ]
            },
        )
        self.assertNotIn("supersecret", result.stdout)
        self.assertNotIn("private-guid", result.stdout)

    def test_request_preview_selects_one_topic_without_writing(self) -> None:
        request_log: list[str] = []
        server, base_url = self.start_api(request_log)
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        config = self.root / "manual-request.json"
        config.write_text(
            json.dumps(
                {
                    "requester_password_file": str(self.requester_password_file),
                    "requester_username": "nik-requester",
                    "rmab_url": base_url,
                }
            ),
            encoding="utf-8",
        )

        result = subprocess.run(
            [
                sys.executable,
                str(MANUAL_REQUEST),
                "--config",
                str(config),
                "request",
                "--title",
                "Кляксы",
                "--author",
                "Конофальский Борис",
                "--topic-id",
                "6887881",
                "--json",
            ],
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            json.loads(result.stdout),
            {
                "action": "would-request",
                "author": "Конофальский Борис",
                "manual_id": "manual:rutracker:6887881",
                "release": {
                    "format": "MP3",
                    "indexer": "RuTracker",
                    "leechers": 7,
                    "protocol": "torrent",
                    "rank": 1,
                    "score": 40.5,
                    "seeders": 44,
                    "size_bytes": 572522496,
                    "title": "Конофальский Борис - Рейд 8, Глубокий рейд 4, Кляксы",
                    "topic_id": "6887881",
                },
                "title": "Кляксы",
            },
        )
        self.assertEqual(
            request_log,
            ["/api/auth/local/login", "/api/audiobooks/search-torrents"],
        )

    def test_execute_creates_an_awaiting_approval_request(self) -> None:
        request_log: list[str] = []
        server, base_url = self.start_api(request_log)
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        config = self.root / "manual-request.json"
        config.write_text(
            json.dumps(
                {
                    "admin_password_file": str(self.admin_password_file),
                    "admin_username": "nik",
                    "requester_password_file": str(self.requester_password_file),
                    "requester_username": "nik-requester",
                    "rmab_url": base_url,
                }
            ),
            encoding="utf-8",
        )

        result = subprocess.run(
            [
                sys.executable,
                str(MANUAL_REQUEST),
                "--config",
                str(config),
                "request",
                "--title",
                "Кляксы",
                "--author",
                "Конофальский Борис",
                "--topic-id",
                "6887881",
                "--execute",
                "--json",
            ],
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            json.loads(result.stdout),
            {
                "action": "requested",
                "manual_id": "manual:rutracker:6887881",
                "request_id": "req-manual-1",
                "status": "awaiting_approval",
            },
        )
        self.assertEqual(
            request_log,
            [
                "/api/auth/local/login",
                "/api/auth/me",
                "/api/auth/local/login",
                "/api/admin/settings/auto-approve",
                "/api/admin/users",
                "/api/audiobooks/search-torrents",
                "/api/audiobooks/request-with-torrent",
            ],
        )
        self.assertNotIn("supersecret", result.stdout)
        self.assertNotIn("private-guid", result.stdout)

    def test_execute_text_output_reports_created_request(self) -> None:
        server, base_url = self.start_api()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        config = self.root / "manual-request.json"
        config.write_text(
            json.dumps(
                {
                    "admin_password_file": str(self.admin_password_file),
                    "admin_username": "nik",
                    "requester_password_file": str(self.requester_password_file),
                    "requester_username": "nik-requester",
                    "rmab_url": base_url,
                }
            ),
            encoding="utf-8",
        )

        result = subprocess.run(
            [
                sys.executable,
                str(MANUAL_REQUEST),
                "--config",
                str(config),
                "request",
                "--title",
                "Кляксы",
                "--author",
                "Конофальский Борис",
                "--topic-id",
                "6887881",
                "--execute",
            ],
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            result.stdout.splitlines(),
            [
                "action: requested",
                "manual_id: manual:rutracker:6887881",
                "request_id: req-manual-1",
                "status: awaiting_approval",
            ],
        )
        self.assertNotIn("supersecret", result.stdout)
        self.assertNotIn("private-guid", result.stdout)

    def test_execute_refuses_auto_approval_before_search_or_request(self) -> None:
        request_log: list[str] = []
        server, base_url = self.start_api(
            request_log, global_auto_approve=True, user_auto_approve=None
        )
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        config = self.root / "manual-request.json"
        config.write_text(
            json.dumps(
                {
                    "admin_password_file": str(self.admin_password_file),
                    "admin_username": "nik",
                    "requester_password_file": str(self.requester_password_file),
                    "requester_username": "nik-requester",
                    "rmab_url": base_url,
                }
            ),
            encoding="utf-8",
        )

        result = subprocess.run(
            [
                sys.executable,
                str(MANUAL_REQUEST),
                "--config",
                str(config),
                "request",
                "--title",
                "Кляксы",
                "--author",
                "Конофальский Борис",
                "--topic-id",
                "6887881",
                "--execute",
                "--json",
            ],
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("auto-approval is enabled", result.stderr)
        self.assertEqual(
            request_log,
            [
                "/api/auth/local/login",
                "/api/auth/me",
                "/api/auth/local/login",
                "/api/admin/settings/auto-approve",
                "/api/admin/users",
            ],
        )


if __name__ == "__main__":
    unittest.main()
