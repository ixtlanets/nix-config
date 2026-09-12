#!/usr/bin/env python3

import argparse
import base64
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any
from urllib.error import HTTPError
from urllib.request import Request, urlopen


class PolicyError(RuntimeError):
    pass


def load_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise PolicyError(f"expected a JSON object in {path}")
    return value


def atomic_write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(json.dumps(value, sort_keys=True, indent=2) + "\n")
    temporary.chmod(0o600)
    temporary.replace(path)


def read_secret(path: str) -> str:
    expanded = Path(os.path.expandvars(path))
    if expanded.is_symlink() or not expanded.is_file():
        raise PolicyError(f"secret file is missing or unsafe: {expanded}")
    value = expanded.read_text(encoding="utf-8").strip()
    if not value:
        raise PolicyError(f"secret file is empty: {expanded}")
    return value


def allocated_bytes(root: Path) -> int:
    canonical = root.resolve(strict=True)
    if canonical.is_symlink() or not canonical.is_dir():
        raise PolicyError(f"working-set root is unsafe: {root}")
    total = 0
    seen: set[tuple[int, int]] = set()
    for current_root, directory_names, file_names in os.walk(canonical, followlinks=False):
        current = Path(current_root)
        for name in directory_names:
            if (current / name).is_symlink():
                raise PolicyError(f"symlink in working-set root: {current / name}")
        for name in file_names:
            path = current / name
            if path.is_symlink() or not path.is_file():
                raise PolicyError(f"non-regular working-set file: {path}")
            stat = path.stat()
            identity = (stat.st_dev, stat.st_ino)
            if identity not in seen:
                total += stat.st_blocks * 512
                seen.add(identity)
    return total


def transmission_url(config: dict[str, Any]) -> str:
    configured = config.get("transmission_rpc_url")
    if isinstance(configured, str) and configured:
        return configured
    docker_bin = config.get("docker_bin", "docker")
    container = config.get("transmission_container", "readmeabook-transmission")
    result = subprocess.run(
        [
            docker_bin,
            "inspect",
            "--format",
            "{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}",
            container,
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    address = result.stdout.strip()
    if result.returncode != 0 or not address:
        raise PolicyError("cannot resolve the dedicated Transmission container address")
    return f"http://{address}:9091/transmission/rpc"


class TransmissionRpc:
    def __init__(self, url: str, username: str, password: str) -> None:
        self.url = url
        self.authorization = base64.b64encode(
            f"{username}:{password}".encode()
        ).decode()
        self.session_id: str | None = None

    def call(self, method: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
        payload = json.dumps(
            {"arguments": arguments or {}, "method": method}, separators=(",", ":")
        ).encode()
        for _attempt in range(2):
            headers = {
                "Authorization": f"Basic {self.authorization}",
                "Content-Type": "application/json",
                "Host": "transmission",
            }
            if self.session_id:
                headers["X-Transmission-Session-Id"] = self.session_id
            request = Request(self.url, data=payload, headers=headers, method="POST")
            try:
                with urlopen(request, timeout=15) as response:
                    result = json.load(response)
            except HTTPError as error:
                if error.code == 409:
                    self.session_id = error.headers.get("X-Transmission-Session-Id")
                    if self.session_id:
                        continue
                raise PolicyError(f"Transmission RPC HTTP error: {error.code}") from error
            if not isinstance(result, dict) or result.get("result") != "success":
                raise PolicyError("Transmission RPC returned an error")
            returned = result.get("arguments", {})
            if not isinstance(returned, dict):
                raise PolicyError("Transmission RPC returned invalid arguments")
            return returned
        raise PolicyError("Transmission RPC session negotiation failed")


def torrent_list(rpc: TransmissionRpc) -> list[dict[str, Any]]:
    response = rpc.call(
        "torrent-get",
        {
            "fields": [
                "addedDate",
                "doneDate",
                "hashString",
                "id",
                "leftUntilDone",
                "name",
                "status",
                "uploadRatio",
            ]
        },
    )
    torrents = response.get("torrents")
    if not isinstance(torrents, list) or not all(
        isinstance(torrent, dict) for torrent in torrents
    ):
        raise PolicyError("Transmission RPC returned an invalid torrent list")
    return torrents


def published_torrent_hashes(state_dir: Path) -> tuple[dict[str, Any], set[str]]:
    ledger_path = state_dir / "ledger.json"
    ledger: dict[str, Any] = {"pending": {}, "publications": {}}
    if ledger_path.exists():
        ledger.update(load_json(ledger_path))
    hashes = {
        str(publication["torrent_hash"]).lower()
        for publication in ledger.get("publications", {}).values()
        if isinstance(publication, dict)
        and publication.get("status", "published") == "published"
        and isinstance(publication.get("torrent_hash"), str)
        and "torrent_source_removed_at_epoch" not in publication
    }
    return ledger, hashes


def build_plan(config: dict[str, Any], rpc: TransmissionRpc) -> tuple[dict[str, Any], dict[str, Any]]:
    downloads_root = Path(config["downloads_root"])
    staging_root = Path(config["staging_root"])
    working_bytes = allocated_bytes(downloads_root) + allocated_bytes(staging_root)
    maximum = int(config.get("max_working_set_gib", 50)) * 1024**3
    minimum_free = int(config.get("min_local_free_gib", 100)) * 1024**3
    free_bytes = min(
        shutil.disk_usage(downloads_root).free,
        shutil.disk_usage(staging_root).free,
    )
    state_dir = Path(config["publisher_state_dir"])
    publisher_blocked = (state_dir / "blocked.json").exists()
    torrents = torrent_list(rpc)
    active = sorted(
        [torrent for torrent in torrents if torrent.get("status") in {3, 4}],
        key=lambda torrent: (int(torrent.get("addedDate", 0)), int(torrent.get("id", 0))),
    )
    remaining_bytes = sum(int(torrent.get("leftUntilDone", 0) or 0) for torrent in active)
    projected_working_bytes = working_bytes + remaining_bytes
    capacity_blocked = projected_working_bytes > maximum or free_bytes < minimum_free
    concurrency_blocked = len(active) > 1
    if publisher_blocked or capacity_blocked or concurrency_blocked:
        pause_hashes = [str(torrent.get("hashString", "")) for torrent in active]
    else:
        pause_hashes = [str(torrent.get("hashString", "")) for torrent in active[1:]]
    pause_hashes = [torrent_hash for torrent_hash in pause_hashes if torrent_hash]

    ledger, allowed_hashes = published_torrent_hashes(state_dir)
    ratio_limit = float(config.get("seed_ratio", 1.0))
    age_cutoff = time.time() - int(config.get("seed_max_days", 7)) * 86400
    remove_hashes: list[str] = []
    for torrent in torrents:
        torrent_hash = str(torrent.get("hashString", "")).lower()
        if torrent_hash not in allowed_hashes:
            continue
        done_date = int(torrent.get("doneDate", 0) or 0)
        ratio = float(torrent.get("uploadRatio", 0.0) or 0.0)
        if ratio >= ratio_limit or (done_date > 0 and done_date <= age_cutoff):
            remove_hashes.append(torrent_hash)

    return (
        {
            "active_downloads": len(active),
            "capacity_blocked": capacity_blocked,
            "concurrency_blocked": concurrency_blocked,
            "free_bytes": free_bytes,
            "pause_hashes": sorted(set(pause_hashes)),
            "projected_working_set_bytes": projected_working_bytes,
            "publisher_blocked": publisher_blocked,
            "remove_hashes": sorted(set(remove_hashes)),
            "working_set_bytes": working_bytes,
        },
        ledger,
    )


def execute_plan(
    config: dict[str, Any], rpc: TransmissionRpc, plan: dict[str, Any], ledger: dict[str, Any]
) -> None:
    if plan["capacity_blocked"] or plan["concurrency_blocked"]:
        reasons = []
        if plan["capacity_blocked"]:
            reasons.append("working-set capacity or local free-space reserve violated")
        if plan["concurrency_blocked"]:
            reasons.append("more than one active dedicated Transmission download")
        atomic_write_json(
            Path(config["publisher_state_dir"]) / "blocked.json",
            {"reason": "; ".join(reasons)},
        )
    if plan["pause_hashes"]:
        rpc.call("torrent-stop", {"ids": plan["pause_hashes"]})
    if plan["remove_hashes"]:
        rpc.call(
            "torrent-remove",
            {"delete-local-data": True, "ids": plan["remove_hashes"]},
        )
        removed = set(plan["remove_hashes"])
        now = int(time.time())
        for publication in ledger.get("publications", {}).values():
            if (
                isinstance(publication, dict)
                and str(publication.get("torrent_hash", "")).lower() in removed
            ):
                publication["torrent_source_removed_at_epoch"] = now
        atomic_write_json(Path(config["publisher_state_dir"]) / "ledger.json", ledger)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Guarded dedicated Transmission policy")
    parser.add_argument("--config", required=True, type=Path)
    commands = parser.add_subparsers(dest="command", required=True)
    status = commands.add_parser("status")
    status.add_argument("--json", action="store_true", dest="as_json")
    run = commands.add_parser("run")
    run.add_argument("--execute", action="store_true")
    run.add_argument("--json", action="store_true", dest="as_json")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.command == "run" and not args.execute:
        print("run requires --execute", file=sys.stderr)
        return 2
    config: dict[str, Any] | None = None
    try:
        config = load_json(args.config)
        rpc = TransmissionRpc(
            transmission_url(config),
            str(config.get("transmission_username", "readmeabook")),
            read_secret(config["transmission_password_file"]),
        )
        plan, ledger = build_plan(config, rpc)
        if args.command == "run":
            execute_plan(config, rpc, plan, ledger)
    except (OSError, ValueError, PolicyError) as error:
        if args.command == "run" and config is not None:
            try:
                atomic_write_json(
                    Path(config["publisher_state_dir"]) / "blocked.json",
                    {"reason": f"torrent policy failure: {error}"},
                )
            except (KeyError, OSError):
                pass
        print(f"torrent policy error: {error}", file=sys.stderr)
        return 1
    if getattr(args, "as_json", False):
        print(json.dumps(plan, sort_keys=True))
    else:
        for key, value in plan.items():
            print(f"{key}: {value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
