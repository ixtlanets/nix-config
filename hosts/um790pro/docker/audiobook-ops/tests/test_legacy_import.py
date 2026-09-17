from __future__ import annotations

from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from audiobook_ops.interface import AudiobookOperations, OperationError
from audiobook_ops.legacy import import_legacy_ledger

from test_domain_interface import (
    FakeCatalogAdapter,
    FakeClock,
    FakeExternalActionAdapter,
    FakeReleaseAdapter,
)


BUNDLE = Path(__file__).resolve().parents[1]


def old_manifest(content: bytes, *, with_cover: bool = False) -> dict[str, object]:
    files = [
        {
            "path": "book.m4b",
            "sha256": hashlib.sha256(content).hexdigest(),
            "size": len(content),
            "duration": 42.5,
        }
    ]
    if with_cover:
        files.append(
            {
                "path": "cover.jpg",
                "sha256": hashlib.sha256(b"cover").hexdigest(),
                "size": len(b"cover"),
            }
        )
    body = {"audio_files": 1, "files": files}
    return {
        **body,
        "manifest_id": hashlib.sha256(
            json.dumps(body, separators=(",", ":"), sort_keys=True).encode()
        ).hexdigest(),
    }


class LegacyImportTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.fixture_count = 0
        self.operations = AudiobookOperations.open(
            self.root / "state.sqlite3",
            clock=FakeClock(datetime(2026, 9, 13, tzinfo=UTC)),
            release_adapter=FakeReleaseAdapter(),
            external_action_adapter=FakeExternalActionAdapter(),
            catalog_adapter=FakeCatalogAdapter(),
        )

    def tearDown(self) -> None:
        self.operations.close()
        self.temporary_directory.cleanup()

    def write_fixture(
        self, *, pending: dict[str, object] | None = None, map_active: bool = True
    ) -> tuple[Path, Path]:
        self.fixture_count += 1
        active_id = "11111111-1111-4111-8111-111111111111"
        tombstone_id = "22222222-2222-4222-8222-222222222222"
        active_manifest = old_manifest(b"active", with_cover=True)
        tombstone_manifest = old_manifest(b"tombstone")
        ledger = {
            "pending": pending or {},
            "publications": {
                active_id: {
                    "request_id": active_id,
                    "status": "published",
                    "final_relative_path": "Автор/Книга",
                    "torrent_hash": "a" * 40,
                    "manifest_id": active_manifest["manifest_id"],
                    "manifest": active_manifest,
                    "bytes": 11,
                    "files": 2,
                    "published_at_epoch": 100,
                    "abs_confirmed_at_epoch": 200,
                    "staging_path": "/legacy/staging/active",
                    "asin": "manual:active",
                },
                tombstone_id: {
                    "request_id": tombstone_id,
                    "status": "unpublished",
                    "final_relative_path": "Автор/Удалённая книга",
                    "torrent_hash": "b" * 40,
                    "manifest_id": tombstone_manifest["manifest_id"],
                    "manifest": tombstone_manifest,
                    "bytes": 9,
                    "files": 1,
                    "published_at_epoch": 300,
                    "abs_confirmed_at_epoch": 400,
                    "staging_path": "/legacy/staging/tombstone",
                    "asin": None,
                },
            },
        }
        ledger_path = self.root / f"legacy-ledger-{self.fixture_count}.json"
        ledger_bytes = (json.dumps(ledger, ensure_ascii=False, sort_keys=True) + "\n").encode()
        ledger_path.write_bytes(ledger_bytes)
        ledger_path.chmod(0o400)
        mapping = {
            "source_ledger_sha256": hashlib.sha256(ledger_bytes).hexdigest(),
            "active_items": {
                active_id: {
                    "library_id": "library-one",
                    "item_id": "item-one",
                    "media_id": "media-one",
                }
            }
            if map_active
            else {},
        }
        mapping_path = self.root / f"mapping-{self.fixture_count}.json"
        mapping_path.write_text(json.dumps(mapping))
        return ledger_path, mapping_path

    def test_import_is_idempotent_maps_active_and_invents_no_tasks(self) -> None:
        ledger, mapping = self.write_fixture()

        first = import_legacy_ledger(self.operations, ledger, mapping)
        second = import_legacy_ledger(self.operations, ledger, mapping)

        self.assertEqual(first, {"imported": 2, "unchanged": 0, "total": 2})
        self.assertEqual(second, {"imported": 0, "unchanged": 2, "total": 2})
        rows = self.operations.legacy_publications()
        self.assertEqual(len(rows), 2)
        active = next(row for row in rows if row["status"] == "published")
        tombstone = next(row for row in rows if row["status"] == "unpublished")
        self.assertEqual(active["abs_item_id"], "item-one")
        self.assertEqual(active["manifest"]["files"][0]["path"], "book.m4b")
        self.assertIsNone(tombstone["abs_item_id"])
        self.assertEqual(self.operations.invoke("task_list", {}), {"tasks": []})

    def test_writable_changed_pending_or_unmapped_ledger_fails_closed(self) -> None:
        ledger, mapping = self.write_fixture()
        ledger.chmod(0o600)
        with self.assertRaisesRegex(OperationError, "read-only"):
            import_legacy_ledger(self.operations, ledger, mapping)

        ledger, mapping = self.write_fixture(pending={"task": {}})
        with self.assertRaisesRegex(OperationError, "pending"):
            import_legacy_ledger(self.operations, ledger, mapping)

        ledger, mapping = self.write_fixture(map_active=False)
        with self.assertRaisesRegex(OperationError, "mapping"):
            import_legacy_ledger(self.operations, ledger, mapping)

        ledger, mapping = self.write_fixture()
        mapping_payload = json.loads(mapping.read_text())
        mapping_payload["source_ledger_sha256"] = "0" * 64
        mapping.write_text(json.dumps(mapping_payload))
        with self.assertRaisesRegex(OperationError, "checksum"):
            import_legacy_ledger(self.operations, ledger, mapping)

    def test_repository_mapping_pins_the_observed_immutable_ledger(self) -> None:
        mapping = json.loads(
            (BUNDLE / "migration/readmeabook-publication-mapping.json").read_text()
        )

        self.assertEqual(
            mapping["source_ledger_sha256"],
            "a20f20e3c7df929eac479b1d9be94a59f82ffe9bae15eafe4e33fc28382f37e8",
        )
        self.assertEqual(len(mapping["active_items"]), 3)
        self.assertEqual(
            set(mapping["active_items"]),
            {
                "0cc1a664-29a5-4542-a483-aaebae3bf0b3",
                "83920e0c-1504-4882-8aba-3c25460e20dc",
                "8c229675-3f6b-43ba-a7af-e71232936f2e",
            },
        )


if __name__ == "__main__":
    unittest.main()
