#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import time

from audiobook_ops.interface import OperationError
from audiobook_ops.publisher import SSHRemotePublisher
from audiobook_ops.runtime import expanded_path, load_config


def allocated_bytes(root: Path) -> int:
    if root.is_symlink() or not root.is_dir():
        raise OperationError("policy working-set root is missing or unsafe")
    canonical = root.resolve(strict=True)
    seen: set[tuple[int, int]] = set()
    total = 0
    for current_root, directory_names, file_names in os.walk(
        canonical, followlinks=False
    ):
        current = Path(current_root)
        for name in directory_names:
            if (current / name).is_symlink():
                raise OperationError("policy working-set root contains a symlink")
        for name in file_names:
            path = current / name
            metadata = path.lstat()
            if path.is_symlink() or not stat.S_ISREG(metadata.st_mode):
                raise OperationError("policy working-set root contains an unsafe entry")
            identity = (metadata.st_dev, metadata.st_ino)
            if identity not in seen:
                total += metadata.st_blocks * 512
                seen.add(identity)
    return total


def remote_capacity(config: dict[str, object]) -> int:
    publisher = config.get("publisher")
    if not isinstance(publisher, dict):
        raise OperationError("policy publisher configuration is invalid")
    remote = SSHRemotePublisher(
        remote_host=str(publisher.get("remote_host", "")),
        identity_file=expanded_path(
            publisher.get("publisher_identity_file"), "publisher identity"
        ),
        known_hosts_file=expanded_path(
            publisher.get("known_hosts_file"), "known hosts"
        ),
        ssh_bin=str(publisher.get("ssh_bin", "/usr/bin/ssh")),
        rsync_bin=str(publisher.get("rsync_bin", "/usr/bin/rsync")),
    )
    return remote.capacity_bytes()


def vless_healthy(config: dict[str, object]) -> bool:
    unit = str(config.get("vless_unit", "vless-sing-box.service"))
    interface = str(config.get("vless_interface", "nekoray-tun"))
    probe_url = str(config.get("vless_probe_url", "https://www.cloudflare.com/cdn-cgi/trace"))
    checks = (
        [str(config.get("systemctl_bin", "/usr/bin/systemctl")), "is-active", "--quiet", unit],
        [str(config.get("ip_bin", "/usr/bin/ip")), "link", "show", "dev", interface],
        [
            str(config.get("curl_bin", "/usr/bin/curl")),
            "--fail",
            "--silent",
            "--show-error",
            "--max-time",
            "15",
            "--interface",
            interface,
            probe_url,
        ],
    )
    for command in checks:
        result = subprocess.run(
            command,
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=30,
        )
        if result.returncode != 0:
            return False
    return True


def snapshot(config: dict[str, object]) -> tuple[dict[str, object], dict[str, object]]:
    downloads = expanded_path(config.get("downloads_root"), "downloads root")
    staging = expanded_path(config.get("staging_root"), "staging root")
    local_free = min(shutil.disk_usage(downloads).free, shutil.disk_usage(staging).free)
    remote_free = remote_capacity(config)
    working = allocated_bytes(downloads) + allocated_bytes(staging)
    limits = config.get("limits", {})
    if not isinstance(limits, dict):
        raise OperationError("policy limits are invalid")
    healthy = (
        local_free >= int(limits.get("min_local_free_gib", 100)) * 1024**3
        and remote_free >= int(limits.get("min_remote_free_gib", 200)) * 1024**3
        and working <= int(limits.get("max_working_set_gib", 50)) * 1024**3
    )
    now = int(time.time())
    return (
        {
            "local_free_bytes": local_free,
            "observed_at_epoch": now,
            "remote_free_bytes": remote_free,
            "status": "ok" if healthy else "blocked",
            "working_set_bytes": working,
        },
        {
            "observed_at_epoch": now,
            "route": "vless",
            "status": "ok" if vless_healthy(config) else "degraded",
        },
    )


def atomic_json(path: Path, value: dict[str, object]) -> None:
    if path.parent.is_symlink() or not path.parent.is_dir():
        raise OperationError("policy evidence parent is missing or unsafe")
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    if path.is_symlink() or temporary.exists() or temporary.is_symlink():
        raise OperationError("policy evidence destination is unsafe")
    temporary.write_text(
        json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    temporary.chmod(0o600)
    temporary.replace(path)


def main() -> int:
    parser = argparse.ArgumentParser(description="Audiobook capacity and VLESS policy")
    parser.add_argument("--config", required=True, type=Path)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("status")
    run = commands.add_parser("run")
    run.add_argument("--execute", action="store_true")
    arguments = parser.parse_args()
    if arguments.command == "run" and not arguments.execute:
        print("run requires --execute", file=sys.stderr)
        return 2
    try:
        config = load_config(arguments.config)
        capacity, route = snapshot(config)
        if arguments.command == "run":
            atomic_json(
                expanded_path(config.get("capacity_evidence_file"), "capacity evidence"),
                capacity,
            )
            atomic_json(
                expanded_path(config.get("vless_evidence_file"), "VLESS evidence"),
                route,
            )
        print(json.dumps({"capacity": capacity, "vless": route}, sort_keys=True))
        return 0 if capacity["status"] == "ok" else 1
    except (OSError, TypeError, ValueError, OperationError) as error:
        print(
            json.dumps(
                {"event": "policy_error", "reason": str(error)},
                separators=(",", ":"),
            ),
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
