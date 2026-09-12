#!/usr/bin/env python3

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path


BUNDLE_DIR = Path(__file__).resolve().parents[1]
BACKUP = BUNDLE_DIR / "scripts" / "backup.sh"
RESTORE_REHEARSAL = BUNDLE_DIR / "scripts" / "restore-rehearsal.sh"


class BackupRestoreTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        self.state_root = self.root / "state"
        self.publisher_state = self.root / "publisher-state"
        self.operator_config = self.root / "operator-config"
        self.secrets_root = self.root / "secrets"
        self.backup_root = self.root / "backups"
        self.rehearsal_root = self.root / "rehearsals"
        for relative in (
            "rmab/config",
            "prowlarr",
            "transmission",
            "flaresolverr",
            "downloads",
            "staging",
        ):
            (self.state_root / relative).mkdir(parents=True)
        self.publisher_state.mkdir()
        self.operator_config.mkdir()
        self.secrets_root.mkdir()
        (self.state_root / "rmab/config/settings.json").write_text("rmab-config")
        (self.state_root / "prowlarr/prowlarr.db").write_text("prowlarr-config")
        (self.state_root / "transmission/settings.json").write_text("transmission-config")
        (self.state_root / "flaresolverr/config.json").write_text("flaresolverr-config")
        (self.state_root / "downloads/not-backed-up.torrent").write_text("download")
        (self.state_root / "staging/not-backed-up.m4b").write_text("staging")
        (self.publisher_state / "ledger.json").write_text(
            json.dumps({"pending": {}, "publications": {}})
        )
        (self.operator_config / "publisher.json").write_text("{}")
        (self.secrets_root / "rmab-secret-key").write_text("secret")
        self.docker_log = self.root / "docker.log"
        self.fake_docker = self.root / "docker"
        self.fake_docker.write_text(
            "#!/bin/sh\n"
            "printf '%s\\n' \"$*\" >> \"$READMABOOK_TEST_DOCKER_LOG\"\n"
            "case \"$1 $2\" in\n"
            "  'exec readmeabook') printf '%s\\n' 'fake-pg-dump' ;;\n"
            "  'inspect --format') printf '%s\\n' 'readmeabook pinned-image' ;;\n"
            "  'run --rm') printf '%s\\n' 'rehearsal-container-id' ;;\n"
            "esac\n",
            encoding="utf-8",
        )
        self.fake_docker.chmod(0o755)

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def environment(self) -> dict[str, str]:
        environment = os.environ.copy()
        environment.update(
            {
                "READMABOOK_BACKUP_ROOT": str(self.backup_root),
                "READMABOOK_DOCKER_BIN": str(self.fake_docker),
                "READMABOOK_OPERATOR_CONFIG_DIR": str(self.operator_config),
                "READMABOOK_PUBLISHER_STATE_DIR": str(self.publisher_state),
                "READMABOOK_REHEARSAL_ROOT": str(self.rehearsal_root),
                "READMABOOK_SECRETS_ROOT": str(self.secrets_root),
                "READMABOOK_STATE_ROOT": str(self.state_root),
                "READMABOOK_TEST_DOCKER_LOG": str(self.docker_log),
            }
        )
        return environment

    def run_script(self, script: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["bash", str(script), *arguments],
            check=False,
            capture_output=True,
            env=self.environment(),
            text=True,
        )

    def test_backup_requires_execute_and_excludes_bulk_media(self) -> None:
        preview = self.run_script(BACKUP)

        self.assertEqual(preview.returncode, 0, preview.stderr)
        self.assertIn("preview", preview.stdout.lower())
        self.assertFalse(self.backup_root.exists())

        executed = self.run_script(BACKUP, "--execute")

        self.assertEqual(executed.returncode, 0, executed.stderr)
        backups = [path for path in self.backup_root.iterdir() if not path.name.startswith(".")]
        self.assertEqual(len(backups), 1)
        snapshot = backups[0]
        self.assertEqual((snapshot / "postgres.dump").read_text(), "fake-pg-dump\n")
        self.assertEqual(
            (snapshot / "state/rmab/config/settings.json").read_text(), "rmab-config"
        )
        self.assertTrue((snapshot / "publisher-state/ledger.json").is_file())
        self.assertTrue((snapshot / "operator-config/publisher.json").is_file())
        self.assertTrue((snapshot / "secrets/rmab-secret-key").is_file())
        self.assertEqual(
            (snapshot / "state/flaresolverr/config.json").read_text(),
            "flaresolverr-config",
        )
        self.assertFalse((snapshot / "state/downloads").exists())
        self.assertFalse((snapshot / "state/staging").exists())
        self.assertTrue((snapshot / "SHA256SUMS").is_file())
        verified = subprocess.run(
            ["sha256sum", "--check", "SHA256SUMS"],
            cwd=snapshot,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(verified.returncode, 0, verified.stderr)
        self.assertEqual(snapshot.stat().st_mode & 0o777, 0o700)
        docker_commands = self.docker_log.read_text()
        self.assertIn("readmeabook-rutracker-gateway", docker_commands)

    def test_restore_rehearsal_never_overwrites_production_state(self) -> None:
        created = self.run_script(BACKUP, "--execute")
        self.assertEqual(created.returncode, 0, created.stderr)
        snapshot = next(path for path in self.backup_root.iterdir() if not path.name.startswith("."))
        production_before = (self.state_root / "rmab/config/settings.json").read_text()

        preview = self.run_script(RESTORE_REHEARSAL, "--backup", str(snapshot))
        self.assertEqual(preview.returncode, 0, preview.stderr)
        self.assertFalse(self.rehearsal_root.exists())

        restored = self.run_script(
            RESTORE_REHEARSAL, "--backup", str(snapshot), "--execute"
        )

        self.assertEqual(restored.returncode, 0, restored.stderr)
        rehearsals = list(self.rehearsal_root.iterdir())
        self.assertEqual(len(rehearsals), 1)
        self.assertEqual(
            (rehearsals[0] / "state/rmab/config/settings.json").read_text(),
            "rmab-config",
        )
        self.assertEqual(
            (self.state_root / "rmab/config/settings.json").read_text(), production_before
        )
        docker_commands = self.docker_log.read_text()
        self.assertIn("postgres:16-bookworm@sha256:", docker_commands)
        self.assertIn("pg_restore", docker_commands)
        self.assertIn("rm -f readmeabook-restore-", docker_commands)

    def test_restore_rehearsal_rejects_a_destination_below_production_state(self) -> None:
        created = self.run_script(BACKUP, "--execute")
        self.assertEqual(created.returncode, 0, created.stderr)
        snapshot = next(path for path in self.backup_root.iterdir() if not path.name.startswith("."))
        environment = self.environment()
        dangerous = self.state_root / "restore-rehearsal"
        environment["READMABOOK_REHEARSAL_ROOT"] = str(dangerous)

        result = subprocess.run(
            [
                "bash",
                str(RESTORE_REHEARSAL),
                "--backup",
                str(snapshot),
                "--execute",
            ],
            check=False,
            capture_output=True,
            env=environment,
            text=True,
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("unsafe rehearsal root", result.stderr)
        self.assertFalse(dangerous.exists())


if __name__ == "__main__":
    unittest.main()
