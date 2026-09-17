from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch


BUNDLE = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "audiobook_ops_healthcheck", BUNDLE / "scripts/healthcheck.py"
)
assert SPEC is not None and SPEC.loader is not None
HEALTHCHECK = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(HEALTHCHECK)


class HealthcheckTests(unittest.TestCase):
    def test_container_health_gets_a_bounded_post_backup_settle_window(self) -> None:
        results = [
            SimpleNamespace(returncode=0, stdout="true|unhealthy\n"),
            SimpleNamespace(returncode=0, stdout="true|healthy\n"),
        ]

        with (
            patch.object(HEALTHCHECK.subprocess, "run", side_effect=results) as run,
            patch.object(HEALTHCHECK.time, "sleep") as sleep,
        ):
            result = HEALTHCHECK.container_status(
                "/usr/bin/docker",
                "audiobook-ops",
                attempts=2,
                interval_seconds=0.01,
            )

        self.assertEqual(result, {"status": "ok"})
        self.assertEqual(run.call_count, 2)
        sleep.assert_called_once_with(0.01)


if __name__ == "__main__":
    unittest.main()
