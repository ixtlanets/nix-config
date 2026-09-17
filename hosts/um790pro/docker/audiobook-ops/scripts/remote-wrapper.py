#!/usr/bin/env python3

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import sys


class RemoteError(RuntimeError):
    pass


SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,199}$")
MANIFEST_NAME = ".audiobook-ops-manifest.json"
MAX_MANIFEST_BYTES = 16 * 1024 * 1024
MAX_MANIFEST_FILES = 10_000
MAX_RELATIVE_PATH_BYTES = 1_000


def configured_root(variable: str) -> Path:
    value = os.environ.get(variable)
    if not value:
        raise RemoteError(f"missing {variable}")
    candidate = Path(value)
    if candidate.is_symlink() or not candidate.is_dir():
        raise RemoteError(f"unsafe {variable}")
    return candidate.resolve(strict=True)


def safe_id(value: str) -> str:
    if not SAFE_ID.fullmatch(value):
        raise RemoteError("unsafe task ID")
    return value


def safe_relative_path(root: Path, value: str) -> Path:
    if "\\" in value:
        raise RemoteError("unsafe final path")
    relative = Path(value)
    if (
        relative.is_absolute()
        or not relative.parts
        or any(part in {"", ".", ".."} for part in relative.parts)
    ):
        raise RemoteError("unsafe final path")
    resolved = (root / relative).resolve(strict=False)
    if resolved == root or root not in resolved.parents:
        raise RemoteError("unsafe final path")
    return resolved


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_manifest(path: Path) -> dict[str, object]:
    if path.is_symlink() or not path.is_file():
        raise RemoteError("verified manifest does not exist")
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise RemoteError("verified manifest is invalid") from error
    if not isinstance(manifest, dict):
        raise RemoteError("verified manifest is invalid")
    return manifest


def verify_manifest(task_id: str, source: Path, final_root: Path) -> dict[str, object]:
    try:
        raw_manifest = sys.stdin.buffer.read(MAX_MANIFEST_BYTES + 1)
        if len(raw_manifest) > MAX_MANIFEST_BYTES:
            raise RemoteError("manifest JSON is too large")
        manifest = json.loads(raw_manifest)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise RemoteError("invalid manifest JSON") from error
    required = {
        "task_id",
        "final_relative_path",
        "manifest_id",
        "audio_files",
        "total_size_bytes",
        "files",
    }
    if not isinstance(manifest, dict) or set(manifest) != required:
        raise RemoteError("invalid manifest shape")
    if manifest.get("task_id") != task_id:
        raise RemoteError("manifest task ID mismatch")
    entries = manifest.get("files")
    if (
        not isinstance(entries, list)
        or not entries
        or len(entries) > MAX_MANIFEST_FILES
    ):
        raise RemoteError("manifest contains no files")
    calculated_id = hashlib.sha256(
        json.dumps(entries, separators=(",", ":"), sort_keys=True).encode()
    ).hexdigest()
    if manifest.get("manifest_id") != calculated_id:
        raise RemoteError("manifest ID mismatch")

    expected_paths: set[str] = set()
    total_bytes = 0
    audio_count = 0
    for entry in entries:
        if not isinstance(entry, dict) or set(entry) != {
            "relative_path",
            "size_bytes",
            "sha256",
            "duration_seconds",
        }:
            raise RemoteError("invalid manifest entry")
        relative = entry["relative_path"]
        if (
            not isinstance(relative, str)
            or len(relative.encode()) > MAX_RELATIVE_PATH_BYTES
            or relative in expected_paths
        ):
            raise RemoteError("invalid or duplicate manifest path")
        path = safe_relative_path(source, relative)
        if path.is_symlink() or not path.is_file():
            raise RemoteError("manifest file is not regular")
        size = entry["size_bytes"]
        if not isinstance(size, int) or size < 0 or path.stat().st_size != size:
            raise RemoteError("manifest size mismatch")
        if sha256_file(path) != entry["sha256"]:
            raise RemoteError("manifest checksum mismatch")
        duration = entry["duration_seconds"]
        if not isinstance(duration, (int, float)) or duration <= 0:
            raise RemoteError("manifest duration is invalid")
        if path.suffix.casefold() not in {".flac", ".m4a", ".m4b", ".mp3"}:
            raise RemoteError("manifest contains unsupported content")
        expected_paths.add(relative)
        total_bytes += size
        audio_count += 1
    if manifest["audio_files"] != audio_count:
        raise RemoteError("manifest audio count mismatch")
    if manifest["total_size_bytes"] != total_bytes:
        raise RemoteError("manifest byte count mismatch")
    maximum = int(os.environ.get("AUDIOBOOK_OPS_MAX_RELEASE_GIB", "20")) * 1024**3
    if total_bytes > maximum:
        raise RemoteError("publication exceeds the remote size limit")
    minimum_free = (
        int(os.environ.get("AUDIOBOOK_OPS_MIN_REMOTE_FREE_GIB", "200"))
        * 1024**3
    )
    if shutil.disk_usage(final_root).free - total_bytes < minimum_free:
        raise RemoteError("remote free-space reserve would be violated")

    actual_paths: set[str] = set()
    for current_root, directory_names, file_names in os.walk(
        source, followlinks=False
    ):
        current = Path(current_root)
        for name in directory_names:
            if (current / name).is_symlink():
                raise RemoteError("symlink is forbidden in incoming directory")
        for name in file_names:
            if name == MANIFEST_NAME:
                continue
            path = current / name
            if path.is_symlink() or not path.is_file():
                raise RemoteError("non-regular incoming content is forbidden")
            actual_paths.add(path.relative_to(source).as_posix())
    if actual_paths != expected_paths:
        raise RemoteError("incoming file set does not match manifest")

    final_relative = manifest["final_relative_path"]
    if not isinstance(final_relative, str):
        raise RemoteError("manifest has no final path")
    safe_relative_path(final_root, final_relative)
    source.chmod(0o2775)
    for current_root, directory_names, file_names in os.walk(
        source, followlinks=False
    ):
        current = Path(current_root)
        for name in directory_names:
            (current / name).chmod(0o2775)
        for name in file_names:
            (current / name).chmod(0o664)
    temporary = source / f"{MANIFEST_NAME}.tmp"
    target = source / MANIFEST_NAME
    temporary.write_text(
        json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.chmod(0o600)
    temporary.replace(target)
    return manifest


def dispatch(command: str) -> int:
    try:
        arguments = shlex.split(command)
    except ValueError as error:
        raise RemoteError("invalid command") from error
    if not arguments:
        raise RemoteError("missing command")
    incoming_root = configured_root("AUDIOBOOK_OPS_INCOMING_ROOT")
    final_root = configured_root("AUDIOBOOK_OPS_FINAL_ROOT")

    if arguments == ["capacity"]:
        print(json.dumps({"free_bytes": shutil.disk_usage(final_root).free}))
        return 0

    if arguments[0] == "prepare" and len(arguments) == 2:
        task_id = safe_id(arguments[1])
        source = incoming_root / task_id
        source.mkdir(mode=0o700, exist_ok=True)
        if source.is_symlink() or not source.is_dir():
            raise RemoteError("unsafe incoming task directory")
        print(json.dumps({"prepared": True, "task_id": task_id}))
        return 0

    if arguments[0] == "verify" and len(arguments) == 2:
        task_id = safe_id(arguments[1])
        source = incoming_root / task_id
        if source.is_symlink() or not source.is_dir():
            raise RemoteError("incoming task does not exist")
        manifest = verify_manifest(task_id, source, final_root)
        print(json.dumps({"manifest_id": manifest["manifest_id"], "verified": True}))
        return 0

    if arguments[0] == "rsync-receive" and len(arguments) >= 6:
        task_id = safe_id(arguments[1])
        rsync_arguments = arguments[2:]
        if rsync_arguments[0] != "--server" or "--sender" in rsync_arguments:
            raise RemoteError("rsync receive-only server mode is required")
        if rsync_arguments[-2] != ".":
            raise RemoteError("invalid rsync destination syntax")
        forbidden = {
            "--backup-dir",
            "--compare-dest",
            "--config",
            "--copy-dest",
            "--daemon",
            "--files-from",
            "--link-dest",
            "--log-file",
            "--only-write-batch",
            "--partial-dir",
            "--password-file",
            "--remove-source-files",
            "--temp-dir",
            "--write-batch",
        }
        if any(arg.split("=", 1)[0] in forbidden for arg in rsync_arguments):
            raise RemoteError("forbidden rsync option")
        destination = incoming_root / task_id
        if destination.is_symlink() or not destination.is_dir():
            raise RemoteError("incoming task is not prepared")
        rsync_bin = os.environ.get("AUDIOBOOK_OPS_RSYNC_BIN", "/usr/bin/rsync")
        os.execv(
            rsync_bin,
            [rsync_bin, *rsync_arguments[:-1], str(destination)],
        )

    if arguments[0] == "promote" and len(arguments) == 4:
        task_id = safe_id(arguments[1])
        final_relative = arguments[2]
        manifest_id = arguments[3]
        if not re.fullmatch(r"[0-9a-f]{64}", manifest_id):
            raise RemoteError("invalid manifest ID")
        source = incoming_root / task_id
        destination = safe_relative_path(final_root, final_relative)
        if destination.exists():
            if destination.is_symlink() or not destination.is_dir() or source.exists():
                raise RemoteError("final destination already exists")
            manifest = load_manifest(destination / MANIFEST_NAME)
            if (
                manifest.get("task_id") != task_id
                or manifest.get("manifest_id") != manifest_id
                or manifest.get("final_relative_path") != final_relative
            ):
                raise RemoteError("existing final destination identity mismatch")
            print(json.dumps({"promoted": True, "replayed": True}))
            return 0
        if source.is_symlink() or not source.is_dir():
            raise RemoteError("incoming task does not exist")
        manifest = load_manifest(source / MANIFEST_NAME)
        if (
            manifest.get("task_id") != task_id
            or manifest.get("manifest_id") != manifest_id
            or manifest.get("final_relative_path") != final_relative
        ):
            raise RemoteError("verified manifest identity mismatch")
        destination.parent.mkdir(parents=True, exist_ok=True)
        parent = destination.parent
        while parent != final_root:
            if parent.is_symlink():
                raise RemoteError("final parent is a symlink")
            parent.chmod(0o2775)
            parent = parent.parent
        source.rename(destination)
        print(json.dumps({"promoted": True, "replayed": False}))
        return 0

    raise RemoteError("command is not allowed")


def main() -> int:
    try:
        return dispatch(os.environ.get("SSH_ORIGINAL_COMMAND", ""))
    except (OSError, ValueError, RemoteError) as error:
        print(f"remote wrapper error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
