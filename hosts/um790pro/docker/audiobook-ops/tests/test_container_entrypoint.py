from __future__ import annotations

import importlib.util
import os
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest import mock


BUNDLE = Path(__file__).resolve().parents[1]
ENTRYPOINT = BUNDLE / "scripts/container-entrypoint.py"
SPEC = importlib.util.spec_from_file_location("container_entrypoint", ENTRYPOINT)
assert SPEC is not None and SPEC.loader is not None
entrypoint = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(entrypoint)


class ContainerEntrypointTests(unittest.TestCase):
    def test_source_file_must_be_root_owned_and_non_writable_by_others(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "secret"
            source.write_text("sentinel")
            source.chmod(0o600)
            real_fstat = os.fstat

            def untrusted_owner(descriptor: int) -> SimpleNamespace:
                metadata = real_fstat(descriptor)
                return SimpleNamespace(st_mode=metadata.st_mode, st_uid=1000)

            with mock.patch.object(entrypoint.os, "fstat", side_effect=untrusted_owner):
                with self.assertRaisesRegex(entrypoint.BootstrapError, "unsafe"):
                    entrypoint.read_root_owned_file(
                        source, 1024, require_private=True
                    )

            source.chmod(0o622)
            with mock.patch.object(entrypoint.os, "fstat", side_effect=real_fstat):
                with self.assertRaisesRegex(entrypoint.BootstrapError, "unsafe"):
                    entrypoint.read_root_owned_file(
                        source, 1024, require_private=False
                    )

    def test_runtime_copy_is_atomic_private_and_owned_by_runtime_user(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "runtime-secret"
            with (
                mock.patch.object(entrypoint, "RUNTIME_UID", os.getuid()),
                mock.patch.object(entrypoint, "RUNTIME_GID", os.getgid()),
            ):
                entrypoint.atomic_runtime_file(target, b"sentinel")

            metadata = target.stat()
            self.assertEqual(target.read_bytes(), b"sentinel")
            self.assertEqual(metadata.st_mode & 0o777, 0o400)
            self.assertEqual(metadata.st_uid, os.getuid())
            self.assertEqual(metadata.st_gid, os.getgid())
            self.assertEqual(list(target.parent.glob(".*.tmp")), [])

    def test_runtime_copy_sets_mode_before_transferring_ownership(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "runtime-secret"
            calls: list[str] = []
            real_fchmod = os.fchmod

            def record_fchmod(descriptor: int, mode: int) -> None:
                calls.append("fchmod")
                real_fchmod(descriptor, mode)

            def record_fchown(descriptor: int, uid: int, gid: int) -> None:
                calls.append("fchown")

            with (
                mock.patch.object(entrypoint.os, "fchmod", side_effect=record_fchmod),
                mock.patch.object(entrypoint.os, "fchown", side_effect=record_fchown),
            ):
                entrypoint.atomic_runtime_file(target, b"sentinel")

            self.assertEqual(calls, ["fchmod", "fchown"])


if __name__ == "__main__":
    unittest.main()
