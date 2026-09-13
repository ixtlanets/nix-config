#!/usr/bin/env python3

from __future__ import annotations

import argparse
import fcntl
import json
import os
from pathlib import Path
import shutil
import sys
import time

from audiobook_ops.interface import AudiobookOperations, OperationError
from audiobook_ops.publisher import (
    PublicationCoordinator,
    PublicationValidator,
    SSHRemotePublisher,
)
from audiobook_ops.validation import SubprocessAudioProbe


def load_config(path: Path) -> dict[str, object]:
    if path.is_symlink() or not path.is_file():
        raise OperationError("publisher configuration is missing or unsafe")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise OperationError("publisher configuration is invalid") from error
    if not isinstance(value, dict):
        raise OperationError("publisher configuration is invalid")
    return value


def expanded_path(value: object) -> Path:
    if not isinstance(value, str) or not value:
        raise OperationError("publisher path configuration is invalid")
    return Path(os.path.expandvars(os.path.expanduser(value)))


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description="Verified audiobook publisher")
    result.add_argument("--config", required=True, type=Path)
    commands = result.add_subparsers(dest="command", required=True)
    status = commands.add_parser("status")
    status.add_argument("--json", action="store_true", dest="as_json")
    run_once = commands.add_parser("run-once")
    run_once.add_argument("--execute", action="store_true")
    run_once.add_argument("--json", action="store_true", dest="as_json")
    return result


def build_coordinator(
    operations: AudiobookOperations, config: dict[str, object]
) -> PublicationCoordinator:
    staging_root = expanded_path(config.get("staging_root"))
    remote = SSHRemotePublisher(
        remote_host=str(config.get("remote_host", "")),
        identity_file=expanded_path(config.get("publisher_identity_file")),
        known_hosts_file=expanded_path(config.get("known_hosts_file")),
        ssh_bin=str(config.get("ssh_bin", "ssh")),
        rsync_bin=str(config.get("rsync_bin", "rsync")),
    )
    stability_seconds = int(config.get("stability_seconds", 30))
    return PublicationCoordinator(
        operations,
        PublicationValidator(
            staging_root=staging_root,
            probe=SubprocessAudioProbe(str(config.get("ffprobe_bin", "ffprobe"))),
            local_free_bytes=lambda: shutil.disk_usage(staging_root).free,
            stability_hook=lambda: time.sleep(stability_seconds),
            min_local_free_bytes=int(config.get("min_local_free_gib", 100))
            * 1024**3,
            max_release_bytes=int(config.get("max_release_gib", 20)) * 1024**3,
        ),
        remote,
        publisher_id=str(config.get("publisher_id", "audiobook-publisher")),
        min_remote_free_bytes=int(config.get("min_remote_free_gib", 200))
        * 1024**3,
    )


def main() -> int:
    arguments = parser().parse_args()
    if arguments.command == "run-once" and not arguments.execute:
        print("run-once requires --execute", file=sys.stderr)
        return 2
    try:
        config = load_config(arguments.config)
        database = expanded_path(config.get("database_path"))
        lock_path = expanded_path(config.get("lock_path"))
        lock_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        with lock_path.open("a+", encoding="utf-8") as lock:
            lock_path.chmod(0o600)
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise OperationError("another publisher run holds the lock")
            operations = AudiobookOperations.open(database)
            try:
                if arguments.command == "status":
                    result = operations.outstanding_publication()
                    output: object = result or {"status": "idle"}
                elif arguments.command == "run-once":
                    coordinator = build_coordinator(operations, config)
                    output = coordinator.reconcile_once() or {"status": "idle"}
                else:
                    raise AssertionError(arguments.command)
            except (OSError, TypeError, ValueError, OperationError) as error:
                outstanding = operations.outstanding_publication()
                if outstanding is not None:
                    operations.record_publication_error(
                        str(outstanding["publication"]["publication_id"]), str(error)
                    )
                raise
            finally:
                operations.close()
        if getattr(arguments, "as_json", False):
            print(json.dumps(output, ensure_ascii=False, sort_keys=True))
        else:
            publication = output.get("publication") if isinstance(output, dict) else None
            print(
                f"status: {publication.get('status') if isinstance(publication, dict) else 'idle'}"
            )
        return 0
    except (OSError, TypeError, ValueError, OperationError) as error:
        print(
            json.dumps(
                {"event": "publisher_error", "reason": str(error)},
                separators=(",", ":"),
            ),
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
