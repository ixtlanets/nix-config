from __future__ import annotations

from datetime import UTC, datetime, timedelta
from copy import deepcopy
from difflib import SequenceMatcher
import hashlib
import json
from pathlib import Path
import sqlite3
from typing import Any, Protocol
from uuid import uuid4


class OperationError(RuntimeError):
    """A fail-closed error safe to return through an interface adapter."""


class Clock(Protocol):
    def now(self) -> datetime: ...


class ReleaseAdapter(Protocol):
    def search(self, queries: list[str]) -> list[dict[str, object]]: ...

    def inspect(self, candidate_id: str) -> dict[str, object]: ...

    def resolve(self, candidate_id: str) -> dict[str, object]: ...


class ExternalActionAdapter(Protocol):
    def find(self, kind: str, idempotency_key: str) -> str | None: ...

    def perform(
        self, kind: str, payload: dict[str, object], idempotency_key: str
    ) -> str: ...


class CatalogAdapter(Protocol):
    def get_item(self, library_id: str, item_id: str) -> dict[str, object]: ...


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(UTC)


class UnavailableReleaseAdapter:
    def search(self, queries: list[str]) -> list[dict[str, object]]:
        raise OperationError("release search adapter is unavailable")

    def inspect(self, candidate_id: str) -> dict[str, object]:
        raise KeyError(candidate_id)

    def resolve(self, candidate_id: str) -> dict[str, object]:
        raise KeyError(candidate_id)


class UnavailableCatalogAdapter:
    def get_item(self, library_id: str, item_id: str) -> dict[str, object]:
        raise KeyError((library_id, item_id))


class UnavailableExternalActionAdapter:
    def find(self, kind: str, idempotency_key: str) -> str | None:
        return None

    def perform(
        self, kind: str, payload: dict[str, object], idempotency_key: str
    ) -> str:
        raise OperationError("external action adapter is unavailable")


WRITE_TOOLS = {
    "metadata_apply",
    "metadata_undo",
    "request_apply",
    "task_cancel",
    "task_retry",
}
CANDIDATE_PUBLIC_FIELDS = frozenset(
    {
        "candidate_id",
        "format",
        "leechers",
        "matched_queries",
        "rank_evidence",
        "revision",
        "seeders",
        "size_bytes",
        "source",
        "title",
        "topic_excerpt",
        "topic_id",
        "topic_title",
    }
)

LEGAL_TRANSITIONS = {
    "queued": {"cancelled", "downloading", "failed", "needs_input"},
    "downloading": {"cancelled", "failed", "needs_input", "validating"},
    "validating": {"cancelled", "failed", "needs_input", "ready_to_publish"},
    "ready_to_publish": {"cancelled", "failed", "needs_input", "publishing"},
    "publishing": {"awaiting_abs", "failed", "needs_input"},
    "awaiting_abs": {"applying_metadata", "failed", "needs_input"},
    "applying_metadata": {"failed", "needs_input", "verified"},
    "needs_input": set(),
    "failed": set(),
    "cancelled": set(),
    "verified": set(),
}
TASK_STATES = frozenset(LEGAL_TRANSITIONS)

PUBLICATION_STARTED = {"publishing", "awaiting_abs", "applying_metadata", "verified"}
ACTIVE_STATES = {
    "downloading",
    "validating",
    "ready_to_publish",
    "publishing",
    "awaiting_abs",
    "applying_metadata",
}
RETRY_DELAYS_SECONDS = (60, 300, 900)
SCHEMA_VERSION = 2
METADATA_FIELDS = frozenset(
    {
        "abridged",
        "asin",
        "authors",
        "cover",
        "description",
        "explicit",
        "genres",
        "isbn",
        "language",
        "narrators",
        "published_date",
        "published_year",
        "publisher",
        "series",
        "subtitle",
        "tags",
        "title",
    }
)


def _canonical(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical(value).encode()).hexdigest()


def _timestamp(value: datetime) -> str:
    if value.tzinfo is None:
        raise ValueError("clock must return timezone-aware values")
    return value.astimezone(UTC).isoformat()


def _non_empty_string(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _normalized_text(value: object) -> str:
    return " ".join(str(value).casefold().replace("ё", "е").split())


class AudiobookOperations:
    """Deep domain module shared by transport and emergency CLI adapters."""

    def __init__(
        self,
        connection: sqlite3.Connection,
        *,
        clock: Clock,
        release_adapter: ReleaseAdapter,
        external_action_adapter: ExternalActionAdapter,
        catalog_adapter: CatalogAdapter,
    ) -> None:
        self._connection = connection
        self._clock = clock
        self._releases = release_adapter
        self._external_actions = external_action_adapter
        self._catalog = catalog_adapter

    @classmethod
    def open(
        cls,
        database: Path | str,
        *,
        clock: Clock | None = None,
        release_adapter: ReleaseAdapter | None = None,
        external_action_adapter: ExternalActionAdapter | None = None,
        catalog_adapter: CatalogAdapter | None = None,
    ) -> AudiobookOperations:
        connection = sqlite3.connect(database, isolation_level=None, check_same_thread=False)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        try:
            cls._migrate(connection)
        except Exception:
            connection.close()
            raise
        return cls(
            connection,
            clock=clock or SystemClock(),
            release_adapter=release_adapter or UnavailableReleaseAdapter(),
            external_action_adapter=(
                external_action_adapter or UnavailableExternalActionAdapter()
            ),
            catalog_adapter=catalog_adapter or UnavailableCatalogAdapter(),
        )

    @staticmethod
    def _migrate(connection: sqlite3.Connection) -> None:
        has_migrations = connection.execute(
            """
            SELECT 1 FROM sqlite_master
             WHERE type = 'table' AND name = 'schema_migrations'
            """
        ).fetchone()
        if has_migrations:
            row = connection.execute(
                "SELECT COALESCE(MAX(version), 0) FROM schema_migrations"
            ).fetchone()
            if row[0] > SCHEMA_VERSION:
                raise OperationError(
                    f"database has newer schema version {row[0]}"
                )
        connection.executescript(
            """
            BEGIN IMMEDIATE;

            CREATE TABLE IF NOT EXISTS schema_migrations (
              version INTEGER PRIMARY KEY,
              applied_at TEXT NOT NULL
            );

            INSERT OR IGNORE INTO schema_migrations(version, applied_at)
            VALUES (1, '2026-09-13T00:00:00+00:00');

            INSERT OR IGNORE INTO schema_migrations(version, applied_at)
            VALUES (2, '2026-09-13T12:00:00+00:00');

            CREATE TABLE IF NOT EXISTS acquisition_plans (
              plan_id TEXT PRIMARY KEY,
              revision TEXT NOT NULL,
              candidate_id TEXT NOT NULL,
              candidate_revision TEXT NOT NULL,
              payload_json TEXT NOT NULL,
              created_at TEXT NOT NULL,
              expires_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS acquisition_tasks (
              task_id TEXT PRIMARY KEY,
              plan_id TEXT NOT NULL REFERENCES acquisition_plans(plan_id),
              candidate_id TEXT NOT NULL,
              candidate_source TEXT NOT NULL,
              topic_id TEXT,
              infohash TEXT,
              state TEXT NOT NULL,
              revision INTEGER NOT NULL,
              retry_count INTEGER NOT NULL DEFAULT 0,
              next_retry_at TEXT,
              resume_state TEXT,
              worker_id TEXT,
              origin_conversation_id TEXT NOT NULL,
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL
            );

            CREATE UNIQUE INDEX IF NOT EXISTS acquisition_tasks_source_topic
              ON acquisition_tasks(candidate_source, topic_id)
              WHERE topic_id IS NOT NULL;
            CREATE UNIQUE INDEX IF NOT EXISTS acquisition_tasks_infohash
              ON acquisition_tasks(infohash)
              WHERE infohash IS NOT NULL;

            CREATE TABLE IF NOT EXISTS task_transitions (
              transition_id INTEGER PRIMARY KEY AUTOINCREMENT,
              task_id TEXT NOT NULL REFERENCES acquisition_tasks(task_id),
              from_state TEXT,
              to_state TEXT NOT NULL,
              reason TEXT,
              occurred_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS plan_applications (
              plan_id TEXT PRIMARY KEY REFERENCES acquisition_plans(plan_id),
              task_id TEXT NOT NULL UNIQUE REFERENCES acquisition_tasks(task_id),
              applied_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS idempotency_results (
              idempotency_key TEXT PRIMARY KEY,
              operation TEXT NOT NULL,
              input_digest TEXT NOT NULL,
              result_json TEXT NOT NULL,
              created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS publications (
              publication_id TEXT PRIMARY KEY,
              task_id TEXT NOT NULL UNIQUE REFERENCES acquisition_tasks(task_id),
              worker_id TEXT NOT NULL,
              status TEXT NOT NULL,
              attempt INTEGER NOT NULL,
              claimed_at TEXT NOT NULL,
              acknowledged_at TEXT
            );

            CREATE TABLE IF NOT EXISTS external_actions (
              action_id TEXT PRIMARY KEY,
              task_id TEXT NOT NULL REFERENCES acquisition_tasks(task_id),
              kind TEXT NOT NULL,
              payload_json TEXT NOT NULL,
              input_digest TEXT NOT NULL,
              idempotency_key TEXT NOT NULL UNIQUE,
              status TEXT NOT NULL,
              external_id TEXT,
              created_at TEXT NOT NULL,
              acknowledged_at TEXT
            );

            CREATE TABLE IF NOT EXISTS notification_events (
              event_id INTEGER PRIMARY KEY AUTOINCREMENT,
              task_id TEXT NOT NULL REFERENCES acquisition_tasks(task_id),
              kind TEXT NOT NULL,
              origin_conversation_id TEXT NOT NULL,
              reason TEXT,
              created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS metadata_plans (
              plan_id TEXT PRIMARY KEY,
              revision TEXT NOT NULL,
              library_id TEXT NOT NULL,
              item_id TEXT NOT NULL,
              item_path TEXT NOT NULL,
              item_revision TEXT NOT NULL,
              payload_json TEXT NOT NULL,
              created_at TEXT NOT NULL,
              expires_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS managed_audiobooks (
              managed_audiobook_id TEXT PRIMARY KEY,
              task_id TEXT NOT NULL UNIQUE REFERENCES acquisition_tasks(task_id),
              library_id TEXT NOT NULL,
              item_id TEXT NOT NULL UNIQUE,
              item_path TEXT NOT NULL UNIQUE,
              item_revision TEXT NOT NULL,
              created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS acquisition_artifacts (
              task_id TEXT PRIMARY KEY REFERENCES acquisition_tasks(task_id),
              torrent_hash TEXT NOT NULL,
              staging_id TEXT NOT NULL UNIQUE,
              manifest_json TEXT NOT NULL,
              created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS acquisition_cleanups (
              task_id TEXT PRIMARY KEY REFERENCES acquisition_tasks(task_id),
              terminal_state TEXT NOT NULL,
              completed_at TEXT NOT NULL
            );

            COMMIT;
            """
        )

    def close(self) -> None:
        self._connection.close()

    def schema_version(self) -> int:
        row = self._connection.execute(
            "SELECT COALESCE(MAX(version), 0) FROM schema_migrations"
        ).fetchone()
        return int(row[0])

    def backup_to(self, destination: Path | str) -> dict[str, object]:
        target = Path(destination)
        if target.exists() or target.is_symlink():
            raise OperationError("backup destination already exists")
        if not target.parent.is_dir() or target.parent.is_symlink():
            raise OperationError("backup destination parent is unsafe")
        backup = sqlite3.connect(target)
        try:
            self._connection.backup(backup)
            integrity = backup.execute("PRAGMA integrity_check").fetchone()[0]
            version = backup.execute(
                "SELECT COALESCE(MAX(version), 0) FROM schema_migrations"
            ).fetchone()[0]
        except Exception:
            backup.close()
            target.unlink(missing_ok=True)
            raise
        backup.close()
        target.chmod(0o600)
        if integrity != "ok":
            target.unlink(missing_ok=True)
            raise OperationError("SQLite backup integrity check failed")
        return {"integrity": integrity, "schema_version": int(version)}

    @classmethod
    def restore_backup(
        cls, source: Path | str, destination: Path | str
    ) -> dict[str, object]:
        backup_path = Path(source)
        target = Path(destination)
        if (
            not backup_path.is_file()
            or backup_path.is_symlink()
            or backup_path.resolve() == target.resolve()
        ):
            raise OperationError("backup source is missing or unsafe")
        if target.exists() or target.is_symlink():
            raise OperationError("restore destination already exists")
        if not target.parent.is_dir() or target.parent.is_symlink():
            raise OperationError("restore destination parent is unsafe")
        source_connection = sqlite3.connect(
            f"{backup_path.resolve().as_uri()}?mode=ro", uri=True
        )
        destination_connection: sqlite3.Connection | None = None
        try:
            integrity = source_connection.execute("PRAGMA integrity_check").fetchone()[0]
            if integrity != "ok":
                raise OperationError("SQLite backup integrity check failed")
            version = source_connection.execute(
                "SELECT COALESCE(MAX(version), 0) FROM schema_migrations"
            ).fetchone()[0]
            if version > SCHEMA_VERSION:
                raise OperationError("backup has a newer schema version")
            destination_connection = sqlite3.connect(target)
            source_connection.backup(destination_connection)
            restored_integrity = destination_connection.execute(
                "PRAGMA integrity_check"
            ).fetchone()[0]
            if restored_integrity != "ok":
                raise OperationError("restored SQLite integrity check failed")
        except Exception:
            if destination_connection is not None:
                destination_connection.close()
            source_connection.close()
            target.unlink(missing_ok=True)
            raise
        destination_connection.close()
        source_connection.close()
        target.chmod(0o600)
        return {"integrity": "ok", "schema_version": int(version)}

    def invoke(
        self,
        tool_name: str,
        arguments: dict[str, object],
        *,
        mutation_authorized: bool = False,
    ) -> dict[str, object]:
        if tool_name in WRITE_TOOLS and not mutation_authorized:
            raise OperationError("mutation requires execution gate")
        if tool_name == "request_plan":
            return self._request_plan(arguments)
        if tool_name == "request_apply":
            return self._request_apply(arguments)
        if tool_name == "task_list":
            return {"tasks": self._task_list(arguments)}
        if tool_name == "task_get":
            return self._task_view(str(arguments.get("task_id", "")))
        if tool_name == "task_cancel":
            return self._task_cancel(arguments)
        if tool_name == "task_retry":
            return self._task_retry(arguments)
        if tool_name == "notification_list":
            return self._notification_list(arguments)
        if tool_name == "metadata_plan":
            return self._metadata_plan(arguments)
        if tool_name == "release_search":
            return self._release_search(arguments)
        if tool_name == "release_inspect":
            return self._candidate_public(
                self._inspect_candidate(str(arguments.get("candidate_id", "")))
            )
        raise OperationError(f"unknown operation: {tool_name}")

    def _release_search(self, arguments: dict[str, object]) -> dict[str, object]:
        queries = arguments.get("queries")
        if (
            not isinstance(queries, list)
            or not 1 <= len(queries) <= 12
            or any(not _non_empty_string(query) for query in queries)
        ):
            raise OperationError("one to twelve non-empty search queries are required")
        try:
            candidates = self._releases.search(queries)
        except (KeyError, ValueError) as error:
            raise OperationError("release search failed") from error
        if not isinstance(candidates, list) or any(
            not isinstance(candidate, dict) for candidate in candidates
        ):
            raise OperationError("release adapter returned invalid candidates")
        return {
            "candidates": [self._candidate_public(candidate) for candidate in candidates]
        }

    @staticmethod
    def _candidate_public(candidate: dict[str, object]) -> dict[str, object]:
        return {
            key: deepcopy(value)
            for key, value in candidate.items()
            if key in CANDIDATE_PUBLIC_FIELDS
        }

    def register_managed_audiobook(
        self,
        task_id: str,
        expected_revision: int,
        exact_item: dict[str, object],
    ) -> dict[str, object]:
        required = ("library_id", "item_id", "path", "revision")
        if any(not isinstance(exact_item.get(key), str) or not exact_item[key] for key in required):
            raise OperationError("exact managed audiobook identity is required")
        observed = self._catalog_item(
            str(exact_item["library_id"]), str(exact_item["item_id"])
        )
        if any(observed.get(key) != exact_item[key] for key in required):
            raise OperationError("managed audiobook identity changed")
        try:
            self._connection.execute("BEGIN IMMEDIATE")
            task = self._connection.execute(
                "SELECT state, revision FROM acquisition_tasks WHERE task_id = ?",
                (task_id,),
            ).fetchone()
            if task is None:
                raise OperationError("unknown acquisition task")
            if task["revision"] != expected_revision:
                raise OperationError("stale task revision")
            if task["state"] != "awaiting_abs":
                raise OperationError("managed audiobook can only bind while awaiting ABS")
            managed_id = str(uuid4())
            now = _timestamp(self._clock.now())
            self._connection.execute(
                """
                INSERT INTO managed_audiobooks(
                  managed_audiobook_id, task_id, library_id, item_id, item_path,
                  item_revision, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    managed_id,
                    task_id,
                    exact_item["library_id"],
                    exact_item["item_id"],
                    exact_item["path"],
                    exact_item["revision"],
                    now,
                ),
            )
            task_view = self._transition_locked(
                task_id, expected_revision, "applying_metadata", None
            )
            self._connection.execute("COMMIT")
            return {
                "managed_audiobook": {
                    "entity_kind": "managed_audiobook",
                    "managed_audiobook_id": managed_id,
                    "task_id": task_id,
                    **exact_item,
                },
                "task": task_view,
            }
        except Exception:
            if self._connection.in_transaction:
                self._connection.execute("ROLLBACK")
            raise

    def acquisition_source(self, task_id: str) -> dict[str, object]:
        row = self._connection.execute(
            """
            SELECT plan.payload_json
              FROM acquisition_tasks AS task
              JOIN acquisition_plans AS plan ON plan.plan_id = task.plan_id
             WHERE task.task_id = ?
            """,
            (task_id,),
        ).fetchone()
        if row is None:
            raise OperationError("unknown acquisition task")
        payload = json.loads(row["payload_json"])
        resolution = payload.get("candidate_resolution")
        if not isinstance(resolution, dict):
            raise OperationError("task has no internal release resolution")
        return deepcopy(resolution)

    def record_validated_artifact(
        self,
        task_id: str,
        expected_revision: int,
        torrent_hash: str,
        artifact: dict[str, object],
    ) -> dict[str, object]:
        staging_id = artifact.get("staging_id")
        manifest = artifact.get("manifest")
        if (
            not _non_empty_string(torrent_hash)
            or not _non_empty_string(staging_id)
            or not isinstance(manifest, list)
            or not manifest
        ):
            raise OperationError("validated acquisition artifact is incomplete")
        try:
            self._connection.execute("BEGIN IMMEDIATE")
            task = self._connection.execute(
                "SELECT state, revision FROM acquisition_tasks WHERE task_id = ?",
                (task_id,),
            ).fetchone()
            if task is None:
                raise OperationError("unknown acquisition task")
            if task["revision"] != expected_revision:
                raise OperationError("stale task revision")
            if task["state"] != "validating":
                raise OperationError("artifact can only bind while validating")
            existing = self._connection.execute(
                "SELECT * FROM acquisition_artifacts WHERE task_id = ?", (task_id,)
            ).fetchone()
            if existing is not None:
                if (
                    existing["torrent_hash"] != torrent_hash
                    or existing["staging_id"] != staging_id
                    or existing["manifest_json"] != _canonical(manifest)
                ):
                    raise OperationError("validated acquisition artifact changed")
                result = self._transition_locked(
                    task_id, expected_revision, "ready_to_publish", None
                )
                self._connection.execute("COMMIT")
                return result
            now = _timestamp(self._clock.now())
            self._connection.execute(
                """
                INSERT INTO acquisition_artifacts(
                  task_id, torrent_hash, staging_id, manifest_json, created_at
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (task_id, torrent_hash, staging_id, _canonical(manifest), now),
            )
            result = self._transition_locked(
                task_id, expected_revision, "ready_to_publish", None
            )
            self._connection.execute("COMMIT")
            return result
        except Exception:
            if self._connection.in_transaction:
                self._connection.execute("ROLLBACK")
            raise

    def validated_artifact(self, task_id: str) -> dict[str, object]:
        row = self._connection.execute(
            "SELECT * FROM acquisition_artifacts WHERE task_id = ?", (task_id,)
        ).fetchone()
        if row is None:
            raise OperationError("task has no validated acquisition artifact")
        return {
            "task_id": row["task_id"],
            "torrent_hash": row["torrent_hash"],
            "staging_id": row["staging_id"],
            "manifest": json.loads(row["manifest_json"]),
            "created_at": row["created_at"],
        }

    def cleanup_pending_tasks(self) -> list[dict[str, object]]:
        rows = self._connection.execute(
            """
            SELECT task.task_id
              FROM acquisition_tasks AS task
              LEFT JOIN acquisition_cleanups AS cleanup
                ON cleanup.task_id = task.task_id
             WHERE task.state IN ('cancelled', 'verified')
               AND cleanup.task_id IS NULL
             ORDER BY task.created_at, task.task_id
            """
        ).fetchall()
        return [self._task_view(str(row["task_id"])) for row in rows]

    def mark_acquisition_cleanup(self, task_id: str, terminal_state: str) -> None:
        if terminal_state not in {"cancelled", "verified"}:
            raise OperationError("cleanup requires a terminal acquisition state")
        try:
            self._connection.execute("BEGIN IMMEDIATE")
            task = self._connection.execute(
                "SELECT state FROM acquisition_tasks WHERE task_id = ?", (task_id,)
            ).fetchone()
            if task is None:
                raise OperationError("unknown acquisition task")
            if task["state"] != terminal_state:
                raise OperationError("cleanup terminal state changed")
            existing = self._connection.execute(
                "SELECT terminal_state FROM acquisition_cleanups WHERE task_id = ?",
                (task_id,),
            ).fetchone()
            if existing is not None and existing["terminal_state"] != terminal_state:
                raise OperationError("cleanup completion identity changed")
            self._connection.execute(
                """
                INSERT OR IGNORE INTO acquisition_cleanups(
                  task_id, terminal_state, completed_at
                ) VALUES (?, ?, ?)
                """,
                (task_id, terminal_state, _timestamp(self._clock.now())),
            )
            self._connection.execute("COMMIT")
        except Exception:
            if self._connection.in_transaction:
                self._connection.execute("ROLLBACK")
            raise

    def _catalog_item(self, library_id: str, item_id: str) -> dict[str, object]:
        try:
            item = self._catalog.get_item(library_id, item_id)
        except (KeyError, ValueError) as error:
            raise OperationError("unknown library item") from error
        if item.get("library_id") != library_id or item.get("item_id") != item_id:
            raise OperationError("catalog adapter returned a different item")
        return item

    def _metadata_plan(self, arguments: dict[str, object]) -> dict[str, object]:
        library_id = str(arguments.get("library_id", ""))
        item_id = str(arguments.get("item_id", ""))
        item_revision = str(arguments.get("item_revision", ""))
        changes = arguments.get("changes")
        if (
            not library_id
            or not item_id
            or not item_revision
            or not isinstance(changes, dict)
            or not changes
        ):
            raise OperationError("exact item revision and metadata changes are required")
        item = self._catalog_item(library_id, item_id)
        if item.get("revision") != item_revision:
            raise OperationError("item revision changed")
        before = {
            "metadata": deepcopy(item.get("metadata", {})),
            "cover": deepcopy(item.get("cover")),
        }
        after = deepcopy(before)
        for field, change in changes.items():
            if field not in METADATA_FIELDS or not isinstance(change, dict):
                raise OperationError(f"invalid metadata change for {field}")
            if (
                change.get("operation") not in {"set", "clear"}
                or not _non_empty_string(change.get("source"))
                or change.get("confidence") not in {"low", "medium", "high"}
            ):
                raise OperationError(f"invalid metadata provenance for {field}")
            try:
                observed_at = datetime.fromisoformat(str(change.get("observed_at", "")))
            except ValueError as error:
                raise OperationError(
                    f"invalid metadata observation time for {field}"
                ) from error
            if observed_at.tzinfo is None:
                raise OperationError(f"invalid metadata observation time for {field}")
            if change["operation"] == "set" and "value" not in change:
                raise OperationError(f"invalid metadata value for {field}")
            if field == "cover":
                after["cover"] = change.get("value") if change["operation"] == "set" else None
            else:
                metadata = after["metadata"]
                if not isinstance(metadata, dict):
                    raise OperationError("invalid catalog metadata")
                metadata[field] = change.get("value") if change["operation"] == "set" else None
        now = self._clock.now()
        expires_at = now + timedelta(hours=24)
        target = {
            "library_id": library_id,
            "item_id": item_id,
            "path": item.get("path"),
            "revision": item_revision,
        }
        payload = {"target": target, "before": before, "after": after, "changes": changes}
        revision = _digest(payload)
        plan_id = str(uuid4())
        self._connection.execute(
            """
            INSERT INTO metadata_plans(
              plan_id, revision, library_id, item_id, item_path, item_revision,
              payload_json, created_at, expires_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                plan_id,
                revision,
                library_id,
                item_id,
                item.get("path"),
                item_revision,
                _canonical(payload),
                _timestamp(now),
                _timestamp(expires_at),
            ),
        )
        return {
            "entity_kind": "metadata_plan",
            "plan_id": plan_id,
            "revision": revision,
            "expires_at": _timestamp(expires_at),
            **payload,
        }

    def record_transient_failure(
        self,
        task_id: str,
        expected_revision: int,
        reason: str,
    ) -> dict[str, object]:
        if not reason:
            raise OperationError("failure reason is required")
        try:
            self._connection.execute("BEGIN IMMEDIATE")
            row = self._connection.execute(
                """
                SELECT state, revision, retry_count FROM acquisition_tasks
                 WHERE task_id = ?
                """,
                (task_id,),
            ).fetchone()
            if row is None:
                raise OperationError("unknown acquisition task")
            if row["revision"] != expected_revision:
                raise OperationError("stale task revision")
            if row["state"] not in ACTIVE_STATES:
                raise OperationError("transient retry is not allowed in this state")
            if row["retry_count"] >= len(RETRY_DELAYS_SECONDS):
                self._connection.execute(
                    "UPDATE acquisition_tasks SET resume_state = ? WHERE task_id = ?",
                    (row["state"], task_id),
                )
                result = self._transition_locked(
                    task_id,
                    expected_revision,
                    "failed",
                    "transient retry budget exhausted",
                )
            else:
                retry_count = row["retry_count"] + 1
                next_retry = self._clock.now() + timedelta(
                    seconds=RETRY_DELAYS_SECONDS[retry_count - 1]
                )
                now = _timestamp(self._clock.now())
                self._connection.execute(
                    """
                    UPDATE acquisition_tasks
                       SET retry_count = ?, next_retry_at = ?,
                           revision = revision + 1, updated_at = ?
                     WHERE task_id = ?
                    """,
                    (retry_count, _timestamp(next_retry), now, task_id),
                )
                self._connection.execute(
                    """
                    INSERT INTO task_transitions(
                      task_id, from_state, to_state, reason, occurred_at
                    ) VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        task_id,
                        row["state"],
                        row["state"],
                        f"transient retry {retry_count}/3: {reason}",
                        now,
                    ),
                )
                result = self._task_view(task_id)
            self._connection.execute("COMMIT")
            return result
        except Exception:
            if self._connection.in_transaction:
                self._connection.execute("ROLLBACK")
            raise

    def plan_external_action(
        self,
        task_id: str,
        expected_revision: int,
        kind: str,
        payload: dict[str, object],
        idempotency_key: str,
    ) -> dict[str, object]:
        if not kind or not idempotency_key or not isinstance(payload, dict):
            raise OperationError("external action kind, payload, and key are required")
        input_digest = _digest({"kind": kind, "payload": payload, "task_id": task_id})
        try:
            self._connection.execute("BEGIN IMMEDIATE")
            existing = self._connection.execute(
                "SELECT * FROM external_actions WHERE idempotency_key = ?",
                (idempotency_key,),
            ).fetchone()
            if existing is not None:
                if existing["input_digest"] != input_digest:
                    raise OperationError("external action idempotency key conflict")
                self._connection.execute("COMMIT")
                return self._action_view(existing)
            task = self._connection.execute(
                "SELECT revision FROM acquisition_tasks WHERE task_id = ?", (task_id,)
            ).fetchone()
            if task is None:
                raise OperationError("unknown acquisition task")
            if task["revision"] != expected_revision:
                raise OperationError("stale task revision")
            action_id = str(uuid4())
            now = _timestamp(self._clock.now())
            self._connection.execute(
                """
                INSERT INTO external_actions(
                  action_id, task_id, kind, payload_json, input_digest,
                  idempotency_key, status, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, 'pending', ?)
                """,
                (
                    action_id,
                    task_id,
                    kind,
                    _canonical(payload),
                    input_digest,
                    idempotency_key,
                    now,
                ),
            )
            self._connection.execute(
                """
                UPDATE acquisition_tasks
                   SET revision = revision + 1, updated_at = ? WHERE task_id = ?
                """,
                (now, task_id),
            )
            row = self._connection.execute(
                "SELECT * FROM external_actions WHERE action_id = ?", (action_id,)
            ).fetchone()
            result = self._action_view(row)
            self._connection.execute("COMMIT")
            return result
        except Exception:
            if self._connection.in_transaction:
                self._connection.execute("ROLLBACK")
            raise

    def reconcile_external_actions(self) -> list[dict[str, object]]:
        pending = self._connection.execute(
            """
            SELECT * FROM external_actions WHERE status = 'pending'
             ORDER BY created_at, action_id
            """
        ).fetchall()
        reconciled: list[dict[str, object]] = []
        for action in pending:
            external_id = self._external_actions.find(
                action["kind"], action["idempotency_key"]
            )
            if external_id is None:
                external_id = self._external_actions.perform(
                    action["kind"],
                    json.loads(action["payload_json"]),
                    action["idempotency_key"],
                )
            now = _timestamp(self._clock.now())
            try:
                self._connection.execute("BEGIN IMMEDIATE")
                current = self._connection.execute(
                    "SELECT * FROM external_actions WHERE action_id = ?",
                    (action["action_id"],),
                ).fetchone()
                if current["status"] == "pending":
                    self._connection.execute(
                        """
                        UPDATE external_actions
                           SET status = 'acknowledged', external_id = ?,
                               acknowledged_at = ?
                         WHERE action_id = ?
                        """,
                        (external_id, now, action["action_id"]),
                    )
                current = self._connection.execute(
                    "SELECT * FROM external_actions WHERE action_id = ?",
                    (action["action_id"],),
                ).fetchone()
                self._connection.execute("COMMIT")
                reconciled.append(self._action_view(current))
            except Exception:
                if self._connection.in_transaction:
                    self._connection.execute("ROLLBACK")
                raise
        return reconciled

    @staticmethod
    def _action_view(row: sqlite3.Row) -> dict[str, object]:
        return {
            "action_id": row["action_id"],
            "task_id": row["task_id"],
            "kind": row["kind"],
            "status": row["status"],
            "external_id": row["external_id"],
        }

    def claim_next_task(self, worker_id: str) -> dict[str, object] | None:
        if not worker_id:
            raise OperationError("worker ID is required")
        try:
            self._connection.execute("BEGIN IMMEDIATE")
            placeholders = ",".join("?" for _ in ACTIVE_STATES)
            active = self._connection.execute(
                f"SELECT task_id FROM acquisition_tasks WHERE state IN ({placeholders}) LIMIT 1",
                tuple(sorted(ACTIVE_STATES)),
            ).fetchone()
            if active is not None:
                self._connection.execute("COMMIT")
                return None
            row = self._connection.execute(
                """
                SELECT task_id, revision FROM acquisition_tasks
                 WHERE state = 'queued' ORDER BY created_at, task_id LIMIT 1
                """
            ).fetchone()
            if row is None:
                self._connection.execute("COMMIT")
                return None
            self._connection.execute(
                "UPDATE acquisition_tasks SET worker_id = ? WHERE task_id = ?",
                (worker_id, row["task_id"]),
            )
            result = self._transition_locked(
                row["task_id"], row["revision"], "downloading", None
            )
            self._connection.execute("COMMIT")
            return result
        except Exception:
            if self._connection.in_transaction:
                self._connection.execute("ROLLBACK")
            raise

    def claim_publication(self, worker_id: str) -> dict[str, object] | None:
        if not worker_id:
            raise OperationError("publisher ID is required")
        try:
            self._connection.execute("BEGIN IMMEDIATE")
            row = self._connection.execute(
                """
                SELECT task_id, revision FROM acquisition_tasks
                 WHERE state = 'ready_to_publish'
                 ORDER BY created_at, task_id LIMIT 1
                """
            ).fetchone()
            if row is None:
                self._connection.execute("COMMIT")
                return None
            publication_id = str(uuid4())
            now = _timestamp(self._clock.now())
            self._connection.execute(
                """
                INSERT INTO publications(
                  publication_id, task_id, worker_id, status, attempt, claimed_at
                ) VALUES (?, ?, ?, 'claimed', 1, ?)
                """,
                (publication_id, row["task_id"], worker_id, now),
            )
            task = self._transition_locked(
                row["task_id"], row["revision"], "publishing", None
            )
            self._connection.execute("COMMIT")
            return {
                "publication": {
                    "publication_id": publication_id,
                    "task_id": row["task_id"],
                    "worker_id": worker_id,
                    "status": "claimed",
                    "attempt": 1,
                    "claimed_at": now,
                },
                "task": task,
            }
        except Exception:
            if self._connection.in_transaction:
                self._connection.execute("ROLLBACK")
            raise

    def transition_task(
        self,
        task_id: str,
        expected_revision: int,
        to_state: str,
        reason: str | None = None,
    ) -> dict[str, object]:
        try:
            self._connection.execute("BEGIN IMMEDIATE")
            result = self._transition_locked(
                task_id, expected_revision, to_state, reason
            )
            self._connection.execute("COMMIT")
            return result
        except Exception:
            if self._connection.in_transaction:
                self._connection.execute("ROLLBACK")
            raise

    def _transition_locked(
        self,
        task_id: str,
        expected_revision: int,
        to_state: str,
        reason: str | None,
    ) -> dict[str, object]:
        row = self._connection.execute(
            "SELECT state, revision FROM acquisition_tasks WHERE task_id = ?", (task_id,)
        ).fetchone()
        if row is None:
            raise OperationError("unknown acquisition task")
        if row["revision"] != expected_revision:
            raise OperationError("stale task revision")
        if to_state not in LEGAL_TRANSITIONS.get(row["state"], set()):
            raise OperationError(
                f"prohibited transition: {row['state']} -> {to_state}"
            )
        now = _timestamp(self._clock.now())
        if to_state in {"failed", "needs_input"}:
            if not reason:
                raise OperationError("exception transition requires a reason")
            self._connection.execute(
                "UPDATE acquisition_tasks SET resume_state = ? WHERE task_id = ?",
                (row["state"], task_id),
            )
        self._connection.execute(
            """
            UPDATE acquisition_tasks
               SET state = ?, revision = revision + 1, next_retry_at = NULL,
                   updated_at = ?
             WHERE task_id = ?
            """,
            (to_state, now, task_id),
        )
        self._connection.execute(
            """
            INSERT INTO task_transitions(
              task_id, from_state, to_state, reason, occurred_at
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (task_id, row["state"], to_state, reason, now),
        )
        if to_state in {"failed", "needs_input", "verified"}:
            origin = self._connection.execute(
                "SELECT origin_conversation_id FROM acquisition_tasks WHERE task_id = ?",
                (task_id,),
            ).fetchone()["origin_conversation_id"]
            self._connection.execute(
                """
                INSERT INTO notification_events(
                  task_id, kind, origin_conversation_id, reason, created_at
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (task_id, to_state, origin, reason, now),
            )
        return self._task_view(task_id)

    def _task_cancel(self, arguments: dict[str, object]) -> dict[str, object]:
        task_id = str(arguments.get("task_id", ""))
        idempotency_key = str(arguments.get("idempotency_key", ""))
        expected_revision = arguments.get("expected_revision")
        if not task_id or not idempotency_key or not isinstance(expected_revision, int):
            raise OperationError("task, revision, and idempotency key are required")
        input_digest = _digest(
            {"task_id": task_id, "expected_revision": expected_revision}
        )
        replay = self._idempotent_replay(
            idempotency_key, "task_cancel", input_digest
        )
        if replay is not None:
            return replay
        try:
            self._connection.execute("BEGIN IMMEDIATE")
            replay = self._idempotent_replay(
                idempotency_key, "task_cancel", input_digest
            )
            if replay is not None:
                self._connection.execute("COMMIT")
                return replay
            current = self._connection.execute(
                "SELECT state FROM acquisition_tasks WHERE task_id = ?", (task_id,)
            ).fetchone()
            if current is None:
                raise OperationError("unknown acquisition task")
            if current["state"] in PUBLICATION_STARTED:
                raise OperationError("task cannot be cancelled after publication has begun")
            result = self._transition_locked(
                task_id, expected_revision, "cancelled", "owner cancellation"
            )
            now = _timestamp(self._clock.now())
            self._connection.execute(
                """
                INSERT INTO idempotency_results(
                  idempotency_key, operation, input_digest, result_json, created_at
                ) VALUES (?, 'task_cancel', ?, ?, ?)
                """,
                (idempotency_key, input_digest, _canonical(result), now),
            )
            self._connection.execute("COMMIT")
            return result
        except Exception:
            if self._connection.in_transaction:
                self._connection.execute("ROLLBACK")
            raise

    def _task_retry(self, arguments: dict[str, object]) -> dict[str, object]:
        task_id = str(arguments.get("task_id", ""))
        idempotency_key = str(arguments.get("idempotency_key", ""))
        expected_revision = arguments.get("expected_revision")
        if not task_id or not idempotency_key or not isinstance(expected_revision, int):
            raise OperationError("task, revision, and idempotency key are required")
        input_digest = _digest(
            {"task_id": task_id, "expected_revision": expected_revision}
        )
        replay = self._idempotent_replay(idempotency_key, "task_retry", input_digest)
        if replay is not None:
            return replay
        try:
            self._connection.execute("BEGIN IMMEDIATE")
            replay = self._idempotent_replay(
                idempotency_key, "task_retry", input_digest
            )
            if replay is not None:
                self._connection.execute("COMMIT")
                return replay
            row = self._connection.execute(
                """
                SELECT state, revision, resume_state FROM acquisition_tasks
                 WHERE task_id = ?
                """,
                (task_id,),
            ).fetchone()
            if row is None:
                raise OperationError("unknown acquisition task")
            if row["revision"] != expected_revision:
                raise OperationError("stale task revision")
            if row["state"] not in {"failed", "needs_input"} or not row["resume_state"]:
                raise OperationError("task is not retryable")
            if row["resume_state"] in ACTIVE_STATES:
                placeholders = ",".join("?" for _ in ACTIVE_STATES)
                active = self._connection.execute(
                    f"SELECT task_id FROM acquisition_tasks "
                    f"WHERE state IN ({placeholders}) AND task_id != ? LIMIT 1",
                    (*sorted(ACTIVE_STATES), task_id),
                ).fetchone()
                if active is not None:
                    raise OperationError("another acquisition is active")
            now = _timestamp(self._clock.now())
            self._connection.execute(
                """
                UPDATE acquisition_tasks
                   SET state = ?, revision = revision + 1, retry_count = 0,
                       next_retry_at = NULL, resume_state = NULL, updated_at = ?
                 WHERE task_id = ?
                """,
                (row["resume_state"], now, task_id),
            )
            self._connection.execute(
                """
                INSERT INTO task_transitions(
                  task_id, from_state, to_state, reason, occurred_at
                ) VALUES (?, ?, ?, 'owner-approved retry', ?)
                """,
                (task_id, row["state"], row["resume_state"], now),
            )
            result = self._task_view(task_id)
            self._connection.execute(
                """
                INSERT INTO idempotency_results(
                  idempotency_key, operation, input_digest, result_json, created_at
                ) VALUES (?, 'task_retry', ?, ?, ?)
                """,
                (idempotency_key, input_digest, _canonical(result), now),
            )
            self._connection.execute("COMMIT")
            return result
        except Exception:
            if self._connection.in_transaction:
                self._connection.execute("ROLLBACK")
            raise

    def _request_plan(self, arguments: dict[str, object]) -> dict[str, object]:
        candidate_id = str(arguments.get("candidate_id", ""))
        expected_revision = str(arguments.get("candidate_revision", ""))
        work = arguments.get("work")
        audio_edition = arguments.get("audio_edition")
        origin = str(arguments.get("origin_conversation_id", ""))
        if not candidate_id or not expected_revision or not origin:
            raise OperationError("candidate, revision, and origin are required")
        if not isinstance(work, dict) or not isinstance(audio_edition, dict):
            raise OperationError("work and audio edition are required")
        authors = work.get("authors")
        series = work.get("series", [])
        if (
            not _non_empty_string(work.get("title"))
            or not isinstance(authors, list)
            or not authors
            or any(not _non_empty_string(author) for author in authors)
            or not isinstance(series, list)
            or any(
                not isinstance(membership, dict)
                or not _non_empty_string(membership.get("name"))
                or not _non_empty_string(membership.get("sequence"))
                for membership in series
            )
        ):
            raise OperationError("invalid work")
        narrators = audio_edition.get("narrators")
        narrator_unknown = audio_edition.get("narrator_unknown", False)
        if (
            not isinstance(narrators, list)
            or any(not _non_empty_string(narrator) for narrator in narrators)
            or not isinstance(narrator_unknown, bool)
            or (not narrators and not narrator_unknown)
        ):
            raise OperationError("invalid audio edition")

        candidate = self._inspect_candidate(candidate_id)
        if candidate["revision"] != expected_revision:
            raise OperationError("candidate revision changed")
        try:
            candidate_resolution = self._releases.resolve(candidate_id)
        except (KeyError, ValueError) as error:
            raise OperationError("release candidate cannot be resolved") from error
        if not isinstance(candidate_resolution, dict):
            raise OperationError("release candidate resolution is invalid")
        work = dict(work)
        work["work_id"] = str(uuid4())
        audio_edition = dict(audio_edition)
        audio_edition["edition_id"] = str(uuid4())
        audio_edition["work_id"] = work["work_id"]
        work_title = _normalized_text(work["title"])
        work_authors = tuple(
            sorted(_normalized_text(author) for author in work["authors"])
        )
        warnings: list[str] = []
        existing_plans = self._connection.execute(
            """
            SELECT plan.payload_json
              FROM acquisition_tasks AS task
              JOIN acquisition_plans AS plan ON plan.plan_id = task.plan_id
            """
        ).fetchall()
        for existing_plan in existing_plans:
            existing_work = json.loads(existing_plan["payload_json"])["work"]
            existing_title = _normalized_text(existing_work.get("title"))
            existing_authors = tuple(
                sorted(
                    _normalized_text(author)
                    for author in existing_work.get("authors", [])
                )
            )
            title_similarity = SequenceMatcher(
                None, existing_title, work_title, autojunk=False
            ).ratio()
            if existing_authors == work_authors and title_similarity >= 0.8:
                warnings.append(
                    "possible existing work or audio edition requires owner review"
                )
                break
        now = self._clock.now()
        plan_id = str(uuid4())
        payload = {
            "audio_edition": audio_edition,
            "candidate": candidate,
            "candidate_resolution": candidate_resolution,
            "origin_conversation_id": origin,
            "warnings": warnings,
            "work": work,
        }
        revision = _digest(payload)
        expires_at = now + timedelta(hours=24)
        self._connection.execute(
            """
            INSERT INTO acquisition_plans(
              plan_id, revision, candidate_id, candidate_revision, payload_json,
              created_at, expires_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                plan_id,
                revision,
                candidate_id,
                expected_revision,
                _canonical(payload),
                _timestamp(now),
                _timestamp(expires_at),
            ),
        )
        public_candidate = self._candidate_public(candidate)
        return {
            "plan_id": plan_id,
            "revision": revision,
            "status": "awaiting_approval",
            "expires_at": _timestamp(expires_at),
            "candidate": public_candidate,
            "work": work,
            "audio_edition": audio_edition,
            "warnings": warnings,
        }

    def _inspect_candidate(self, candidate_id: str) -> dict[str, object]:
        try:
            candidate = self._releases.inspect(candidate_id)
        except (KeyError, ValueError) as error:
            raise OperationError("unknown release candidate") from error
        required = {"candidate_id", "revision", "source"}
        if not required.issubset(candidate) or candidate["candidate_id"] != candidate_id:
            raise OperationError("invalid release candidate")
        return candidate

    def _request_apply(self, arguments: dict[str, object]) -> dict[str, object]:
        plan_id = str(arguments.get("plan_id", ""))
        revision = str(arguments.get("revision", ""))
        idempotency_key = str(arguments.get("idempotency_key", ""))
        if not plan_id or not revision or not idempotency_key:
            raise OperationError("plan, revision, and idempotency key are required")
        input_digest = _digest({"plan_id": plan_id, "revision": revision})
        replay = self._idempotent_replay(idempotency_key, "request_apply", input_digest)
        if replay is not None:
            return replay

        plan = self._connection.execute(
            "SELECT * FROM acquisition_plans WHERE plan_id = ?", (plan_id,)
        ).fetchone()
        if plan is None:
            raise OperationError("unknown plan")
        if plan["revision"] != revision:
            raise OperationError("stale plan revision")
        if self._clock.now() > datetime.fromisoformat(plan["expires_at"]):
            raise OperationError("plan expired")
        candidate = self._inspect_candidate(plan["candidate_id"])
        if candidate["revision"] != plan["candidate_revision"]:
            raise OperationError("candidate revision changed")

        now = _timestamp(self._clock.now())
        task_id = str(uuid4())
        payload = json.loads(plan["payload_json"])
        candidate_resolution = payload.get("candidate_resolution", {})
        if not isinstance(candidate_resolution, dict):
            raise OperationError("release candidate resolution is invalid")
        infohash = candidate_resolution.get("infohash")
        try:
            self._connection.execute("BEGIN IMMEDIATE")
            replay = self._idempotent_replay(
                idempotency_key, "request_apply", input_digest
            )
            if replay is not None:
                self._connection.execute("COMMIT")
                return replay
            duplicate = self._connection.execute(
                """
                SELECT task_id FROM acquisition_tasks
                 WHERE (candidate_source = ? AND topic_id = ?)
                    OR (infohash IS NOT NULL AND infohash = ?)
                 LIMIT 1
                """,
                (
                    str(candidate["source"]),
                    candidate.get("topic_id"),
                    infohash,
                ),
            ).fetchone()
            if duplicate is not None:
                raise OperationError("exact release duplicate")
            self._connection.execute(
                """
                INSERT INTO acquisition_tasks(
                  task_id, plan_id, candidate_id, candidate_source, topic_id,
                  infohash, state, revision, origin_conversation_id, created_at,
                  updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, 'queued', 2, ?, ?, ?)
                """,
                (
                    task_id,
                    plan_id,
                    plan["candidate_id"],
                    str(candidate["source"]),
                    candidate.get("topic_id"),
                    infohash,
                    payload["origin_conversation_id"],
                    now,
                    now,
                ),
            )
            for from_state, to_state in (
                (None, "draft"),
                ("draft", "awaiting_approval"),
                ("awaiting_approval", "queued"),
            ):
                self._connection.execute(
                    """
                    INSERT INTO task_transitions(
                      task_id, from_state, to_state, occurred_at
                    ) VALUES (?, ?, ?, ?)
                    """,
                    (task_id, from_state, to_state, now),
                )
            self._connection.execute(
                "INSERT INTO plan_applications(plan_id, task_id, applied_at) VALUES (?, ?, ?)",
                (plan_id, task_id, now),
            )
            result = self._task_view(task_id)
            self._connection.execute(
                """
                INSERT INTO idempotency_results(
                  idempotency_key, operation, input_digest, result_json, created_at
                ) VALUES (?, 'request_apply', ?, ?, ?)
                """,
                (idempotency_key, input_digest, _canonical(result), now),
            )
            self._connection.execute("COMMIT")
            return result
        except Exception:
            if self._connection.in_transaction:
                self._connection.execute("ROLLBACK")
            raise

    def _idempotent_replay(
        self, key: str, operation: str, input_digest: str
    ) -> dict[str, object] | None:
        row = self._connection.execute(
            "SELECT * FROM idempotency_results WHERE idempotency_key = ?", (key,)
        ).fetchone()
        if row is None:
            return None
        if row["operation"] != operation or row["input_digest"] != input_digest:
            raise OperationError("idempotency key conflict")
        return json.loads(row["result_json"])

    def _notification_list(self, arguments: dict[str, object]) -> dict[str, object]:
        after_event_id = arguments.get("after_event_id", 0)
        limit = arguments.get("limit", 100)
        if not isinstance(after_event_id, int) or after_event_id < 0:
            raise OperationError("notification cursor must be a non-negative integer")
        if not isinstance(limit, int) or not 1 <= limit <= 100:
            raise OperationError("notification limit must be between 1 and 100")
        rows = self._connection.execute(
            """
            SELECT event_id, task_id, kind, origin_conversation_id, reason, created_at
              FROM notification_events WHERE event_id > ?
             ORDER BY event_id LIMIT ?
            """,
            (after_event_id, limit),
        ).fetchall()
        events = [dict(row) for row in rows]
        cursor = events[-1]["event_id"] if events else after_event_id
        return {"events": events, "cursor": cursor}

    def _task_list(
        self, arguments: dict[str, object] | None = None
    ) -> list[dict[str, object]]:
        requested_states = (arguments or {}).get("states")
        if requested_states is None:
            rows = self._connection.execute(
                "SELECT task_id FROM acquisition_tasks ORDER BY created_at, task_id"
            ).fetchall()
        else:
            if (
                not isinstance(requested_states, list)
                or not requested_states
                or any(state not in TASK_STATES for state in requested_states)
            ):
                raise OperationError("unknown task state")
            placeholders = ",".join("?" for _ in requested_states)
            rows = self._connection.execute(
                f"SELECT task_id FROM acquisition_tasks WHERE state IN ({placeholders}) "
                "ORDER BY created_at, task_id",
                requested_states,
            ).fetchall()
        return [self._task_view(row["task_id"]) for row in rows]

    def _task_view(self, task_id: str) -> dict[str, object]:
        row = self._connection.execute(
            "SELECT * FROM acquisition_tasks WHERE task_id = ?", (task_id,)
        ).fetchone()
        if row is None:
            raise OperationError("unknown acquisition task")
        transitions = self._connection.execute(
            """
            SELECT from_state, to_state, reason, occurred_at
              FROM task_transitions WHERE task_id = ? ORDER BY transition_id
            """,
            (task_id,),
        ).fetchall()
        plan = self._connection.execute(
            "SELECT payload_json FROM acquisition_plans WHERE plan_id = ?",
            (row["plan_id"],),
        ).fetchone()
        payload = json.loads(plan["payload_json"])
        return {
            "task_id": row["task_id"],
            "plan_id": row["plan_id"],
            "candidate_id": row["candidate_id"],
            "state": row["state"],
            "revision": row["revision"],
            "retry_count": row["retry_count"],
            "next_retry_at": row["next_retry_at"],
            "resume_state": row["resume_state"],
            "origin_conversation_id": row["origin_conversation_id"],
            "candidate": self._candidate_public(payload["candidate"]),
            "work": payload["work"],
            "audio_edition": payload["audio_edition"],
            "transitions": [dict(transition) for transition in transitions],
        }
