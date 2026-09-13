from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
from typing import Callable, Protocol

from audiobook_ops.interface import OperationError


AUDIO_EXTENSIONS = frozenset({".flac", ".m4a", ".m4b", ".mp3"})
IGNORED_ANCILLARY_EXTENSIONS = frozenset(
    {".cue", ".jpeg", ".jpg", ".nfo", ".png", ".txt", ".webp"}
)
FORBIDDEN_EXTENSIONS = frozenset(
    {
        ".7z",
        ".bat",
        ".bz2",
        ".cmd",
        ".com",
        ".dll",
        ".exe",
        ".gz",
        ".msi",
        ".rar",
        ".sh",
        ".so",
        ".tar",
        ".xz",
        ".zip",
    }
)


class AudioProbe(Protocol):
    def duration(self, path: Path) -> float: ...


class SubprocessAudioProbe:
    def __init__(self, ffprobe_bin: str = "ffprobe") -> None:
        self._ffprobe_bin = ffprobe_bin

    def duration(self, path: Path) -> float:
        result = subprocess.run(
            [
                self._ffprobe_bin,
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "json",
                str(path.resolve(strict=True)),
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode != 0:
            raise OperationError("ffprobe rejected an audio stream")
        try:
            payload = json.loads(result.stdout)
            duration = float(payload["format"]["duration"])
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
            raise OperationError("ffprobe returned an invalid audio stream") from error
        if duration <= 0:
            raise OperationError("ffprobe returned an invalid audio stream")
        return duration


@dataclass(frozen=True)
class CapacitySnapshot:
    working_set_bytes: int
    local_free_bytes: int
    remote_free_bytes: int


class MediaValidator:
    """Validate and stage one release behind one fail-closed interface."""

    def __init__(
        self,
        *,
        downloads_root: Path,
        staging_root: Path,
        probe: AudioProbe,
        capacity: Callable[[], CapacitySnapshot],
        stability_hook: Callable[[], None],
        max_release_bytes: int = 20 * 1024**3,
        max_working_set_bytes: int = 50 * 1024**3,
        min_local_free_bytes: int = 100 * 1024**3,
        min_remote_free_bytes: int = 200 * 1024**3,
        max_ancillary_files: int = 20,
        max_ancillary_bytes: int = 10 * 1024**2,
    ) -> None:
        self._downloads_root = downloads_root
        self._staging_root = staging_root
        self._probe = probe
        self._capacity = capacity
        self._stability_hook = stability_hook
        self._max_release_bytes = max_release_bytes
        self._max_working_set_bytes = max_working_set_bytes
        self._min_local_free_bytes = min_local_free_bytes
        self._min_remote_free_bytes = min_remote_free_bytes
        self._max_ancillary_files = max_ancillary_files
        self._max_ancillary_bytes = max_ancillary_bytes

    def validate_and_stage(
        self, task_id: str, release_root: Path
    ) -> dict[str, object]:
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,199}", task_id):
            raise OperationError("invalid task staging identity")
        downloads = self._safe_directory(self._downloads_root, "downloads root")
        staging = self._safe_directory(self._staging_root, "staging root")
        release = self._safe_directory(release_root, "release root")
        try:
            release.relative_to(downloads)
        except ValueError as error:
            raise OperationError("release is outside the claimed download root") from error

        capacity = self._capacity()
        self._require_capacity(capacity)
        first = self._manifest(release)
        if first["total_size_bytes"] > self._max_release_bytes:
            raise OperationError("release exceeds the 20 GiB limit")
        self._stability_hook()
        second = self._manifest(release)
        if second != first:
            raise OperationError("release manifest changed during stability interval")

        destination = staging / task_id
        partial = staging / f".{task_id}.partial"
        if destination.is_symlink():
            raise OperationError("task staging destination is unsafe")
        if destination.exists():
            if not destination.is_dir() or self._manifest(destination) != first:
                raise OperationError("existing task staging content changed")
            return self._result(first, task_id)
        if partial.is_symlink():
            raise OperationError("partial task staging destination is unsafe")
        if partial.exists():
            if not partial.is_dir():
                raise OperationError("partial task staging destination is unsafe")
            shutil.rmtree(partial)
        partial.mkdir(mode=0o700)
        try:
            for entry in first["manifest"]:
                relative = Path(str(entry["relative_path"]))
                target = partial / relative
                target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
                shutil.copyfile(release / relative, target, follow_symlinks=False)
                target.chmod(0o600)
                if self._sha256(target) != entry["sha256"]:
                    raise OperationError("staged audio checksum changed")
            partial.rename(destination)
        except Exception:
            shutil.rmtree(partial, ignore_errors=True)
            raise

        return self._result(first, task_id)

    def preflight(self, expected_release_bytes: int) -> CapacitySnapshot:
        if not isinstance(expected_release_bytes, int) or expected_release_bytes < 0:
            raise OperationError("candidate size is missing or invalid")
        capacity = self._capacity()
        self._require_capacity(capacity)
        if expected_release_bytes > self._max_release_bytes:
            raise OperationError("release exceeds the 20 GiB limit")
        if (
            capacity.working_set_bytes + expected_release_bytes
            > self._max_working_set_bytes
        ):
            raise OperationError("working set exceeds the 50 GiB limit")
        return capacity

    def discard_staging(self, task_id: str) -> None:
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,199}", task_id):
            raise OperationError("invalid task staging identity")
        staging = self._safe_directory(self._staging_root, "staging root")
        destination = staging / task_id
        if destination.is_symlink():
            raise OperationError("task staging destination is unsafe")
        if destination.exists():
            if not destination.is_dir():
                raise OperationError("task staging destination is unsafe")
            shutil.rmtree(destination)

    def _require_capacity(self, capacity: CapacitySnapshot) -> None:
        if capacity.local_free_bytes < self._min_local_free_bytes:
            raise OperationError("local free-space reserve is below 100 GiB")
        if capacity.remote_free_bytes < self._min_remote_free_bytes:
            raise OperationError("Moscow free-space reserve is below 200 GiB")
        if capacity.working_set_bytes > self._max_working_set_bytes:
            raise OperationError("working set exceeds the 50 GiB limit")

    def _manifest(self, release: Path) -> dict[str, object]:
        entries: list[dict[str, object]] = []
        ancillary_files = 0
        ancillary_bytes = 0
        for current_root, directory_names, file_names in os.walk(
            release, followlinks=False
        ):
            current = Path(current_root)
            for name in directory_names:
                directory = current / name
                if directory.is_symlink():
                    raise OperationError("symlinks are forbidden in a release")
            for name in file_names:
                path = current / name
                metadata = path.lstat()
                if path.is_symlink() or not stat.S_ISREG(metadata.st_mode):
                    raise OperationError("non-regular files are forbidden in a release")
                suffix = path.suffix.casefold()
                if metadata.st_mode & 0o111 or suffix in FORBIDDEN_EXTENSIONS:
                    raise OperationError("executable or archive content is forbidden")
                if suffix in IGNORED_ANCILLARY_EXTENSIONS:
                    ancillary_files += 1
                    ancillary_bytes += metadata.st_size
                    if (
                        ancillary_files > self._max_ancillary_files
                        or ancillary_bytes > self._max_ancillary_bytes
                    ):
                        raise OperationError("ancillary content exceeds the bounded allowance")
                    continue
                if suffix not in AUDIO_EXTENSIONS:
                    raise OperationError("unsupported release content")
                duration = self._probe.duration(path)
                if not isinstance(duration, (int, float)) or duration <= 0:
                    raise OperationError("ffprobe returned an invalid audio stream")
                entries.append(
                    {
                        "relative_path": path.relative_to(release).as_posix(),
                        "size_bytes": metadata.st_size,
                        "sha256": self._sha256(path),
                        "duration_seconds": float(duration),
                    }
                )
        entries.sort(key=lambda entry: str(entry["relative_path"]))
        if not entries:
            raise OperationError("release contains no supported audio")
        logical_roots = {
            Path(str(entry["relative_path"])).parts[0]
            if len(Path(str(entry["relative_path"])).parts) > 1
            else "."
            for entry in entries
        }
        if len(logical_roots) > 1:
            raise OperationError("release contains multiple logical audiobooks")
        numbered_books = {
            match.group(1)
            for entry in entries
            if (
                match := re.search(
                    r"(?:^|\W)(?:книга|том|book|volume|vol)\s*[-_. ]*(\d+)(?:\W|$)",
                    Path(str(entry["relative_path"])).stem.casefold(),
                )
            )
        }
        if len(numbered_books) > 1:
            raise OperationError("release contains multiple logical audiobooks")
        return {
            "manifest": entries,
            "audio_file_count": len(entries),
            "total_size_bytes": sum(int(entry["size_bytes"]) for entry in entries),
            "total_duration_seconds": sum(
                float(entry["duration_seconds"]) for entry in entries
            ),
        }

    @staticmethod
    def _safe_directory(path: Path, description: str) -> Path:
        if path.is_symlink() or not path.is_dir():
            raise OperationError(f"{description} is missing or unsafe")
        return path.resolve(strict=True)

    @staticmethod
    def _sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    @staticmethod
    def _result(manifest: dict[str, object], task_id: str) -> dict[str, object]:
        return {
            **manifest,
            "staging_id": task_id,
            "manifest_id": hashlib.sha256(
                json.dumps(
                    manifest["manifest"], separators=(",", ":"), sort_keys=True
                ).encode()
            ).hexdigest(),
        }
