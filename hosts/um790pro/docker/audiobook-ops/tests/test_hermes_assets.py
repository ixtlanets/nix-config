from __future__ import annotations

import json
from pathlib import Path
import unittest

from audiobook_ops.contract import tool_contracts


BUNDLE = Path(__file__).resolve().parents[1]
HERMES = BUNDLE / "hermes"


class HermesAssetTests(unittest.TestCase):
    def test_mcp_fragment_is_fail_closed_and_matches_contract(self) -> None:
        payload = json.loads((HERMES / "mcp" / "audiobook-ops.json").read_text())
        server = payload["mcp_servers"]["audiobook-ops"]
        expected = {str(tool["name"]) for tool in tool_contracts()}

        self.assertEqual(server["url"], "http://100.95.213.117:8300/mcp")
        self.assertTrue(server["enabled"])
        self.assertEqual(server["trust"], "untrusted")
        self.assertTrue(server["strict_redirect_headers"])
        self.assertEqual(
            server["headers"],
            {"Authorization": "Bearer ${MCP_AUDIOBOOK_OPS_API_KEY}"},
        )
        self.assertEqual(set(server["tools"]["include"]), expected)
        self.assertEqual(len(server["tools"]["include"]), len(expected))
        self.assertNotIn("secret", json.dumps(payload).lower())

    def test_normal_skill_encodes_the_safe_russian_workflow(self) -> None:
        text = (HERMES / "skills" / "audiobooks" / "SKILL.md").read_text()

        self.assertTrue(text.startswith("---\n"))
        self.assertIn("name: audiobooks", text)
        self.assertIn("русск", text.lower())
        self.assertIn("Найди аудиокнигу", text)
        self.assertIn("library_search", text)
        self.assertIn("release_search", text)
        self.assertIn("request_plan", text)
        self.assertIn("request_apply", text)
        self.assertIn("metadata_plan", text)
        self.assertIn("metadata_undo", text)
        self.assertIn("provenance", text.lower())
        self.assertIn("confidence", text.lower())
        self.assertIn("origin.py", text)
        for forbidden in ("curl ", "ssh ", "transmission-remote", "/api/"):
            self.assertNotIn(forbidden, text.lower())

    def test_admin_skill_is_narrow_and_keeps_restore_owner_gated(self) -> None:
        text = (HERMES / "skills" / "audiobook-admin" / "SKILL.md").read_text()

        self.assertIn("name: audiobook-admin", text)
        self.assertIn("task_retry", text)
        self.assertIn("system_status", text)
        self.assertIn("owner", text.lower())
        self.assertIn("restore", text.lower())
        self.assertNotIn("обычн", text.split("---", 2)[1].lower())

    def test_runbook_has_install_verify_and_rollback_without_secrets(self) -> None:
        text = (HERMES / "HERMES-RUNBOOK.md").read_text()

        for required in (
            "hermes mcp test audiobook-ops",
            "hermes mcp remove audiobook-ops",
            "hermes cron create",
            "hermes cron remove",
            "hermes gateway restart",
            "MCP_AUDIOBOOK_OPS_API_KEY",
        ):
            self.assertIn(required, text)
        self.assertNotIn("Bearer ey", text)
        self.assertIn("--script audiobook_notifications.py", text)


if __name__ == "__main__":
    unittest.main()
