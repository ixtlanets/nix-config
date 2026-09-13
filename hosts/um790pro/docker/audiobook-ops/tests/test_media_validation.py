from __future__ import annotations

import hashlib
import os
from pathlib import Path
import tempfile
import unittest

from audiobook_ops.validation import CapacitySnapshot, MediaValidator, SubprocessAudioProbe
from audiobook_ops.interface import OperationError


class FakeProbe:
    def __init__(self) -> None:
        self.paths: list[Path] = []

    def duration(self, path: Path) -> float:
        self.paths.append(path)
        return 61.5 if path.suffix == ".mp3" else 125.25


class MediaValidatorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.downloads = self.root / "downloads"
        self.staging = self.root / "staging"
        self.downloads.mkdir()
        self.staging.mkdir()
        self.probe = FakeProbe()

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def validator(self, **overrides: object) -> MediaValidator:
        arguments: dict[str, object] = {
            "downloads_root": self.downloads,
            "staging_root": self.staging,
            "probe": self.probe,
            "capacity": lambda: CapacitySnapshot(
                working_set_bytes=0,
                local_free_bytes=101 * 1024**3,
                remote_free_bytes=201 * 1024**3,
            ),
            "stability_hook": lambda: None,
        }
        arguments.update(overrides)
        return MediaValidator(**arguments)

    def test_mp3_and_m4b_release_is_staged_without_changing_audio_bytes(self) -> None:
        release = self.downloads / "Кроткая"
        release.mkdir()
        sources = {
            "01.mp3": b"ID3\x00chapter-one",
            "02.m4b": b"\x00\x00\x00\x18ftypM4B chapter-two",
        }
        for name, content in sources.items():
            (release / name).write_bytes(content)
        (release / "release.nfo").write_text("not authoritative")

        result = self.validator().validate_and_stage("task-one", release)

        self.assertEqual(result["audio_file_count"], 2)
        self.assertEqual(result["total_duration_seconds"], 186.75)
        self.assertEqual(
            [entry["relative_path"] for entry in result["manifest"]],
            ["01.mp3", "02.m4b"],
        )
        self.assertEqual(
            sorted(path.name for path in self.probe.paths),
            ["01.mp3", "01.mp3", "02.m4b", "02.m4b"],
        )
        for name, content in sources.items():
            staged = self.staging / "task-one" / name
            self.assertEqual(staged.read_bytes(), content)
            self.assertEqual(
                next(
                    entry["sha256"]
                    for entry in result["manifest"]
                    if entry["relative_path"] == name
                ),
                hashlib.sha256(content).hexdigest(),
            )
        self.assertFalse((self.staging / "task-one" / "release.nfo").exists())

    def test_multiple_top_level_book_directories_fail_closed(self) -> None:
        release = self.downloads / "collection"
        for book in ("Книга 1", "Книга 2"):
            directory = release / book
            directory.mkdir(parents=True)
            (directory / "01.mp3").write_bytes(book.encode())

        with self.assertRaisesRegex(OperationError, "multiple logical audiobooks"):
            self.validator().validate_and_stage("task-multiple", release)

        self.assertFalse((self.staging / "task-multiple").exists())

    def test_numbered_books_in_one_directory_fail_closed(self) -> None:
        release = self.downloads / "collection-flat"
        release.mkdir()
        (release / "Книга 1.mp3").write_bytes(b"first")
        (release / "Книга 2.mp3").write_bytes(b"second")

        with self.assertRaisesRegex(OperationError, "multiple logical audiobooks"):
            self.validator().validate_and_stage("task-flat-multiple", release)

    def test_ancillary_files_are_bounded_by_count_and_total_bytes(self) -> None:
        release = self.downloads / "ancillary"
        release.mkdir()
        (release / "book.mp3").write_bytes(b"audio")
        (release / "one.txt").write_bytes(b"12")
        (release / "two.nfo").write_bytes(b"34")

        with self.assertRaisesRegex(OperationError, "ancillary content exceeds"):
            self.validator(max_ancillary_files=1).validate_and_stage(
                "task-ancillary-count", release
            )
        with self.assertRaisesRegex(OperationError, "ancillary content exceeds"):
            self.validator(max_ancillary_bytes=3).validate_and_stage(
                "task-ancillary-size", release
            )

    def test_unsafe_filesystem_entries_fail_closed(self) -> None:
        cases = ("symlink", "archive", "executable", "special")
        for case in cases:
            with self.subTest(case=case):
                release = self.downloads / case
                release.mkdir()
                if case == "symlink":
                    outside = self.root / "outside.mp3"
                    outside.write_bytes(b"audio")
                    (release / "linked.mp3").symlink_to(outside)
                elif case == "archive":
                    (release / "payload.rar").write_bytes(b"archive")
                elif case == "executable":
                    executable = release / "payload.mp3"
                    executable.write_bytes(b"audio")
                    executable.chmod(0o700)
                else:
                    os.mkfifo(release / "payload.mp3")

                with self.assertRaises(OperationError):
                    self.validator().validate_and_stage(f"task-{case}", release)
                self.assertFalse((self.staging / f"task-{case}").exists())

        outside_release = self.root / "not-a-download"
        outside_release.mkdir()
        (outside_release / "book.mp3").write_bytes(b"audio")
        with self.assertRaisesRegex(OperationError, "outside the claimed download root"):
            self.validator().validate_and_stage("task-outside", outside_release)

    def test_invalid_stream_and_unstable_manifest_fail_closed(self) -> None:
        invalid = self.downloads / "invalid"
        invalid.mkdir()
        (invalid / "book.mp3").write_bytes(b"not audio")

        class InvalidProbe:
            def duration(self, _path: Path) -> float:
                return 0

        with self.assertRaisesRegex(OperationError, "invalid audio stream"):
            self.validator(probe=InvalidProbe()).validate_and_stage(
                "task-invalid", invalid
            )

        unstable = self.downloads / "unstable"
        unstable.mkdir()
        audio = unstable / "book.m4b"
        audio.write_bytes(b"first")

        def mutate() -> None:
            audio.write_bytes(b"second")

        with self.assertRaisesRegex(OperationError, "stability interval"):
            self.validator(stability_hook=mutate).validate_and_stage(
                "task-unstable", unstable
            )

    def test_release_working_set_and_free_space_limits_fail_closed(self) -> None:
        release = self.downloads / "limits"
        release.mkdir()
        (release / "book.mp3").write_bytes(b"audio")
        healthy = CapacitySnapshot(
            working_set_bytes=0,
            local_free_bytes=101 * 1024**3,
            remote_free_bytes=201 * 1024**3,
        )
        cases = (
            ("20 GiB", {"max_release_bytes": 1, "capacity": lambda: healthy}),
            (
                "50 GiB",
                {
                    "max_working_set_bytes": 1,
                    "capacity": lambda: CapacitySnapshot(
                        working_set_bytes=2,
                        local_free_bytes=101 * 1024**3,
                        remote_free_bytes=201 * 1024**3,
                    ),
                },
            ),
            (
                "100 GiB",
                {
                    "capacity": lambda: CapacitySnapshot(
                        working_set_bytes=0,
                        local_free_bytes=99 * 1024**3,
                        remote_free_bytes=201 * 1024**3,
                    )
                },
            ),
            (
                "200 GiB",
                {
                    "capacity": lambda: CapacitySnapshot(
                        working_set_bytes=0,
                        local_free_bytes=101 * 1024**3,
                        remote_free_bytes=199 * 1024**3,
                    )
                },
            ),
        )
        for expected, overrides in cases:
            with self.subTest(expected=expected):
                with self.assertRaisesRegex(OperationError, expected):
                    self.validator(**overrides).validate_and_stage(
                        f"task-{expected.split()[0]}", release
                    )

    def test_ffprobe_adapter_requires_a_positive_duration_without_using_a_shell(self) -> None:
        ffprobe = self.root / "ffprobe"
        ffprobe.write_text(
            "#!/usr/bin/env python3\n"
            "import json\n"
            "print(json.dumps({'format': {'duration': '10.5'}}))\n"
        )
        ffprobe.chmod(0o755)
        audio = self.root / "name; touch pwned.mp3"
        audio.write_bytes(b"fixture")

        duration = SubprocessAudioProbe(str(ffprobe)).duration(audio)

        self.assertEqual(duration, 10.5)
        self.assertFalse((self.root / "pwned.mp3").exists())


if __name__ == "__main__":
    unittest.main()
