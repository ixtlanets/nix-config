#!/usr/bin/env python3

from __future__ import annotations

import json
import os
from pathlib import Path
import stat
import sys


RUNTIME_UID = 1000
RUNTIME_GID = 1000
RUNTIME_ROOT = Path("/run/audiobook-ops-runtime")
SOURCE_CONFIG = Path("/etc/audiobook-ops/config.json")
SECRET_PATHS = {
    "abs_api_token_file": Path("/run/secrets/abs-api-token"),
    "mcp_bearer_file": Path("/run/secrets/mcp-bearer"),
    "prowlarr_api_key_file": Path("/run/secrets/prowlarr-api-key"),
    "transmission_password_file": Path("/run/secrets/transmission-password"),
}


class BootstrapError(RuntimeError):
    pass


def read_root_owned_file(
    path: Path, maximum_bytes: int, *, require_private: bool
) -> bytes:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as error:
        raise BootstrapError(f"required root-owned file is unavailable: {path.name}") from error
    try:
        metadata = os.fstat(descriptor)
        mode = stat.S_IMODE(metadata.st_mode)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_uid != 0
            or mode & 0o400 == 0
            or mode & 0o022 != 0
            or (require_private and mode & 0o077 != 0)
        ):
            raise BootstrapError(f"required root-owned file is unsafe: {path.name}")
        value = bytearray()
        while len(value) <= maximum_bytes:
            chunk = os.read(descriptor, min(64 * 1024, maximum_bytes + 1 - len(value)))
            if not chunk:
                break
            value.extend(chunk)
        if not value or len(value) > maximum_bytes:
            raise BootstrapError(f"required root-owned file has an invalid size: {path.name}")
        return bytes(value)
    finally:
        os.close(descriptor)


def atomic_runtime_file(path: Path, value: bytes) -> None:
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    descriptor = -1
    try:
        descriptor = os.open(temporary, flags, 0o600)
        view = memoryview(value)
        while view:
            written = os.write(descriptor, view)
            view = view[written:]
        os.fsync(descriptor)
        os.fchown(descriptor, RUNTIME_UID, RUNTIME_GID)
        os.fchmod(descriptor, 0o400)
        os.close(descriptor)
        descriptor = -1
        os.replace(temporary, path)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def prepare_runtime_files() -> Path:
    try:
        metadata = RUNTIME_ROOT.stat(follow_symlinks=False)
    except OSError as error:
        raise BootstrapError("private runtime tmpfs is unavailable") from error
    if (
        not stat.S_ISDIR(metadata.st_mode)
        or metadata.st_uid != 0
        or stat.S_IMODE(metadata.st_mode) != 0o711
    ):
        raise BootstrapError("private runtime tmpfs is unsafe")

    raw_config = read_root_owned_file(
        SOURCE_CONFIG, 1024 * 1024, require_private=False
    )
    try:
        config = json.loads(raw_config.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise BootstrapError("runtime configuration is invalid") from error
    if not isinstance(config, dict):
        raise BootstrapError("runtime configuration is invalid")

    for field, source in SECRET_PATHS.items():
        if config.get(field) != str(source):
            raise BootstrapError(f"runtime secret path is not pinned: {field}")
        target = RUNTIME_ROOT / source.name
        atomic_runtime_file(
            target,
            read_root_owned_file(source, 64 * 1024, require_private=True),
        )
        config[field] = str(target)

    target_config = RUNTIME_ROOT / "config.json"
    atomic_runtime_file(
        target_config,
        (json.dumps(config, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8"),
    )
    return target_config


def drop_privileges() -> None:
    os.setgroups([])
    os.setgid(RUNTIME_GID)
    os.setuid(RUNTIME_UID)
    if os.getuid() != RUNTIME_UID or os.getgid() != RUNTIME_GID or os.getgroups():
        raise BootstrapError("failed to drop container privileges")


def main() -> int:
    try:
        config = prepare_runtime_files()
        os.environ["AUDIOBOOK_OPS_CONFIG"] = str(config)
        drop_privileges()
        os.execvp(
            "python",
            ["python", "-m", "audiobook_ops", *sys.argv[1:]],
        )
    except (BootstrapError, OSError) as error:
        print(
            json.dumps({"event": "bootstrap_error", "reason": str(error)}),
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
