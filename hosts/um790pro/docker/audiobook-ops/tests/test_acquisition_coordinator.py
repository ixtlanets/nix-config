from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
import tempfile
import unittest

from audiobook_ops.acquisition_worker import AcquisitionCoordinator
from audiobook_ops.interface import AudiobookOperations, OperationError
from audiobook_ops.validation import CapacitySnapshot, MediaValidator

from test_domain_interface import (
    FakeCatalogAdapter,
    FakeClock,
    FakeExternalActionAdapter,
    FakeReleaseAdapter,
)


class FakeTransmission:
    def __init__(self, release_root: Path) -> None:
        self.release_root = release_root
        self.torrent_hash = "a" * 40
        self.status = "downloading"
        self.rate_download = 100
        self.activity_at_epoch = 0
        self.submit_calls = 0
        self.additions = 0
        self.submitted = False
        self.removals: list[str] = []
        self.fail_operation: str | None = None

    def submit(self, resolution: dict[str, object], idempotency_key: str) -> str:
        if self.fail_operation == "submit":
            raise OperationError("simulated RPC failure")
        self.submit_calls += 1
        self.assert_resolution(resolution, idempotency_key)
        if not self.submitted:
            self.submitted = True
            self.additions += 1
        return self.torrent_hash

    def find(self, idempotency_key: str) -> str | None:
        if self.fail_operation == "find":
            raise OperationError("simulated RPC failure")
        if self.removals:
            return None
        return self.torrent_hash if self.submitted else None

    def observe(self, torrent_hash: str) -> dict[str, object]:
        if self.fail_operation == "observe":
            raise OperationError("simulated RPC failure")
        return {
            "torrent_hash": torrent_hash,
            "status": self.status,
            "percent_done": 1.0 if self.status == "complete" else 0.5,
            "left_bytes": 0 if self.status == "complete" else 100,
            "rate_download": self.rate_download,
            "activity_at_epoch": self.activity_at_epoch,
            "download_root": str(self.release_root),
            "error": "transmission-error" if self.status == "error" else None,
        }

    def remove(self, torrent_hash: str) -> None:
        self.removals.append(torrent_hash)

    @staticmethod
    def assert_resolution(
        resolution: dict[str, object], idempotency_key: str
    ) -> None:
        if not str(resolution.get("magnet_uri", "")).startswith("magnet:"):
            raise AssertionError("missing internal magnet")
        if not idempotency_key.startswith("transmission:"):
            raise AssertionError("unexpected idempotency key")


class FakeProbe:
    def duration(self, _path: Path) -> float:
        return 100.0


class AcquisitionCoordinatorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.downloads = self.root / "downloads"
        self.staging = self.root / "staging"
        self.release = self.downloads / "Кроткая"
        self.release.mkdir(parents=True)
        self.staging.mkdir()
        (self.release / "book.m4b").write_bytes(b"audio bytes")
        self.clock = FakeClock(datetime(2026, 9, 13, tzinfo=UTC))
        self.releases = FakeReleaseAdapter()
        self.catalog = FakeCatalogAdapter()
        self.operations = AudiobookOperations.open(
            self.root / "state.sqlite3",
            clock=self.clock,
            release_adapter=self.releases,
            external_action_adapter=FakeExternalActionAdapter(),
            catalog_adapter=self.catalog,
        )
        self.transmission = FakeTransmission(self.release)
        self.validator = MediaValidator(
            downloads_root=self.downloads,
            staging_root=self.staging,
            probe=FakeProbe(),
            capacity=lambda: CapacitySnapshot(
                working_set_bytes=0,
                local_free_bytes=101 * 1024**3,
                remote_free_bytes=201 * 1024**3,
            ),
            stability_hook=lambda: None,
        )
        self.coordinator = AcquisitionCoordinator(
            self.operations,
            self.transmission,
            self.validator,
            self.clock,
        )

    def tearDown(self) -> None:
        self.operations.close()
        self.temporary_directory.cleanup()

    def create_task(self) -> dict[str, object]:
        plan = self.operations.invoke(
            "request_plan",
            {
                "candidate_id": "candidate-one",
                "candidate_revision": "source-revision-one",
                "work": {"title": "Кроткая", "authors": ["Достоевский"], "series": []},
                "audio_edition": {"narrators": ["Иван"]},
                "origin_conversation_id": "conversation-one",
            },
        )
        return self.operations.invoke(
            "request_apply",
            {
                "plan_id": plan["plan_id"],
                "revision": plan["revision"],
                "idempotency_key": "request-key-one",
            },
            mutation_authorized=True,
        )

    def acknowledge_publication(self) -> dict[str, object]:
        task = self.create_task()
        task = self.operations.claim_next_task("acquisition")
        for state in ("validating", "ready_to_publish"):
            task = self.operations.transition_task(
                str(task["task_id"]), int(task["revision"]), state
            )
        publication = self.operations.claim_publication("publisher-one")
        publication_id = str(publication["publication"]["publication_id"])
        publication = self.operations.advance_publication(
            publication_id,
            "claimed",
            "validated",
            {
                "final_relative_path": "Достоевский/Кроткая",
                "manifest_id": "b" * 64,
                "manifest": [
                    {
                        "relative_path": "book.m4b",
                        "size_bytes": 11,
                        "sha256": "c" * 64,
                        "duration_seconds": 100.0,
                    }
                ],
                "total_size_bytes": 11,
            },
        )
        for state in (
            "prepared",
            "transferred",
            "remote_verified",
            "promoted",
            "acknowledged",
        ):
            evidence = (
                {"remote_manifest_id": "b" * 64}
                if state == "remote_verified"
                else None
            )
            publication = self.operations.advance_publication(
                publication_id,
                str(publication["publication"]["status"]),
                state,
                evidence,
            )
        return publication["task"]

    def expose_published_item(self, *, path: str = "/readmeabook/Достоевский/Кроткая") -> None:
        self.catalog.items[("library-managed", "item-new")] = {
            "library_id": "library-managed",
            "item_id": "item-new",
            "path": path,
            "revision": "item-new-revision-one",
            "metadata": {
                "title": "Кроткая",
                "authors": [],
                "narrators": [],
                "series": [],
                "publisher": None,
            },
            "cover": None,
        }

    def test_complete_download_reaches_ready_and_cleanup_waits_for_verified(self) -> None:
        task = self.create_task()

        downloading = self.coordinator.reconcile_once()
        self.assertEqual(downloading["state"], "downloading")
        self.assertEqual(self.transmission.submit_calls, 1)
        self.assertEqual(self.transmission.removals, [])

        self.transmission.status = "complete"
        ready = self.coordinator.reconcile_once()
        self.assertEqual(ready["state"], "ready_to_publish")
        self.assertTrue((self.staging / task["task_id"] / "book.m4b").is_file())
        self.assertEqual(self.transmission.removals, [])

        for state in ("publishing", "awaiting_abs", "applying_metadata", "verified"):
            ready = self.operations.transition_task(
                ready["task_id"], ready["revision"], state
            )
        cleaned = self.coordinator.reconcile_once()

        self.assertEqual(cleaned["state"], "verified")
        self.assertEqual(self.transmission.removals, ["a" * 40])
        self.assertFalse((self.staging / task["task_id"]).exists())

    def test_acknowledged_publication_is_bound_and_metadata_verified(self) -> None:
        self.acknowledge_publication()
        self.expose_published_item()

        verified = self.coordinator.reconcile_once()

        self.assertEqual(verified["state"], "verified")
        self.assertEqual(
            self.catalog.items[("library-managed", "item-new")]["metadata"],
            {
                "title": "Кроткая",
                "authors": ["Достоевский"],
                "narrators": ["Иван"],
                "series": [],
                "publisher": None,
            },
        )
        event = self.operations.invoke(
            "notification_list", {"after_event_id": 0}
        )["events"][-1]
        self.assertEqual(event["kind"], "verified")

    def test_finalization_waits_for_the_exact_abs_path(self) -> None:
        awaiting = self.acknowledge_publication()
        self.expose_published_item(path="/readmeabook/Достоевский/Другая Кроткая")

        unchanged = self.coordinator.reconcile_once()

        self.assertEqual(unchanged["task_id"], awaiting["task_id"])
        self.assertEqual(unchanged["state"], "awaiting_abs")
        self.assertEqual(self.catalog.apply_calls, 0)

    def test_finalization_resumes_after_crash_before_abs_write(self) -> None:
        awaiting = self.acknowledge_publication()
        self.expose_published_item()
        self.catalog.fail_mode = "crash_before"
        with self.assertRaisesRegex(SystemExit, "simulated worker crash"):
            self.coordinator.reconcile_once()
        applying = self.operations.invoke(
            "task_get", {"task_id": awaiting["task_id"]}
        )
        self.assertEqual(applying["state"], "applying_metadata")
        self.catalog.fail_mode = None
        self.operations.close()
        self.operations = AudiobookOperations.open(
            self.root / "state.sqlite3",
            clock=self.clock,
            release_adapter=self.releases,
            external_action_adapter=FakeExternalActionAdapter(),
            catalog_adapter=self.catalog,
        )
        self.coordinator = AcquisitionCoordinator(
            self.operations, self.transmission, self.validator, self.clock
        )

        verified = self.coordinator.reconcile_once()

        self.assertEqual(verified["state"], "verified")
        self.assertEqual(self.catalog.apply_calls, 2)

    def test_restart_observes_the_existing_transmission_identity_before_submit(self) -> None:
        task = self.create_task()
        downloading = self.coordinator.reconcile_once()
        self.assertEqual(downloading["state"], "downloading")
        self.operations.close()
        self.operations = AudiobookOperations.open(
            self.root / "state.sqlite3",
            clock=self.clock,
            release_adapter=self.releases,
            external_action_adapter=FakeExternalActionAdapter(),
            catalog_adapter=FakeCatalogAdapter(),
        )
        self.coordinator = AcquisitionCoordinator(
            self.operations,
            self.transmission,
            self.validator,
            self.clock,
        )

        resumed = self.coordinator.reconcile_once()

        self.assertEqual(resumed["task_id"], task["task_id"])
        self.assertEqual(resumed["state"], "downloading")
        self.assertEqual(self.transmission.submit_calls, 2)
        self.assertEqual(self.transmission.additions, 1)

    def test_stalled_download_honors_backoff_and_exhausts_three_retries(self) -> None:
        self.create_task()
        self.transmission.rate_download = 0
        self.transmission.activity_at_epoch = int(
            (self.clock.now() - timedelta(minutes=20)).timestamp()
        )

        first = self.coordinator.reconcile_once()
        self.assertEqual(first["retry_count"], 1)
        unchanged = self.coordinator.reconcile_once()
        self.assertEqual(unchanged["revision"], first["revision"])

        for expected_delay in (60, 300, 900):
            self.clock.advance(timedelta(seconds=expected_delay))
            current = self.coordinator.reconcile_once()
        self.assertEqual(current["state"], "failed")
        self.assertEqual(current["retry_count"], 3)

    def test_capacity_is_checked_before_transmission_submission(self) -> None:
        self.releases.candidates["candidate-one"]["size_bytes"] = 21 * 1024**3
        task = self.create_task()

        blocked = self.coordinator.reconcile_once()

        self.assertEqual(blocked["task_id"], task["task_id"])
        self.assertEqual(blocked["state"], "needs_input")
        self.assertEqual(blocked["resume_state"], "queued")
        self.assertEqual(self.transmission.submit_calls, 0)

    def test_transient_transmission_rpc_failure_uses_the_bounded_retry_model(self) -> None:
        self.create_task()
        self.transmission.fail_operation = "observe"

        retrying = self.coordinator.reconcile_once()

        self.assertEqual(retrying["state"], "downloading")
        self.assertEqual(retrying["retry_count"], 1)
        self.assertEqual(retrying["next_retry_at"], "2026-09-13T00:01:00+00:00")

    def test_prepublication_cancellation_removes_only_its_transmission_data(self) -> None:
        self.create_task()
        self.transmission.status = "complete"
        ready = self.coordinator.reconcile_once()
        self.assertEqual(ready["state"], "ready_to_publish")
        self.assertTrue((self.staging / ready["task_id"]).is_dir())
        cancelled = self.operations.invoke(
            "task_cancel",
            {
                "task_id": ready["task_id"],
                "expected_revision": ready["revision"],
                "idempotency_key": "cancel-key-one",
            },
            mutation_authorized=True,
        )

        cleaned = self.coordinator.reconcile_once()

        self.assertEqual(cancelled["state"], "cancelled")
        self.assertEqual(cleaned["task_id"], cancelled["task_id"])
        self.assertEqual(self.transmission.removals, ["a" * 40])
        self.assertFalse((self.staging / cancelled["task_id"]).exists())

    def test_cleanup_completion_is_durable_and_does_not_starve_later_tasks(self) -> None:
        first = self.create_task()
        first = self.operations.invoke(
            "task_cancel",
            {
                "task_id": first["task_id"],
                "expected_revision": first["revision"],
                "idempotency_key": "cancel-key-first",
            },
            mutation_authorized=True,
        )
        second_plan = self.operations.invoke(
            "request_plan",
            {
                "candidate_id": "candidate-two",
                "candidate_revision": "source-revision-two",
                "work": {
                    "title": "Другая книга",
                    "authors": ["Другой автор"],
                    "series": [],
                },
                "audio_edition": {"narrators": ["Другой чтец"]},
                "origin_conversation_id": "conversation-two",
            },
        )
        second = self.operations.invoke(
            "request_apply",
            {
                "plan_id": second_plan["plan_id"],
                "revision": second_plan["revision"],
                "idempotency_key": "request-key-two",
            },
            mutation_authorized=True,
        )
        second = self.operations.invoke(
            "task_cancel",
            {
                "task_id": second["task_id"],
                "expected_revision": second["revision"],
                "idempotency_key": "cancel-key-second",
            },
            mutation_authorized=True,
        )

        cleaned_first = self.coordinator.reconcile_once()
        self.operations.close()
        self.operations = AudiobookOperations.open(
            self.root / "state.sqlite3",
            clock=self.clock,
            release_adapter=self.releases,
            external_action_adapter=FakeExternalActionAdapter(),
            catalog_adapter=FakeCatalogAdapter(),
        )
        self.coordinator = AcquisitionCoordinator(
            self.operations, self.transmission, self.validator, self.clock
        )
        cleaned_second = self.coordinator.reconcile_once()
        nothing_left = self.coordinator.reconcile_once()

        self.assertEqual(
            {cleaned_first["task_id"], cleaned_second["task_id"]},
            {first["task_id"], second["task_id"]},
        )
        self.assertIsNone(nothing_left)

    def test_validation_failure_requires_input_without_publishing_or_cleanup(self) -> None:
        class InvalidProbe:
            def duration(self, _path: Path) -> float:
                return 0

        validator = MediaValidator(
            downloads_root=self.downloads,
            staging_root=self.staging,
            probe=InvalidProbe(),
            capacity=lambda: CapacitySnapshot(
                working_set_bytes=0,
                local_free_bytes=101 * 1024**3,
                remote_free_bytes=201 * 1024**3,
            ),
            stability_hook=lambda: None,
        )
        coordinator = AcquisitionCoordinator(
            self.operations, self.transmission, validator, self.clock
        )
        task = self.create_task()
        self.transmission.status = "complete"

        result = coordinator.reconcile_once()

        self.assertEqual(result["state"], "needs_input")
        self.assertEqual(result["resume_state"], "validating")
        self.assertFalse((self.staging / task["task_id"]).exists())
        self.assertEqual(self.transmission.removals, [])

    def test_validated_manifest_is_durable_for_the_publisher(self) -> None:
        task = self.create_task()
        self.transmission.status = "complete"
        ready = self.coordinator.reconcile_once()
        expected = self.operations.validated_artifact(task["task_id"])
        self.operations.close()
        self.operations = AudiobookOperations.open(
            self.root / "state.sqlite3",
            clock=self.clock,
            release_adapter=self.releases,
            external_action_adapter=FakeExternalActionAdapter(),
            catalog_adapter=FakeCatalogAdapter(),
        )

        restored = self.operations.validated_artifact(task["task_id"])

        self.assertEqual(ready["state"], "ready_to_publish")
        self.assertEqual(restored, expected)
        self.assertEqual(restored["torrent_hash"], "a" * 40)
        self.assertEqual(restored["staging_id"], task["task_id"])
        self.assertEqual(restored["manifest"][0]["relative_path"], "book.m4b")

    def test_restart_reuses_identical_staging_after_lost_database_ack(self) -> None:
        task = self.create_task()
        task = self.operations.claim_next_task("acquisition")
        source = self.operations.acquisition_source(task["task_id"])
        self.transmission.submit(source, f"transmission:{task['task_id']}")
        self.transmission.status = "complete"
        task = self.operations.transition_task(
            task["task_id"], task["revision"], "validating"
        )
        self.validator.validate_and_stage(task["task_id"], self.release)
        self.operations.close()
        self.operations = AudiobookOperations.open(
            self.root / "state.sqlite3",
            clock=self.clock,
            release_adapter=self.releases,
            external_action_adapter=FakeExternalActionAdapter(),
            catalog_adapter=FakeCatalogAdapter(),
        )
        self.coordinator = AcquisitionCoordinator(
            self.operations,
            self.transmission,
            self.validator,
            self.clock,
        )

        resumed = self.coordinator.reconcile_once()

        self.assertEqual(resumed["state"], "ready_to_publish")
        self.assertEqual(
            self.operations.validated_artifact(task["task_id"])["staging_id"],
            task["task_id"],
        )


if __name__ == "__main__":
    unittest.main()
