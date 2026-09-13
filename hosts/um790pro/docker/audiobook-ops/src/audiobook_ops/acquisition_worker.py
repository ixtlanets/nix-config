from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Protocol

from audiobook_ops.interface import AudiobookOperations, Clock, OperationError
from audiobook_ops.validation import MediaValidator


class Transmission(Protocol):
    def submit(
        self, resolution: dict[str, object], idempotency_key: str
    ) -> str: ...

    def find(self, idempotency_key: str) -> str | None: ...

    def observe(self, torrent_hash: str) -> dict[str, object]: ...

    def remove(self, torrent_hash: str) -> None: ...


class AcquisitionCoordinator:
    """Advance at most one acquisition using durable task and upstream identity."""

    def __init__(
        self,
        operations: AudiobookOperations,
        transmission: Transmission,
        validator: MediaValidator,
        clock: Clock,
        *,
        stall_after_seconds: int = 900,
    ) -> None:
        self._operations = operations
        self._transmission = transmission
        self._validator = validator
        self._clock = clock
        self._stall_after_seconds = stall_after_seconds

    def reconcile_once(self) -> dict[str, object] | None:
        active = self._operations.invoke(
            "task_list", {"states": ["downloading", "validating"]}
        )["tasks"]
        if active:
            task = active[0]
        else:
            queued = self._operations.invoke(
                "task_list", {"states": ["queued"]}
            )["tasks"]
            if queued:
                try:
                    self._validator.preflight(self._candidate_size(queued[0]))
                except OperationError:
                    return self._operations.transition_task(
                        str(queued[0]["task_id"]),
                        int(queued[0]["revision"]),
                        "needs_input",
                        "acquisition capacity policy is not satisfied",
                    )
            task = self._operations.claim_next_task("acquisition")
        if task is not None:
            return self._advance(task)

        terminal = self._operations.cleanup_pending_tasks()
        if not terminal:
            return None
        task = terminal[0]
        key = self._idempotency_key(str(task["task_id"]))
        torrent_hash = self._transmission.find(key)
        if torrent_hash is not None:
            self._transmission.remove(torrent_hash)
        self._validator.discard_staging(str(task["task_id"]))
        self._operations.mark_acquisition_cleanup(
            str(task["task_id"]), str(task["state"])
        )
        return task

    def _advance(self, task: dict[str, object]) -> dict[str, object]:
        task_id = str(task["task_id"])
        next_retry_at = task.get("next_retry_at")
        if isinstance(next_retry_at, str):
            retry_at = datetime.fromisoformat(next_retry_at)
            if self._clock.now() < retry_at:
                return task
        key = self._idempotency_key(task_id)
        if task["state"] == "downloading":
            try:
                self._validator.preflight(self._candidate_size(task))
            except OperationError:
                return self._operations.transition_task(
                    task_id,
                    int(task["revision"]),
                    "needs_input",
                    "acquisition capacity policy is not satisfied",
                )
            resolution = self._operations.acquisition_source(task_id)
            try:
                torrent_hash = self._transmission.submit(resolution, key)
                observed = self._transmission.observe(torrent_hash)
            except OperationError:
                return self._operations.record_transient_failure(
                    task_id,
                    int(task["revision"]),
                    "Transmission RPC is unavailable",
                )
            status = observed.get("status")
            if status == "complete":
                task = self._operations.transition_task(
                    task_id, int(task["revision"]), "validating"
                )
            elif status in {"error", "stopped"} or self._is_stalled(observed):
                return self._operations.record_transient_failure(
                    task_id,
                    int(task["revision"]),
                    "Transmission acquisition is stalled or unavailable",
                )
            else:
                return task

        try:
            torrent_hash = self._transmission.find(key)
        except OperationError:
            return self._operations.record_transient_failure(
                task_id,
                int(task["revision"]),
                "Transmission RPC is unavailable",
            )
        if torrent_hash is None:
            return self._operations.transition_task(
                task_id,
                int(task["revision"]),
                "needs_input",
                "Transmission acquisition identity is missing",
            )
        try:
            observed = self._transmission.observe(torrent_hash)
        except OperationError:
            return self._operations.record_transient_failure(
                task_id,
                int(task["revision"]),
                "Transmission RPC is unavailable",
            )
        if observed.get("status") != "complete":
            return self._operations.record_transient_failure(
                task_id,
                int(task["revision"]),
                "completed Transmission content is no longer stable",
            )
        try:
            artifact = self._validator.validate_and_stage(
                task_id, Path(str(observed["download_root"]))
            )
        except OperationError:
            return self._operations.transition_task(
                task_id,
                int(task["revision"]),
                "needs_input",
                "release validation failed",
            )
        return self._operations.record_validated_artifact(
            task_id, int(task["revision"]), torrent_hash, artifact
        )

    def _is_stalled(self, observed: dict[str, object]) -> bool:
        if int(observed.get("rate_download", 0) or 0) > 0:
            return False
        activity = int(observed.get("activity_at_epoch", 0) or 0)
        now = self._clock.now()
        if not isinstance(now, datetime) or now.tzinfo is None:
            raise OperationError("clock must return a timezone-aware value")
        return now.timestamp() - activity >= self._stall_after_seconds

    @staticmethod
    def _idempotency_key(task_id: str) -> str:
        return f"transmission:{task_id}"

    @staticmethod
    def _candidate_size(task: dict[str, object]) -> int:
        candidate = task.get("candidate")
        if not isinstance(candidate, dict):
            raise OperationError("task has no release candidate")
        size = candidate.get("size_bytes")
        if not isinstance(size, int):
            raise OperationError("candidate size is missing or invalid")
        return size
