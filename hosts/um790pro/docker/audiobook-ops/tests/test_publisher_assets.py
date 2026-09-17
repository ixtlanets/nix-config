from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


BUNDLE = Path(__file__).resolve().parents[1]


class PublisherAssetTests(unittest.TestCase):
    def test_publisher_has_no_legacy_application_or_datastore_dependency(self) -> None:
        paths = [
            BUNDLE / "src/audiobook_ops/publisher.py",
            BUNDLE / "scripts/publisher.py",
            BUNDLE / "scripts/remote-wrapper.py",
            BUNDLE / "config/publisher.example.json",
        ]
        serialized = "\n".join(path.read_text().casefold() for path in paths)
        for forbidden in (
            "/api/requests",
            "organize_files",
            "postgres",
            "redis",
            "rmab_token",
            "rmab_url",
            "request_id",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, serialized)

    def test_publisher_config_preserves_host_side_safety_controls(self) -> None:
        config = json.loads((BUNDLE / "config/publisher.example.json").read_text())

        self.assertEqual(config["min_local_free_gib"], 100)
        self.assertEqual(config["min_remote_free_gib"], 200)
        self.assertEqual(config["max_release_gib"], 20)
        self.assertEqual(config["ffprobe_bin"], "/usr/bin/ffprobe")
        self.assertEqual(config["rsync_bin"], "/usr/bin/rsync")
        self.assertEqual(config["ssh_bin"], "/usr/bin/ssh")
        self.assertEqual(
            config["publisher_identity_file"],
            "${CREDENTIALS_DIRECTORY}/publisher-ssh-key",
        )

    def test_forced_command_keeps_exact_existing_roots_and_has_no_delete(self) -> None:
        command = (BUNDLE / "moscow/authorized-key-command.example").read_text()

        self.assertIn(
            "AUDIOBOOK_OPS_INCOMING_ROOT=/media/disk1/media/.readmeabook-incoming",
            command,
        )
        self.assertIn(
            "AUDIOBOOK_OPS_FINAL_ROOT=/media/disk1/media/ReadMeABook", command
        )
        self.assertIn("restrict,command=", command)
        self.assertNotIn("unpublish", command)
        self.assertNotIn("delete", command)

    def test_publisher_cli_requires_explicit_execution(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = root / "publisher.json"
            config.write_text(
                json.dumps(
                    {
                        "database_path": str(root / "state.sqlite3"),
                        "lock_path": str(root / "publisher.lock"),
                    }
                )
            )
            result = subprocess.run(
                [
                    sys.executable,
                    str(BUNDLE / "scripts/publisher.py"),
                    "--config",
                    str(config),
                    "run-once",
                ],
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertFalse((root / "state.sqlite3").exists())
            self.assertFalse((root / "publisher.lock").exists())

        self.assertEqual(result.returncode, 2)
        self.assertIn("requires --execute", result.stderr)


if __name__ == "__main__":
    unittest.main()
