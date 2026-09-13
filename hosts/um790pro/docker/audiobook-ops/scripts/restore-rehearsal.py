#!/usr/bin/env python3

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sys

from audiobook_ops.interface import AudiobookOperations, OperationError


CHECKSUM = re.compile(r"^([0-9a-f]{64})  ([^\n]+)$")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_backup(backup: Path) -> Path:
    if backup.is_symlink() or not backup.is_dir():
        raise OperationError("backup is missing or unsafe")
    root = backup.resolve(strict=True)
    sums = root / "SHA256SUMS"
    if sums.is_symlink() or not sums.is_file():
        raise OperationError("backup checksum manifest is missing or unsafe")
    for path in root.rglob("*"):
        if path.is_symlink():
            raise OperationError("backup contains an unsafe symlink")
    expected: dict[str, str] = {}
    for line in sums.read_text(encoding="utf-8").splitlines():
        match = CHECKSUM.fullmatch(line)
        if match is None or match.group(2) in expected:
            raise OperationError("backup checksum manifest is invalid")
        relative = Path(match.group(2))
        if relative.is_absolute() or any(part in {"", ".", ".."} for part in relative.parts):
            raise OperationError("backup checksum path is unsafe")
        path = (root / relative).resolve(strict=True)
        if root not in path.parents or not path.is_file():
            raise OperationError("backup checksum path is unsafe")
        expected[relative.as_posix()] = match.group(1)
    actual = {
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file() and path != sums
    }
    if actual != set(expected):
        raise OperationError("backup checksum file set changed")
    for relative, checksum in expected.items():
        if sha256(root / relative) != checksum:
            raise OperationError("backup checksum mismatch")
    required = {
        "audiobook-ops.sqlite3",
        "backup.json",
        "migration/readmeabook-ledger.json",
    }
    if not required.issubset(actual):
        raise OperationError("backup is incomplete")
    return root


def safe_destination(destination: Path, backup: Path, production: list[Path]) -> Path:
    if destination.is_symlink():
        raise OperationError("restore destination is unsafe")
    target = destination.resolve(strict=False)
    if target == Path("/") or target == backup or backup in target.parents:
        raise OperationError("restore destination is unsafe")
    for value in production:
        protected = value.resolve(strict=False)
        if target == protected or protected in target.parents or target in protected.parents:
            raise OperationError("restore destination overlaps production")
    if target.exists() or target.is_symlink():
        raise OperationError("restore destination already exists")
    if not target.parent.is_dir() or target.parent.is_symlink():
        raise OperationError("restore destination parent is unsafe")
    return target


def restore(backup: Path, destination: Path) -> None:
    partial = destination.parent / f".{destination.name}.partial-{os.getpid()}"
    if partial.exists() or partial.is_symlink():
        raise OperationError("restore partial destination already exists")
    partial.mkdir(mode=0o700)
    try:
        AudiobookOperations.restore_backup(
            backup / "audiobook-ops.sqlite3",
            partial / "audiobook-ops.sqlite3",
        )
        shutil.copytree(backup / "operator", partial / "operator", symlinks=False)
        shutil.copytree(backup / "secrets", partial / "secrets", symlinks=False)
        shutil.copytree(backup / "retained", partial / "retained", symlinks=False)
        (partial / "staging").mkdir(mode=0o700)
        (partial / "retained" / "downloads").mkdir(mode=0o700)
        ledger = partial / "legacy-ledger.json"
        shutil.copyfile(
            backup / "migration" / "readmeabook-ledger.json",
            ledger,
            follow_symlinks=False,
        )
        ledger.chmod(0o400)
        for secret in (partial / "secrets").iterdir():
            if secret.is_symlink() or not secret.is_file():
                raise OperationError("restored secret entry is unsafe")
            secret.chmod(0o600)
        partial.rename(destination)
    except Exception:
        if partial.exists() and partial.parent == destination.parent:
            shutil.rmtree(partial)
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description="Disposable audiobook-ops restore rehearsal")
    parser.add_argument("--backup", required=True, type=Path)
    parser.add_argument("--destination", required=True, type=Path)
    parser.add_argument("--production-path", action="append", default=[], type=Path)
    parser.add_argument("--execute", action="store_true")
    arguments = parser.parse_args()
    try:
        if arguments.backup.is_symlink() or not arguments.backup.is_dir():
            raise OperationError("backup is missing or unsafe")
        backup_root = arguments.backup.resolve(strict=True)
        destination = safe_destination(
            arguments.destination, backup_root, arguments.production_path
        )
        backup = verify_backup(backup_root)
        if not arguments.execute:
            print('{"status":"preview","writes":false}')
            return 0
        restore(backup, destination)
        print(
            json.dumps(
                {"restore": str(destination), "status": "verified"},
                separators=(",", ":"),
                sort_keys=True,
            )
        )
        return 0
    except (OSError, ValueError, OperationError) as error:
        print(f"restore rehearsal error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
