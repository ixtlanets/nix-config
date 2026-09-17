from __future__ import annotations

from datetime import UTC, datetime
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from audiobook_ops.interface import AudiobookOperations

from test_domain_interface import (
    FakeCatalogAdapter,
    FakeClock,
    FakeExternalActionAdapter,
    FakeReleaseAdapter,
)


BUNDLE = Path(__file__).resolve().parents[1]


class BackupRestoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.state = self.root / "state"
        self.state.mkdir()
        self.database = self.state / "audiobook-ops.sqlite3"
        operations = AudiobookOperations.open(
            self.database,
            clock=FakeClock(datetime(2026, 9, 13, tzinfo=UTC)),
            release_adapter=FakeReleaseAdapter(),
            external_action_adapter=FakeExternalActionAdapter(),
            catalog_adapter=FakeCatalogAdapter(),
        )
        operations.close()
        self.operator_files: dict[str, str] = {}
        for name in (
            "audiobook-ops.json",
            "backup.json",
            "compose.env",
            "health.json",
            "policy.json",
            "publisher.json",
        ):
            operator = self.root / f"operator-{name}"
            operator.write_text('{"safe":"configuration"}\n')
            self.operator_files[name] = str(operator)
        self.ledger = self.root / "legacy-ledger.json"
        self.ledger.write_text('{"pending":{},"publications":{}}\n')
        self.ledger.chmod(0o400)
        self.retained = self.root / "retained"
        for name in ("prowlarr", "transmission", "flaresolverr"):
            directory = self.retained / name
            directory.mkdir(parents=True)
            (directory / "state.txt").write_text(name)
        self.secrets = self.root / "secrets"
        self.secrets.mkdir()
        for name in (
            "abs-api-token",
            "mcp-bearer",
            "prowlarr-api-key",
            "publisher-ssh-key",
            "transmission-password",
        ):
            secret = self.secrets / name
            secret.write_text(f"fixture-{name}\n")
            secret.chmod(0o600)
        self.backups = self.root / "backups"
        self.backups.mkdir()
        self.backups.chmod(0o700)
        self.docker = self.root / "fake-docker"
        self.docker.write_text("#!/bin/sh\nexit 0\n")
        self.docker.chmod(0o755)
        self.config = self.root / "backup.json"
        self.config.write_text(
            json.dumps(
                {
                    "backup_evidence_file": str(self.state / "backup-health.json"),
                    "backup_root": str(self.backups),
                    "database_path": str(self.database),
                    "docker_bin": str(self.docker),
                    "legacy_ledger_path": str(self.ledger),
                    "operator_files": self.operator_files,
                    "pause_containers": [
                        "audiobook-ops",
                        "audiobook-ops-flaresolverr",
                        "audiobook-ops-rutracker-gateway",
                        "audiobook-ops-prowlarr",
                        "audiobook-ops-transmission",
                    ],
                    "retained_state": {
                        name: str(self.retained / name)
                        for name in ("prowlarr", "transmission", "flaresolverr")
                    },
                    "secret_files": {
                        name: str(self.secrets / name)
                        for name in (
                            "abs-api-token",
                            "mcp-bearer",
                            "prowlarr-api-key",
                            "publisher-ssh-key",
                            "transmission-password",
                        )
                    },
                }
            )
        )

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def run_script(self, script: str, *arguments: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(BUNDLE / "scripts" / script), *arguments],
            check=False,
            capture_output=True,
            text=True,
            env={"PYTHONPATH": str(BUNDLE / "src")},
        )

    def create_backup(self) -> Path:
        result = self.run_script(
            "backup.py",
            "--config",
            str(self.config),
            "--timestamp",
            "20260913T120000Z",
            "--execute",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        return Path(payload["backup"])

    def test_backup_and_disposable_restore_are_exact_and_replay_safe(self) -> None:
        backup = self.create_backup()
        destination = self.root / "rehearsal"

        evidence = json.loads((self.state / "backup-health.json").read_text())
        self.assertEqual(
            evidence,
            {
                "created_at": "20260913T120000Z",
                "format": 1,
                "status": "ok",
            },
        )

        restored = self.run_script(
            "restore-rehearsal.py",
            "--backup",
            str(backup),
            "--destination",
            str(destination),
            "--production-path",
            str(self.state),
            "--execute",
        )
        replay = self.run_script(
            "restore-rehearsal.py",
            "--backup",
            str(backup),
            "--destination",
            str(destination),
            "--production-path",
            str(self.state),
            "--execute",
        )

        self.assertEqual(restored.returncode, 0, restored.stderr)
        self.assertNotEqual(replay.returncode, 0)
        self.assertTrue((destination / "audiobook-ops.sqlite3").is_file())
        self.assertEqual((destination / "legacy-ledger.json").stat().st_mode & 0o777, 0o400)
        self.assertEqual((destination / "secrets/abs-api-token").stat().st_mode & 0o777, 0o600)
        operations = AudiobookOperations.open(destination / "audiobook-ops.sqlite3")
        try:
            self.assertEqual(operations.schema_version(), 4)
        finally:
            operations.close()

    def test_tampering_and_production_destinations_fail_closed(self) -> None:
        backup = self.create_backup()
        (backup / "operator/audiobook-ops.json").write_text("tampered")

        tampered = self.run_script(
            "restore-rehearsal.py",
            "--backup",
            str(backup),
            "--destination",
            str(self.root / "tampered-restore"),
            "--production-path",
            str(self.state),
            "--execute",
        )
        production = self.run_script(
            "restore-rehearsal.py",
            "--backup",
            str(backup),
            "--destination",
            str(self.state / "restore"),
            "--production-path",
            str(self.state),
            "--execute",
        )

        self.assertNotEqual(tampered.returncode, 0)
        self.assertIn("checksum", tampered.stderr)
        self.assertNotEqual(production.returncode, 0)
        self.assertIn("production", production.stderr)
        self.assertFalse((self.root / "tampered-restore").exists())

    def test_restore_rejects_a_symlink_even_when_its_content_matches(self) -> None:
        backup = self.create_backup()
        operator = backup / "operator/audiobook-ops.json"
        original = Path(self.operator_files["audiobook-ops.json"]).resolve()
        operator.unlink()
        operator.symlink_to(original)

        result = self.run_script(
            "restore-rehearsal.py",
            "--backup",
            str(backup),
            "--destination",
            str(self.root / "symlink-restore"),
            "--production-path",
            str(self.state),
            "--execute",
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("symlink", result.stderr)
        self.assertFalse((self.root / "symlink-restore").exists())

    def test_restore_rejects_a_symlink_destination(self) -> None:
        backup = self.create_backup()
        destination = self.root / "destination-link"
        destination.symlink_to(self.root / "redirected")

        result = self.run_script(
            "restore-rehearsal.py",
            "--backup",
            str(backup),
            "--destination",
            str(destination),
            "--production-path",
            str(self.state),
            "--execute",
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("unsafe", result.stderr)
        self.assertFalse((self.root / "redirected").exists())

    def test_preview_has_no_side_effects(self) -> None:
        result = self.run_script("backup.py", "--config", str(self.config))

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(list(self.backups.iterdir()), [])
        self.assertIn("preview", result.stdout.casefold())


if __name__ == "__main__":
    unittest.main()
