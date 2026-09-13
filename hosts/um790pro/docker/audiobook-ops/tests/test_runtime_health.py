from __future__ import annotations

from datetime import UTC, datetime
import json
from pathlib import Path
import tempfile
import time
import unittest

from audiobook_ops.interface import AudiobookOperations
from audiobook_ops.runtime import RuntimeStatus


class FakeABSHTTP:
    def json(self, method: str, path: str) -> object:
        assert method == "GET" and path == "/api/libraries"
        return [
            {"id": "books", "mediaType": "book"},
            {"id": "podcasts", "mediaType": "podcast"},
        ]


class FakeProwlarrHTTP:
    def __init__(self) -> None:
        self.calls = 0

    def health(self) -> None:
        self.calls += 1


class FakeTransmissionRPC:
    def call(self, method: str, arguments: dict[str, object]) -> dict[str, object]:
        assert method == "session-get" and arguments == {}
        return {}


class RuntimeHealthTests(unittest.TestCase):
    def test_vless_outage_degrades_search_without_hiding_catalog_or_core(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            database = root / "state.sqlite3"
            AudiobookOperations.open(database).close()
            vless = root / "vless.json"
            vless.write_text(
                json.dumps(
                    {
                        "observed_at_epoch": int(time.time()),
                        "route": "vless",
                        "status": "ok",
                    }
                )
            )
            backup = root / "backup.json"
            backup.write_text(
                json.dumps(
                    {
                        "created_at": datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ"),
                        "format": 1,
                        "status": "ok",
                    }
                )
            )
            prowlarr = FakeProwlarrHTTP()
            status = RuntimeStatus(
                database=database,
                abs_http=FakeABSHTTP(),
                prowlarr_http=prowlarr,
                transmission_rpc=FakeTransmissionRPC(),
                vless_evidence=vless,
                backup_evidence=backup,
            )

            healthy = status.status()
            self.assertEqual(healthy["core"], {"status": "ok", "schema_version": 4})
            self.assertEqual(healthy["catalog"], {"status": "ok", "book_libraries": 1})
            self.assertEqual(healthy["external-search"], {"status": "ok"})
            self.assertEqual(healthy["acquisition"], {"status": "ok"})
            self.assertEqual(healthy["backup"]["status"], "ok")
            self.assertEqual(prowlarr.calls, 1)

            vless.write_text(
                json.dumps(
                    {
                        "observed_at_epoch": int(time.time()),
                        "route": "vless",
                        "status": "degraded",
                    }
                )
            )
            degraded = status.status()

            self.assertEqual(degraded["external-search"], {"status": "degraded"})
            self.assertEqual(degraded["catalog"]["status"], "ok")
            self.assertEqual(degraded["core"]["status"], "ok")
            self.assertEqual(prowlarr.calls, 1)


if __name__ == "__main__":
    unittest.main()
