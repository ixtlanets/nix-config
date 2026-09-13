#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import time

from audiobook_ops.acquisition_worker import AcquisitionCoordinator
from audiobook_ops.interface import AudiobookOperations, OperationError, SystemClock
from audiobook_ops.runtime import expanded_path, load_config, read_secret
from audiobook_ops.transmission import TransmissionAdapter, TransmissionHTTPRPC
from audiobook_ops.validation import CapacitySnapshot, MediaValidator, SubprocessAudioProbe


def capacity_snapshot(config: dict[str, object]) -> CapacitySnapshot:
    path = expanded_path(config.get("capacity_evidence_file"), "capacity evidence")
    if path.is_symlink() or not path.is_file():
        raise OperationError("capacity evidence is missing or unsafe")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise OperationError("capacity evidence is invalid") from error
    required = {
        "local_free_bytes",
        "observed_at_epoch",
        "remote_free_bytes",
        "status",
        "working_set_bytes",
    }
    if not isinstance(value, dict) or set(value) != required or value["status"] != "ok":
        raise OperationError("capacity evidence is invalid")
    observed = value["observed_at_epoch"]
    maximum_age = int(config.get("capacity_evidence_max_age_seconds", 900))
    if (
        not isinstance(observed, (int, float))
        or time.time() - float(observed) > maximum_age
        or float(observed) > time.time() + 60
    ):
        raise OperationError("capacity evidence is stale")
    try:
        return CapacitySnapshot(
            working_set_bytes=int(value["working_set_bytes"]),
            local_free_bytes=int(value["local_free_bytes"]),
            remote_free_bytes=int(value["remote_free_bytes"]),
        )
    except (TypeError, ValueError) as error:
        raise OperationError("capacity evidence is invalid") from error


def require_vless_evidence(config: dict[str, object]) -> None:
    path = expanded_path(config.get("vless_evidence_file"), "VLESS evidence")
    if path.is_symlink() or not path.is_file():
        raise OperationError("VLESS evidence is missing or unsafe")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise OperationError("VLESS evidence is invalid") from error
    observed = value.get("observed_at_epoch") if isinstance(value, dict) else None
    maximum_age = int(config.get("capacity_evidence_max_age_seconds", 900))
    if (
        not isinstance(value, dict)
        or value.get("route") != "vless"
        or value.get("status") != "ok"
        or not isinstance(observed, (int, float))
        or time.time() - float(observed) > maximum_age
        or float(observed) > time.time() + 60
    ):
        raise OperationError("VLESS evidence is stale or degraded")
def build_coordinator(
    operations: AudiobookOperations, config: dict[str, object]
) -> AcquisitionCoordinator:
    password = read_secret(
        config.get("transmission_password_file"), "Transmission password"
    )
    transmission = TransmissionAdapter(
        TransmissionHTTPRPC(
            str(config.get("transmission_url", "")),
            str(config.get("transmission_username", "audiobook-ops")),
            password,
        ),
        download_dir=str(config.get("transmission_download_dir", "/downloads/complete")),
    )
    limits = config.get("limits", {})
    if not isinstance(limits, dict):
        raise OperationError("runtime limits are invalid")
    stability_seconds = int(config.get("stability_seconds", 30))
    validator = MediaValidator(
        downloads_root=expanded_path(config.get("downloads_root"), "downloads root"),
        staging_root=expanded_path(config.get("staging_root"), "staging root"),
        probe=SubprocessAudioProbe(str(config.get("ffprobe_bin", "/usr/bin/ffprobe"))),
        capacity=lambda: capacity_snapshot(config),
        stability_hook=lambda: time.sleep(stability_seconds),
        max_release_bytes=int(limits.get("max_release_gib", 20)) * 1024**3,
        max_working_set_bytes=int(limits.get("max_working_set_gib", 50)) * 1024**3,
        min_local_free_bytes=int(limits.get("min_local_free_gib", 100)) * 1024**3,
        min_remote_free_bytes=int(limits.get("min_remote_free_gib", 200)) * 1024**3,
        max_ancillary_files=int(limits.get("max_ancillary_files", 20)),
        max_ancillary_bytes=int(limits.get("max_ancillary_mib", 10)) * 1024**2,
    )
    return AcquisitionCoordinator(operations, transmission, validator, SystemClock())


def main() -> int:
    parser = argparse.ArgumentParser(description="Reconcile audiobook acquisition work")
    parser.add_argument("--config", required=True, type=Path)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("status")
    for name in ("run-once", "cleanup-once"):
        command = commands.add_parser(name)
        command.add_argument("--execute", action="store_true")
    arguments = parser.parse_args()
    if arguments.command != "status" and not arguments.execute:
        print(f"{arguments.command} requires --execute", file=sys.stderr)
        return 2
    operations = None
    try:
        config = load_config(arguments.config)
        operations = AudiobookOperations.open(
            expanded_path(config.get("database_path"), "database path")
        )
        if arguments.command == "status":
            snapshot = capacity_snapshot(config)
            output: object = {
                "capacity": {
                    "local_free_bytes": snapshot.local_free_bytes,
                    "remote_free_bytes": snapshot.remote_free_bytes,
                    "working_set_bytes": snapshot.working_set_bytes,
                },
                "tasks": operations.invoke("task_list", {})["tasks"],
            }
        else:
            coordinator = build_coordinator(operations, config)
            if arguments.command == "run-once":
                require_vless_evidence(config)
            output = (
                coordinator.cleanup_once()
                if arguments.command == "cleanup-once"
                else coordinator.reconcile_once()
            ) or {"status": "idle"}
        print(json.dumps(output, ensure_ascii=False, separators=(",", ":")))
        return 0
    except (OSError, TypeError, ValueError, OperationError) as error:
        print(
            json.dumps(
                {"event": "worker_error", "reason": str(error)},
                separators=(",", ":"),
            ),
            file=sys.stderr,
        )
        return 1
    finally:
        if operations is not None:
            operations.close()


if __name__ == "__main__":
    raise SystemExit(main())
