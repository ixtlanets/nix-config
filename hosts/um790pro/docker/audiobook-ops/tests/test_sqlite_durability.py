from __future__ import annotations

from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path
import sqlite3
import tempfile
import unittest

from audiobook_ops.interface import AudiobookOperations, OperationError

from test_domain_interface import (
    FakeCatalogAdapter,
    FakeClock,
    FakeExternalActionAdapter,
    FakeReleaseAdapter,
)


class SQLiteDurabilityTests(unittest.TestCase):
    def adapters(self) -> dict[str, object]:
        return {
            "clock": FakeClock(datetime(2026, 9, 13, tzinfo=UTC)),
            "release_adapter": FakeReleaseAdapter(),
            "external_action_adapter": FakeExternalActionAdapter(),
            "catalog_adapter": FakeCatalogAdapter(),
        }

    def create_task(self, operations: AudiobookOperations) -> dict[str, object]:
        plan = operations.invoke(
            "request_plan",
            {
                "candidate_id": "candidate-one",
                "candidate_revision": "source-revision-one",
                "work": {
                    "title": "Кляксы",
                    "authors": ["Борис Конофальский"],
                    "series": [{"name": "Глубокий рейд", "sequence": "4"}],
                },
                "audio_edition": {"narrators": ["Один"]},
                "origin_conversation_id": "conversation-one",
            },
        )
        return operations.invoke(
            "request_apply",
            {
                "plan_id": plan["plan_id"],
                "revision": plan["revision"],
                "idempotency_key": "request-key-one",
            },
            mutation_authorized=True,
        )

    def test_online_backup_and_disposable_restore_preserve_interface_results(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            database = root / "state.sqlite3"
            backup = root / "backup.sqlite3"
            restored = root / "restored.sqlite3"
            operations = AudiobookOperations.open(database, **self.adapters())
            try:
                self.create_task(operations)
                expected = operations.invoke("task_list", {})
                evidence = operations.backup_to(backup)
            finally:
                operations.close()

            self.assertEqual(evidence["integrity"], "ok")
            self.assertEqual(evidence["schema_version"], 4)
            restore_evidence = AudiobookOperations.restore_backup(backup, restored)
            self.assertEqual(restore_evidence["integrity"], "ok")

            restored_operations = AudiobookOperations.open(restored, **self.adapters())
            try:
                self.assertEqual(restored_operations.invoke("task_list", {}), expected)
            finally:
                restored_operations.close()

    def test_migration_is_idempotent_and_rejects_a_newer_schema(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            database = root / "legacy.sqlite3"
            with closing(sqlite3.connect(database)) as connection:
                connection.execute(
                    "create table schema_migrations("
                    "version integer primary key, applied_at text not null)"
                )
                connection.execute(
                    "insert into schema_migrations values (1, '2026-09-12T00:00:00+00:00')"
                )
                connection.commit()

            operations = AudiobookOperations.open(database, **self.adapters())
            self.assertEqual(operations.schema_version(), 4)
            operations.close()
            reopened = AudiobookOperations.open(database, **self.adapters())
            self.assertEqual(reopened.schema_version(), 4)
            reopened.close()

            v3 = root / "v3.sqlite3"
            with closing(sqlite3.connect(v3)) as connection:
                connection.executescript(
                    """
                    CREATE TABLE schema_migrations(
                      version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL
                    );
                    INSERT INTO schema_migrations VALUES
                      (1, '2026-09-12T00:00:00+00:00'),
                      (2, '2026-09-12T01:00:00+00:00'),
                      (3, '2026-09-12T02:00:00+00:00');
                    CREATE TABLE publications(
                      publication_id TEXT PRIMARY KEY,
                      task_id TEXT NOT NULL UNIQUE,
                      worker_id TEXT NOT NULL,
                      status TEXT NOT NULL,
                      attempt INTEGER NOT NULL,
                      claimed_at TEXT NOT NULL,
                      acknowledged_at TEXT
                    );
                    """
                )
            migrated = AudiobookOperations.open(v3, **self.adapters())
            self.assertEqual(migrated.schema_version(), 4)
            migrated.close()
            with closing(sqlite3.connect(v3)) as connection:
                columns = {
                    row[1] for row in connection.execute("PRAGMA table_info(publications)")
                }
            self.assertIn("remote_manifest_id", columns)
            self.assertIn("updated_at", columns)

            future = root / "future.sqlite3"
            with closing(sqlite3.connect(future)) as connection:
                connection.execute(
                    "create table schema_migrations("
                    "version integer primary key, applied_at text not null)"
                )
                connection.execute(
                    "insert into schema_migrations values (99, '2030-01-01T00:00:00+00:00')"
                )
                connection.commit()
            with self.assertRaisesRegex(OperationError, "newer schema version"):
                AudiobookOperations.open(future, **self.adapters())

    def test_restore_refuses_overwrite(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            source = root / "source.sqlite3"
            destination = root / "destination.sqlite3"
            operations = AudiobookOperations.open(source, **self.adapters())
            operations.close()
            destination.write_bytes(b"do not overwrite")

            with self.assertRaisesRegex(OperationError, "destination already exists"):
                AudiobookOperations.restore_backup(source, destination)
            self.assertEqual(destination.read_bytes(), b"do not overwrite")


if __name__ == "__main__":
    unittest.main()
