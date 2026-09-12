#!/usr/bin/env python3

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse


BUNDLE_DIR = Path(__file__).resolve().parents[1]
PUBLISHER = BUNDLE_DIR / "scripts" / "publisher.py"


class PublisherCliTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        self.state_dir = self.root / "state"
        self.staging_dir = self.root / "staging"
        self.staging_dir.mkdir()
        self.config_path = self.root / "publisher.json"
        self.config_path.write_text(
            json.dumps(
                {
                    "state_dir": str(self.state_dir),
                    "staging_root": str(self.staging_dir),
                }
            ),
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def run_publisher(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(PUBLISHER), "--config", str(self.config_path), *args],
            check=False,
            capture_output=True,
            text=True,
        )

    def start_api(self, routes: dict[str, object]) -> tuple[ThreadingHTTPServer, str]:
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                path = urlparse(self.path).path
                if path not in routes:
                    self.send_response(404)
                    self.end_headers()
                    return
                payload = json.dumps(routes[path]).encode()
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

    def stop_api(self, server: ThreadingHTTPServer) -> None:
        server.shutdown()
        server.server_close()

    def test_status_reports_a_fresh_publisher_as_unblocked(self) -> None:
        result = self.run_publisher("status", "--json")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            json.loads(result.stdout),
            {
                "blocked": False,
                "blocked_reason": None,
                "published": 0,
                "pending": 0,
            },
        )

    def test_acknowledge_requires_execute_before_clearing_a_block(self) -> None:
        self.state_dir.mkdir()
        (self.state_dir / "blocked.json").write_text(
            json.dumps({"reason": "checksum mismatch"}), encoding="utf-8"
        )

        refused = self.run_publisher("acknowledge")
        still_blocked = self.run_publisher("status", "--json")
        cleared = self.run_publisher("acknowledge", "--execute")
        final_status = self.run_publisher("status", "--json")

        self.assertNotEqual(refused.returncode, 0)
        self.assertIn("acknowledge requires --execute", refused.stderr)
        self.assertTrue(json.loads(still_blocked.stdout)["blocked"])
        self.assertEqual(cleared.returncode, 0, cleared.stderr)
        self.assertFalse(json.loads(final_status.stdout)["blocked"])

    def test_blocked_run_preserves_the_original_failure_reason(self) -> None:
        self.state_dir.mkdir()
        blocked_path = self.state_dir / "blocked.json"
        blocked_path.write_text(
            json.dumps({"reason": "more than one publish candidate is pending"}),
            encoding="utf-8",
        )

        result = self.run_publisher("run-once", "--execute")

        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(
            json.loads(blocked_path.read_text(encoding="utf-8")),
            {"reason": "more than one publish candidate is pending"},
        )

    def test_run_once_dry_run_validates_a_completed_request_without_writes(self) -> None:
        book_dir = self.staging_dir / "Author" / "Book B123"
        book_dir.mkdir(parents=True)
        (book_dir / "book.m4b").write_bytes(b"audio-data")
        ffprobe = self.root / "ffprobe"
        ffprobe.write_text(
            "#!/bin/sh\nprintf '%s\\n' '{\"format\":{\"duration\":\"60.0\"}}'\n",
            encoding="utf-8",
        )
        ffprobe.chmod(0o755)

        request_id = "req-123"
        routes = {
            "/api/requests": {"requests": [{"id": request_id}]},
            f"/api/requests/{request_id}": {
                "success": True,
                "request": {
                    "id": request_id,
                    "status": "downloaded",
                    "audiobook": {
                        "asin": "B123",
                        "author": "Author",
                        "filePath": "/media/Author/Book B123",
                        "status": "completed",
                        "title": "Book",
                    },
                    "jobs": [
                        {
                            "status": "completed",
                            "type": "organize_files",
                            "result": {
                                "errors": [],
                                "success": True,
                                "targetPath": str(book_dir),
                            },
                        }
                    ],
                },
            },
            "/api/libraries/lib-1/items": {"results": []},
        }
        server, base_url = self.start_api(routes)
        self.addCleanup(self.stop_api, server)
        token_file = self.root / "token"
        token_file.write_text("secret-token\n", encoding="utf-8")
        self.config_path.write_text(
            json.dumps(
                {
                    "abs_library_id": "lib-1",
                    "abs_token_file": str(token_file),
                    "abs_url": base_url,
                    "allowed_extensions": [".m4b", ".m4a", ".mp3", ".flac"],
                    "ffprobe_bin": str(ffprobe),
                    "max_release_gib": 20,
                    "min_local_free_gib": 0,
                    "rmab_token_file": str(token_file),
                    "rmab_media_root": "/media",
                    "rmab_url": base_url,
                    "stability_seconds": 0,
                    "staging_root": str(self.staging_dir),
                    "state_dir": str(self.state_dir),
                }
            ),
            encoding="utf-8",
        )

        result = self.run_publisher("run-once", "--json")

        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(result.stdout)
        self.assertEqual(output["action"], "would-publish")
        self.assertEqual(output["request_id"], request_id)
        self.assertEqual(output["final_relative_path"], "Author/Book B123")
        self.assertEqual(output["files"], 1)
        self.assertFalse(self.state_dir.exists())

    def test_run_once_ignores_already_published_candidates(self) -> None:
        book_dir = self.staging_dir / "Author" / "New Book B456"
        book_dir.mkdir(parents=True)
        (book_dir / "book.m4b").write_bytes(b"audio-data")
        ffprobe = self.root / "ffprobe"
        ffprobe.write_text(
            "#!/bin/sh\nprintf '%s\\n' '{\"format\":{\"duration\":\"60.0\"}}'\n",
            encoding="utf-8",
        )
        ffprobe.chmod(0o755)

        published_request_id = "req-published"
        new_request_id = "req-new"
        routes = {
            "/api/requests": {
                "requests": [
                    {"id": new_request_id},
                    {"id": published_request_id},
                ]
            },
            f"/api/requests/{new_request_id}": {
                "success": True,
                "request": {
                    "id": new_request_id,
                    "status": "downloaded",
                    "audiobook": {
                        "asin": "B456",
                        "author": "Author",
                        "filePath": "/media/Author/New Book B456",
                        "status": "completed",
                        "title": "New Book",
                    },
                    "jobs": [
                        {
                            "status": "completed",
                            "type": "organize_files",
                            "result": {
                                "errors": [],
                                "success": True,
                                "targetPath": str(book_dir),
                            },
                        }
                    ],
                },
            },
            "/api/libraries/lib-1/items": {"results": []},
        }
        server, base_url = self.start_api(routes)
        self.addCleanup(self.stop_api, server)
        token_file = self.root / "token"
        token_file.write_text("secret-token\n", encoding="utf-8")
        self.state_dir.mkdir()
        (self.state_dir / "ledger.json").write_text(
            json.dumps(
                {
                    "pending": {},
                    "publications": {
                        published_request_id: {
                            "request_id": published_request_id,
                            "status": "published",
                        }
                    },
                }
            ),
            encoding="utf-8",
        )
        self.config_path.write_text(
            json.dumps(
                {
                    "abs_library_id": "lib-1",
                    "abs_token_file": str(token_file),
                    "abs_url": base_url,
                    "allowed_extensions": [".m4b", ".m4a", ".mp3", ".flac"],
                    "ffprobe_bin": str(ffprobe),
                    "max_release_gib": 20,
                    "min_local_free_gib": 0,
                    "rmab_token_file": str(token_file),
                    "rmab_media_root": "/media",
                    "rmab_url": base_url,
                    "stability_seconds": 0,
                    "staging_root": str(self.staging_dir),
                    "state_dir": str(self.state_dir),
                }
            ),
            encoding="utf-8",
        )

        result = self.run_publisher("run-once", "--json")

        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(result.stdout)
        self.assertEqual(output["action"], "would-publish")
        self.assertEqual(output["request_id"], new_request_id)

    def test_run_once_does_not_republish_an_unpublished_request(self) -> None:
        request_id = "req-unpublished"
        routes = {"/api/requests": {"requests": [{"id": request_id}]}}
        server, base_url = self.start_api(routes)
        self.addCleanup(self.stop_api, server)
        token_file = self.root / "token"
        token_file.write_text("secret-token\n", encoding="utf-8")
        self.state_dir.mkdir()
        (self.state_dir / "ledger.json").write_text(
            json.dumps(
                {
                    "pending": {},
                    "publications": {
                        request_id: {
                            "request_id": request_id,
                            "status": "unpublished",
                        }
                    },
                }
            ),
            encoding="utf-8",
        )
        self.config_path.write_text(
            json.dumps(
                {
                    "min_local_free_gib": 0,
                    "rmab_token_file": str(token_file),
                    "rmab_url": base_url,
                    "staging_root": str(self.staging_dir),
                    "state_dir": str(self.state_dir),
                }
            ),
            encoding="utf-8",
        )

        result = self.run_publisher("run-once", "--json")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), {"action": "idle"})

    def test_run_once_execute_publishes_then_records_the_ledger(self) -> None:
        book_dir = self.staging_dir / "Author" / "Book B123"
        book_dir.mkdir(parents=True)
        (book_dir / "book.m4b").write_bytes(b"audio-data")
        ffprobe = self.root / "ffprobe"
        ffprobe.write_text(
            "#!/bin/sh\nprintf '%s\\n' '{\"format\":{\"duration\":\"60.0\"}}'\n",
            encoding="utf-8",
        )
        ffprobe.chmod(0o755)
        command_log = self.root / "commands.log"
        fake_ssh = self.root / "ssh"
        fake_ssh.write_text(
            "#!/bin/sh\n"
            f"printf 'ssh %s\\n' \"$*\" >> {command_log}\n"
            "case \"$*\" in\n"
            "  *capacity*) printf '%s\\n' '{\"free_bytes\":1099511627776}' ;;\n"
            "  *verify*) cat >/dev/null; printf '%s\\n' '{\"verified\":true}' ;;\n"
            "esac\n",
            encoding="utf-8",
        )
        fake_ssh.chmod(0o755)
        fake_rsync = self.root / "rsync"
        fake_rsync.write_text(
            "#!/bin/sh\n" f"printf 'rsync %s\\n' \"$*\" >> {command_log}\n",
            encoding="utf-8",
        )
        fake_rsync.chmod(0o755)
        identity = self.root / "publisher-key"
        identity.write_text("test key", encoding="utf-8")

        request_id = "req-123"
        routes = {
            "/api/requests": {"requests": [{"id": request_id}]},
            f"/api/requests/{request_id}": {
                "downloadHistory": [{"torrentHash": "c" * 40}],
                "id": request_id,
                "status": "downloaded",
                "audiobook": {
                    "asin": "B123",
                    "filePath": str(book_dir),
                    "status": "completed",
                },
                "jobs": [
                    {
                        "status": "completed",
                        "type": "organize_files",
                        "result": {
                            "errors": [],
                            "success": True,
                            "targetPath": str(book_dir),
                        },
                    }
                ],
            },
            "/api/libraries/lib-1/items": {"results": []},
        }
        server, base_url = self.start_api(routes)
        self.addCleanup(self.stop_api, server)
        token_file = self.root / "token"
        token_file.write_text("secret-token\n", encoding="utf-8")
        self.config_path.write_text(
            json.dumps(
                {
                    "abs_library_id": "lib-1",
                    "abs_token_file": str(token_file),
                    "abs_url": base_url,
                    "allowed_extensions": [".m4b", ".m4a", ".mp3", ".flac"],
                    "ffprobe_bin": str(ffprobe),
                    "max_release_gib": 20,
                    "min_local_free_gib": 0,
                    "min_remote_free_gib": 200,
                    "publisher_identity_file": str(identity),
                    "remote_host": "moscow",
                    "rmab_token_file": str(token_file),
                    "rmab_url": base_url,
                    "rsync_bin": str(fake_rsync),
                    "ssh_bin": str(fake_ssh),
                    "stability_seconds": 0,
                    "staging_root": str(self.staging_dir),
                    "state_dir": str(self.state_dir),
                }
            ),
            encoding="utf-8",
        )

        result = self.run_publisher("run-once", "--execute", "--json")

        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(result.stdout)
        self.assertEqual(output["action"], "published")
        ledger = json.loads((self.state_dir / "ledger.json").read_text())
        self.assertIn(request_id, ledger["publications"])
        self.assertEqual(
            ledger["publications"][request_id]["manifest"]["manifest_id"],
            output["manifest_id"],
        )
        self.assertEqual(ledger["publications"][request_id]["torrent_hash"], "c" * 40)
        commands = command_log.read_text()
        self.assertIn("capacity", commands)
        self.assertIn(f"prepare {request_id}", commands)
        self.assertIn("rsync ", commands)
        self.assertIn(f"verify {request_id}", commands)
        self.assertIn(f"promote {request_id}", commands)
        self.assertNotIn("--protect-args", commands)
        self.assertIn("UpdateHostKeys=no", commands)

    def test_unpublish_requires_execute_and_updates_the_ledger(self) -> None:
        self.state_dir.mkdir()
        manifest_id = "a" * 64
        ledger = {
            "pending": {},
            "publications": {
                "req-1": {
                    "final_relative_path": "Author/Book B123",
                    "manifest_id": manifest_id,
                    "request_id": "req-1",
                    "status": "published",
                }
            },
        }
        (self.state_dir / "ledger.json").write_text(json.dumps(ledger), encoding="utf-8")
        command_log = self.root / "commands.log"
        fake_ssh = self.root / "ssh"
        fake_ssh.write_text(
            "#!/bin/sh\n" f"printf '%s\\n' \"$*\" >> {command_log}\n",
            encoding="utf-8",
        )
        fake_ssh.chmod(0o755)
        identity = self.root / "publisher-key"
        identity.write_text("test key", encoding="utf-8")
        known_hosts = self.root / "known_hosts"
        known_hosts.write_text("moscow ssh-ed25519 test-host-key\n", encoding="utf-8")
        self.config_path.write_text(
            json.dumps(
                {
                    "known_hosts_file": str(known_hosts),
                    "publisher_identity_file": str(identity),
                    "remote_host": "moscow",
                    "ssh_bin": str(fake_ssh),
                    "staging_root": str(self.staging_dir),
                    "state_dir": str(self.state_dir),
                }
            ),
            encoding="utf-8",
        )

        refused = self.run_publisher("unpublish", manifest_id)
        removed = self.run_publisher("unpublish", manifest_id, "--execute")

        self.assertNotEqual(refused.returncode, 0)
        self.assertIn("unpublish requires --execute", refused.stderr)
        self.assertIn("Author/Book B123", refused.stdout)
        self.assertIn(manifest_id, refused.stdout)
        self.assertEqual(removed.returncode, 0, removed.stderr)
        updated = json.loads((self.state_dir / "ledger.json").read_text())
        self.assertEqual(updated["publications"]["req-1"]["status"], "unpublished")
        self.assertIn(
            f"unpublish {manifest_id} 'Author/Book B123'", command_log.read_text()
        )
        self.assertIn("StrictHostKeyChecking=yes", command_log.read_text())
        self.assertIn(
            f"UserKnownHostsFile={known_hosts}", command_log.read_text()
        )

    def test_execute_failure_persists_a_block(self) -> None:
        book_dir = self.staging_dir / "Author" / "Book B123"
        book_dir.mkdir(parents=True)
        (book_dir / "book.m4b").write_bytes(b"audio-data")
        ffprobe = self.root / "ffprobe"
        ffprobe.write_text(
            "#!/bin/sh\nprintf '%s\\n' '{\"format\":{\"duration\":\"60\"}}'\n",
            encoding="utf-8",
        )
        ffprobe.chmod(0o755)
        failing_ssh = self.root / "ssh"
        failing_ssh.write_text(
            "#!/bin/sh\nprintf '%s\\n' 'network unavailable' >&2\nexit 42\n",
            encoding="utf-8",
        )
        failing_ssh.chmod(0o755)
        identity = self.root / "key"
        identity.write_text("test key", encoding="utf-8")
        token_file = self.root / "token"
        token_file.write_text("token", encoding="utf-8")
        routes = {
            "/api/requests": {"requests": [{"id": "req-1"}]},
            "/api/requests/req-1": {
                "id": "req-1",
                "status": "downloaded",
                "audiobook": {
                    "asin": "B123",
                    "filePath": str(book_dir),
                    "status": "completed",
                },
                "jobs": [
                    {
                        "status": "completed",
                        "type": "organize_files",
                        "result": {
                            "errors": [],
                            "success": True,
                            "targetPath": str(book_dir),
                        },
                    }
                ],
            },
            "/api/libraries/lib-1/items": {"results": []},
        }
        server, base_url = self.start_api(routes)
        self.addCleanup(self.stop_api, server)
        self.config_path.write_text(
            json.dumps(
                {
                    "abs_library_id": "lib-1",
                    "abs_token_file": str(token_file),
                    "abs_url": base_url,
                    "allowed_extensions": [".m4b"],
                    "ffprobe_bin": str(ffprobe),
                    "max_release_gib": 20,
                    "min_local_free_gib": 0,
                    "publisher_identity_file": str(identity),
                    "remote_host": "moscow",
                    "rmab_token_file": str(token_file),
                    "rmab_url": base_url,
                    "ssh_bin": str(failing_ssh),
                    "stability_seconds": 0,
                    "staging_root": str(self.staging_dir),
                    "state_dir": str(self.state_dir),
                }
            ),
            encoding="utf-8",
        )

        failed = self.run_publisher("run-once", "--execute")
        status = self.run_publisher("status", "--json")

        self.assertNotEqual(failed.returncode, 0)
        self.assertTrue(json.loads(status.stdout)["blocked"])
        self.assertIn("network unavailable", json.loads(status.stdout)["blocked_reason"])

    def test_execute_duplicate_validation_persists_a_block(self) -> None:
        book_dir = self.staging_dir / "Author" / "Book B123"
        book_dir.mkdir(parents=True)
        (book_dir / "book.m4b").write_bytes(b"audio")
        ffprobe = self.root / "ffprobe"
        ffprobe.write_text(
            "#!/bin/sh\nprintf '%s\\n' '{\"format\":{\"duration\":\"60\"}}'\n"
        )
        ffprobe.chmod(0o755)
        token_file = self.root / "token"
        token_file.write_text("token")
        routes = {
            "/api/requests": {"requests": [{"id": "req-duplicate"}]},
            "/api/requests/req-duplicate": {
                "id": "req-duplicate",
                "status": "downloaded",
                "audiobook": {
                    "asin": "B123",
                    "filePath": str(book_dir),
                    "status": "completed",
                },
                "jobs": [
                    {
                        "status": "completed",
                        "type": "organize_files",
                        "result": {
                            "errors": [],
                            "success": True,
                            "targetPath": str(book_dir),
                        },
                    }
                ],
            },
            "/api/libraries/lib-1/items": {
                "results": [{"media": {"metadata": {"asin": "B123"}}}]
            },
        }
        server, base_url = self.start_api(routes)
        self.addCleanup(self.stop_api, server)
        self.config_path.write_text(
            json.dumps(
                {
                    "abs_library_id": "lib-1",
                    "abs_token_file": str(token_file),
                    "abs_url": base_url,
                    "allowed_extensions": [".m4b"],
                    "ffprobe_bin": str(ffprobe),
                    "max_release_gib": 20,
                    "min_local_free_gib": 0,
                    "rmab_token_file": str(token_file),
                    "rmab_url": base_url,
                    "stability_seconds": 0,
                    "staging_root": str(self.staging_dir),
                    "state_dir": str(self.state_dir),
                }
            )
        )

        failed = self.run_publisher("run-once", "--execute")
        status = self.run_publisher("status", "--json")

        self.assertNotEqual(failed.returncode, 0)
        self.assertIn("duplicate ASIN", failed.stderr)
        self.assertTrue(json.loads(status.stdout)["blocked"])

    def test_cleanup_removes_only_confirmed_staging_after_the_safety_window(self) -> None:
        self.state_dir.mkdir()
        book_dir = self.staging_dir / "Author" / "Book B123"
        book_dir.mkdir(parents=True)
        (book_dir / "book.m4b").write_bytes(b"audio")
        ledger = {
            "pending": {},
            "publications": {
                "req-1": {
                    "abs_confirmed_at_epoch": int(time.time()) - 25 * 60 * 60,
                    "final_relative_path": "Author/Book B123",
                    "manifest_id": "a" * 64,
                    "request_id": "req-1",
                    "staging_path": str(book_dir),
                    "status": "published",
                }
            },
        }
        (self.state_dir / "ledger.json").write_text(json.dumps(ledger), encoding="utf-8")
        self.config_path.write_text(
            json.dumps(
                {
                    "staging_retention_hours": 24,
                    "staging_root": str(self.staging_dir),
                    "state_dir": str(self.state_dir),
                }
            ),
            encoding="utf-8",
        )

        dry_run = self.run_publisher("cleanup", "--json")
        executed = self.run_publisher("cleanup", "--execute", "--json")

        self.assertEqual(dry_run.returncode, 0, dry_run.stderr)
        self.assertEqual(json.loads(dry_run.stdout)["eligible"], ["req-1"])
        self.assertEqual(executed.returncode, 0, executed.stderr)
        self.assertFalse(book_dir.exists())
        updated = json.loads((self.state_dir / "ledger.json").read_text())
        self.assertEqual(updated["publications"]["req-1"]["status"], "published")
        self.assertIsInstance(
            updated["publications"]["req-1"]["staging_cleaned_at_epoch"], int
        )

    def test_execute_reconciles_a_published_book_seen_by_audiobookshelf(self) -> None:
        self.state_dir.mkdir()
        token_file = self.root / "token"
        token_file.write_text("token", encoding="utf-8")
        ledger = {
            "pending": {},
            "publications": {
                "req-1": {
                    "asin": "B123",
                    "final_relative_path": "Author/Book B123",
                    "manifest_id": "a" * 64,
                    "request_id": "req-1",
                    "status": "published",
                }
            },
        }
        (self.state_dir / "ledger.json").write_text(json.dumps(ledger), encoding="utf-8")
        routes = {
            "/api/requests": {"requests": []},
            "/api/libraries/lib-1/items": {
                "results": [
                    {
                        "path": "/readmeabook/Author/Book B123",
                        "media": {"metadata": {"asin": "B123"}},
                    }
                ]
            },
        }
        server, base_url = self.start_api(routes)
        self.addCleanup(self.stop_api, server)
        self.config_path.write_text(
            json.dumps(
                {
                    "abs_library_id": "lib-1",
                    "abs_token_file": str(token_file),
                    "abs_url": base_url,
                    "min_local_free_gib": 0,
                    "rmab_token_file": str(token_file),
                    "rmab_url": base_url,
                    "staging_root": str(self.staging_dir),
                    "state_dir": str(self.state_dir),
                }
            ),
            encoding="utf-8",
        )

        result = self.run_publisher("run-once", "--execute", "--json")

        self.assertEqual(result.returncode, 0, result.stderr)
        updated = json.loads((self.state_dir / "ledger.json").read_text())
        self.assertIsInstance(
            updated["publications"]["req-1"]["abs_confirmed_at_epoch"], int
        )

    def test_execute_reconciles_a_manual_book_by_exact_path_without_asin(self) -> None:
        self.state_dir.mkdir()
        token_file = self.root / "token"
        token_file.write_text("token", encoding="utf-8")
        ledger = {
            "pending": {},
            "publications": {
                "req-manual": {
                    "asin": "manual:rutracker:6887881",
                    "final_relative_path": "Конофальский Борис/Кляксы manual:rutracker:6887881",
                    "manifest_id": "b" * 64,
                    "request_id": "req-manual",
                    "status": "published",
                }
            },
        }
        (self.state_dir / "ledger.json").write_text(json.dumps(ledger), encoding="utf-8")
        routes = {
            "/api/requests": {"requests": []},
            "/api/libraries/lib-1/items": {
                "results": [
                    {
                        "path": "/readmeabook/Конофальский Борис/Кляксы manual:rutracker:6887881",
                        "media": {"metadata": {"asin": None}},
                    }
                ]
            },
        }
        server, base_url = self.start_api(routes)
        self.addCleanup(self.stop_api, server)
        self.config_path.write_text(
            json.dumps(
                {
                    "abs_library_id": "lib-1",
                    "abs_token_file": str(token_file),
                    "abs_url": base_url,
                    "min_local_free_gib": 0,
                    "rmab_token_file": str(token_file),
                    "rmab_url": base_url,
                    "staging_root": str(self.staging_dir),
                    "state_dir": str(self.state_dir),
                }
            ),
            encoding="utf-8",
        )

        result = self.run_publisher("run-once", "--execute", "--json")

        self.assertEqual(result.returncode, 0, result.stderr)
        updated = json.loads((self.state_dir / "ledger.json").read_text())
        self.assertIsInstance(
            updated["publications"]["req-manual"]["abs_confirmed_at_epoch"], int
        )

    def test_status_counts_only_currently_published_records(self) -> None:
        self.state_dir.mkdir()
        (self.state_dir / "ledger.json").write_text(
            json.dumps(
                {
                    "pending": {},
                    "publications": {
                        "req-active": {"status": "published"},
                        "req-cleaned": {
                            "staging_cleaned_at_epoch": 1,
                            "status": "published",
                        },
                        "req-removed": {"status": "unpublished"},
                    },
                }
            ),
            encoding="utf-8",
        )

        result = self.run_publisher("status", "--json")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["published"], 2)

    def test_execute_retry_is_idempotent_after_abs_has_seen_the_book(self) -> None:
        book_dir = self.staging_dir / "Author" / "Book B123"
        book_dir.mkdir(parents=True)
        audio = book_dir / "book.m4b"
        audio.write_bytes(b"audio-data")
        ffprobe = self.root / "ffprobe"
        ffprobe.write_text(
            "#!/bin/sh\nprintf '%s\\n' '{\"format\":{\"duration\":\"60\"}}'\n",
            encoding="utf-8",
        )
        ffprobe.chmod(0o755)
        token_file = self.root / "token"
        token_file.write_text("token", encoding="utf-8")
        body = {
            "audio_files": 1,
            "files": [
                {
                    "duration": 60.0,
                    "path": "book.m4b",
                    "sha256": hashlib.sha256(b"audio-data").hexdigest(),
                    "size": len(b"audio-data"),
                }
            ],
        }
        manifest_id = hashlib.sha256(
            json.dumps(body, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        self.state_dir.mkdir()
        (self.state_dir / "ledger.json").write_text(
            json.dumps(
                {
                    "pending": {},
                    "publications": {
                        "req-1": {
                            "asin": "B123",
                            "final_relative_path": "Author/Book B123",
                            "manifest_id": manifest_id,
                            "request_id": "req-1",
                            "status": "published",
                        }
                    },
                }
            ),
            encoding="utf-8",
        )
        routes = {
            "/api/requests": {"requests": [{"id": "req-1"}]},
            "/api/requests/req-1": {
                "id": "req-1",
                "status": "downloaded",
                "audiobook": {
                    "asin": "B123",
                    "filePath": str(book_dir),
                    "status": "completed",
                },
                "jobs": [
                    {
                        "status": "completed",
                        "type": "organize_files",
                        "result": {
                            "errors": [],
                            "success": True,
                            "targetPath": str(book_dir),
                        },
                    }
                ],
            },
            "/api/libraries/lib-1/items": {
                "results": [
                    {
                        "path": "/readmeabook/Author/Book B123",
                        "media": {"metadata": {"asin": "B123"}},
                    }
                ]
            },
        }
        server, base_url = self.start_api(routes)
        self.addCleanup(self.stop_api, server)
        self.config_path.write_text(
            json.dumps(
                {
                    "abs_library_id": "lib-1",
                    "abs_token_file": str(token_file),
                    "abs_url": base_url,
                    "allowed_extensions": [".m4b"],
                    "ffprobe_bin": str(ffprobe),
                    "max_release_gib": 20,
                    "min_local_free_gib": 0,
                    "rmab_token_file": str(token_file),
                    "rmab_url": base_url,
                    "stability_seconds": 0,
                    "staging_root": str(self.staging_dir),
                    "state_dir": str(self.state_dir),
                }
            ),
            encoding="utf-8",
        )

        result = self.run_publisher("run-once", "--execute", "--json")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["action"], "already-published")


if __name__ == "__main__":
    unittest.main()
