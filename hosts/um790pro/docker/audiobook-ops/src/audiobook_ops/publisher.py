from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import stat
import subprocess
from typing import Callable, Protocol
import unicodedata

from audiobook_ops.interface import AudiobookOperations, OperationError
from audiobook_ops.validation import AUDIO_EXTENSIONS, AudioProbe


class RemotePublisher(Protocol):
    def capacity_bytes(self) -> int: ...

    def prepare(self, task_id: str) -> None: ...

    def transfer(self, task_id: str, source: Path) -> None: ...

    def verify(self, task_id: str, manifest: dict[str, object]) -> str: ...

    def promote(
        self, task_id: str, final_relative_path: str, manifest_id: str
    ) -> None: ...


def _manifest_id(manifest: list[dict[str, object]]) -> str:
    return hashlib.sha256(
        json.dumps(manifest, separators=(",", ":"), sort_keys=True).encode()
    ).hexdigest()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_segment(value: object) -> str:
    normalized = unicodedata.normalize("NFC", str(value))
    normalized = re.sub(r"[/\\\x00-\x1f\x7f]", " ", normalized)
    normalized = " ".join(normalized.split()).strip(" .")
    if not normalized or normalized in {".", ".."} or len(normalized.encode()) > 240:
        raise OperationError("publication path segment is invalid")
    return normalized


def final_relative_path(work: object) -> str:
    if not isinstance(work, dict):
        raise OperationError("publication work metadata is missing")
    authors = work.get("authors")
    series = work.get("series", [])
    if (
        not isinstance(authors, list)
        or not authors
        or not isinstance(series, list)
    ):
        raise OperationError("publication work metadata is invalid")
    author = _safe_segment(authors[0])
    title = _safe_segment(work.get("title"))
    if not series:
        return f"{author}/{title}"
    membership = series[0]
    if not isinstance(membership, dict):
        raise OperationError("publication series metadata is invalid")
    series_name = _safe_segment(membership.get("name"))
    sequence = _safe_segment(membership.get("sequence"))
    if sequence.isdigit():
        sequence = sequence.zfill(2)
    return f"{author}/{series_name}/{sequence} - {title}"


class PublicationValidator:
    """Revalidate immutable staging before any remote publication action."""

    def __init__(
        self,
        *,
        staging_root: Path,
        probe: AudioProbe,
        local_free_bytes: Callable[[], int],
        stability_hook: Callable[[], None],
        min_local_free_bytes: int = 100 * 1024**3,
        max_release_bytes: int = 20 * 1024**3,
    ) -> None:
        self._staging_root = staging_root
        self._probe = probe
        self._local_free_bytes = local_free_bytes
        self._stability_hook = stability_hook
        self._min_local_free_bytes = min_local_free_bytes
        self._max_release_bytes = max_release_bytes

    def validate(self, context: dict[str, object]) -> dict[str, object]:
        artifact = context.get("artifact")
        if not isinstance(artifact, dict):
            raise OperationError("publication has no validated artifact")
        staging_id = artifact.get("staging_id")
        if not isinstance(staging_id, str) or not re.fullmatch(
            r"[A-Za-z0-9][A-Za-z0-9._-]{0,199}", staging_id
        ):
            raise OperationError("publication staging identity is invalid")
        root = self._staging_root.resolve(strict=True)
        candidate = root / staging_id
        if candidate.is_symlink():
            raise OperationError("publication staging path is unsafe")
        source = candidate.resolve(strict=True)
        if source == root or root not in source.parents:
            raise OperationError("publication staging path is unsafe")
        first = self._build_manifest(source)
        self._stability_hook()
        second = self._build_manifest(source)
        stored = artifact.get("manifest")
        if first != second or first != stored:
            raise OperationError("publication manifest changed after validation")
        total_size = sum(int(entry["size_bytes"]) for entry in first)
        if total_size > self._max_release_bytes:
            raise OperationError("publication exceeds the release size limit")
        if self._local_free_bytes() < self._min_local_free_bytes:
            raise OperationError("local free-space reserve would be violated")
        manifest_id = _manifest_id(first)
        if artifact.get("manifest_id") != manifest_id:
            raise OperationError("validated manifest identity changed")
        relative_path = final_relative_path(context.get("work"))
        remote_manifest = {
            "task_id": artifact["task_id"],
            "final_relative_path": relative_path,
            "manifest_id": manifest_id,
            "audio_files": len(first),
            "total_size_bytes": total_size,
            "files": first,
        }
        return {
            "source": source,
            "final_relative_path": relative_path,
            "manifest_id": manifest_id,
            "manifest": first,
            "total_size_bytes": total_size,
            "remote_manifest": remote_manifest,
        }

    def _build_manifest(self, source: Path) -> list[dict[str, object]]:
        entries: list[dict[str, object]] = []
        for current_root, directory_names, file_names in os.walk(
            source, followlinks=False
        ):
            current = Path(current_root)
            for name in directory_names:
                if (current / name).is_symlink():
                    raise OperationError("symlink is forbidden in publication staging")
            for name in file_names:
                path = current / name
                metadata = path.lstat()
                if path.is_symlink() or not stat.S_ISREG(metadata.st_mode):
                    raise OperationError("non-regular publication content is forbidden")
                if path.suffix.casefold() not in AUDIO_EXTENSIONS:
                    raise OperationError("unsupported publication content")
                duration = self._probe.duration(path)
                if not isinstance(duration, (int, float)) or duration <= 0:
                    raise OperationError("ffprobe returned an invalid audio stream")
                entries.append(
                    {
                        "relative_path": path.relative_to(source).as_posix(),
                        "size_bytes": metadata.st_size,
                        "sha256": _sha256(path),
                        "duration_seconds": float(duration),
                    }
                )
        entries.sort(key=lambda entry: str(entry["relative_path"]))
        if not entries:
            raise OperationError("publication staging contains no supported audio")
        return entries


class PublicationCoordinator:
    def __init__(
        self,
        operations: AudiobookOperations,
        validator: PublicationValidator,
        remote: RemotePublisher,
        *,
        publisher_id: str,
        checkpoint_hook: Callable[[str], None] = lambda _status: None,
        min_remote_free_bytes: int = 200 * 1024**3,
    ) -> None:
        self._operations = operations
        self._validator = validator
        self._remote = remote
        self._publisher_id = publisher_id
        self._checkpoint_hook = checkpoint_hook
        self._min_remote_free_bytes = min_remote_free_bytes

    def reconcile_once(self) -> dict[str, object] | None:
        context = self._operations.claim_publication(self._publisher_id)
        if context is None:
            return None
        publication = context["publication"]
        publication_id = str(publication["publication_id"])
        plan = self._validator.validate(context)
        status = str(publication["status"])
        if status == "claimed":
            context = self._advance(
                publication_id,
                "claimed",
                "validated",
                {
                    "final_relative_path": plan["final_relative_path"],
                    "manifest_id": plan["manifest_id"],
                    "manifest": plan["manifest"],
                    "total_size_bytes": plan["total_size_bytes"],
                },
            )
            status = "validated"
        else:
            persisted = context["publication"]
            if any(
                persisted.get(key) != plan[key]
                for key in (
                    "final_relative_path",
                    "manifest_id",
                    "manifest",
                    "total_size_bytes",
                )
            ):
                raise OperationError("durable publication evidence changed")

        if status in {
            "validated",
            "prepared",
            "transferred",
            "remote_verified",
        }:
            if (
                self._remote.capacity_bytes() - int(plan["total_size_bytes"])
                < self._min_remote_free_bytes
            ):
                raise OperationError("remote free-space reserve would be violated")
        task_id = str(context["task"]["task_id"])
        if status == "validated":
            self._remote.prepare(task_id)
            context = self._advance(publication_id, "validated", "prepared")
            status = "prepared"
        if status == "prepared":
            self._remote.transfer(task_id, plan["source"])
            context = self._advance(publication_id, "prepared", "transferred")
            status = "transferred"
        if status == "transferred":
            remote_manifest_id = self._remote.verify(
                task_id, plan["remote_manifest"]
            )
            context = self._advance(
                publication_id,
                "transferred",
                "remote_verified",
                {"remote_manifest_id": remote_manifest_id},
            )
            status = "remote_verified"
        if status == "remote_verified":
            self._remote.promote(
                task_id,
                str(plan["final_relative_path"]),
                str(plan["manifest_id"]),
            )
            context = self._advance(
                publication_id, "remote_verified", "promoted"
            )
            status = "promoted"
        if status == "promoted":
            context = self._advance(publication_id, "promoted", "acknowledged")
        return context

    def _advance(
        self,
        publication_id: str,
        expected_status: str,
        new_status: str,
        evidence: dict[str, object] | None = None,
    ) -> dict[str, object]:
        context = self._operations.advance_publication(
            publication_id, expected_status, new_status, evidence
        )
        self._checkpoint_hook(new_status)
        return context


class SSHRemotePublisher:
    """Dedicated-key SSH transport constrained by the Moscow forced command."""

    def __init__(
        self,
        *,
        remote_host: str,
        identity_file: Path,
        known_hosts_file: Path,
        ssh_bin: str = "ssh",
        rsync_bin: str = "rsync",
    ) -> None:
        if not remote_host or not identity_file.is_file() or not known_hosts_file.is_file():
            raise OperationError("publisher SSH configuration is incomplete")
        self._remote_host = remote_host
        self._identity_file = identity_file
        self._known_hosts_file = known_hosts_file
        self._ssh_bin = ssh_bin
        self._rsync_bin = rsync_bin

    def _ssh(self) -> list[str]:
        return [
            self._ssh_bin,
            "-T",
            "-i",
            str(self._identity_file),
            "-o",
            "BatchMode=yes",
            "-o",
            "ClearAllForwardings=yes",
            "-o",
            "StrictHostKeyChecking=yes",
            "-o",
            f"UserKnownHostsFile={self._known_hosts_file}",
            "-o",
            "UpdateHostKeys=no",
            self._remote_host,
        ]

    def _call(self, arguments: list[str], stdin: str | None = None) -> str:
        result = subprocess.run(
            [*self._ssh(), shlex.join(arguments)],
            check=False,
            capture_output=True,
            input=stdin,
            text=True,
            timeout=1800,
        )
        if result.returncode != 0:
            raise OperationError(f"remote publisher {arguments[0]} failed")
        return result.stdout

    def capacity_bytes(self) -> int:
        try:
            payload = json.loads(self._call(["capacity"]))
            free_bytes = int(payload["free_bytes"])
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
            raise OperationError("remote publisher capacity is invalid") from error
        if free_bytes < 0:
            raise OperationError("remote publisher capacity is invalid")
        return free_bytes

    def prepare(self, task_id: str) -> None:
        self._call(["prepare", task_id])

    def transfer(self, task_id: str, source: Path) -> None:
        identity = shlex.quote(str(self._identity_file))
        known_hosts = shlex.quote(str(self._known_hosts_file))
        remote_shell = (
            f"{shlex.quote(self._ssh_bin)} -T -i {identity} -o BatchMode=yes "
            "-o ClearAllForwardings=yes -o StrictHostKeyChecking=yes "
            f"-o UserKnownHostsFile={known_hosts} -o UpdateHostKeys=no"
        )
        result = subprocess.run(
            [
                self._rsync_bin,
                "--archive",
                "--delete",
                "--chmod=D2775,F0664",
                "--rsh",
                remote_shell,
                "--rsync-path",
                f"rsync-receive {task_id}",
                f"{source}/",
                f"{self._remote_host}:/",
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=1800,
        )
        if result.returncode != 0:
            raise OperationError("publisher rsync failed")

    def verify(self, task_id: str, manifest: dict[str, object]) -> str:
        try:
            payload = json.loads(
                self._call(
                    ["verify", task_id],
                    json.dumps(manifest, ensure_ascii=False, sort_keys=True),
                )
            )
        except json.JSONDecodeError as error:
            raise OperationError("remote publisher verification is invalid") from error
        if payload.get("verified") is not True or not re.fullmatch(
            r"[0-9a-f]{64}", str(payload.get("manifest_id", ""))
        ):
            raise OperationError("remote publisher verification is invalid")
        return str(payload["manifest_id"])

    def promote(
        self, task_id: str, final_relative_path: str, manifest_id: str
    ) -> None:
        try:
            payload = json.loads(
                self._call(["promote", task_id, final_relative_path, manifest_id])
            )
        except json.JSONDecodeError as error:
            raise OperationError("remote publisher promotion is invalid") from error
        if payload.get("promoted") is not True:
            raise OperationError("remote publisher promotion is invalid")
