#!/usr/bin/env python3

import json
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


BUNDLE_DIR = Path(__file__).resolve().parents[1]
POLICY = BUNDLE_DIR / "scripts" / "torrent-policy.py"


class TorrentPolicyTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        self.downloads = self.root / "downloads"
        self.staging = self.root / "staging"
        self.state = self.root / "publisher-state"
        self.downloads.mkdir()
        self.staging.mkdir()
        self.state.mkdir()
        self.password = self.root / "password"
        self.password.write_text("test-password")
        self.config = self.root / "policy.json"
        self.calls: list[dict[str, object]] = []
        self.torrents: list[dict[str, object]] = []

        owner = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:
                if self.headers.get("X-Transmission-Session-Id") != "test-session":
                    self.send_response(409)
                    self.send_header("X-Transmission-Session-Id", "test-session")
                    self.end_headers()
                    return
                length = int(self.headers.get("Content-Length", "0"))
                request = json.loads(self.rfile.read(length))
                owner.calls.append(request)
                method = request["method"]
                arguments: dict[str, object] = {}
                if method == "torrent-get":
                    arguments["torrents"] = owner.torrents
                payload = json.dumps(
                    {"arguments": arguments, "result": "success"}
                ).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def log_message(self, _format: str, *_args: object) -> None:
                return

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        host, port = self.server.server_address
        self.rpc_url = f"http://{host}:{port}/transmission/rpc"

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.tempdir.cleanup()

    def write_config(self, **overrides: object) -> None:
        config: dict[str, object] = {
            "downloads_root": str(self.downloads),
            "max_working_set_gib": 50,
            "min_local_free_gib": 0,
            "publisher_state_dir": str(self.state),
            "seed_max_days": 7,
            "seed_ratio": 1.0,
            "staging_root": str(self.staging),
            "transmission_password_file": str(self.password),
            "transmission_rpc_url": self.rpc_url,
            "transmission_username": "readmeabook",
        }
        config.update(overrides)
        self.config.write_text(json.dumps(config))

    def run_policy(self, *arguments: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(POLICY), "--config", str(self.config), *arguments],
            check=False,
            capture_output=True,
            text=True,
        )

    def test_status_plans_a_pause_when_working_set_exceeds_the_limit(self) -> None:
        (self.downloads / "large.part").write_bytes(b"x")
        self.torrents = [
            {
                "addedDate": 1,
                "doneDate": 0,
                "hashString": "a" * 40,
                "id": 1,
                "name": "active",
                "status": 4,
                "uploadRatio": 0.0,
            }
        ]
        self.write_config(max_working_set_gib=0)

        result = self.run_policy("status", "--json")

        self.assertEqual(result.returncode, 0, result.stderr)
        status = json.loads(result.stdout)
        self.assertTrue(status["capacity_blocked"])
        self.assertEqual(status["pause_hashes"], ["a" * 40])
        self.assertFalse([call for call in self.calls if call["method"] == "torrent-stop"])

    def test_run_requires_execute_before_mutating_transmission(self) -> None:
        self.write_config()

        result = self.run_policy("run")

        self.assertEqual(result.returncode, 2)
        self.assertIn("requires --execute", result.stderr)
        self.assertEqual(self.calls, [])

    def test_execute_capacity_violation_persists_the_shared_block(self) -> None:
        (self.downloads / "large.part").write_bytes(b"x")
        self.torrents = [
            {
                "addedDate": 1,
                "doneDate": 0,
                "hashString": "a" * 40,
                "id": 1,
                "name": "active",
                "status": 4,
                "uploadRatio": 0.0,
            }
        ]
        self.write_config(max_working_set_gib=0)

        result = self.run_policy("run", "--execute", "--json")

        self.assertEqual(result.returncode, 0, result.stderr)
        blocked = json.loads((self.state / "blocked.json").read_text())
        self.assertIn("capacity", blocked["reason"])
        self.assertTrue([call for call in self.calls if call["method"] == "torrent-stop"])

    def test_execute_deletes_only_seeded_source_with_a_published_ledger_record(self) -> None:
        published_hash = "a" * 40
        unrelated_hash = "b" * 40
        (self.state / "ledger.json").write_text(
            json.dumps(
                {
                    "pending": {},
                    "publications": {
                        "req-1": {
                            "status": "published",
                            "torrent_hash": published_hash,
                        }
                    },
                }
            )
        )
        self.torrents = [
            {
                "addedDate": 1,
                "doneDate": int(time.time()) - 60,
                "hashString": published_hash,
                "id": 1,
                "name": "published",
                "status": 6,
                "uploadRatio": 1.0,
            },
            {
                "addedDate": 2,
                "doneDate": int(time.time()) - 8 * 86400,
                "hashString": unrelated_hash,
                "id": 2,
                "name": "not-in-ledger",
                "status": 6,
                "uploadRatio": 2.0,
            },
        ]
        self.write_config()

        result = self.run_policy("run", "--execute", "--json")

        self.assertEqual(result.returncode, 0, result.stderr)
        removals = [call for call in self.calls if call["method"] == "torrent-remove"]
        self.assertEqual(len(removals), 1)
        self.assertEqual(removals[0]["arguments"]["ids"], [published_hash])
        self.assertTrue(removals[0]["arguments"]["delete-local-data"])

    def test_execute_pauses_all_downloads_on_a_concurrency_violation(self) -> None:
        self.torrents = [
            {
                "addedDate": 1,
                "doneDate": 0,
                "hashString": "a" * 40,
                "id": 1,
                "name": "oldest",
                "status": 4,
                "uploadRatio": 0.0,
            },
            {
                "addedDate": 2,
                "doneDate": 0,
                "hashString": "b" * 40,
                "id": 2,
                "name": "newer",
                "status": 4,
                "uploadRatio": 0.0,
            },
        ]
        self.write_config()

        result = self.run_policy("run", "--execute", "--json")

        self.assertEqual(result.returncode, 0, result.stderr)
        stops = [call for call in self.calls if call["method"] == "torrent-stop"]
        self.assertEqual(stops[0]["arguments"]["ids"], ["a" * 40, "b" * 40])
        self.assertTrue((self.state / "blocked.json").is_file())

    def test_execute_rpc_failure_persists_the_shared_block(self) -> None:
        self.write_config()
        self.server.shutdown()
        self.server.server_close()

        result = self.run_policy("run", "--execute")

        self.assertNotEqual(result.returncode, 0)
        blocked = json.loads((self.state / "blocked.json").read_text())
        self.assertIn("torrent policy failure", blocked["reason"])


if __name__ == "__main__":
    unittest.main()
