#!/usr/bin/env python3

import os
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


BUNDLE_DIR = Path(__file__).resolve().parents[1]
WRAPPER = BUNDLE_DIR / "scripts" / "remote-wrapper.py"


class RemoteWrapperCliTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        self.incoming = self.root / "incoming"
        self.final = self.root / "final"
        self.incoming.mkdir()
        self.final.mkdir()

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def run_wrapper(self, command: str, stdin: str = "") -> subprocess.CompletedProcess[str]:
        environment = os.environ.copy()
        environment.update(
            {
                "READMABOOK_FINAL_ROOT": str(self.final),
                "READMABOOK_INCOMING_ROOT": str(self.incoming),
                "READMABOOK_MIN_REMOTE_FREE_GIB": "0",
                "SSH_ORIGINAL_COMMAND": command,
            }
        )
        return subprocess.run(
            [sys.executable, str(WRAPPER)],
            check=False,
            capture_output=True,
            env=environment,
            input=stdin,
            text=True,
        )

    def test_promote_rejects_a_path_outside_the_final_root(self) -> None:
        result = self.run_wrapper("promote req-1 ../../Audiobooks")

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("unsafe final path", result.stderr)
        self.assertEqual(list(self.final.iterdir()), [])

    def test_verified_incoming_book_is_promoted_atomically(self) -> None:
        prepared = self.run_wrapper("prepare req-1")
        self.assertEqual(prepared.returncode, 0, prepared.stderr)
        book = self.incoming / "req-1"
        audio = book / "book.m4b"
        audio.write_bytes(b"verified audio")
        files = [
            {
                "path": "book.m4b",
                "sha256": hashlib.sha256(b"verified audio").hexdigest(),
                "size": len(b"verified audio"),
            }
        ]
        body = {"audio_files": 1, "files": files}
        manifest_id = hashlib.sha256(
            json.dumps(body, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        manifest = {
            **body,
            "final_relative_path": "Author/Book B123",
            "manifest_id": manifest_id,
            "request_id": "req-1",
        }

        verified = self.run_wrapper("verify req-1", json.dumps(manifest))
        promoted = self.run_wrapper("promote req-1 'Author/Book B123'")

        self.assertEqual(verified.returncode, 0, verified.stderr)
        self.assertEqual(promoted.returncode, 0, promoted.stderr)
        final_book = self.final / "Author" / "Book B123"
        self.assertEqual((final_book / "book.m4b").read_bytes(), b"verified audio")
        self.assertEqual(
            json.loads((final_book / ".readmeabook-manifest.json").read_text()),
            manifest,
        )
        self.assertEqual(final_book.stat().st_mode & 0o7777, 0o2775)
        self.assertEqual(final_book.parent.stat().st_mode & 0o7777, 0o2775)
        self.assertEqual((final_book / "book.m4b").stat().st_mode & 0o777, 0o664)
        self.assertEqual(
            (final_book / ".readmeabook-manifest.json").stat().st_mode & 0o777,
            0o600,
        )
        self.assertFalse(book.exists())

    def test_verify_rejects_a_manifest_without_supported_audio(self) -> None:
        self.assertEqual(self.run_wrapper("prepare req-text").returncode, 0)
        book = self.incoming / "req-text"
        payload = b"not an audiobook"
        (book / "notes.txt").write_bytes(payload)
        files = [
            {
                "path": "notes.txt",
                "sha256": hashlib.sha256(payload).hexdigest(),
                "size": len(payload),
            }
        ]
        body = {"audio_files": 0, "files": files}
        manifest = {
            **body,
            "final_relative_path": "Author/Notes B123",
            "manifest_id": hashlib.sha256(
                json.dumps(body, sort_keys=True, separators=(",", ":")).encode()
            ).hexdigest(),
            "request_id": "req-text",
        }

        result = self.run_wrapper("verify req-text", json.dumps(manifest))

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("supported audio", result.stderr)

    def test_unpublish_requires_the_exact_manifest_id(self) -> None:
        final_book = self.final / "Author" / "Book B123"
        final_book.mkdir(parents=True)
        (final_book / "book.m4b").write_bytes(b"audio")
        manifest = {
            "final_relative_path": "Author/Book B123",
            "manifest_id": "a" * 64,
            "request_id": "req-1",
        }
        (final_book / ".readmeabook-manifest.json").write_text(
            json.dumps(manifest), encoding="utf-8"
        )

        refused = self.run_wrapper(
            "unpublish " + "b" * 64 + " 'Author/Book B123'"
        )
        removed = self.run_wrapper(
            "unpublish " + "a" * 64 + " 'Author/Book B123'"
        )

        self.assertNotEqual(refused.returncode, 0)
        self.assertIn("manifest ID mismatch", refused.stderr)
        self.assertEqual(removed.returncode, 0, removed.stderr)
        self.assertFalse(final_book.exists())

    def test_rsync_receive_forces_the_prepared_incoming_directory(self) -> None:
        self.assertEqual(self.run_wrapper("prepare req-1").returncode, 0)
        command_log = self.root / "rsync.log"
        fake_rsync = self.root / "rsync"
        fake_rsync.write_text(
            "#!/bin/sh\nprintf '%s\\n' \"$@\" > \"$READMABOOK_RSYNC_LOG\"\n",
            encoding="utf-8",
        )
        fake_rsync.chmod(0o755)
        environment = os.environ.copy()
        environment.update(
            {
                "READMABOOK_FINAL_ROOT": str(self.final),
                "READMABOOK_INCOMING_ROOT": str(self.incoming),
                "READMABOOK_MIN_REMOTE_FREE_GIB": "0",
                "READMABOOK_RSYNC_BIN": str(fake_rsync),
                "READMABOOK_RSYNC_LOG": str(command_log),
                "SSH_ORIGINAL_COMMAND": "rsync-receive req-1 --server -logDtpre.iLsfxCIvu . /tmp/escape",
            }
        )

        received = subprocess.run(
            [sys.executable, str(WRAPPER)],
            check=False,
            capture_output=True,
            env=environment,
            text=True,
        )
        sender = self.run_wrapper(
            "rsync-receive req-1 --server --sender -logDtpre.iLsfxCIvu . /"
        )

        self.assertEqual(received.returncode, 0, received.stderr)
        self.assertEqual(command_log.read_text().splitlines()[-1], str(self.incoming / "req-1"))
        self.assertNotEqual(sender.returncode, 0)
        self.assertIn("sender mode is forbidden", sender.stderr)

        redirected_temporary = self.run_wrapper(
            "rsync-receive req-1 --server --temp-dir=/tmp -logDtpre.iLsfxCIvu . /"
        )
        self.assertNotEqual(redirected_temporary.returncode, 0)
        self.assertIn("forbidden rsync option", redirected_temporary.stderr)

    def test_capacity_reports_free_bytes_for_the_final_filesystem(self) -> None:
        result = self.run_wrapper("capacity")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertGreater(json.loads(result.stdout)["free_bytes"], 0)

    def test_corrupt_published_manifest_is_a_controlled_error(self) -> None:
        final_book = self.final / "Author" / "Book B123"
        final_book.mkdir(parents=True)
        (final_book / ".readmeabook-manifest.json").write_text("not-json")

        result = self.run_wrapper(
            "unpublish " + "a" * 64 + " 'Author/Book B123'"
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("remote wrapper error:", result.stderr)
        self.assertNotIn("Traceback", result.stderr)


if __name__ == "__main__":
    unittest.main()
