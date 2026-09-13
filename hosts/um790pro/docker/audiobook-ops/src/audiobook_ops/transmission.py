from __future__ import annotations

import base64
import json
from pathlib import PurePosixPath
import re
from typing import Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlparse
from urllib.request import Request, urlopen

from audiobook_ops.interface import OperationError


TRANSMISSION_ACTIVE = frozenset({3, 4})
TRANSMISSION_CHECKING = frozenset({1, 2})
TRANSMISSION_COMPLETE = frozenset({5, 6})


class TransmissionRPC(Protocol):
    def call(
        self, method: str, arguments: dict[str, object]
    ) -> dict[str, object]: ...


class TransmissionHTTPRPC:
    """Bounded Transmission JSON-RPC transport with session negotiation."""

    def __init__(self, url: str, username: str, password: str) -> None:
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise OperationError("invalid Transmission address")
        if not username or not password:
            raise OperationError("Transmission credentials are required")
        self._url = url
        self._authorization = base64.b64encode(
            f"{username}:{password}".encode()
        ).decode()
        self._session_id: str | None = None

    def call(
        self, method: str, arguments: dict[str, object]
    ) -> dict[str, object]:
        if not re.fullmatch(r"[a-z][a-z-]{0,63}", method):
            raise OperationError("invalid Transmission method")
        payload = json.dumps(
            {"arguments": arguments, "method": method}, separators=(",", ":")
        ).encode()
        for _attempt in range(2):
            headers = {
                "Authorization": f"Basic {self._authorization}",
                "Content-Type": "application/json",
            }
            if self._session_id is not None:
                headers["X-Transmission-Session-Id"] = self._session_id
            request = Request(self._url, data=payload, headers=headers, method="POST")
            try:
                with urlopen(request, timeout=15) as response:
                    raw = response.read(2 * 1024 * 1024 + 1)
            except HTTPError as error:
                try:
                    if error.code == 409:
                        self._session_id = error.headers.get(
                            "X-Transmission-Session-Id"
                        )
                        if self._session_id:
                            continue
                finally:
                    error.close()
                raise OperationError("Transmission RPC request failed") from error
            except (URLError, TimeoutError) as error:
                raise OperationError("Transmission RPC request failed") from error
            if len(raw) > 2 * 1024 * 1024:
                raise OperationError("Transmission RPC response exceeds the size limit")
            try:
                result = json.loads(raw)
            except json.JSONDecodeError as error:
                raise OperationError("Transmission RPC returned invalid JSON") from error
            if not isinstance(result, dict) or result.get("result") != "success":
                raise OperationError("Transmission RPC returned an error")
            returned = result.get("arguments", {})
            if not isinstance(returned, dict):
                raise OperationError("Transmission RPC returned invalid arguments")
            return returned
        raise OperationError("Transmission RPC session negotiation failed")


class TransmissionAdapter:
    """Own Transmission semantics without exposing its generic RPC interface."""

    def __init__(self, rpc: TransmissionRPC, *, download_dir: str) -> None:
        if not download_dir.startswith("/"):
            raise OperationError("Transmission download directory must be absolute")
        self._rpc = rpc
        self._download_dir = download_dir.rstrip("/")

    def submit(
        self, resolution: dict[str, object], idempotency_key: str
    ) -> str:
        label = self._label(idempotency_key)
        existing = self._find_by_label(label)
        if existing is not None:
            return existing
        source = self._safe_source(resolution)
        response = self._rpc.call(
            "torrent-add",
            {
                "download-dir": self._download_dir,
                "filename": source,
                "labels": [label],
                "paused": False,
            },
        )
        added = response.get("torrent-added") or response.get("torrent-duplicate")
        if not isinstance(added, dict):
            raise OperationError("Transmission did not acknowledge the acquisition")
        return self._hash(added.get("hashString"))

    def find(self, idempotency_key: str) -> str | None:
        return self._find_by_label(self._label(idempotency_key))

    def observe(self, torrent_hash: str) -> dict[str, object]:
        identity = self._hash(torrent_hash)
        matches = [
            torrent
            for torrent in self._torrents()
            if str(torrent.get("hashString", "")).lower() == identity
        ]
        if len(matches) != 1:
            raise OperationError("Transmission acquisition identity is missing or ambiguous")
        torrent = matches[0]
        status_code = torrent.get("status")
        if int(torrent.get("error", 0) or 0) != 0:
            status = "error"
        elif torrent.get("isFinished") is True or float(
            torrent.get("percentDone", 0.0) or 0.0
        ) >= 1.0:
            status = "complete"
        elif status_code in TRANSMISSION_ACTIVE:
            status = "downloading"
        elif status_code in TRANSMISSION_CHECKING:
            status = "checking"
        elif status_code in TRANSMISSION_COMPLETE:
            status = "complete"
        else:
            status = "stopped"
        download_dir = str(torrent.get("downloadDir", ""))
        name = str(torrent.get("name", ""))
        if (
            not download_dir.startswith("/")
            or not name
            or name in {".", ".."}
            or PurePosixPath(name).name != name
        ):
            raise OperationError("Transmission returned an unsafe download identity")
        return {
            "torrent_hash": identity,
            "status": status,
            "percent_done": float(torrent.get("percentDone", 0.0) or 0.0),
            "left_bytes": max(0, int(torrent.get("leftUntilDone", 0) or 0)),
            "rate_download": max(0, int(torrent.get("rateDownload", 0) or 0)),
            "activity_at_epoch": max(0, int(torrent.get("activityDate", 0) or 0)),
            "download_root": f"{download_dir.rstrip('/')}/{name}",
            "error": "transmission-error" if status == "error" else None,
        }

    def stop(self, torrent_hash: str) -> None:
        self._rpc.call("torrent-stop", {"ids": [self._hash(torrent_hash)]})

    def remove(self, torrent_hash: str) -> None:
        self._rpc.call(
            "torrent-remove",
            {"delete-local-data": True, "ids": [self._hash(torrent_hash)]},
        )

    def _find_by_label(self, label: str) -> str | None:
        matches = [
            self._hash(torrent.get("hashString"))
            for torrent in self._torrents()
            if label in torrent.get("labels", [])
        ]
        if len(matches) > 1:
            raise OperationError("Transmission idempotency identity is ambiguous")
        return matches[0] if matches else None

    def _torrents(self) -> list[dict[str, object]]:
        response = self._rpc.call(
            "torrent-get",
            {
                "fields": [
                    "activityDate",
                    "downloadDir",
                    "error",
                    "errorString",
                    "hashString",
                    "id",
                    "isFinished",
                    "labels",
                    "leftUntilDone",
                    "name",
                    "percentDone",
                    "rateDownload",
                    "status",
                ]
            },
        )
        torrents = response.get("torrents")
        if not isinstance(torrents, list) or any(
            not isinstance(torrent, dict) for torrent in torrents
        ):
            raise OperationError("Transmission returned an invalid torrent list")
        return torrents

    @staticmethod
    def _label(idempotency_key: str) -> str:
        if (
            not isinstance(idempotency_key, str)
            or not 1 <= len(idempotency_key) <= 160
            or not re.fullmatch(r"[A-Za-z0-9._:-]+", idempotency_key)
        ):
            raise OperationError("invalid Transmission idempotency key")
        return f"audiobook-ops:{idempotency_key}"

    @staticmethod
    def _hash(value: object) -> str:
        if not isinstance(value, str) or not re.fullmatch(r"[0-9a-fA-F]{40}", value):
            raise OperationError("invalid torrent identity")
        return value.lower()

    @staticmethod
    def _safe_source(resolution: dict[str, object]) -> str:
        magnet = resolution.get("magnet_uri")
        if isinstance(magnet, str):
            parsed = urlparse(magnet)
            xt = parse_qs(parsed.query).get("xt", [])
            if (
                parsed.scheme == "magnet"
                and len(xt) == 1
                and re.fullmatch(r"urn:btih:[0-9a-fA-F]{40}", xt[0])
            ):
                return magnet
        download_url = resolution.get("download_url")
        if isinstance(download_url, str):
            parsed = urlparse(download_url)
            if (
                parsed.scheme == "http"
                and parsed.hostname == "prowlarr"
                and parsed.port == 9696
                and (
                    parsed.path == "/download"
                    or parsed.path.startswith("/download/")
                )
            ):
                return download_url
        raise OperationError("unsafe release resolution")
