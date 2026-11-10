#!/usr/bin/python3
"""Isolated synthetic HOME/cache tests; no services, installs, or live writes.

Run: python3 tests/test_dsh_local_snapshot.py
"""
import os
from pathlib import Path
import runpy
import socket
import tarfile
import tempfile
import unittest
from unittest import mock


HELPER = Path(__file__).resolve().parents[1] / "dotfiles/dsh/local/dsh-local-snapshot.py"
archive_state = runpy.run_path(str(HELPER))["archive_state"]
RESERVED = ".dsh-local-package-cache"


def strict_restore(archive_path, staging):
    """Same root/link policy as the existing VM restore, including data_filter."""
    staging.mkdir(mode=0o700)

    def state_filter(member, destination):
        filtered = tarfile.data_filter(member, destination)
        root = staging / "state"
        path = staging / member.name
        if not path.resolve().is_relative_to(root):
            raise ValueError("Snapshot member escapes state directory")
        if member.issym() or member.islnk():
            linked = (path.parent if member.issym() else staging) / member.linkname
            if not linked.resolve().is_relative_to(root):
                raise ValueError("Snapshot link escapes state directory")
        return filtered

    with tarfile.open(archive_path) as archive:
        for member in archive.getmembers():
            if member.name != "state" and not member.name.startswith("state/"):
                raise ValueError("Snapshot archive contains an unexpected root")
        archive.extractall(staging, filter=state_filter)
    return staging / "state"


class SnapshotTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="dsh-snapshot-test-")
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        self.home = self.base / "home"
        self.state = self.home / ".dsh"
        self.modules = self.state / "profiles/node_modules"
        self.modules.mkdir(parents=True)
        self.cache = self.home / ".npm/_npx/1a2b3c/node_modules"
        self.cache.mkdir(parents=True)
        self.archive = self.base / "state.tar"
        (self.state / "state.db").write_bytes(b"synthetic database")

    def payload(self, path, data=b"payload"):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return path

    def package(self, name="express", target=None):
        target = target or self.cache / name
        target.mkdir(parents=True, exist_ok=True)
        link = self.modules / name
        link.parent.mkdir(parents=True, exist_ok=True)
        link.symlink_to(target, target_is_directory=True)
        return link

    def reject(self):
        with self.assertRaises((ValueError, OSError)):
            archive_state(self.state, self.archive)
        self.assertFalse(self.archive.exists())
        self.assertEqual(list(self.base.glob(".dsh-local-state-*")), [])

    def test_complete_dependency_graph_strict_restore_and_unchanged_source(self):
        express = self.package()
        self.payload(self.cache / "express/index.js", b"express")
        self.payload(self.cache / "express/node_modules/debug/index.js", b"nested-old-debug")
        self.payload(self.cache / "debug/index.js", b"hoisted-new-debug")
        nested = self.package("debug", self.cache / "express/node_modules/debug")
        scoped = self.package("@scope/tool")
        self.payload(self.cache / "@scope/tool/index.js", b"scoped")
        # No profile link refers to these optional packages. The full cache is
        # still required by Node's nearest-parent node_modules lookup.
        self.payload(self.cache / "@native/linux-x64/binding.node", b"native-optional")
        self.payload(self.cache / "unlinked/package.json", b"unlinked-hoisted")
        binary = self.payload(self.cache / "express/bin/cli.js", b"executable")
        binary.chmod(0o755)
        (self.cache / ".bin").mkdir()
        (self.cache / ".bin/express").symlink_to("../express/bin/cli.js")
        (self.state / "internal").symlink_to("state.db")
        (self.state / "tool").symlink_to("profiles/node_modules/express/bin/cli.js")
        original = {link: os.readlink(link) for link in (express, nested, scoped)}

        archive_state(self.state, self.archive)
        self.assertEqual(self.archive.stat().st_mode & 0o777, 0o600)
        restored = strict_restore(self.archive, self.base / "restore")
        embedded = restored / RESERVED / "npx-1a2b3c/node_modules"
        profile = restored / "profiles/node_modules"
        self.assertEqual((profile / "express/index.js").read_bytes(), b"express")
        self.assertEqual((profile / "debug/index.js").read_bytes(), b"nested-old-debug")
        self.assertEqual((embedded / "debug/index.js").read_bytes(), b"hoisted-new-debug")
        self.assertEqual((profile / "express/node_modules/debug/index.js").read_bytes(), b"nested-old-debug")
        self.assertEqual((profile / "@scope/tool/index.js").read_bytes(), b"scoped")
        self.assertEqual((embedded / "@native/linux-x64/binding.node").read_bytes(), b"native-optional")
        self.assertEqual((embedded / "unlinked/package.json").read_bytes(), b"unlinked-hoisted")
        self.assertEqual((embedded / ".bin/express").resolve(), embedded / "express/bin/cli.js")
        self.assertEqual((restored / "tool").read_bytes(), b"executable")
        self.assertEqual((embedded / "express/bin/cli.js").stat().st_mode & 0o777, 0o755)
        self.assertEqual((restored / "internal").read_bytes(), b"synthetic database")
        for link, value in original.items():
            self.assertEqual(os.readlink(link), value)
        self.assertFalse((self.state / RESERVED).exists())
        with tarfile.open(self.archive) as archive:
            names = archive.getnames()
            self.assertEqual(len(names), len(set(names)))
            self.assertEqual(names.count("state/" + RESERVED + "/npx-1a2b3c/node_modules"), 1)
            for member in archive.getmembers():
                self.assertTrue(member.name == "state" or member.name.startswith("state/"))
                if member.issym():
                    self.assertFalse(Path(member.linkname).is_absolute())
                    linked = restored / Path(member.name).relative_to("state")
                    self.assertTrue(linked.resolve().is_relative_to(restored))

    def test_restored_existing_cache_archives_normally_without_duplication(self):
        self.package()
        self.payload(self.cache / "express/index.js")
        archive_state(self.state, self.archive)
        restored = strict_restore(self.archive, self.base / "first")
        second_archive = self.base / "second.tar"
        archive_state(restored, second_archive)
        second = strict_restore(second_archive, self.base / "second")
        self.assertEqual((second / "profiles/node_modules/express/index.js").read_bytes(), b"payload")
        with tarfile.open(self.archive) as first, tarfile.open(second_archive) as second:
            self.assertEqual(set(first.getnames()), set(second.getnames()))
            self.assertEqual(len(second.getnames()), len(set(second.getnames())))

    def test_multiple_cache_roots_and_old_reserved_cache_can_coexist(self):
        self.package()
        other = self.home / ".npm/_npx/abcd/node_modules/pkg"
        self.package("pkg", other)
        self.payload(self.state / RESERVED / "npx-old/node_modules/retained/index.js", b"retained")
        archive_state(self.state, self.archive)
        restored = strict_restore(self.archive, self.base / "restore")
        self.assertTrue((restored / RESERVED / "npx-1a2b3c/node_modules/express").is_dir())
        self.assertTrue((restored / RESERVED / "npx-abcd/node_modules/pkg").is_dir())
        self.assertEqual((restored / RESERVED / "npx-old/node_modules/retained/index.js").read_bytes(), b"retained")

    def test_private_from_creation_even_with_permissive_umask(self):
        original_open = tarfile.open

        def checked_open(*args, **kwargs):
            if kwargs.get("mode") == "w":
                self.assertEqual(os.fstat(kwargs["fileobj"].fileno()).st_mode & 0o777, 0o600)
                self.assertFalse(self.archive.exists())
            return original_open(*args, **kwargs)

        previous = os.umask(0)
        try:
            with mock.patch.object(tarfile, "open", side_effect=checked_open):
                archive_state(self.state, self.archive)
        finally:
            os.umask(previous)
        self.assertEqual(self.archive.stat().st_mode & 0o777, 0o600)

    def test_write_failure_does_not_publish_archive(self):
        with mock.patch.object(tarfile.TarFile, "addfile", side_effect=OSError("synthetic failure")):
            with self.assertRaises(OSError):
                archive_state(self.state, self.archive)
        self.assertFalse(self.archive.exists())
        self.assertEqual(list(self.base.glob(".dsh-local-state-*")), [])

    def test_existing_archive_or_destination_symlink_is_not_replaced(self):
        self.archive.write_bytes(b"keep")
        with self.assertRaises(FileExistsError):
            archive_state(self.state, self.archive)
        self.assertEqual(self.archive.read_bytes(), b"keep")
        other = self.base / "link.tar"
        other.symlink_to(self.base / "absent")
        with self.assertRaises(FileExistsError):
            archive_state(self.state, other)
        self.assertTrue(other.is_symlink())
        self.assertFalse((self.base / "absent").exists())

    def test_reject_arbitrary_absolute_external_and_absolute_internal_links(self):
        for target in (self.base / "external", self.state / "state.db"):
            with self.subTest(target=target):
                link = self.state / "arbitrary"
                link.symlink_to(target)
                self.reject()
                link.unlink()

    def test_reject_relative_external_link_and_forward_link_chain(self):
        (self.state / "a").symlink_to("z/secret")
        (self.state / "z").symlink_to("../outside")
        self.reject()

    def test_reject_symlink_cycles(self):
        (self.state / "a").symlink_to("b")
        (self.state / "b").symlink_to("a")
        self.reject()

    def test_reject_external_link_outside_package_root_location(self):
        target = self.cache / "express"
        target.mkdir()
        for relative in ("other/node_modules/express", "profiles/other/node_modules/express",
                         "profiles/node_modules/@scope", "profiles/node_modules/.bin/tool",
                         "profiles/node_modules/pkg/deeper"):
            with self.subTest(relative=relative):
                link = self.state / relative
                link.parent.mkdir(parents=True, exist_ok=True)
                link.symlink_to(target)
                self.reject()
                link.unlink()

    def test_reject_alternate_home_prefix_and_non_npx_paths(self):
        for target in (self.base / "home-extra/.npm/_npx/1a2b3c/node_modules/pkg",
                       self.base / "other/.npm/_npx/1a2b3c/node_modules/pkg",
                       self.home / ".npm/_npx/not-hex/node_modules/pkg",
                       self.home / ".npm/_npx/1a2b3c/not_node_modules/pkg",
                       self.home / ".npm/node_modules/pkg"):
            with self.subTest(target=target):
                target.mkdir(parents=True)
                link = self.package("pkg", target)
                self.reject()
                link.unlink()

    def test_reject_target_subpath_and_traversal_spelling(self):
        self.payload(self.cache / "pkg/lib/index.js")
        targets = (str(self.cache / "pkg/lib"), str(self.cache / "pkg/lib/index.js"),
                   str(self.cache / "pkg") + "/../pkg", str(self.cache) + "/./pkg",
                   str(self.cache / "pkg/node_modules"), str(self.cache))
        for target in targets:
            with self.subTest(target=target):
                link = self.modules / "pkg"
                link.symlink_to(target)
                self.reject()
                link.unlink()

    def test_reject_missing_package_target(self):
        (self.modules / "pkg").symlink_to(self.cache / "missing")
        self.reject()

    def test_reject_symlinked_node_modules_root(self):
        actual = self.home / ".npm/_npx/1a2b3c/real_modules"
        actual.mkdir()
        self.cache.rmdir()
        self.cache.symlink_to(actual)
        self.package()
        self.reject()

    def test_reject_symlinked_cache_ancestor(self):
        actual = self.home / ".npm/actual"
        actual.mkdir()
        self.cache.rmdir()
        self.cache.parent.rmdir()
        self.cache.parent.symlink_to(actual)
        self.cache.mkdir()
        self.package()
        self.reject()

    def test_reject_symlinked_package_target(self):
        actual = self.cache / "actual"
        actual.mkdir()
        (self.cache / "pkg").symlink_to("actual")
        (self.modules / "pkg").symlink_to(self.cache / "pkg")
        self.reject()

    def test_reject_absolute_or_escaping_cache_links_even_in_unlinked_package(self):
        self.package()
        for target in ("../../outside", str(self.cache / "express")):
            with self.subTest(target=target):
                link = self.cache / "unlinked"
                link.symlink_to(target)
                self.reject()
                link.unlink()

    def test_reject_cache_link_chain_escape(self):
        self.package()
        (self.cache / "a").symlink_to("z/secret")
        (self.cache / "z").symlink_to("../outside")
        self.reject()

    def test_reject_special_files_in_state_or_unlinked_cache(self):
        self.package()
        for parent in (self.state, self.cache):
            with self.subTest(parent=parent):
                fifo = parent / "special"
                os.mkfifo(fifo)
                self.reject()
                fifo.unlink()

    def test_reject_socket(self):
        with socket.socket(socket.AF_UNIX) as server:
            server.bind(str(self.state / "socket"))
            self.reject()

    def test_reject_reserved_file_symlink_and_matching_destination_collision(self):
        self.package()
        reserved = self.state / RESERVED
        reserved.write_bytes(b"ambiguous")
        self.reject()
        reserved.unlink()
        reserved.symlink_to("profiles")
        self.reject()
        reserved.unlink()
        (reserved / "npx-1a2b3c").mkdir(parents=True)
        self.reject()

    def test_reject_existing_reserved_broken_destination_link(self):
        self.package()
        reserved = self.state / RESERVED
        reserved.mkdir()
        (reserved / "npx-1a2b3c").symlink_to("missing")
        self.reject()

    def test_reject_state_root_or_ancestor_symlink(self):
        for source in (self.base / "linked-state", self.base / "linked-home/.dsh"):
            if source.name == ".dsh":
                source.parent.symlink_to(self.home)
            else:
                source.symlink_to(self.state)
            with self.subTest(source=source):
                with self.assertRaises(ValueError):
                    archive_state(source, self.archive)
                self.assertFalse(self.archive.exists())

    def test_reject_archive_inside_state_or_cache(self):
        self.package()
        for destination in (self.state / "snapshot.tar", self.cache / "snapshot.tar"):
            with self.subTest(destination=destination):
                with self.assertRaises(ValueError):
                    archive_state(self.state, destination)
                self.assertFalse(destination.exists())

    def test_archive_does_not_create_destination_directory(self):
        with self.assertRaises(FileNotFoundError):
            archive_state(self.state, self.base / "absent/state.tar")
        self.assertFalse((self.base / "absent").exists())


if __name__ == "__main__":
    unittest.main()
