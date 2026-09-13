from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import tempfile
import time
import unittest

from audiobook_ops.interface import OperationError


BUNDLE = Path(__file__).resolve().parents[1]


def load_worker():
    spec = importlib.util.spec_from_file_location(
        "audiobook_ops_worker", BUNDLE / "scripts/worker.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class WorkerPolicyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.worker = load_worker()

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def write(self, name: str, value: object) -> Path:
        path = self.root / name
        path.write_text(json.dumps(value))
        return path

    def test_capacity_requires_exact_fresh_ok_evidence(self) -> None:
        path = self.write(
            "capacity.json",
            {
                "local_free_bytes": 11,
                "observed_at_epoch": int(time.time()),
                "remote_free_bytes": 22,
                "status": "ok",
                "working_set_bytes": 3,
            },
        )

        snapshot = self.worker.capacity_snapshot(
            {"capacity_evidence_file": str(path)}
        )

        self.assertEqual(snapshot.local_free_bytes, 11)
        self.assertEqual(snapshot.remote_free_bytes, 22)
        self.assertEqual(snapshot.working_set_bytes, 3)
        value = json.loads(path.read_text())
        value["unexpected"] = True
        path.write_text(json.dumps(value))
        with self.assertRaisesRegex(OperationError, "invalid"):
            self.worker.capacity_snapshot({"capacity_evidence_file": str(path)})

    def test_worker_fails_closed_for_stale_or_degraded_vless_evidence(self) -> None:
        path = self.write(
            "vless.json",
            {
                "observed_at_epoch": int(time.time()) - 901,
                "route": "vless",
                "status": "ok",
            },
        )
        config = {
            "capacity_evidence_max_age_seconds": 900,
            "vless_evidence_file": str(path),
        }

        with self.assertRaisesRegex(OperationError, "stale or degraded"):
            self.worker.require_vless_evidence(config)
        path.write_text(
            json.dumps(
                {
                    "observed_at_epoch": int(time.time()),
                    "route": "vless",
                    "status": "degraded",
                }
            )
        )
        with self.assertRaisesRegex(OperationError, "stale or degraded"):
            self.worker.require_vless_evidence(config)


if __name__ == "__main__":
    unittest.main()
