from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import importlib.util
import io
import json
import os
from pathlib import Path
import tempfile
from threading import Thread
import unittest
from unittest.mock import patch


BUNDLE = Path(__file__).resolve().parents[1]
POLLER_PATH = BUNDLE / "hermes" / "scripts" / "audiobook_notifications.py"
ORIGIN_PATH = BUNDLE / "hermes" / "skills" / "audiobooks" / "scripts" / "origin.py"


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class MCPHandler(BaseHTTPRequestHandler):
    events: list[dict[str, object]] = []
    bearer = "test-bearer-value"
    requests: list[dict[str, object]] = []

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length", "0"))
        request = json.loads(self.rfile.read(length))
        type(self).requests.append(
            {"authorization": self.headers.get("Authorization"), "body": request}
        )
        if self.headers.get("Authorization") != f"Bearer {self.bearer}":
            self.send_response(401)
            self.end_headers()
            return
        method = request["method"]
        if method == "initialize":
            result: object = {
                "protocolVersion": request["params"]["protocolVersion"],
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": "test", "version": "1"},
            }
        elif method == "tools/call":
            after = request["params"]["arguments"]["after_event_id"]
            events = [event for event in self.events if event["event_id"] > after]
            result = {
                "content": [],
                "structuredContent": {
                    "events": events,
                    "cursor": events[-1]["event_id"] if events else after,
                },
                "isError": False,
            }
        else:
            result = {}
        body = json.dumps({"jsonrpc": "2.0", "id": request["id"], "result": result}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, _format: str, *_args: object) -> None:
        return


class NotificationPollerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.poller = load_module(POLLER_PATH, "audiobook_notifications_test")
        MCPHandler.requests = []
        MCPHandler.events = [
            {
                "event_id": 1,
                "task_id": "task-one",
                "kind": "verified",
                "origin_conversation_id": "telegram:42424242",
                "reason": "Книга опубликована",
                "created_at": "2026-09-13T10:00:00Z",
            },
            {
                "event_id": 2,
                "task_id": "task-two",
                "kind": "needs_input",
                "origin_conversation_id": "telegram:42424242",
                "reason": "Нужно выбрать издание",
                "created_at": "2026-09-13T10:01:00Z",
            },
            {
                "event_id": 3,
                "task_id": "task-three",
                "kind": "failed",
                "origin_conversation_id": "telegram:42424242",
                "reason": "Повторы исчерпаны",
                "created_at": "2026-09-13T10:02:00Z",
            },
        ]
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), MCPHandler)
        self.thread = Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.cursor = self.root / "cursor"
        self.sent = self.root / "sent.jsonl"
        self.hermes = self.root / "hermes"
        self.hermes.write_text(
            "#!/usr/bin/env python3\n"
            "import json, os, pathlib, sys\n"
            "record = {'args': sys.argv[1:], 'bearer_present': 'MCP_AUDIOBOOK_OPS_API_KEY' in os.environ}\n"
            "pathlib.Path(os.environ['TEST_SENT']).open('a').write(json.dumps(record) + '\\n')\n"
        )
        self.hermes.chmod(0o755)
        self.config = self.root / "config.json"
        self.config.write_text(
            json.dumps(
                {
                    "mcp_url": f"http://127.0.0.1:{self.server.server_port}/mcp",
                    "bearer_env": "MCP_AUDIOBOOK_OPS_API_KEY",
                    "cursor_file": str(self.cursor),
                    "hermes_bin": str(self.hermes),
                    "allowed_origins": ["telegram:42424242"],
                    "timeout_seconds": 2,
                    "page_size": 50,
                }
            )
        )
        self.environment = {
            "MCP_AUDIOBOOK_OPS_API_KEY": MCPHandler.bearer,
            "TEST_SENT": str(self.sent),
        }

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.temporary.cleanup()

    def run_poller(self) -> tuple[int, str, str]:
        stdout = io.StringIO()
        stderr = io.StringIO()
        with patch.dict(os.environ, self.environment, clear=True):
            with redirect_stdout(stdout), redirect_stderr(stderr):
                code = self.poller.main(["--config", str(self.config)])
        return code, stdout.getvalue(), stderr.getvalue()

    def delivery_records(self) -> list[dict[str, object]]:
        if not self.sent.exists():
            return []
        return [json.loads(line) for line in self.sent.read_text().splitlines()]

    def sent_commands(self) -> list[list[str]]:
        return [record["args"] for record in self.delivery_records()]

    def test_delivers_only_durable_outcomes_and_deduplicates_by_cursor(self) -> None:
        code, stdout, stderr = self.run_poller()

        self.assertEqual((code, stdout, stderr), (0, "", ""))
        commands = self.sent_commands()
        self.assertEqual(len(commands), 3)
        self.assertTrue(all(command[:2] == ["send", "--to"] for command in commands))
        self.assertTrue(all(command[2] == "telegram:42424242" for command in commands))
        self.assertIn("event #1", commands[0][3])
        self.assertIn("event #2", commands[1][3])
        self.assertIn("event #3", commands[2][3])
        self.assertTrue(
            all(record["bearer_present"] is False for record in self.delivery_records())
        )
        self.assertEqual(self.cursor.read_text(), "3\n")
        self.assertEqual(self.cursor.stat().st_mode & 0o777, 0o600)
        self.assertEqual(
            MCPHandler.requests[0]["authorization"],
            f"Bearer {MCPHandler.bearer}",
        )

        code, stdout, stderr = self.run_poller()
        self.assertEqual((code, stdout, stderr), (0, "", ""))
        self.assertEqual(len(self.sent_commands()), 3)

    def test_rejects_unapproved_origin_without_advancing_cursor(self) -> None:
        MCPHandler.events[0]["origin_conversation_id"] = "telegram:999"

        code, stdout, stderr = self.run_poller()

        self.assertEqual(code, 1)
        self.assertEqual(stdout, "")
        self.assertIn("origin_not_allowed", stderr)
        self.assertNotIn(MCPHandler.bearer, stderr)
        self.assertFalse(self.cursor.exists())
        self.assertEqual(self.sent_commands(), [])

    def test_failed_delivery_does_not_advance_cursor_or_leak_bearer(self) -> None:
        self.hermes.write_text("#!/bin/sh\necho delivery-failed >&2\nexit 7\n")
        self.hermes.chmod(0o755)

        code, stdout, stderr = self.run_poller()

        self.assertEqual(code, 1)
        self.assertEqual(stdout, "")
        self.assertIn("delivery_failed", stderr)
        self.assertNotIn(MCPHandler.bearer, stderr)
        self.assertFalse(self.cursor.exists())

    def test_rejects_public_or_redirecting_mcp_endpoints(self) -> None:
        for url in (
            "https://example.com/mcp",
            "http://0.0.0.0/mcp",
            "http://224.0.0.1/mcp",
        ):
            with self.subTest(url=url):
                payload = json.loads(self.config.read_text())
                payload["mcp_url"] = url
                self.config.write_text(json.dumps(payload))
                code, _stdout, stderr = self.run_poller()
                self.assertEqual(code, 1)
                self.assertIn("private_mcp_url_required", stderr)
        self.assertEqual(MCPHandler.requests, [])

    def test_base_allowlist_accepts_the_originating_telegram_thread(self) -> None:
        MCPHandler.events[0]["origin_conversation_id"] = "telegram:42424242:77"

        code, stdout, stderr = self.run_poller()

        self.assertEqual((code, stdout, stderr), (0, "", ""))
        self.assertEqual(self.sent_commands()[0][2], "telegram:42424242:77")

    def test_default_config_path_uses_the_active_hermes_profile(self) -> None:
        with patch.dict(os.environ, {"HERMES_HOME": "/tmp/hermes-profile"}, clear=True):
            self.assertEqual(
                self.poller.default_config_path(),
                Path("/tmp/hermes-profile/audiobook-notifications.json"),
            )


class OriginHelperTests(unittest.TestCase):
    def setUp(self) -> None:
        self.origin = load_module(ORIGIN_PATH, "audiobook_origin_test")

    def test_formats_exact_telegram_origin(self) -> None:
        with patch.dict(
            os.environ,
            {
                "HERMES_SESSION_PLATFORM": "telegram",
                "HERMES_SESSION_CHAT_ID": "42424242",
                "HERMES_SESSION_THREAD_ID": "42",
            },
            clear=True,
        ):
            self.assertEqual(self.origin.current_origin(), "telegram:42424242:42")

    def test_rejects_missing_or_unsupported_origin(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(ValueError):
                self.origin.current_origin()
        with patch.dict(
            os.environ,
            {"HERMES_SESSION_PLATFORM": "shell", "HERMES_SESSION_CHAT_ID": "1"},
            clear=True,
        ):
            with self.assertRaises(ValueError):
                self.origin.current_origin()


if __name__ == "__main__":
    unittest.main()
