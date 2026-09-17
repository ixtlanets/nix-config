from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


BUNDLE = Path(__file__).resolve().parents[1]
WRAPPER = BUNDLE / "scripts" / "remote-wrapper.py"


class RemotePublisherWrapperTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.incoming = self.root / "incoming"
        self.final = self.root / "final"
        self.incoming.mkdir()
        self.final.mkdir()

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def run_wrapper(
        self, command: str, stdin: str = "", extra: dict[str, str] | None = None
    ) -> subprocess.CompletedProcess[str]:
        environment = os.environ.copy()
        environment.update(
            {
                "AUDIOBOOK_OPS_FINAL_ROOT": str(self.final),
                "AUDIOBOOK_OPS_INCOMING_ROOT": str(self.incoming),
                "AUDIOBOOK_OPS_MIN_REMOTE_FREE_GIB": "0",
                "SSH_ORIGINAL_COMMAND": command,
            }
        )
        environment.update(extra or {})
        return subprocess.run(
            [sys.executable, str(WRAPPER)],
            check=False,
            capture_output=True,
            env=environment,
            input=stdin,
            text=True,
        )

    @staticmethod
    def manifest(task_id: str, files: dict[str, bytes]) -> dict[str, object]:
        entries = [
            {
                "relative_path": name,
                "size_bytes": len(content),
                "sha256": hashlib.sha256(content).hexdigest(),
                "duration_seconds": 42.5,
            }
            for name, content in sorted(files.items())
        ]
        return {
            "task_id": task_id,
            "final_relative_path": "Автор/Серия/04 - Книга",
            "manifest_id": hashlib.sha256(
                json.dumps(entries, separators=(",", ":"), sort_keys=True).encode()
            ).hexdigest(),
            "audio_files": len(entries),
            "total_size_bytes": sum(len(content) for content in files.values()),
            "files": entries,
        }

    def prepare_files(self, task_id: str, files: dict[str, bytes]) -> Path:
        self.assertEqual(self.run_wrapper(f"prepare {task_id}").returncode, 0)
        source = self.incoming / task_id
        for name, content in files.items():
            path = source / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
        return source

    def test_mp3_and_m4b_are_verified_and_promoted_byte_identically(self) -> None:
        files = {"one.mp3": b"mp3-source-bytes", "disc/two.m4b": b"m4b-source-bytes"}
        source = self.prepare_files("task-one", files)
        manifest = self.manifest("task-one", files)

        verified = self.run_wrapper("verify task-one", json.dumps(manifest))
        promoted = self.run_wrapper(
            f"promote task-one '{manifest['final_relative_path']}' {manifest['manifest_id']}"
        )
        replayed = self.run_wrapper(
            f"promote task-one '{manifest['final_relative_path']}' {manifest['manifest_id']}"
        )

        self.assertEqual(verified.returncode, 0, verified.stderr)
        self.assertEqual(promoted.returncode, 0, promoted.stderr)
        self.assertEqual(replayed.returncode, 0, replayed.stderr)
        self.assertFalse(source.exists())
        destination = self.final / str(manifest["final_relative_path"])
        for name, content in files.items():
            self.assertEqual((destination / name).read_bytes(), content)
        self.assertTrue(json.loads(replayed.stdout)["replayed"])
        self.assertEqual(
            (destination / ".audiobook-ops-manifest.json").stat().st_mode & 0o777,
            0o600,
        )

    def test_arbitrary_delete_traversal_and_symlink_escape_are_rejected(self) -> None:
        outside = self.root / "outside"
        outside.mkdir()
        (self.final / "escape").symlink_to(outside, target_is_directory=True)
        commands = (
            "sh -c id",
            "delete task-one",
            "unpublish " + "a" * 64 + " Author/Book",
            "promote task-one ../../outside " + "a" * 64,
            "promote task-one escape/book " + "a" * 64,
        )
        for command in commands:
            with self.subTest(command=command):
                result = self.run_wrapper(command)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("remote wrapper error", result.stderr)
        self.assertEqual(list(outside.iterdir()), [])

    def test_existing_destination_with_different_identity_blocks_promotion(self) -> None:
        files = {"book.m4b": b"audio"}
        self.prepare_files("task-one", files)
        manifest = self.manifest("task-one", files)
        self.assertEqual(
            self.run_wrapper("verify task-one", json.dumps(manifest)).returncode, 0
        )
        destination = self.final / str(manifest["final_relative_path"])
        destination.mkdir(parents=True)
        (destination / ".audiobook-ops-manifest.json").write_text(
            json.dumps({**manifest, "task_id": "other-task"})
        )

        result = self.run_wrapper(
            f"promote task-one '{manifest['final_relative_path']}' {manifest['manifest_id']}"
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("already exists", result.stderr)
        self.assertTrue((self.incoming / "task-one").is_dir())

    def test_rsync_server_is_receive_only_and_forces_prepared_destination(self) -> None:
        self.assertEqual(self.run_wrapper("prepare task-one").returncode, 0)
        log = self.root / "rsync.log"
        fake = self.root / "rsync"
        fake.write_text(
            "#!/bin/sh\nprintf '%s\\n' \"$@\" > \"$AUDIOBOOK_OPS_RSYNC_LOG\"\n"
        )
        fake.chmod(0o755)
        accepted = self.run_wrapper(
            "rsync-receive task-one --server -logDtpre.iLsfxCIvu . /tmp/escape",
            extra={
                "AUDIOBOOK_OPS_RSYNC_BIN": str(fake),
                "AUDIOBOOK_OPS_RSYNC_LOG": str(log),
            },
        )
        sender = self.run_wrapper(
            "rsync-receive task-one --server --sender -logDtpre.iLsfxCIvu . /"
        )
        redirected = self.run_wrapper(
            "rsync-receive task-one --server --temp-dir=/tmp -logDtpre.iLsfxCIvu . /"
        )

        self.assertEqual(accepted.returncode, 0, accepted.stderr)
        self.assertEqual(log.read_text().splitlines()[-1], str(self.incoming / "task-one"))
        self.assertNotEqual(sender.returncode, 0)
        self.assertNotEqual(redirected.returncode, 0)


if __name__ == "__main__":
    unittest.main()
