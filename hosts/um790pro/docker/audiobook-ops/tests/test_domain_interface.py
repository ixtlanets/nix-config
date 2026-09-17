from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import tempfile
import unittest

from audiobook_ops.interface import (
    AudiobookOperations,
    CatalogMutationError,
    OperationError,
)


@dataclass
class FakeClock:
    now_value: datetime

    def now(self) -> datetime:
        return self.now_value

    def advance(self, delta: timedelta) -> None:
        self.now_value += delta


class FakeReleaseAdapter:
    def __init__(self) -> None:
        self.candidates = {
            "candidate-one": {
                "candidate_id": "candidate-one",
                "revision": "source-revision-one",
                "source": "rutracker",
                "topic_id": "6887881",
                "infohash": "1a5eb6b90595e74de2d12f5366e733795de29071",
                "title": "Глубокий рейд. Кляксы",
                "size_bytes": 572_920_033,
            },
            "candidate-two": {
                "candidate_id": "candidate-two",
                "revision": "source-revision-two",
                "source": "rutracker",
                "topic_id": "6557008",
                "infohash": "00d415a3230944772364297e9efe58c02dcf62d0",
                "title": "Глубокий рейд 5",
                "size_bytes": 543_823_726,
            },
            "candidate-three": {
                "candidate_id": "candidate-three",
                "revision": "source-revision-three",
                "source": "rutracker",
                "topic_id": "7999999",
                "infohash": "1a5eb6b90595e74de2d12f5366e733795de29071",
                "title": "Кляксы, повторная раздача",
                "size_bytes": 572_920_033,
            },
        }

    def inspect(self, candidate_id: str) -> dict[str, object]:
        return {
            key: value
            for key, value in self.candidates[candidate_id].items()
            if key != "infohash"
        }

    def search(self, queries: list[str]) -> list[dict[str, object]]:
        return [
            {**candidate, "matched_queries": list(queries)}
            for candidate_id, candidate in self.candidates.items()
            if candidate_id != "candidate-three"
        ]

    def resolve(self, candidate_id: str) -> dict[str, object]:
        candidate = self.candidates[candidate_id]
        return {
            "infohash": candidate["infohash"],
            "magnet_uri": "magnet:?xt=urn:btih:" + str(candidate["infohash"]),
        }


class FakeExternalActionAdapter:
    def __init__(self) -> None:
        self.external: dict[tuple[str, str], str] = {}
        self.perform_calls: list[tuple[str, str]] = []

    def find(self, kind: str, idempotency_key: str) -> str | None:
        return self.external.get((kind, idempotency_key))

    def perform(
        self, kind: str, payload: dict[str, object], idempotency_key: str
    ) -> str:
        self.perform_calls.append((kind, idempotency_key))
        external_id = f"external-{len(self.perform_calls)}"
        self.external[(kind, idempotency_key)] = external_id
        return external_id


class FakeCatalogAdapter:
    def __init__(self) -> None:
        self.apply_calls = 0
        self.fail_mode: str | None = None
        self.items = {
            ("library-one", "item-one"): {
                "library_id": "library-one",
                "item_id": "item-one",
                "path": "/readmeabook/Автор/Книга",
                "revision": "item-revision-one",
                "metadata": {
                    "title": "Старое название",
                    "authors": ["Автор"],
                    "narrators": ["Чтец"],
                    "publisher": "Старый издатель",
                },
                "cover": {"checksum": "old-cover-checksum"},
            }
        }

    def get_item(self, library_id: str, item_id: str) -> dict[str, object]:
        return dict(self.items[(library_id, item_id)])

    def find_by_path(self, path: str) -> dict[str, object] | None:
        matches = [dict(item) for item in self.items.values() if item["path"] == path]
        if len(matches) > 1:
            raise OperationError("catalog path is not unique")
        return matches[0] if matches else None

    def search(self, query: str) -> list[dict[str, object]]:
        return [
            dict(item)
            for item in self.items.values()
            if query.casefold() in str(item["metadata"]["title"]).casefold()
        ]

    def audit(self, library_ids: list[str]) -> dict[str, object]:
        return {"library_ids": library_ids or ["library-one"], "issues": []}

    def prepare_cover(self, source_url: str) -> dict[str, object]:
        return {
            "source_url": source_url,
            "checksum": "new-cover-checksum",
            "mime_type": "image/jpeg",
            "filename": "cover.jpg",
            "width": 1200,
            "height": 1200,
            "_content_b64": "bmV3IGNvdmVy",
        }

    def snapshot_exact(self, target: dict[str, object]) -> dict[str, object]:
        item = self.items[(str(target["library_id"]), str(target["item_id"]))]
        if item["path"] != target["path"] or item["revision"] != target["revision"]:
            raise OperationError("catalog item identity changed")
        return {
            "metadata": json.loads(json.dumps(item["metadata"])),
            "cover": (
                {**item["cover"], "_content_b64": "b2xkIGNvdmVy"}
                if item["cover"] is not None
                else None
            ),
        }

    def apply_exact(
        self,
        target: dict[str, object],
        desired: dict[str, object],
        rollback: dict[str, object],
    ) -> dict[str, object]:
        item = self.items[(str(target["library_id"]), str(target["item_id"]))]
        if item["path"] != target["path"] or item["revision"] != target["revision"]:
            raise OperationError("catalog item identity changed")
        self.apply_calls += 1
        if self.fail_mode == "crash_before":
            raise SystemExit("simulated worker crash before catalog write")
        if self.fail_mode is not None:
            raise CatalogMutationError(
                "simulated catalog mutation failure",
                compensated=self.fail_mode == "compensated",
            )
        item["metadata"] = json.loads(json.dumps(desired["metadata"]))
        cover = desired["cover"]
        item["cover"] = (
            {key: value for key, value in cover.items() if not key.startswith("_")}
            if isinstance(cover, dict)
            else None
        )
        item["revision"] = f"item-revision-{self.apply_calls + 1}"
        return dict(item)


class RequestLifecycleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.database = Path(self.temporary_directory.name) / "state.sqlite3"
        self.clock = FakeClock(datetime(2026, 9, 13, 0, 0, tzinfo=UTC))
        self.releases = FakeReleaseAdapter()
        self.actions = FakeExternalActionAdapter()
        self.catalog = FakeCatalogAdapter()
        self.operations = AudiobookOperations.open(
            self.database,
            clock=self.clock,
            release_adapter=self.releases,
            external_action_adapter=self.actions,
            catalog_adapter=self.catalog,
        )

    def tearDown(self) -> None:
        self.operations.close()
        self.temporary_directory.cleanup()

    def request_plan(
        self,
        candidate_id: str = "candidate-one",
        *,
        title: str = "Глубокий рейд. Кляксы",
    ) -> dict[str, object]:
        candidate = self.releases.inspect(candidate_id)
        return self.operations.invoke(
            "request_plan",
            {
                "candidate_id": candidate_id,
                "candidate_revision": candidate["revision"],
                "work": {
                    "title": title,
                    "authors": ["Борис Конофальский"],
                    "series": [{"name": "Глубокий рейд", "sequence": "4.5"}],
                },
                "audio_edition": {
                    "narrators": ["Один"],
                    "abridged": False,
                },
                "origin_conversation_id": "conversation-one",
            },
        )

    def apply(self, plan: dict[str, object], key: str) -> dict[str, object]:
        return self.operations.invoke(
            "request_apply",
            {
                "plan_id": plan["plan_id"],
                "revision": plan["revision"],
                "idempotency_key": key,
            },
            mutation_authorized=True,
        )

    def test_plan_is_immutable_for_24_hours_and_apply_is_idempotent(self) -> None:
        plan = self.request_plan()

        self.assertEqual(plan["status"], "awaiting_approval")
        self.assertEqual(plan["expires_at"], "2026-09-14T00:00:00+00:00")
        self.assertNotIn("infohash", plan["candidate"])
        self.assertNotIn("magnet:", json.dumps(plan))
        first = self.apply(plan, "request-key-one")
        replay = self.apply(plan, "request-key-one")

        self.assertEqual(first, replay)
        self.assertEqual(first["state"], "queued")
        self.assertEqual(first["revision"], 2)
        self.assertEqual(
            [transition["to_state"] for transition in first["transitions"]],
            ["draft", "awaiting_approval", "queued"],
        )

        with self.assertRaisesRegex(OperationError, "idempotency key conflict"):
            second_plan = self.request_plan("candidate-two")
            self.apply(second_plan, "request-key-one")

    def test_release_tools_return_only_safe_candidate_evidence(self) -> None:
        searched = self.operations.invoke(
            "release_search", {"queries": ["Фёдор", "Федор"]}
        )
        inspected = self.operations.invoke(
            "release_inspect",
            {"candidate_id": searched["candidates"][0]["candidate_id"]},
        )

        self.assertEqual(len(searched["candidates"]), 2)
        self.assertEqual(searched["candidates"][0]["matched_queries"], ["Фёдор", "Федор"])
        encoded = json.dumps({"searched": searched, "inspected": inspected})
        self.assertNotIn("infohash", encoded)
        self.assertNotIn("magnet", encoded)

    def test_work_audio_edition_and_release_candidate_remain_distinct(self) -> None:
        plan = self.request_plan()

        self.assertNotEqual(plan["work"]["work_id"], plan["audio_edition"]["edition_id"])
        self.assertEqual(
            plan["audio_edition"]["work_id"], plan["work"]["work_id"]
        )
        self.assertEqual(
            plan["work"]["series"],
            [{"name": "Глубокий рейд", "sequence": "4.5"}],
        )
        self.assertEqual(plan["audio_edition"]["narrators"], ["Один"])
        self.assertNotEqual(plan["candidate"]["candidate_id"], plan["work"]["work_id"])

        task = self.apply(plan, "request-key-one")
        observed = self.operations.invoke("task_get", {"task_id": task["task_id"]})
        self.assertEqual(observed["work"], plan["work"])
        self.assertEqual(observed["audio_edition"], plan["audio_edition"])

    def test_work_and_audio_edition_shapes_fail_closed(self) -> None:
        invalid_cases = (
            (
                {"title": "Кляксы", "authors": "Автор", "series": []},
                {"narrators": ["Один"]},
            ),
            (
                {
                    "title": "Кляксы",
                    "authors": ["Автор"],
                    "series": [{"name": "", "sequence": "4"}],
                },
                {"narrators": ["Один"]},
            ),
            (
                {"title": "Кляксы", "authors": ["Автор"], "series": []},
                {"narrators": []},
            ),
        )
        for work, audio_edition in invalid_cases:
            with self.subTest(work=work, audio_edition=audio_edition):
                with self.assertRaisesRegex(
                    OperationError, "invalid (work|audio edition)"
                ):
                    self.operations.invoke(
                        "request_plan",
                        {
                            "candidate_id": "candidate-one",
                            "candidate_revision": "source-revision-one",
                            "work": work,
                            "audio_edition": audio_edition,
                            "origin_conversation_id": "conversation-one",
                        },
                    )

        unknown_narrator = self.operations.invoke(
            "request_plan",
            {
                "candidate_id": "candidate-one",
                "candidate_revision": "source-revision-one",
                "work": {"title": "Кляксы", "authors": ["Автор"], "series": []},
                "audio_edition": {"narrators": [], "narrator_unknown": True},
                "origin_conversation_id": "conversation-one",
            },
        )
        self.assertTrue(unknown_narrator["audio_edition"]["narrator_unknown"])

    def test_notification_events_are_durable_and_cursor_based(self) -> None:
        task = self.apply(self.request_plan(), "request-key-one")
        task = self.operations.claim_next_task("worker-one")
        task = self.operations.transition_task(
            task["task_id"], task["revision"], "needs_input", "author conflict"
        )

        first = self.operations.invoke("notification_list", {"after_event_id": 0})
        self.assertEqual(len(first["events"]), 1)
        event = first["events"][0]
        self.assertEqual(event["kind"], "needs_input")
        self.assertEqual(event["task_id"], task["task_id"])
        self.assertEqual(event["origin_conversation_id"], "conversation-one")
        self.assertEqual(first["cursor"], event["event_id"])
        self.assertEqual(
            self.operations.invoke(
                "notification_list", {"after_event_id": event["event_id"]}
            ),
            {"events": [], "cursor": event["event_id"]},
        )

        self.operations.close()
        self.operations = AudiobookOperations.open(
            self.database,
            clock=self.clock,
            release_adapter=self.releases,
            external_action_adapter=self.actions,
            catalog_adapter=self.catalog,
        )
        replay = self.operations.invoke("notification_list", {"after_event_id": 0})
        self.assertEqual(replay["events"], [event])

    def test_expired_or_stale_plan_fails_before_creating_a_task(self) -> None:
        expired = self.request_plan()
        self.clock.advance(timedelta(hours=24, microseconds=1))
        with self.assertRaisesRegex(OperationError, "plan expired"):
            self.apply(expired, "expired-key")

        self.clock.now_value = datetime(2026, 9, 13, 1, 0, tzinfo=UTC)
        stale = self.request_plan()
        self.releases.candidates["candidate-one"]["revision"] = "changed-upstream"
        with self.assertRaisesRegex(OperationError, "candidate revision changed"):
            self.apply(stale, "stale-key")

        tasks = self.operations.invoke("task_list", {})
        self.assertEqual(tasks, {"tasks": []})

    def test_exact_duplicate_is_blocked_and_changed_candidate_gets_a_new_task(self) -> None:
        first = self.apply(self.request_plan(), "request-key-one")

        with self.assertRaisesRegex(OperationError, "exact release duplicate"):
            self.apply(self.request_plan(), "request-key-two")

        with self.assertRaisesRegex(OperationError, "exact release duplicate"):
            self.apply(self.request_plan("candidate-three"), "request-key-infohash")

        alternate_plan = self.request_plan("candidate-two")
        self.assertEqual(
            alternate_plan["warnings"],
            ["possible existing work or audio edition requires owner review"],
        )
        second = self.apply(alternate_plan, "request-key-three")
        self.assertNotEqual(first["task_id"], second["task_id"])
        self.assertEqual(second["candidate_id"], "candidate-two")

    def test_near_duplicate_title_warns_without_blocking_a_distinct_release(self) -> None:
        first = self.request_plan()
        self.apply(first, "request-key-one")

        near_duplicate = self.request_plan(
            "candidate-two", title="Глубокий рейд: Клякса"
        )
        applied = self.apply(near_duplicate, "request-key-two")

        self.assertEqual(
            near_duplicate["warnings"],
            ["possible existing work or audio edition requires owner review"],
        )
        self.assertEqual(applied["state"], "queued")

    def test_write_tools_require_an_explicit_execution_gate(self) -> None:
        plan = self.request_plan()
        with self.assertRaisesRegex(OperationError, "mutation requires execution gate"):
            self.operations.invoke(
                "request_apply",
                {
                    "plan_id": plan["plan_id"],
                    "revision": plan["revision"],
                    "idempotency_key": "request-key-one",
                },
            )

    def test_normal_worker_and_publisher_path_uses_only_legal_transitions(self) -> None:
        task = self.apply(self.request_plan(), "request-key-one")

        task = self.operations.claim_next_task("worker-one")
        self.assertEqual(task["state"], "downloading")
        for state in ("validating", "ready_to_publish"):
            task = self.operations.transition_task(
                task["task_id"], task["revision"], state
            )

        publication = self.operations.claim_publication("publisher-one")
        self.assertEqual(publication["task"]["state"], "publishing")
        self.assertEqual(publication["publication"]["status"], "claimed")
        task = publication["task"]

        for state in ("awaiting_abs", "applying_metadata", "verified"):
            task = self.operations.transition_task(
                task["task_id"], task["revision"], state
            )

        self.assertEqual(task["state"], "verified")
        self.assertEqual(task["revision"], 9)
        self.assertEqual(
            [transition["to_state"] for transition in task["transitions"]],
            [
                "draft",
                "awaiting_approval",
                "queued",
                "downloading",
                "validating",
                "ready_to_publish",
                "publishing",
                "awaiting_abs",
                "applying_metadata",
                "verified",
            ],
        )

    def test_prohibited_and_stale_transitions_fail_closed(self) -> None:
        task = self.apply(self.request_plan(), "request-key-one")

        with self.assertRaisesRegex(OperationError, "prohibited transition"):
            self.operations.transition_task(task["task_id"], task["revision"], "verified")
        with self.assertRaisesRegex(OperationError, "stale task revision"):
            self.operations.transition_task(
                task["task_id"], task["revision"] - 1, "downloading"
            )

        unchanged = self.operations.invoke("task_get", {"task_id": task["task_id"]})
        self.assertEqual(unchanged["state"], "queued")
        self.assertEqual(unchanged["revision"], task["revision"])

    def test_cancel_is_idempotent_only_before_publication(self) -> None:
        task = self.apply(self.request_plan(), "request-key-one")
        with self.assertRaisesRegex(OperationError, "stale task revision"):
            self.operations.invoke(
                "task_cancel",
                {
                    "task_id": task["task_id"],
                    "expected_revision": task["revision"] - 1,
                    "idempotency_key": "cancel-key-stale",
                },
                mutation_authorized=True,
            )
        arguments = {
            "task_id": task["task_id"],
            "expected_revision": task["revision"],
            "idempotency_key": "cancel-key-one",
        }
        cancelled = self.operations.invoke(
            "task_cancel", arguments, mutation_authorized=True
        )
        replay = self.operations.invoke(
            "task_cancel", arguments, mutation_authorized=True
        )
        self.assertEqual(cancelled, replay)
        self.assertEqual(cancelled["state"], "cancelled")

        second = self.apply(self.request_plan("candidate-two"), "request-key-two")
        second = self.operations.claim_next_task("worker-one")
        for state in ("validating", "ready_to_publish"):
            second = self.operations.transition_task(
                second["task_id"], second["revision"], state
            )
        second = self.operations.claim_publication("publisher-one")["task"]
        with self.assertRaisesRegex(OperationError, "publication has begun"):
            self.operations.invoke(
                "task_cancel",
                {
                    "task_id": second["task_id"],
                    "expected_revision": second["revision"],
                    "idempotency_key": "cancel-key-two",
                },
                mutation_authorized=True,
            )

    def test_only_one_queued_task_becomes_active_under_concurrent_claims(self) -> None:
        self.apply(self.request_plan(), "request-key-one")
        self.apply(self.request_plan("candidate-two"), "request-key-two")
        second_connection = AudiobookOperations.open(
            self.database,
            clock=self.clock,
            release_adapter=self.releases,
            external_action_adapter=self.actions,
            catalog_adapter=self.catalog,
        )
        try:
            with ThreadPoolExecutor(max_workers=2) as executor:
                results = list(
                    executor.map(
                        lambda pair: pair[0].claim_next_task(pair[1]),
                        (
                            (self.operations, "worker-one"),
                            (second_connection, "worker-two"),
                        ),
                    )
                )
        finally:
            second_connection.close()

        claimed = [result for result in results if result is not None]
        self.assertEqual(len(claimed), 1)
        self.assertEqual(claimed[0]["state"], "downloading")
        states = [task["state"] for task in self.operations.invoke("task_list", {})["tasks"]]
        self.assertEqual(sorted(states), ["downloading", "queued"])

        filtered = self.operations.invoke("task_list", {"states": ["queued"]})
        self.assertEqual([task["state"] for task in filtered["tasks"]], ["queued"])
        with self.assertRaisesRegex(OperationError, "unknown task state"):
            self.operations.invoke("task_list", {"states": ["surprise"]})

    def test_only_one_publisher_can_claim_a_ready_task(self) -> None:
        task = self.apply(self.request_plan(), "request-key-one")
        for state in ("downloading", "validating", "ready_to_publish"):
            task = self.operations.transition_task(task["task_id"], task["revision"], state)
        second_connection = AudiobookOperations.open(
            self.database,
            clock=self.clock,
            release_adapter=self.releases,
            external_action_adapter=self.actions,
            catalog_adapter=self.catalog,
        )
        try:
            with ThreadPoolExecutor(max_workers=2) as executor:
                results = list(
                    executor.map(
                        lambda pair: pair[0].claim_publication(pair[1]),
                        (
                            (self.operations, "publisher-one"),
                            (second_connection, "publisher-two"),
                        ),
                    )
                )
        finally:
            second_connection.close()

        claimed = [result for result in results if result is not None]
        self.assertEqual(len(claimed), 1)
        self.assertEqual(claimed[0]["task"]["state"], "publishing")
        self.assertEqual(
            self.operations.invoke("task_get", {"task_id": task["task_id"]})["state"],
            "publishing",
        )

    def test_transient_retries_are_bounded_and_admin_retry_is_idempotent(self) -> None:
        task = self.apply(self.request_plan(), "request-key-one")
        task = self.operations.claim_next_task("worker-one")

        for retry_count, delay in enumerate((60, 300, 900), start=1):
            task = self.operations.record_transient_failure(
                task["task_id"], task["revision"], "temporary network failure"
            )
            self.assertEqual(task["state"], "downloading")
            self.assertEqual(task["retry_count"], retry_count)
            self.assertEqual(
                task["next_retry_at"],
                (self.clock.now() + timedelta(seconds=delay)).isoformat(),
            )

        task = self.operations.record_transient_failure(
            task["task_id"], task["revision"], "temporary network failure"
        )
        self.assertEqual(task["state"], "failed")
        self.assertEqual(task["resume_state"], "downloading")

        arguments = {
            "task_id": task["task_id"],
            "expected_revision": task["revision"],
            "idempotency_key": "retry-key-one",
        }
        with self.assertRaisesRegex(OperationError, "stale task revision"):
            self.operations.invoke(
                "task_retry",
                {
                    **arguments,
                    "expected_revision": task["revision"] - 1,
                    "idempotency_key": "retry-key-stale",
                },
                mutation_authorized=True,
            )
        retried = self.operations.invoke(
            "task_retry", arguments, mutation_authorized=True
        )
        replay = self.operations.invoke(
            "task_retry", arguments, mutation_authorized=True
        )
        self.assertEqual(retried, replay)
        self.assertEqual(retried["state"], "downloading")
        self.assertEqual(retried["retry_count"], 0)
        self.assertIsNone(retried["next_retry_at"])

    def test_admin_retry_does_not_create_a_second_active_acquisition(self) -> None:
        first = self.apply(self.request_plan(), "request-key-one")
        first = self.operations.claim_next_task("worker-one")
        for _ in range(4):
            first = self.operations.record_transient_failure(
                first["task_id"], first["revision"], "temporary network failure"
            )

        self.apply(self.request_plan("candidate-two"), "request-key-two")
        second = self.operations.claim_next_task("worker-two")
        self.assertEqual(second["state"], "downloading")

        with self.assertRaisesRegex(OperationError, "another acquisition is active"):
            self.operations.invoke(
                "task_retry",
                {
                    "task_id": first["task_id"],
                    "expected_revision": first["revision"],
                    "idempotency_key": "retry-key-blocked",
                },
                mutation_authorized=True,
            )

    def test_needs_input_resumes_exactly_the_interrupted_state(self) -> None:
        task = self.apply(self.request_plan(), "request-key-one")
        task = self.operations.claim_next_task("worker-one")
        task = self.operations.transition_task(
            task["task_id"], task["revision"], "validating"
        )
        waiting = self.operations.transition_task(
            task["task_id"], task["revision"], "needs_input", "narrator conflict"
        )

        self.assertEqual(waiting["resume_state"], "validating")
        with self.assertRaisesRegex(OperationError, "stale task revision"):
            self.operations.invoke(
                "task_retry",
                {
                    "task_id": waiting["task_id"],
                    "expected_revision": waiting["revision"] - 1,
                    "idempotency_key": "retry-key-stale",
                },
                mutation_authorized=True,
            )
        retried = self.operations.invoke(
            "task_retry",
            {
                "task_id": waiting["task_id"],
                "expected_revision": waiting["revision"],
                "idempotency_key": "retry-key-valid",
            },
            mutation_authorized=True,
        )
        self.assertEqual(retried["state"], "validating")

    def test_restart_reconciliation_observes_before_repeating_external_action(self) -> None:
        task = self.apply(self.request_plan(), "request-key-one")
        task = self.operations.claim_next_task("worker-one")
        action = self.operations.plan_external_action(
            task["task_id"],
            task["revision"],
            "transmission_submit",
            {"candidate_id": task["candidate_id"]},
            "external-action-key-one",
        )

        external_id = self.actions.perform(
            "transmission_submit",
            {"candidate_id": task["candidate_id"]},
            "external-action-key-one",
        )
        self.operations.close()
        self.operations = AudiobookOperations.open(
            self.database,
            clock=self.clock,
            release_adapter=self.releases,
            external_action_adapter=self.actions,
            catalog_adapter=self.catalog,
        )

        reconciled = self.operations.reconcile_external_actions()
        replay = self.operations.reconcile_external_actions()

        self.assertEqual(len(self.actions.perform_calls), 1)
        self.assertEqual(
            reconciled,
            [{**action, "status": "acknowledged", "external_id": external_id}],
        )
        self.assertEqual(replay, [])

    def test_metadata_plan_is_a_distinct_immutable_exact_item_concept(self) -> None:
        plan = self.operations.invoke(
            "metadata_plan",
            {
                "library_id": "library-one",
                "item_id": "item-one",
                "item_revision": "item-revision-one",
                "changes": {
                    "title": {
                        "operation": "set",
                        "value": "Новое название",
                        "source": "rutracker:topic:6887881",
                        "observed_at": "2026-09-12T20:00:00+00:00",
                        "confidence": "high",
                    }
                },
            },
        )

        self.assertEqual(plan["entity_kind"], "metadata_plan")
        self.assertEqual(plan["target"]["library_id"], "library-one")
        self.assertEqual(plan["target"]["item_id"], "item-one")
        self.assertEqual(plan["target"]["path"], "/readmeabook/Автор/Книга")
        self.assertEqual(plan["before"]["metadata"]["title"], "Старое название")
        self.assertEqual(plan["after"]["metadata"]["title"], "Новое название")
        self.assertEqual(plan["expires_at"], "2026-09-14T00:00:00+00:00")

        for changes in (
            {"unknown": {"operation": "clear"}},
            {"title": {"operation": "set", "value": "Без источника"}},
        ):
            with self.subTest(changes=changes):
                with self.assertRaisesRegex(OperationError, "invalid metadata"):
                    self.operations.invoke(
                        "metadata_plan",
                        {
                            "library_id": "library-one",
                            "item_id": "item-one",
                            "item_revision": "item-revision-one",
                            "changes": changes,
                        },
                    )

        self.catalog.items[("library-one", "item-one")]["revision"] = "changed-item"
        with self.assertRaisesRegex(OperationError, "item revision changed"):
            self.operations.invoke(
                "metadata_plan",
                {
                    "library_id": "library-one",
                    "item_id": "item-one",
                    "item_revision": "item-revision-one",
                    "changes": {"title": {"operation": "clear"}},
                    },
                )

    def test_library_reads_use_catalog_adapter_without_exposing_write_routes(self) -> None:
        searched = self.operations.invoke("library_search", {"query": "старое"})
        exact = self.operations.invoke(
            "library_item_get", {"library_id": "library-one", "item_id": "item-one"}
        )
        audit = self.operations.invoke("library_audit", {"library_ids": []})

        self.assertEqual([item["item_id"] for item in searched["items"]], ["item-one"])
        self.assertEqual(exact["item_id"], "item-one")
        self.assertEqual(audit, {"library_ids": ["library-one"], "issues": []})

    def test_combined_metadata_cover_apply_and_undo_are_exact_and_idempotent(self) -> None:
        plan = self.operations.invoke(
            "metadata_plan",
            {
                "library_id": "library-one",
                "item_id": "item-one",
                "item_revision": "item-revision-one",
                "changes": {
                    "title": {
                        "operation": "set",
                        "value": "Новое название",
                        "source": "rutracker:topic:6887881",
                        "observed_at": "2026-09-12T20:00:00+00:00",
                        "confidence": "high",
                    },
                    "subtitle": {
                        "operation": "clear",
                        "source": "owner-review",
                        "observed_at": "2026-09-12T20:00:00+00:00",
                        "confidence": "high",
                    },
                    "authors": {
                        "operation": "set",
                        "value": ["Автор Один", "Автор Два"],
                        "source": "owner-review",
                        "observed_at": "2026-09-12T20:00:00+00:00",
                        "confidence": "high",
                    },
                    "narrators": {
                        "operation": "clear",
                        "source": "owner-review",
                        "observed_at": "2026-09-12T20:00:00+00:00",
                        "confidence": "high",
                    },
                    "tags": {
                        "operation": "clear",
                        "source": "owner-review",
                        "observed_at": "2026-09-12T20:00:00+00:00",
                        "confidence": "high",
                    },
                    "series": {
                        "operation": "set",
                        "value": [
                            {"name": "Цикл", "sequence": "4.5"},
                            {"name": "Другой цикл", "sequence": "1-2"},
                        ],
                        "source": "owner-review",
                        "observed_at": "2026-09-12T20:00:00+00:00",
                        "confidence": "high",
                    },
                    "cover": {
                        "operation": "set",
                        "value": {"source_url": "https://covers.example/new.jpg"},
                        "source": "https://covers.example/new.jpg",
                        "observed_at": "2026-09-12T20:00:00+00:00",
                        "confidence": "high",
                    },
                },
            },
        )
        self.assertNotIn("_content_b64", json.dumps(plan))

        arguments = {
            "plan_id": plan["plan_id"],
            "revision": plan["revision"],
            "idempotency_key": "metadata-apply-key",
        }
        applied = self.operations.invoke(
            "metadata_apply", arguments, mutation_authorized=True
        )
        replay = self.operations.invoke(
            "metadata_apply", arguments, mutation_authorized=True
        )

        self.assertEqual(applied, replay)
        self.assertEqual(self.catalog.apply_calls, 1)
        self.assertEqual(applied["status"], "applied")
        self.assertEqual(applied["item"]["path"], "/readmeabook/Автор/Книга")
        self.assertEqual(applied["item"]["metadata"]["title"], "Новое название")
        self.assertIsNone(applied["item"]["metadata"]["subtitle"])
        self.assertEqual(applied["item"]["metadata"]["narrators"], [])
        self.assertEqual(applied["item"]["metadata"]["tags"], [])
        self.assertEqual(
            applied["item"]["metadata"]["publisher"], "Старый издатель"
        )
        self.assertEqual(applied["undo_expires_at"], "2026-10-13T00:00:00+00:00")

        undone = self.operations.invoke(
            "metadata_undo",
            {
                "change_id": applied["change_id"],
                "revision": applied["revision"],
                "idempotency_key": "metadata-undo-key",
            },
            mutation_authorized=True,
        )
        self.assertEqual(undone["status"], "undone")
        self.assertEqual(undone["item"]["metadata"]["title"], "Старое название")
        self.assertEqual(undone["item"]["cover"]["checksum"], "old-cover-checksum")
        self.assertEqual(undone["item"]["path"], "/readmeabook/Автор/Книга")

    def test_metadata_apply_rejects_expiry_and_stale_path_revision_before_write(self) -> None:
        plan = self.operations.invoke(
            "metadata_plan",
            {
                "library_id": "library-one",
                "item_id": "item-one",
                "item_revision": "item-revision-one",
                "changes": {
                    "title": {
                        "operation": "set",
                        "value": "Новое название",
                        "source": "owner-review",
                        "observed_at": "2026-09-12T20:00:00+00:00",
                        "confidence": "high",
                    }
                },
            },
        )
        self.catalog.items[("library-one", "item-one")]["path"] = "/changed/path"
        with self.assertRaisesRegex(OperationError, "identity changed"):
            self.operations.invoke(
                "metadata_apply",
                {
                    "plan_id": plan["plan_id"],
                    "revision": plan["revision"],
                    "idempotency_key": "metadata-stale-key",
                },
                mutation_authorized=True,
            )
        self.assertEqual(self.catalog.apply_calls, 0)

        self.catalog.items[("library-one", "item-one")]["path"] = "/readmeabook/Автор/Книга"
        self.clock.advance(timedelta(hours=24, microseconds=1))
        with self.assertRaisesRegex(OperationError, "plan expired"):
            self.operations.invoke(
                "metadata_apply",
                {
                    "plan_id": plan["plan_id"],
                    "revision": plan["revision"],
                    "idempotency_key": "metadata-expired-key",
                },
                mutation_authorized=True,
            )

    def test_metadata_partial_failure_records_compensation_or_attention(self) -> None:
        for mode, expected_status in (
            ("compensated", "failed_compensated"),
            ("needs_attention", "needs_attention"),
        ):
            with self.subTest(mode=mode):
                plan = self.operations.invoke(
                    "metadata_plan",
                    {
                        "library_id": "library-one",
                        "item_id": "item-one",
                        "item_revision": "item-revision-one",
                        "changes": {
                            "title": {
                                "operation": "set",
                                "value": f"Failure {mode}",
                                "source": "owner-review",
                                "observed_at": "2026-09-12T20:00:00+00:00",
                                "confidence": "high",
                            }
                        },
                    },
                )
                self.catalog.fail_mode = mode
                with self.assertRaisesRegex(OperationError, "simulated"):
                    self.operations.invoke(
                        "metadata_apply",
                        {
                            "plan_id": plan["plan_id"],
                            "revision": plan["revision"],
                            "idempotency_key": f"metadata-failure-{mode}",
                        },
                        mutation_authorized=True,
                    )
                self.assertEqual(
                    self.operations.metadata_plan_application(plan["plan_id"])["status"],
                    expected_status,
                )
                self.catalog.fail_mode = None
        self.assertEqual(self.catalog.apply_calls, 2)

    def test_metadata_undo_rejects_stale_item_and_expiry_before_write(self) -> None:
        plan = self.operations.invoke(
            "metadata_plan",
            {
                "library_id": "library-one",
                "item_id": "item-one",
                "item_revision": "item-revision-one",
                "changes": {
                    "title": {
                        "operation": "set",
                        "value": "Новое название",
                        "source": "owner-review",
                        "observed_at": "2026-09-12T20:00:00+00:00",
                        "confidence": "high",
                    }
                },
            },
        )
        applied = self.operations.invoke(
            "metadata_apply",
            {
                "plan_id": plan["plan_id"],
                "revision": plan["revision"],
                "idempotency_key": "metadata-apply-for-undo",
            },
            mutation_authorized=True,
        )
        expected_revision = self.catalog.items[("library-one", "item-one")]["revision"]
        self.catalog.items[("library-one", "item-one")]["revision"] = "external-change"
        undo = {
            "change_id": applied["change_id"],
            "revision": applied["revision"],
            "idempotency_key": "metadata-undo-stale",
        }
        with self.assertRaisesRegex(OperationError, "identity changed"):
            self.operations.invoke("metadata_undo", undo, mutation_authorized=True)
        self.assertEqual(self.catalog.apply_calls, 1)

        self.catalog.items[("library-one", "item-one")]["revision"] = expected_revision
        self.clock.advance(timedelta(days=30, microseconds=1))
        undo["idempotency_key"] = "metadata-undo-expired"
        with self.assertRaisesRegex(OperationError, "undo expired"):
            self.operations.invoke("metadata_undo", undo, mutation_authorized=True)
        self.assertEqual(self.catalog.apply_calls, 1)

    def test_metadata_apply_recovers_after_external_success_before_database_ack(self) -> None:
        plan = self.operations.invoke(
            "metadata_plan",
            {
                "library_id": "library-one",
                "item_id": "item-one",
                "item_revision": "item-revision-one",
                "changes": {
                    "title": {
                        "operation": "set",
                        "value": "Новое название",
                        "source": "owner-review",
                        "observed_at": "2026-09-12T20:00:00+00:00",
                        "confidence": "high",
                    }
                },
            },
        )
        arguments = {
            "plan_id": plan["plan_id"],
            "revision": plan["revision"],
            "idempotency_key": "metadata-lost-ack-key",
        }
        self.operations._connection.executescript(
            """
            CREATE TRIGGER fail_metadata_ack
            BEFORE UPDATE OF status ON metadata_changes
            WHEN NEW.status = 'applied'
            BEGIN
              SELECT RAISE(ABORT, 'simulated lost ack');
            END;
            """
        )
        with self.assertRaisesRegex(Exception, "simulated lost ack"):
            self.operations.invoke(
                "metadata_apply", arguments, mutation_authorized=True
            )
        self.operations._connection.execute("DROP TRIGGER fail_metadata_ack")
        self.operations.close()
        self.operations = AudiobookOperations.open(
            self.database,
            clock=self.clock,
            release_adapter=self.releases,
            external_action_adapter=self.actions,
            catalog_adapter=self.catalog,
        )

        recovered = self.operations.invoke(
            "metadata_apply", arguments, mutation_authorized=True
        )

        self.assertEqual(recovered["status"], "applied")
        self.assertEqual(recovered["item"]["metadata"]["title"], "Новое название")
        self.assertEqual(self.catalog.apply_calls, 1)

    def test_metadata_apply_retries_after_restart_before_external_write(self) -> None:
        plan = self.operations.invoke(
            "metadata_plan",
            {
                "library_id": "library-one",
                "item_id": "item-one",
                "item_revision": "item-revision-one",
                "changes": {
                    "title": {
                        "operation": "set",
                        "value": "Новое название",
                        "source": "owner-review",
                        "observed_at": "2026-09-12T20:00:00+00:00",
                        "confidence": "high",
                    }
                },
            },
        )
        arguments = {
            "plan_id": plan["plan_id"],
            "revision": plan["revision"],
            "idempotency_key": "metadata-restart-before-write",
        }
        self.catalog.fail_mode = "crash_before"
        with self.assertRaisesRegex(SystemExit, "simulated worker crash"):
            self.operations.invoke(
                "metadata_apply", arguments, mutation_authorized=True
            )
        self.catalog.fail_mode = None
        self.operations.close()
        self.operations = AudiobookOperations.open(
            self.database,
            clock=self.clock,
            release_adapter=self.releases,
            external_action_adapter=self.actions,
            catalog_adapter=self.catalog,
        )

        recovered = self.operations.invoke(
            "metadata_apply", arguments, mutation_authorized=True
        )

        self.assertEqual(recovered["status"], "applied")
        self.assertEqual(recovered["item"]["metadata"]["title"], "Новое название")
        self.assertEqual(self.catalog.apply_calls, 2)

    def test_managed_audiobook_binds_publication_to_one_exact_item(self) -> None:
        task = self.apply(self.request_plan(), "request-key-one")
        task = self.operations.claim_next_task("worker-one")
        for state in ("validating", "ready_to_publish"):
            task = self.operations.transition_task(task["task_id"], task["revision"], state)
        task = self.operations.claim_publication("publisher-one")["task"]
        task = self.operations.transition_task(
            task["task_id"], task["revision"], "awaiting_abs"
        )

        result = self.operations.register_managed_audiobook(
            task["task_id"],
            task["revision"],
            {
                "library_id": "library-one",
                "item_id": "item-one",
                "path": "/readmeabook/Автор/Книга",
                "revision": "item-revision-one",
            },
        )

        self.assertEqual(result["managed_audiobook"]["entity_kind"], "managed_audiobook")
        self.assertEqual(result["managed_audiobook"]["task_id"], task["task_id"])
        self.assertEqual(result["task"]["state"], "applying_metadata")


class TransitionMatrixTests(unittest.TestCase):
    states = (
        "queued",
        "downloading",
        "validating",
        "ready_to_publish",
        "publishing",
        "awaiting_abs",
        "applying_metadata",
        "verified",
        "needs_input",
        "failed",
        "cancelled",
    )
    allowed = {
        "queued": {"cancelled", "downloading", "failed", "needs_input"},
        "downloading": {"cancelled", "failed", "needs_input", "validating"},
        "validating": {"cancelled", "failed", "needs_input", "ready_to_publish"},
        "ready_to_publish": {"cancelled", "failed", "needs_input", "publishing"},
        "publishing": {"awaiting_abs", "failed", "needs_input"},
        "awaiting_abs": {"applying_metadata", "failed", "needs_input"},
        "applying_metadata": {"failed", "needs_input", "verified"},
        "verified": set(),
        "needs_input": set(),
        "failed": set(),
        "cancelled": set(),
    }

    def task_in_state(
        self, state: str
    ) -> tuple[tempfile.TemporaryDirectory[str], AudiobookOperations, dict[str, object]]:
        temporary_directory = tempfile.TemporaryDirectory()
        releases = FakeReleaseAdapter()
        operations = AudiobookOperations.open(
            Path(temporary_directory.name) / "state.sqlite3",
            clock=FakeClock(datetime(2026, 9, 13, tzinfo=UTC)),
            release_adapter=releases,
            external_action_adapter=FakeExternalActionAdapter(),
            catalog_adapter=FakeCatalogAdapter(),
        )
        candidate = releases.inspect("candidate-one")
        plan = operations.invoke(
            "request_plan",
            {
                "candidate_id": candidate["candidate_id"],
                "candidate_revision": candidate["revision"],
                "work": {"title": "Кляксы", "authors": ["Автор"], "series": []},
                "audio_edition": {"narrators": ["Чтец"]},
                "origin_conversation_id": "conversation-one",
            },
        )
        task = operations.invoke(
            "request_apply",
            {
                "plan_id": plan["plan_id"],
                "revision": plan["revision"],
                "idempotency_key": "request-key-one",
            },
            mutation_authorized=True,
        )
        if state == "queued":
            return temporary_directory, operations, task
        if state == "cancelled":
            task = operations.transition_task(task["task_id"], task["revision"], state)
            return temporary_directory, operations, task
        task = operations.claim_next_task("worker-one")
        if state == "downloading":
            return temporary_directory, operations, task
        if state in {"needs_input", "failed"}:
            task = operations.transition_task(
                task["task_id"], task["revision"], state, "test exception"
            )
            return temporary_directory, operations, task
        for next_state in ("validating", "ready_to_publish"):
            task = operations.transition_task(task["task_id"], task["revision"], next_state)
            if state == next_state:
                return temporary_directory, operations, task
        task = operations.claim_publication("publisher-one")["task"]
        if state == "publishing":
            return temporary_directory, operations, task
        for next_state in ("awaiting_abs", "applying_metadata", "verified"):
            task = operations.transition_task(task["task_id"], task["revision"], next_state)
            if state == next_state:
                return temporary_directory, operations, task
        raise AssertionError(f"unreachable fixture state: {state}")

    def test_every_direct_transition_is_explicitly_allowed_or_prohibited(self) -> None:
        for from_state in self.states:
            for to_state in self.states:
                with self.subTest(from_state=from_state, to_state=to_state):
                    temporary_directory, operations, task = self.task_in_state(from_state)
                    try:
                        if to_state in self.allowed[from_state]:
                            result = operations.transition_task(
                                task["task_id"],
                                task["revision"],
                                to_state,
                                "test exception"
                                if to_state in {"failed", "needs_input"}
                                else None,
                            )
                            self.assertEqual(result["state"], to_state)
                        else:
                            with self.assertRaisesRegex(
                                OperationError, "prohibited transition"
                            ):
                                operations.transition_task(
                                    task["task_id"],
                                    task["revision"],
                                    to_state,
                                    "test exception",
                                )
                    finally:
                        operations.close()
                        temporary_directory.cleanup()


if __name__ == "__main__":
    unittest.main()
