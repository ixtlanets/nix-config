from __future__ import annotations

from datetime import UTC, datetime
import hashlib
from pathlib import Path
import tempfile
import unittest

from audiobook_ops.interface import AudiobookOperations, OperationError
from audiobook_ops.publisher import PublicationCoordinator, PublicationValidator

from test_domain_interface import (
    FakeCatalogAdapter,
    FakeClock,
    FakeExternalActionAdapter,
    FakeReleaseAdapter,
)


class FakeProbe:
    def __init__(self, duration: float = 42.5) -> None:
        self._duration = duration

    def duration(self, _path: Path) -> float:
        return self._duration


class FakeRemote:
    def __init__(self) -> None:
        self.calls: list[str] = []
        self.manifest_id: str | None = None
        self.promoted = False
        self.fail_after: str | None = None
        self.failed = False

    def _effect(self, name: str) -> None:
        self.calls.append(name)
        if self.fail_after == name and not self.failed:
            self.failed = True
            raise OperationError(f"simulated crash after {name}")

    def capacity_bytes(self) -> int:
        self.calls.append("capacity")
        return 300 * 1024**3

    def prepare(self, _task_id: str) -> None:
        self._effect("prepare")

    def transfer(self, _task_id: str, _source: Path) -> None:
        self._effect("transfer")

    def verify(self, _task_id: str, manifest: dict[str, object]) -> str:
        self.manifest_id = str(manifest["manifest_id"])
        self._effect("verify")
        return self.manifest_id

    def promote(
        self, _task_id: str, _final_relative_path: str, manifest_id: str
    ) -> None:
        if manifest_id != self.manifest_id:
            raise OperationError("remote manifest changed")
        self.promoted = True
        self._effect("promote")


class CrashAfterCheckpoint:
    def __init__(self, status: str) -> None:
        self.status = status
        self.triggered = False

    def __call__(self, status: str) -> None:
        if status == self.status and not self.triggered:
            self.triggered = True
            raise RuntimeError(f"simulated crash after {status} checkpoint")


class PublicationPublisherTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.database = self.root / "state.sqlite3"
        self.staging = self.root / "staging"
        self.staging.mkdir()
        self.clock = FakeClock(datetime(2026, 9, 13, tzinfo=UTC))
        self.adapters = {
            "clock": self.clock,
            "release_adapter": FakeReleaseAdapter(),
            "external_action_adapter": FakeExternalActionAdapter(),
            "catalog_adapter": FakeCatalogAdapter(),
        }
        self.operations = AudiobookOperations.open(self.database, **self.adapters)

    def tearDown(self) -> None:
        self.operations.close()
        self.temporary_directory.cleanup()

    def ready_task(self, extension: str = ".m4b") -> tuple[dict[str, object], bytes]:
        plan = self.operations.invoke(
            "request_plan",
            {
                "candidate_id": "candidate-one",
                "candidate_revision": "source-revision-one",
                "work": {
                    "title": "Кляксы",
                    "authors": ["Борис Конофальский"],
                    "series": [{"name": "Глубокий рейд", "sequence": "4"}],
                },
                "audio_edition": {"narrators": ["Чтец"]},
                "origin_conversation_id": "conversation-one",
            },
        )
        task = self.operations.invoke(
            "request_apply",
            {
                "plan_id": plan["plan_id"],
                "revision": plan["revision"],
                "idempotency_key": "publisher-request-one",
            },
            mutation_authorized=True,
        )
        task = self.operations.claim_next_task("acquisition")
        task = self.operations.transition_task(
            task["task_id"], task["revision"], "validating"
        )
        content = b"byte-identical-audio-" + extension.encode()
        task_staging = self.staging / str(task["task_id"])
        task_staging.mkdir()
        audio = task_staging / f"book{extension}"
        audio.write_bytes(content)
        manifest = [
            {
                "relative_path": audio.name,
                "size_bytes": len(content),
                "sha256": hashlib.sha256(content).hexdigest(),
                "duration_seconds": 42.5,
            }
        ]
        ready = self.operations.record_validated_artifact(
            str(task["task_id"]),
            int(task["revision"]),
            "a" * 40,
            {"staging_id": task["task_id"], "manifest": manifest},
        )
        return ready, content

    def coordinator(
        self,
        remote: FakeRemote,
        checkpoint_hook=lambda _status: None,
        probe: FakeProbe | None = None,
    ) -> PublicationCoordinator:
        return PublicationCoordinator(
            self.operations,
            PublicationValidator(
                staging_root=self.staging,
                probe=probe or FakeProbe(),
                local_free_bytes=lambda: 300 * 1024**3,
                stability_hook=lambda: None,
            ),
            remote,
            publisher_id="publisher-one",
            checkpoint_hook=checkpoint_hook,
        )

    def reopen(self) -> None:
        self.operations.close()
        self.operations = AudiobookOperations.open(self.database, **self.adapters)

    def test_publication_reaches_awaiting_abs_with_exact_manifest_and_path(self) -> None:
        ready, _content = self.ready_task()
        remote = FakeRemote()

        result = self.coordinator(remote).reconcile_once()

        self.assertEqual(result["task"]["state"], "awaiting_abs")
        self.assertEqual(result["publication"]["status"], "acknowledged")
        self.assertEqual(
            result["publication"]["final_relative_path"],
            "Борис Конофальский/Глубокий рейд/04 - Кляксы",
        )
        self.assertEqual(
            result["publication"]["manifest_id"],
            self.operations.validated_artifact(str(ready["task_id"]))["manifest_id"],
        )
        self.assertEqual(
            remote.calls,
            ["capacity", "prepare", "transfer", "verify", "promote"],
        )

    def test_restart_resumes_after_every_durable_checkpoint(self) -> None:
        for status in (
            "validated",
            "prepared",
            "transferred",
            "remote_verified",
            "promoted",
            "acknowledged",
        ):
            with self.subTest(status=status):
                if self.operations.invoke("task_list", {})["tasks"]:
                    self.operations.close()
                    self.temporary_directory.cleanup()
                    self.setUp()
                self.ready_task()
                remote = FakeRemote()
                crash = CrashAfterCheckpoint(status)
                with self.assertRaisesRegex(RuntimeError, "simulated crash"):
                    self.coordinator(remote, crash).reconcile_once()
                self.reopen()

                resumed = self.coordinator(remote).reconcile_once()

                if status == "acknowledged":
                    self.assertIsNone(resumed)
                    task = self.operations.invoke("task_list", {})["tasks"][0]
                    self.assertEqual(task["state"], "awaiting_abs")
                else:
                    self.assertEqual(resumed["task"]["state"], "awaiting_abs")
                self.assertTrue(remote.promoted)

    def test_external_success_before_checkpoint_is_replayed_safely(self) -> None:
        for phase in ("prepare", "transfer", "verify", "promote"):
            with self.subTest(phase=phase):
                if self.operations.invoke("task_list", {})["tasks"]:
                    self.operations.close()
                    self.temporary_directory.cleanup()
                    self.setUp()
                self.ready_task(".mp3")
                remote = FakeRemote()
                remote.fail_after = phase
                with self.assertRaisesRegex(OperationError, "simulated crash"):
                    self.coordinator(remote).reconcile_once()
                self.reopen()

                resumed = self.coordinator(remote).reconcile_once()

                self.assertEqual(resumed["task"]["state"], "awaiting_abs")
                self.assertTrue(remote.promoted)
                self.assertGreaterEqual(remote.calls.count(phase), 2)

    def test_local_manifest_change_blocks_before_remote_write(self) -> None:
        task, _content = self.ready_task()
        (self.staging / str(task["task_id"]) / "book.m4b").write_bytes(b"changed")
        remote = FakeRemote()

        with self.assertRaisesRegex(OperationError, "manifest changed"):
            self.coordinator(remote).reconcile_once()

        self.assertEqual(remote.calls, [])
        publication = self.operations.outstanding_publication()
        self.assertEqual(publication["publication"]["status"], "claimed")

    def test_probe_version_duration_difference_does_not_block_publication(self) -> None:
        ready, _content = self.ready_task(".mp3")
        remote = FakeRemote()

        result = self.coordinator(remote, probe=FakeProbe(42.45)).reconcile_once()

        self.assertEqual(result["task"]["state"], "awaiting_abs")
        artifact = self.operations.validated_artifact(str(ready["task_id"]))
        self.assertEqual(result["publication"]["manifest"], artifact["manifest"])
        self.assertEqual(
            result["publication"]["manifest_id"], artifact["manifest_id"]
        )
        self.assertTrue(remote.promoted)


if __name__ == "__main__":
    unittest.main()
