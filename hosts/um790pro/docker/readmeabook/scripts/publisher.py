#!/usr/bin/env python3

import argparse
import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import time
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen


class PublisherError(RuntimeError):
    pass


def load_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError(f"expected a JSON object in {path}")
    return value


def read_secret(path: str) -> str:
    expanded = os.path.expandvars(path)
    value = Path(expanded).read_text(encoding="utf-8").strip()
    if not value:
        raise PublisherError(f"empty secret file: {expanded}")
    return value


def http_get_json(url: str, token: str) -> Any:
    request = Request(url, headers={"Authorization": f"Bearer {token}"})
    with urlopen(request, timeout=15) as response:
        return json.load(response)


def api_url(base: str, path: str, query: dict[str, str] | None = None) -> str:
    url = f"{base.rstrip('/')}/{path.lstrip('/')}"
    if query:
        url = f"{url}?{urlencode(query)}"
    return url


def nested_values(value: Any, key: str) -> list[Any]:
    found: list[Any] = []
    if isinstance(value, dict):
        for child_key, child in value.items():
            if child_key.lower() == key.lower():
                found.append(child)
            found.extend(nested_values(child, key))
    elif isinstance(value, list):
        for child in value:
            found.extend(nested_values(child, key))
    return found


def canonical_descendant(path: Path, root: Path) -> Path:
    canonical_root = root.resolve(strict=True)
    canonical_path = path.resolve(strict=True)
    if canonical_path == canonical_root or canonical_root not in canonical_path.parents:
        raise PublisherError(f"path escapes staging root: {path}")
    return canonical_path


def rmab_staging_path(value: str, config: dict[str, Any]) -> Path:
    staging_root = Path(config["staging_root"])
    host_candidate = Path(value)
    if host_candidate.exists():
        return canonical_descendant(host_candidate, staging_root)

    media_root = PurePosixPath(str(config.get("rmab_media_root", "/media")))
    api_path = PurePosixPath(value)
    try:
        relative = api_path.relative_to(media_root)
    except ValueError as error:
        raise PublisherError(f"RMAB path escapes media root: {value}") from error
    return canonical_descendant(staging_root.joinpath(*relative.parts), staging_root)


def ffprobe_duration(ffprobe_bin: str, path: Path) -> float:
    result = subprocess.run(
        [
            ffprobe_bin,
            "-v",
            "quiet",
            "-print_format",
            "json",
            "-show_format",
            "--",
            str(path),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise PublisherError(f"ffprobe failed for {path}: {result.stderr.strip()}")
    try:
        duration = float(json.loads(result.stdout)["format"]["duration"])
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        raise PublisherError(f"ffprobe returned no duration for {path}") from error
    if duration <= 0:
        raise PublisherError(f"audio duration is not positive: {path}")
    return duration


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def build_manifest(book_dir: Path, allowed_extensions: set[str], ffprobe_bin: str) -> dict[str, Any]:
    files: list[dict[str, Any]] = []
    audio_count = 0
    forbidden_suffixes = {".part", ".partial", ".tmp"}

    for current_root, directory_names, file_names in os.walk(book_dir, followlinks=False):
        current = Path(current_root)
        for directory_name in directory_names:
            directory = current / directory_name
            if directory.is_symlink():
                raise PublisherError(f"symlink is forbidden: {directory}")
        for file_name in file_names:
            path = current / file_name
            if path.is_symlink() or not path.is_file():
                raise PublisherError(f"non-regular file is forbidden: {path}")
            suffix = path.suffix.lower()
            if suffix in forbidden_suffixes:
                raise PublisherError(f"incomplete file is forbidden: {path}")
            relative = path.relative_to(book_dir).as_posix()
            entry: dict[str, Any] = {
                "path": relative,
                "sha256": sha256_file(path),
                "size": path.stat().st_size,
            }
            if suffix in allowed_extensions:
                entry["duration"] = ffprobe_duration(ffprobe_bin, path)
                audio_count += 1
            files.append(entry)

    if audio_count == 0:
        raise PublisherError(f"no supported audio files in {book_dir}")
    files.sort(key=lambda entry: entry["path"].lower())
    body = {"audio_files": audio_count, "files": files}
    encoded = json.dumps(body, sort_keys=True, separators=(",", ":")).encode()
    return {**body, "manifest_id": hashlib.sha256(encoded).hexdigest()}


def completed_organize_job(
    detail: dict[str, Any], book_dir: Path, config: dict[str, Any]
) -> None:
    jobs = detail.get("jobs")
    if not isinstance(jobs, list):
        raise PublisherError("request detail has no jobs")
    for job in jobs:
        if not isinstance(job, dict):
            continue
        kind = job.get("type") or job.get("jobType") or job.get("name")
        if kind not in {"organize_files", "organize-files"}:
            continue
        result = job.get("result")
        if isinstance(result, str):
            try:
                result = json.loads(result)
            except json.JSONDecodeError:
                result = None
        target_path = result.get("targetPath") if isinstance(result, dict) else None
        if (
            job.get("status") == "completed"
            and isinstance(result, dict)
            and result.get("success") is True
            and not result.get("errors")
            and isinstance(target_path, str)
            and rmab_staging_path(target_path, config) == book_dir
        ):
            return
    raise PublisherError("no successful organize_files job matches the staging path")


def ensure_not_duplicate(abs_items: Any, asin: str | None, relative_path: str) -> None:
    if asin:
        wanted_asin = asin.casefold()
        for existing in nested_values(abs_items, "asin"):
            if isinstance(existing, str) and existing.casefold() == wanted_asin:
                raise PublisherError(f"duplicate ASIN already exists in Audiobookshelf: {asin}")
    wanted_suffix = f"/{relative_path}".casefold()
    for existing in nested_values(abs_items, "path"):
        if isinstance(existing, str) and existing.replace("\\", "/").casefold().endswith(wanted_suffix):
            raise PublisherError(f"duplicate path already exists in Audiobookshelf: {relative_path}")


def torrent_hash_from_detail(detail: dict[str, Any]) -> str | None:
    candidates: set[str] = set()
    for key in ("torrentHash", "torrent_hash"):
        for value in nested_values(detail, key):
            if isinstance(value, str) and re.fullmatch(r"[0-9a-fA-F]{40}", value):
                candidates.add(value.lower())
    if len(candidates) > 1:
        raise PublisherError("request detail contains multiple torrent hashes")
    return next(iter(candidates), None)


def run_once_dry(config: dict[str, Any]) -> dict[str, Any]:
    state_dir = Path(config["state_dir"])
    if (state_dir / "blocked.json").exists():
        reason = load_json(state_dir / "blocked.json").get("reason", "unknown")
        raise PublisherError(f"publisher is blocked: {reason}")

    local_free = shutil.disk_usage(Path(config["staging_root"])).free
    min_free = int(config.get("min_local_free_gib", 100)) * 1024**3
    if local_free < min_free:
        raise PublisherError("local free-space reserve would be violated")

    rmab_token = read_secret(config["rmab_token_file"])
    request_list = http_get_json(
        api_url(
            config["rmab_url"],
            "/api/requests",
            {"status": "downloaded", "type": "audiobook"},
        ),
        rmab_token,
    )
    if isinstance(request_list, dict):
        candidates = request_list.get("requests") or request_list.get("results") or []
    elif isinstance(request_list, list):
        candidates = request_list
    else:
        candidates = []

    ledger = load_ledger(state_dir)
    tombstoned_request_ids = {
        str(request_id)
        for request_id, publication in ledger["publications"].items()
        if isinstance(publication, dict) and publication.get("status") == "unpublished"
    }
    candidates = [
        candidate
        for candidate in candidates
        if not (
            isinstance(candidate, dict)
            and str(candidate.get("id")) in tombstoned_request_ids
        )
    ]
    published_request_ids = {
        str(request_id)
        for request_id, publication in ledger["publications"].items()
        if isinstance(publication, dict)
        and publication.get("status", "published") == "published"
    }
    new_candidates = [
        candidate
        for candidate in candidates
        if not (
            isinstance(candidate, dict)
            and str(candidate.get("id")) in published_request_ids
        )
    ]
    if new_candidates:
        candidates = new_candidates
    elif len(candidates) > 1:
        return {"action": "idle"}
    if not candidates:
        return {"action": "idle"}
    if len(candidates) > 1:
        raise PublisherError("more than one publish candidate is pending")
    request_id = str(candidates[0]["id"])
    detail_response = http_get_json(
        api_url(config["rmab_url"], f"/api/requests/{request_id}"), rmab_token
    )
    detail = (
        detail_response.get("request")
        if isinstance(detail_response, dict) and "request" in detail_response
        else detail_response
    )
    if not isinstance(detail, dict) or detail.get("status") != "downloaded":
        raise PublisherError("request is not downloaded")
    audiobook = detail.get("audiobook")
    if not isinstance(audiobook, dict) or audiobook.get("status") != "completed":
        raise PublisherError("audiobook is not completed")
    book_dir = rmab_staging_path(str(audiobook.get("filePath", "")), config)
    completed_organize_job(detail, book_dir, config)

    first = build_manifest(
        book_dir,
        {str(item).lower() for item in config["allowed_extensions"]},
        config.get("ffprobe_bin", "ffprobe"),
    )
    stability_seconds = int(config.get("stability_seconds", 30))
    if stability_seconds:
        time.sleep(stability_seconds)
    second = build_manifest(
        book_dir,
        {str(item).lower() for item in config["allowed_extensions"]},
        config.get("ffprobe_bin", "ffprobe"),
    )
    if first != second:
        raise PublisherError("staging manifest changed during stability interval")
    total_bytes = sum(int(item["size"]) for item in first["files"])
    max_bytes = int(config.get("max_release_gib", 20)) * 1024**3
    if total_bytes > max_bytes:
        raise PublisherError("release exceeds the configured size limit")

    relative_path = book_dir.relative_to(Path(config["staging_root"]).resolve()).as_posix()
    previous = ledger["publications"].get(request_id)
    if isinstance(previous, dict):
        if (
            previous.get("status", "published") == "published"
            and previous.get("manifest_id") == first["manifest_id"]
            and previous.get("final_relative_path") == relative_path
        ):
            return {
                "action": "already-published",
                "bytes": total_bytes,
                "files": len(first["files"]),
                "final_relative_path": relative_path,
                "manifest_id": first["manifest_id"],
                "request_id": request_id,
            }
        raise PublisherError("request ID already has a different publication record")

    abs_token = read_secret(config["abs_token_file"])
    abs_items = http_get_json(
        api_url(
            config["abs_url"],
            f"/api/libraries/{config['abs_library_id']}/items",
            {"limit": "0"},
        ),
        abs_token,
    )
    asin = audiobook.get("asin")
    ensure_not_duplicate(abs_items, str(asin) if asin else None, relative_path)

    return {
        "action": "would-publish",
        "bytes": total_bytes,
        "files": len(first["files"]),
        "final_relative_path": relative_path,
        "manifest": first,
        "manifest_id": first["manifest_id"],
        "request_id": request_id,
        "torrent_hash": torrent_hash_from_detail(detail),
        "book_dir": str(book_dir),
        "asin": str(asin) if asin else None,
    }


def publisher_status(config: dict[str, Any]) -> dict[str, Any]:
    state_dir = Path(config["state_dir"])
    blocked_path = state_dir / "blocked.json"
    ledger_path = state_dir / "ledger.json"

    blocked_reason = None
    if blocked_path.exists():
        blocked_reason = load_json(blocked_path).get("reason", "unknown")

    ledger: dict[str, Any] = {"publications": {}, "pending": {}}
    if ledger_path.exists():
        ledger.update(load_json(ledger_path))

    active_publications = [
        publication
        for publication in ledger.get("publications", {}).values()
        if isinstance(publication, dict)
        and publication.get("status", "published") == "published"
    ]
    return {
        "blocked": blocked_reason is not None,
        "blocked_reason": blocked_reason,
        "published": len(active_publications),
        "pending": len(ledger.get("pending", {})),
    }


def atomic_write_json(path: Path, value: Any, mode: int = 0o600) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    path.parent.chmod(0o700)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(json.dumps(value, sort_keys=True, indent=2) + "\n")
    temporary.chmod(mode)
    temporary.replace(path)


def load_ledger(state_dir: Path) -> dict[str, Any]:
    ledger: dict[str, Any] = {"pending": {}, "publications": {}}
    ledger_path = state_dir / "ledger.json"
    if ledger_path.exists():
        loaded = load_json(ledger_path)
        for key in ledger:
            if isinstance(loaded.get(key), dict):
                ledger[key] = loaded[key]
    return ledger


def ssh_command(config: dict[str, Any]) -> list[str]:
    known_hosts = os.path.expanduser(
        os.path.expandvars(config.get("known_hosts_file", "~/.ssh/known_hosts"))
    )
    return [
        config.get("ssh_bin", "ssh"),
        "-T",
        "-i",
        os.path.expandvars(config["publisher_identity_file"]),
        "-o",
        "BatchMode=yes",
        "-o",
        "ClearAllForwardings=yes",
        "-o",
        "StrictHostKeyChecking=yes",
        "-o",
        f"UserKnownHostsFile={known_hosts}",
        "-o",
        "UpdateHostKeys=no",
        config["remote_host"],
    ]


def remote_call(
    config: dict[str, Any], arguments: list[str], stdin: str | None = None
) -> str:
    result = subprocess.run(
        [*ssh_command(config), shlex.join(arguments)],
        check=False,
        capture_output=True,
        input=stdin,
        text=True,
    )
    if result.returncode != 0:
        raise PublisherError(
            f"remote {arguments[0]} failed: {result.stderr.strip() or result.stdout.strip()}"
        )
    return result.stdout


def rsync_book(config: dict[str, Any], plan: dict[str, Any]) -> None:
    identity = shlex.quote(os.path.expandvars(config["publisher_identity_file"]))
    known_hosts = shlex.quote(
        os.path.expanduser(
            os.path.expandvars(config.get("known_hosts_file", "~/.ssh/known_hosts"))
        )
    )
    ssh_bin = shlex.quote(config.get("ssh_bin", "ssh"))
    remote_shell = (
        f"{ssh_bin} -T -i {identity} -o BatchMode=yes "
        "-o ClearAllForwardings=yes -o StrictHostKeyChecking=yes "
        f"-o UserKnownHostsFile={known_hosts} -o UpdateHostKeys=no"
    )
    result = subprocess.run(
        [
            config.get("rsync_bin", "rsync"),
            "--archive",
            "--delete",
            "--chmod=D2775,F0664",
            "--rsh",
            remote_shell,
            "--rsync-path",
            f"rsync-receive {plan['request_id']}",
            f"{plan['book_dir']}/",
            f"{config['remote_host']}:/",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise PublisherError(f"rsync failed: {result.stderr.strip()}")


def execute_publication(config: dict[str, Any], plan: dict[str, Any]) -> dict[str, Any]:
    state_dir = Path(config["state_dir"])
    ledger = load_ledger(state_dir)
    request_id = plan["request_id"]
    if request_id in ledger["publications"]:
        previous = ledger["publications"][request_id]
        if previous.get("manifest_id") == plan["manifest_id"]:
            return {**plan, "action": "already-published"}
        raise PublisherError("request ID already has a different published manifest")

    try:
        capacity = json.loads(remote_call(config, ["capacity"]))
        remote_free = int(capacity["free_bytes"])
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        raise PublisherError("remote capacity returned invalid data") from error
    min_remote = int(config.get("min_remote_free_gib", 200)) * 1024**3
    if remote_free - int(plan["bytes"]) < min_remote:
        raise PublisherError("remote free-space reserve would be violated")

    publication = {
        "asin": plan.get("asin"),
        "bytes": plan["bytes"],
        "files": plan["files"],
        "final_relative_path": plan["final_relative_path"],
        "manifest": plan["manifest"],
        "manifest_id": plan["manifest_id"],
        "published_at_epoch": int(time.time()),
        "request_id": request_id,
        "staging_path": plan["book_dir"],
        "status": "published",
        "torrent_hash": plan.get("torrent_hash"),
    }
    ledger["pending"][request_id] = publication
    atomic_write_json(state_dir / "ledger.json", ledger)

    remote_call(config, ["prepare", request_id])
    rsync_book(config, plan)
    manifest = {
        **plan["manifest"],
        "final_relative_path": plan["final_relative_path"],
        "request_id": request_id,
    }
    try:
        verified = json.loads(
            remote_call(
                config, ["verify", request_id], json.dumps(manifest, sort_keys=True)
            )
        )
    except json.JSONDecodeError as error:
        raise PublisherError("remote verify returned invalid data") from error
    if verified.get("verified") is not True:
        raise PublisherError("remote verify did not confirm the manifest")
    remote_call(config, ["promote", request_id, plan["final_relative_path"]])

    ledger["pending"].pop(request_id, None)
    ledger["publications"][request_id] = publication
    atomic_write_json(state_dir / "ledger.json", ledger)
    return {**plan, "action": "published"}


def persist_block(config: dict[str, Any], reason: str) -> None:
    atomic_write_json(Path(config["state_dir"]) / "blocked.json", {"reason": reason})


def abs_library_items(config: dict[str, Any]) -> list[Any]:
    token = read_secret(config["abs_token_file"])
    payload = http_get_json(
        api_url(
            config["abs_url"],
            f"/api/libraries/{config['abs_library_id']}/items",
            {"limit": "0"},
        ),
        token,
    )
    if isinstance(payload, dict):
        items = payload.get("results") or payload.get("items") or []
    else:
        items = payload
    if not isinstance(items, list):
        raise PublisherError("Audiobookshelf returned an invalid item list")
    return items


def publication_seen_in_abs(publication: dict[str, Any], items: list[Any]) -> bool:
    relative = str(publication.get("final_relative_path", ""))
    wanted_path = f"/{relative}".casefold()
    wanted_asin = publication.get("asin")
    if isinstance(wanted_asin, str) and wanted_asin.startswith("manual:"):
        wanted_asin = None
    for item in items:
        paths = [
            value.replace("\\", "/").casefold()
            for value in nested_values(item, "path")
            if isinstance(value, str)
        ]
        if not any(path.endswith(wanted_path) for path in paths):
            continue
        if not wanted_asin:
            return True
        asins = [
            value.casefold()
            for value in nested_values(item, "asin")
            if isinstance(value, str)
        ]
        if str(wanted_asin).casefold() in asins:
            return True
    return False


def reconcile_publications(config: dict[str, Any]) -> None:
    state_dir = Path(config["state_dir"])
    ledger = load_ledger(state_dir)
    unconfirmed = [
        publication
        for publication in ledger["publications"].values()
        if publication.get("status", "published") == "published"
        and "abs_confirmed_at_epoch" not in publication
    ]
    if not unconfirmed:
        return
    items = abs_library_items(config)
    changed = False
    for publication in unconfirmed:
        if publication_seen_in_abs(publication, items):
            publication["abs_confirmed_at_epoch"] = int(time.time())
            changed = True
    if changed:
        atomic_write_json(state_dir / "ledger.json", ledger)


def published_record(ledger: dict[str, Any], manifest_id: str) -> dict[str, Any]:
    matches = [
        publication
        for publication in ledger["publications"].values()
        if publication.get("manifest_id") == manifest_id
        and publication.get("status", "published") == "published"
    ]
    if len(matches) != 1:
        raise PublisherError("manifest ID does not identify one published book")
    return matches[0]


def unpublish_plan(config: dict[str, Any], manifest_id: str) -> dict[str, Any]:
    ledger = load_ledger(Path(config["state_dir"]))
    return published_record(ledger, manifest_id)


def unpublish(config: dict[str, Any], manifest_id: str) -> dict[str, Any]:
    state_dir = Path(config["state_dir"])
    ledger = load_ledger(state_dir)
    publication = published_record(ledger, manifest_id)
    remote_call(
        config,
        [
            "unpublish",
            manifest_id,
            publication["final_relative_path"],
        ],
    )
    publication["status"] = "unpublished"
    atomic_write_json(state_dir / "ledger.json", ledger)
    return publication


def cleanup_staging(config: dict[str, Any], execute: bool) -> dict[str, Any]:
    state_dir = Path(config["state_dir"])
    ledger = load_ledger(state_dir)
    cutoff = time.time() - int(config.get("staging_retention_hours", 24)) * 60 * 60
    eligible: list[str] = []
    paths: dict[str, Path] = {}
    staging_root = Path(config["staging_root"])

    for request_id, publication in ledger["publications"].items():
        confirmed_at = publication.get("abs_confirmed_at_epoch")
        if publication.get("status", "published") != "published":
            continue
        if not isinstance(confirmed_at, (int, float)) or confirmed_at > cutoff:
            continue
        staging_path = publication.get("staging_path")
        if not isinstance(staging_path, str):
            continue
        try:
            path = canonical_descendant(Path(staging_path), staging_root)
        except (FileNotFoundError, PublisherError):
            continue
        if path.is_symlink() or not path.is_dir():
            continue
        eligible.append(request_id)
        paths[request_id] = path

    if execute:
        for request_id in eligible:
            shutil.rmtree(paths[request_id])
            publication = ledger["publications"][request_id]
            publication["staging_cleaned_at_epoch"] = int(time.time())
        if eligible:
            atomic_write_json(state_dir / "ledger.json", ledger)
    return {"eligible": eligible, "executed": execute}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Verified ReadMeABook publisher")
    parser.add_argument("--config", required=True, type=Path)
    commands = parser.add_subparsers(dest="command", required=True)

    status = commands.add_parser("status", help="show persistent publisher state")
    status.add_argument("--json", action="store_true", dest="as_json")

    acknowledge = commands.add_parser(
        "acknowledge", help="clear a persistent publisher block"
    )
    acknowledge.add_argument("--execute", action="store_true")

    run_once = commands.add_parser("run-once", help="validate one publish candidate")
    run_once.add_argument("--json", action="store_true", dest="as_json")
    run_once.add_argument("--execute", action="store_true")

    unpublish_command = commands.add_parser(
        "unpublish", help="remove one exactly identified published book"
    )
    unpublish_command.add_argument("manifest_id")
    unpublish_command.add_argument("--execute", action="store_true")

    cleanup = commands.add_parser("cleanup", help="remove confirmed expired staging")
    cleanup.add_argument("--execute", action="store_true")
    cleanup.add_argument("--json", action="store_true", dest="as_json")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    config = load_json(args.config)

    if args.command == "status":
        status = publisher_status(config)
        if args.as_json:
            print(json.dumps(status, sort_keys=True))
        else:
            print(f"blocked: {str(status['blocked']).lower()}")
            print(f"blocked_reason: {status['blocked_reason'] or '-'}")
            print(f"published: {status['published']}")
            print(f"pending: {status['pending']}")
        return 0

    if args.command == "acknowledge":
        if not args.execute:
            print("acknowledge requires --execute", file=sys.stderr)
            return 2
        blocked_path = Path(config["state_dir"]) / "blocked.json"
        blocked_path.unlink(missing_ok=True)
        print("publisher block cleared")
        return 0

    if args.command == "run-once":
        try:
            if args.execute:
                reconcile_publications(config)
            result = run_once_dry(config)
            if args.execute and result.get("action") == "would-publish":
                result = execute_publication(config, result)
        except (OSError, ValueError, PublisherError) as error:
            if args.execute:
                try:
                    blocked_path = Path(config["state_dir"]) / "blocked.json"
                    if not blocked_path.exists():
                        persist_block(config, str(error))
                except OSError as persist_error:
                    print(
                        f"publisher error: {error}; cannot persist block: {persist_error}",
                        file=sys.stderr,
                    )
                    return 1
            print(f"publisher error: {error}", file=sys.stderr)
            return 1
        if args.as_json:
            print(json.dumps(result, sort_keys=True))
        else:
            print(f"action: {result['action']}")
            if "request_id" in result:
                print(f"request_id: {result['request_id']}")
                print(f"manifest_id: {result['manifest_id']}")
        return 0

    if args.command == "unpublish":
        if not args.execute:
            try:
                publication = unpublish_plan(config, args.manifest_id)
            except (OSError, ValueError, PublisherError) as error:
                print(f"publisher error: {error}", file=sys.stderr)
                return 1
            print(f"manifest_id: {publication['manifest_id']}")
            print(f"would unpublish: {publication['final_relative_path']}")
            print("unpublish requires --execute", file=sys.stderr)
            return 2
        try:
            publication = unpublish(config, args.manifest_id)
        except (OSError, ValueError, PublisherError) as error:
            persist_block(config, str(error))
            print(f"publisher error: {error}", file=sys.stderr)
            return 1
        print(f"unpublished: {publication['final_relative_path']}")
        return 0

    if args.command == "cleanup":
        try:
            result = cleanup_staging(config, args.execute)
        except (OSError, ValueError, PublisherError) as error:
            print(f"publisher error: {error}", file=sys.stderr)
            return 1
        if args.as_json:
            print(json.dumps(result, sort_keys=True))
        else:
            action = "removed" if args.execute else "would remove"
            print(f"{action}: {len(result['eligible'])}")
        return 0

    raise AssertionError(f"unhandled command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
