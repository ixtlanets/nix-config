from __future__ import annotations

from datetime import UTC, datetime
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from audiobook_ops.interface import AudiobookOperations
from audiobook_ops.mcp_adapter import MCPAdapter

from test_domain_interface import (
    FakeCatalogAdapter,
    FakeClock,
    FakeExternalActionAdapter,
    FakeReleaseAdapter,
)


BUNDLE = Path(__file__).resolve().parents[1]


class EmergencyCLITests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.database = Path(self.temporary_directory.name) / "state.sqlite3"
        self.releases = FakeReleaseAdapter()
        self.operations = AudiobookOperations.open(
            self.database,
            clock=FakeClock(datetime(2026, 9, 13, tzinfo=UTC)),
            release_adapter=self.releases,
            external_action_adapter=FakeExternalActionAdapter(),
            catalog_adapter=FakeCatalogAdapter(),
        )
        candidate = self.releases.inspect("candidate-one")
        plan = self.operations.invoke(
            "request_plan",
            {
                "candidate_id": candidate["candidate_id"],
                "candidate_revision": candidate["revision"],
                "work": {
                    "title": "Кляксы",
                    "authors": ["Борис Конофальский"],
                    "series": [{"name": "Глубокий рейд", "sequence": "4"}],
                },
                "audio_edition": {"narrators": ["Один"]},
                "origin_conversation_id": "conversation-one",
            },
        )
        self.task = self.operations.invoke(
            "request_apply",
            {
                "plan_id": plan["plan_id"],
                "revision": plan["revision"],
                "idempotency_key": "request-key-one",
            },
            mutation_authorized=True,
        )

    def tearDown(self) -> None:
        self.operations.close()
        self.temporary_directory.cleanup()

    def cli(self, *arguments: str) -> subprocess.CompletedProcess[str]:
        environment = os.environ.copy()
        environment["PYTHONPATH"] = str(BUNDLE / "src")
        return subprocess.run(
            [
                sys.executable,
                "-m",
                "audiobook_ops.cli",
                "--database",
                str(self.database),
                *arguments,
            ],
            cwd=BUNDLE,
            env=environment,
            text=True,
            capture_output=True,
        )

    def test_cli_and_mcp_observe_the_same_domain_result(self) -> None:
        result = self.cli("task", "list")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            json.loads(result.stdout),
            MCPAdapter(self.operations).call("task_list", {}),
        )

    def test_cli_mutation_requires_execute_and_replays_through_mcp(self) -> None:
        arguments = {
            "task_id": self.task["task_id"],
            "expected_revision": self.task["revision"],
            "idempotency_key": "cancel-key-one",
        }
        preview = self.cli(
            "task",
            "cancel",
            self.task["task_id"],
            "--expected-revision",
            str(self.task["revision"]),
            "--idempotency-key",
            "cancel-key-one",
        )
        self.assertEqual(preview.returncode, 2)
        self.assertIn("--execute", preview.stderr)
        self.assertEqual(
            self.operations.invoke("task_get", {"task_id": self.task["task_id"]})[
                "state"
            ],
            "queued",
        )

        executed = self.cli(
            "task",
            "cancel",
            self.task["task_id"],
            "--expected-revision",
            str(self.task["revision"]),
            "--idempotency-key",
            "cancel-key-one",
            "--execute",
        )
        self.assertEqual(executed.returncode, 0, executed.stderr)
        self.assertEqual(
            json.loads(executed.stdout),
            MCPAdapter(self.operations).call(
                "task_cancel", arguments, mutation_authorized=True
            ),
        )


if __name__ == "__main__":
    unittest.main()
