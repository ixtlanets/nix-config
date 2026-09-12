#!/usr/bin/env python3

import hashlib
import json
import os
import re
import shlex
import shutil
import sys
from pathlib import Path


class RemoteError(RuntimeError):
    pass


SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


def configured_root(variable: str) -> Path:
    value = os.environ.get(variable)
    if not value:
        raise RemoteError(f"missing {variable}")
    return Path(value).resolve(strict=True)


def safe_request_id(value: str) -> str:
    if not SAFE_ID.fullmatch(value):
        raise RemoteError("unsafe request ID")
    return value


def safe_relative_path(root: Path, value: str) -> Path:
    relative = Path(value)
    if relative.is_absolute() or not relative.parts or ".." in relative.parts:
        raise RemoteError("unsafe final path")
    resolved = (root / relative).resolve(strict=False)
    if root not in resolved.parents:
        raise RemoteError("unsafe final path")
    return resolved


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def verify_manifest(request_id: str, source: Path) -> dict[str, object]:
    try:
        manifest = json.load(sys.stdin)
    except json.JSONDecodeError as error:
        raise RemoteError("invalid manifest JSON") from error
    if not isinstance(manifest, dict) or manifest.get("request_id") != request_id:
        raise RemoteError("manifest request ID mismatch")
    entries = manifest.get("files")
    if not isinstance(entries, list) or not entries:
        raise RemoteError("manifest contains no files")
    body = {"audio_files": manifest.get("audio_files"), "files": entries}
    calculated_id = hashlib.sha256(
        json.dumps(body, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    if manifest.get("manifest_id") != calculated_id:
        raise RemoteError("manifest ID mismatch")

    expected_paths: set[str] = set()
    allowed_extensions = {".flac", ".m4a", ".m4b", ".mp3"}
    audio_count = 0
    total_bytes = 0
    for entry in entries:
        if not isinstance(entry, dict):
            raise RemoteError("invalid manifest entry")
        relative = entry.get("path")
        if not isinstance(relative, str):
            raise RemoteError("invalid manifest path")
        if relative in expected_paths:
            raise RemoteError("duplicate manifest path")
        path = safe_relative_path(source, relative)
        if path.is_symlink() or not path.is_file():
            raise RemoteError(f"manifest file is not regular: {relative}")
        if path.stat().st_size != entry.get("size"):
            raise RemoteError(f"size mismatch: {relative}")
        if sha256_file(path) != entry.get("sha256"):
            raise RemoteError(f"checksum mismatch: {relative}")
        expected_paths.add(relative)
        total_bytes += path.stat().st_size
        if path.suffix.lower() in allowed_extensions:
            audio_count += 1

    if audio_count == 0 or manifest.get("audio_files") != audio_count:
        raise RemoteError("manifest contains no valid supported audio set")
    maximum = int(os.environ.get("READMABOOK_MAX_RELEASE_GIB", "20")) * 1024**3
    if total_bytes > maximum:
        raise RemoteError("release exceeds the remote size limit")
    minimum_free = int(os.environ.get("READMABOOK_MIN_REMOTE_FREE_GIB", "200")) * 1024**3
    if shutil.disk_usage(configured_root("READMABOOK_FINAL_ROOT")).free - total_bytes < minimum_free:
        raise RemoteError("remote free-space reserve would be violated")

    actual_paths: set[str] = set()
    for current_root, directory_names, file_names in os.walk(source, followlinks=False):
        current = Path(current_root)
        for directory_name in directory_names:
            if (current / directory_name).is_symlink():
                raise RemoteError("symlink is forbidden in incoming directory")
        for file_name in file_names:
            if file_name == ".readmeabook-manifest.json":
                continue
            path = current / file_name
            if path.is_symlink() or not path.is_file():
                raise RemoteError("non-regular file is forbidden in incoming directory")
            actual_paths.add(path.relative_to(source).as_posix())
    if actual_paths != expected_paths:
        raise RemoteError("incoming file set does not match manifest")

    source.chmod(0o2775)
    for current_root, directory_names, file_names in os.walk(source, followlinks=False):
        current = Path(current_root)
        for directory_name in directory_names:
            (current / directory_name).chmod(0o2775)
        for file_name in file_names:
            (current / file_name).chmod(0o664)

    final_relative = manifest.get("final_relative_path")
    if not isinstance(final_relative, str):
        raise RemoteError("manifest has no final path")
    safe_relative_path(configured_root("READMABOOK_FINAL_ROOT"), final_relative)
    manifest_path = source / ".readmeabook-manifest.json"
    temp_path = source / ".readmeabook-manifest.json.tmp"
    temp_path.write_text(json.dumps(manifest, sort_keys=True, indent=2) + "\n")
    temp_path.chmod(0o600)
    temp_path.replace(manifest_path)
    return manifest


def dispatch(command: str) -> int:
    try:
        arguments = shlex.split(command)
    except ValueError as error:
        raise RemoteError("invalid command") from error
    if not arguments:
        raise RemoteError("missing command")

    incoming_root = configured_root("READMABOOK_INCOMING_ROOT")
    final_root = configured_root("READMABOOK_FINAL_ROOT")

    if arguments == ["capacity"]:
        print(json.dumps({"free_bytes": shutil.disk_usage(final_root).free}))
        return 0

    if arguments[0] == "prepare" and len(arguments) == 2:
        request_id = safe_request_id(arguments[1])
        source = incoming_root / request_id
        source.mkdir(mode=0o700, exist_ok=True)
        if source.is_symlink() or not source.is_dir():
            raise RemoteError("unsafe incoming request directory")
        print(source)
        return 0

    if arguments[0] == "verify" and len(arguments) == 2:
        request_id = safe_request_id(arguments[1])
        source = incoming_root / request_id
        if source.is_symlink() or not source.is_dir():
            raise RemoteError("incoming request does not exist")
        manifest = verify_manifest(request_id, source)
        print(json.dumps({"manifest_id": manifest["manifest_id"], "verified": True}))
        return 0

    if arguments[0] == "rsync-receive" and len(arguments) >= 6:
        request_id = safe_request_id(arguments[1])
        rsync_arguments = arguments[2:]
        if rsync_arguments[0] != "--server":
            raise RemoteError("rsync server mode is required")
        if "--sender" in rsync_arguments:
            raise RemoteError("rsync sender mode is forbidden")
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
        if any(argument.split("=", 1)[0] in forbidden for argument in rsync_arguments):
            raise RemoteError("forbidden rsync option")
        destination = incoming_root / request_id
        if destination.is_symlink() or not destination.is_dir():
            raise RemoteError("incoming request is not prepared")
        rsync_bin = os.environ.get("READMABOOK_RSYNC_BIN", "/usr/bin/rsync")
        os.execv(rsync_bin, [rsync_bin, *rsync_arguments[:-1], str(destination)])

    if arguments[0] == "promote" and len(arguments) == 3:
        request_id = safe_request_id(arguments[1])
        destination = safe_relative_path(final_root, arguments[2])
        source = incoming_root / request_id
        if not source.is_dir():
            raise RemoteError("incoming request does not exist")
        manifest_path = source / ".readmeabook-manifest.json"
        if not manifest_path.is_file():
            raise RemoteError("incoming request is not verified")
        manifest = json.loads(manifest_path.read_text())
        if manifest.get("request_id") != request_id:
            raise RemoteError("verified manifest request ID mismatch")
        if manifest.get("final_relative_path") != arguments[2]:
            raise RemoteError("verified manifest final path mismatch")
        if destination.exists():
            raise RemoteError("final destination already exists")
        destination.parent.mkdir(parents=True, exist_ok=True)
        parent = destination.parent
        while parent != final_root:
            parent.chmod(0o2775)
            parent = parent.parent
        source.rename(destination)
        print(destination)
        return 0

    if arguments[0] == "unpublish" and len(arguments) == 3:
        manifest_id = arguments[1]
        if not re.fullmatch(r"[0-9a-f]{64}", manifest_id):
            raise RemoteError("invalid manifest ID")
        destination = safe_relative_path(final_root, arguments[2])
        if destination.is_symlink() or not destination.is_dir():
            raise RemoteError("published directory does not exist")
        manifest_path = destination / ".readmeabook-manifest.json"
        if manifest_path.is_symlink() or not manifest_path.is_file():
            raise RemoteError("published manifest does not exist")
        manifest = json.loads(manifest_path.read_text())
        if manifest.get("manifest_id") != manifest_id:
            raise RemoteError("manifest ID mismatch")
        if manifest.get("final_relative_path") != arguments[2]:
            raise RemoteError("manifest final path mismatch")
        shutil.rmtree(destination)
        if destination.parent != final_root:
            try:
                destination.parent.rmdir()
            except OSError:
                pass
        print(manifest_id)
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
