#!/usr/bin/env python3

from __future__ import annotations

import argparse
from datetime import UTC, datetime
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import stat
import subprocess
import sys

from audiobook_ops.interface import OperationError, SCHEMA_VERSION


SAFE_NAME = re.compile(r"^[a-z0-9][a-z0-9._-]{0,127}$")
SAFE_TIMESTAMP = re.compile(r"^[0-9]{8}T[0-9]{6}Z$")
OPERATOR_FILES = frozenset(
    {
        "audiobook-ops.json",
        "backup.json",
        "compose.env",
        "health.json",
        "policy.json",
        "publisher.json",
    }
)
SECRET_FILES = frozenset(
    {
        "abs-api-token",
        "mcp-bearer",
        "prowlarr-api-key",
        "publisher-ssh-key",
        "transmission-password",
    }
)
RETAINED_STATE = frozenset({"flaresolverr", "prowlarr", "transmission"})
PAUSE_CONTAINERS = frozenset(
    {
        "audiobook-ops",
        "audiobook-ops-flaresolverr",
        "audiobook-ops-rutracker-gateway",
        "audiobook-ops-prowlarr",
        "audiobook-ops-transmission",
    }
)


def load_config(path: Path) -> dict[str, object]:
    if path.is_symlink() or not path.is_file():
        raise OperationError("backup configuration is missing or unsafe")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise OperationError("backup configuration is invalid") from error
    if not isinstance(value, dict):
        raise OperationError("backup configuration is invalid")
    return value


def configured_path(config: dict[str, object], name: str) -> Path:
    value = config.get(name)
    if not isinstance(value, str) or not value:
        raise OperationError(f"backup {name} is invalid")
    return Path(os.path.expandvars(os.path.expanduser(value)))


def named_paths(config: dict[str, object], name: str) -> dict[str, Path]:
    value = config.get(name)
    if not isinstance(value, dict) or not value:
        raise OperationError(f"backup {name} is invalid")
    result: dict[str, Path] = {}
    for key, path in value.items():
        if (
            not isinstance(key, str)
            or not SAFE_NAME.fullmatch(key)
            or not isinstance(path, str)
            or not path
        ):
            raise OperationError(f"backup {name} is invalid")
        result[key] = Path(os.path.expandvars(os.path.expanduser(path)))
    return result


def require_file(path: Path, label: str) -> Path:
    if path.is_symlink() or not path.is_file():
        raise OperationError(f"backup {label} is missing or unsafe")
    return path.resolve(strict=True)


def require_tree(path: Path, label: str) -> Path:
    if path.is_symlink() or not path.is_dir():
        raise OperationError(f"backup {label} is missing or unsafe")
    root = path.resolve(strict=True)
    for current_root, directory_names, file_names in os.walk(root, followlinks=False):
        current = Path(current_root)
        for name in directory_names:
            candidate = current / name
            if candidate.is_symlink() or not candidate.is_dir():
                raise OperationError(f"backup {label} contains an unsafe entry")
        for name in file_names:
            candidate = current / name
            metadata = candidate.lstat()
            if candidate.is_symlink() or not stat.S_ISREG(metadata.st_mode):
                raise OperationError(f"backup {label} contains an unsafe entry")
    return root


def sqlite_backup(source: Path, destination: Path) -> int:
    source_connection = sqlite3.connect(f"{source.as_uri()}?mode=ro", uri=True)
    destination_connection = sqlite3.connect(destination)
    try:
        source_connection.backup(destination_connection)
        integrity = destination_connection.execute("PRAGMA integrity_check").fetchone()[0]
        version = int(
            destination_connection.execute(
                "SELECT COALESCE(MAX(version), 0) FROM schema_migrations"
            ).fetchone()[0]
        )
        if integrity != "ok" or version > SCHEMA_VERSION:
            raise OperationError("SQLite backup integrity or schema check failed")
    except Exception:
        destination_connection.close()
        source_connection.close()
        destination.unlink(missing_ok=True)
        raise
    destination_connection.close()
    source_connection.close()
    destination.chmod(0o600)
    return version


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_checksums(root: Path) -> None:
    paths = sorted(
        path for path in root.rglob("*") if path.is_file() and path.name != "SHA256SUMS"
    )
    lines = [f"{sha256(path)}  {path.relative_to(root).as_posix()}" for path in paths]
    target = root / "SHA256SUMS"
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")
    target.chmod(0o600)


def write_evidence(path: Path, timestamp: str) -> None:
    if path.parent.is_symlink() or not path.parent.is_dir() or path.is_symlink():
        raise OperationError("backup evidence destination is unsafe")
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    if temporary.exists() or temporary.is_symlink():
        raise OperationError("backup evidence destination is unsafe")
    temporary.write_text(
        json.dumps(
            {"created_at": timestamp, "format": 1, "status": "ok"},
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n",
        encoding="utf-8",
    )
    temporary.chmod(0o644)
    temporary.replace(path)


def pause_containers(config: dict[str, object]) -> list[str]:
    containers = config.get("pause_containers", [])
    if not isinstance(containers, list) or any(
        not isinstance(value, str) or not SAFE_NAME.fullmatch(value)
        for value in containers
    ):
        raise OperationError("backup pause_containers is invalid")
    if len(containers) != len(PAUSE_CONTAINERS) or set(containers) != PAUSE_CONTAINERS:
        raise OperationError("backup pause_containers is incomplete")
    docker_bin = str(config.get("docker_bin", "/usr/bin/docker"))
    paused: list[str] = []
    for container in containers:
        result = subprocess.run(
            [docker_bin, "pause", container],
            check=False,
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode != 0:
            unpause_containers(config, paused)
            raise OperationError("backup could not pause retained containers")
        paused.append(container)
    return paused


def unpause_containers(config: dict[str, object], containers: list[str]) -> None:
    if not containers:
        return
    docker_bin = str(config.get("docker_bin", "/usr/bin/docker"))
    result = subprocess.run(
        [docker_bin, "unpause", *containers],
        check=False,
        capture_output=True,
        text=True,
        timeout=120,
    )
    if result.returncode != 0:
        raise OperationError("backup could not unpause retained containers")


def execute(config: dict[str, object], timestamp: str) -> Path:
    if not SAFE_TIMESTAMP.fullmatch(timestamp):
        raise OperationError("backup timestamp is invalid")
    database = require_file(configured_path(config, "database_path"), "database")
    evidence = configured_path(config, "backup_evidence_file")
    ledger = require_file(configured_path(config, "legacy_ledger_path"), "ledger")
    if ledger.stat().st_mode & 0o222:
        raise OperationError("backup ledger artifact must be read-only")
    operator_files = {
        name: require_file(path, f"operator file {name}")
        for name, path in named_paths(config, "operator_files").items()
    }
    if set(operator_files) != OPERATOR_FILES:
        raise OperationError("backup operator file set is incomplete")
    secret_files = {
        name: require_file(path, f"secret file {name}")
        for name, path in named_paths(config, "secret_files").items()
    }
    if set(secret_files) != SECRET_FILES:
        raise OperationError("backup secret file set is incomplete")
    if any(path.stat().st_mode & 0o077 for path in secret_files.values()):
        raise OperationError("backup secret source permissions are not private")
    retained_state = {
        name: require_tree(path, f"retained state {name}")
        for name, path in named_paths(config, "retained_state").items()
    }
    if set(retained_state) != RETAINED_STATE:
        raise OperationError("backup retained state set is incomplete")
    backup_root = configured_path(config, "backup_root")
    if backup_root.is_symlink() or not backup_root.is_dir():
        raise OperationError("backup root is missing or unsafe")
    backup_root = backup_root.resolve(strict=True)
    if backup_root.stat().st_mode & 0o077:
        raise OperationError("backup root permissions are not private")
    sources = [
        database,
        evidence,
        ledger,
        *operator_files.values(),
        *secret_files.values(),
        *retained_state.values(),
    ]
    if any(
        backup_root == source
        or backup_root in source.parents
        or source in backup_root.parents
        for source in sources
    ):
        raise OperationError("backup root overlaps a source")
    final = backup_root / timestamp
    partial = backup_root / f".partial-{timestamp}-{os.getpid()}"
    if final.exists() or final.is_symlink() or partial.exists() or partial.is_symlink():
        raise OperationError("backup destination already exists")
    partial.mkdir(mode=0o700)
    paused: list[str] = []
    try:
        (partial / "operator").mkdir(mode=0o700)
        (partial / "secrets").mkdir(mode=0o700)
        (partial / "retained").mkdir(mode=0o700)
        (partial / "migration").mkdir(mode=0o700)
        paused = pause_containers(config)
        schema_version = sqlite_backup(database, partial / "audiobook-ops.sqlite3")
        for name, source in operator_files.items():
            shutil.copy2(source, partial / "operator" / name, follow_symlinks=False)
        for name, source in secret_files.items():
            target = partial / "secrets" / name
            shutil.copyfile(source, target, follow_symlinks=False)
            target.chmod(0o600)
        for name, source in retained_state.items():
            shutil.copytree(source, partial / "retained" / name, symlinks=False)
        ledger_target = partial / "migration" / "readmeabook-ledger.json"
        shutil.copyfile(ledger, ledger_target, follow_symlinks=False)
        ledger_target.chmod(0o400)
        metadata = {
            "created_at": timestamp,
            "format": 1,
            "schema_version": schema_version,
        }
        (partial / "backup.json").write_text(
            json.dumps(metadata, sort_keys=True, separators=(",", ":")) + "\n",
            encoding="utf-8",
        )
        (partial / "backup.json").chmod(0o600)
        write_checksums(partial)
        partial.rename(final)
        write_evidence(evidence, timestamp)
    except Exception:
        if partial.exists() and partial.parent == backup_root:
            shutil.rmtree(partial)
        raise
    finally:
        unpause_containers(config, paused)
    return final


def main() -> int:
    parser = argparse.ArgumentParser(description="Atomic audiobook-ops state backup")
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--timestamp")
    arguments = parser.parse_args()
    try:
        config = load_config(arguments.config)
        if not arguments.execute:
            print(json.dumps({"status": "preview", "writes": False}, sort_keys=True))
            return 0
        timestamp = arguments.timestamp or datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        backup = execute(config, timestamp)
        print(json.dumps({"backup": str(backup), "status": "created"}, sort_keys=True))
        return 0
    except (OSError, TypeError, ValueError, sqlite3.Error, OperationError) as error:
        print(
            json.dumps(
                {"event": "backup_error", "reason": str(error)},
                separators=(",", ":"),
            ),
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
