from __future__ import annotations

import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import stat

from audiobook_ops.interface import AudiobookOperations, OperationError


def _json_object(path: Path, maximum_bytes: int) -> tuple[dict[str, object], bytes]:
    if path.is_symlink() or not path.is_file():
        raise OperationError("legacy migration input is unsafe")
    data = path.read_bytes()
    if not data or len(data) > maximum_bytes:
        raise OperationError("legacy migration input has an invalid size")
    try:
        value = json.loads(data)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise OperationError("legacy migration input is invalid JSON") from error
    if not isinstance(value, dict):
        raise OperationError("legacy migration input must be an object")
    return value, data


def _safe_legacy_path(value: object) -> str:
    if not isinstance(value, str) or not value or "\\" in value:
        raise OperationError("legacy final path is invalid")
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise OperationError("legacy final path is invalid")
    return value


def _validate_manifest(value: object) -> tuple[dict[str, object], int, int]:
    if not isinstance(value, dict) or set(value) != {
        "audio_files",
        "files",
        "manifest_id",
    }:
        raise OperationError("legacy manifest shape is invalid")
    files = value["files"]
    if not isinstance(files, list) or not files:
        raise OperationError("legacy manifest has no files")
    seen: set[str] = set()
    total = 0
    audio_files = 0
    for entry in files:
        if not isinstance(entry, dict) or set(entry) not in (
            {"duration", "path", "sha256", "size"},
            {"path", "sha256", "size"},
        ):
            raise OperationError("legacy manifest entry is invalid")
        relative = _safe_legacy_path(entry["path"])
        if relative in seen:
            raise OperationError("legacy manifest path is duplicated")
        seen.add(relative)
        size = entry["size"]
        if (
            not isinstance(size, int)
            or size < 0
            or not re.fullmatch(r"[0-9a-f]{64}", str(entry["sha256"]))
        ):
            raise OperationError("legacy manifest entry is invalid")
        suffix = PurePosixPath(relative).suffix.casefold()
        if suffix in {
            ".flac",
            ".m4a",
            ".m4b",
            ".mp3",
        }:
            duration = entry.get("duration")
            if not isinstance(duration, (int, float)) or duration <= 0:
                raise OperationError("legacy audio duration is invalid")
            audio_files += 1
        elif suffix not in {".jpg", ".jpeg", ".png", ".webp"} or "duration" in entry:
            raise OperationError("legacy manifest contains unsupported content")
        total += size
    body = {"audio_files": audio_files, "files": files}
    manifest_id = hashlib.sha256(
        json.dumps(body, separators=(",", ":"), sort_keys=True).encode()
    ).hexdigest()
    if value["audio_files"] != audio_files or value["manifest_id"] != manifest_id:
        raise OperationError("legacy manifest identity changed")
    return value, total, len(files)


def import_legacy_ledger(
    operations: AudiobookOperations, ledger_path: Path, mapping_path: Path
) -> dict[str, int]:
    ledger_metadata = ledger_path.lstat()
    if not stat.S_ISREG(ledger_metadata.st_mode) or ledger_metadata.st_mode & 0o222:
        raise OperationError("legacy ledger artifact must be read-only")
    ledger, ledger_bytes = _json_object(ledger_path, 64 * 1024 * 1024)
    mapping, _mapping_bytes = _json_object(mapping_path, 1024 * 1024)
    checksum = hashlib.sha256(ledger_bytes).hexdigest()
    if mapping.get("source_ledger_sha256") != checksum:
        raise OperationError("legacy ledger checksum does not match mapping")
    if set(ledger) != {"pending", "publications"}:
        raise OperationError("legacy ledger shape is invalid")
    if ledger["pending"] != {}:
        raise OperationError("legacy ledger still has pending publications")
    publications = ledger["publications"]
    active_items = mapping.get("active_items")
    if not isinstance(publications, dict) or not isinstance(active_items, dict):
        raise OperationError("legacy publication mapping is invalid")
    published_ids = {
        str(record_id)
        for record_id, record in publications.items()
        if isinstance(record, dict) and record.get("status", "published") == "published"
    }
    if set(active_items) != published_ids:
        raise OperationError("legacy active publication mapping is incomplete")

    normalized: list[dict[str, object]] = []
    for record_id, record in sorted(publications.items()):
        if not isinstance(record_id, str) or not isinstance(record, dict):
            raise OperationError("legacy publication record is invalid")
        if record.get("request_id") != record_id:
            raise OperationError("legacy publication identity changed")
        status_value = record.get("status", "published")
        if status_value not in {"published", "unpublished"}:
            raise OperationError("legacy publication status is invalid")
        manifest, total_size, file_count = _validate_manifest(record.get("manifest"))
        if (
            record.get("manifest_id") != manifest["manifest_id"]
            or record.get("bytes") != total_size
            or record.get("files") != file_count
        ):
            raise OperationError("legacy publication evidence changed")
        infohash = record.get("torrent_hash")
        if infohash is not None and not re.fullmatch(r"[0-9a-f]{40}", str(infohash)):
            raise OperationError("legacy publication infohash is invalid")
        published_at = record.get("published_at_epoch")
        confirmed_at = record.get("abs_confirmed_at_epoch")
        if not isinstance(published_at, int) or (
            confirmed_at is not None and not isinstance(confirmed_at, int)
        ):
            raise OperationError("legacy publication timestamps are invalid")
        exact = active_items.get(record_id)
        if status_value == "published":
            if (
                not isinstance(exact, dict)
                or set(exact) != {"library_id", "item_id", "media_id"}
                or any(not isinstance(value, str) or not value for value in exact.values())
            ):
                raise OperationError("legacy active publication mapping is invalid")
        else:
            exact = {"library_id": None, "item_id": None, "media_id": None}
        normalized.append(
            {
                "legacy_record_id": record_id,
                "status": status_value,
                "final_relative_path": _safe_legacy_path(
                    record.get("final_relative_path")
                ),
                "infohash": infohash,
                "manifest_id": manifest["manifest_id"],
                "manifest": manifest,
                "total_size_bytes": total_size,
                "file_count": file_count,
                "published_at_epoch": published_at,
                "abs_confirmed_at_epoch": confirmed_at,
                "abs_library_id": exact["library_id"],
                "abs_item_id": exact["item_id"],
                "abs_media_id": exact["media_id"],
                "legacy": record,
            }
        )
    return operations.import_legacy_publications(checksum, normalized)
