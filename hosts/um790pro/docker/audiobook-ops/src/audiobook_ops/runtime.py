from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import json
import os
from pathlib import Path
import sqlite3
import time
from typing import Any

from audiobook_ops.acquisition import (
    HTTPVlessRouteGuard,
    ProwlarrHTTPClient,
    ProwlarrReleaseAdapter,
)
from audiobook_ops.audiobookshelf import AudiobookshelfAdapter, AudiobookshelfHTTPClient
from audiobook_ops.cover import (
    CoverFetcher,
    PinnedHTTPSCoverHTTP,
    SubprocessImageDecoder,
    SystemResolver,
)
from audiobook_ops.interface import AudiobookOperations, OperationError, SCHEMA_VERSION
from audiobook_ops.mcp_adapter import MCPAdapter
from audiobook_ops.transmission import TransmissionHTTPRPC


def load_config(path: Path) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise OperationError("runtime configuration is missing or unsafe")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise OperationError("runtime configuration is invalid") from error
    if not isinstance(value, dict):
        raise OperationError("runtime configuration is invalid")
    return value


def expanded_path(value: object, name: str) -> Path:
    if not isinstance(value, str) or not value:
        raise OperationError(f"runtime {name} is invalid")
    return Path(os.path.expandvars(os.path.expanduser(value)))


def read_secret(value: object, name: str) -> str:
    path = expanded_path(value, name)
    if path.is_symlink() or not path.is_file():
        raise OperationError(f"runtime {name} is missing or unsafe")
    raw = path.read_bytes()
    if not raw or len(raw) > 64 * 1024:
        raise OperationError(f"runtime {name} has an invalid size")
    try:
        secret = raw.decode().strip()
    except UnicodeDecodeError as error:
        raise OperationError(f"runtime {name} is invalid") from error
    if not secret:
        raise OperationError(f"runtime {name} is empty")
    return secret


class RuntimeStatus:
    def __init__(
        self,
        *,
        database: Path,
        abs_http: AudiobookshelfHTTPClient,
        prowlarr_http: ProwlarrHTTPClient,
        transmission_rpc: TransmissionHTTPRPC,
        vless_evidence: Path,
        backup_evidence: Path,
        max_evidence_age_seconds: int = 900,
        max_backup_age_seconds: int = 36 * 60 * 60,
    ) -> None:
        self._database = database
        self._abs = abs_http
        self._prowlarr = prowlarr_http
        self._transmission = transmission_rpc
        self._vless_evidence = vless_evidence
        self._backup_evidence = backup_evidence
        self._max_evidence_age = max_evidence_age_seconds
        self._max_backup_age = max_backup_age_seconds

    def status(self) -> dict[str, object]:
        return {
            name: self.component(name)
            for name in (
                "core",
                "catalog",
                "external-search",
                "acquisition",
                "backup",
            )
        }

    def component(self, name: str) -> dict[str, object]:
        try:
            if name == "core":
                return self._core()
            if name == "catalog":
                payload = self._abs.json("GET", "/api/libraries")
                if not isinstance(payload, dict) or not isinstance(
                    payload.get("libraries"), list
                ):
                    raise OperationError("catalog health response is invalid")
                books = sum(
                    1
                    for library in payload["libraries"]
                    if isinstance(library, dict)
                    and library.get("mediaType") == "book"
                )
                return {"status": "ok", "book_libraries": books}
            if name == "vless-route":
                return self._vless()
            if name == "external-search":
                if self._vless()["status"] != "ok":
                    raise OperationError("VLESS route evidence is unavailable")
                self._prowlarr.health()
                return {"status": "ok"}
            if name == "acquisition":
                self._transmission.call("session-get", {})
                return {"status": "ok"}
            if name == "backup":
                return self._backup()
            raise OperationError("unknown health component")
        except (
            KeyError,
            OSError,
            UnicodeDecodeError,
            ValueError,
            json.JSONDecodeError,
            sqlite3.Error,
            OperationError,
        ):
            return {"status": "failed" if name == "core" else "degraded"}

    def _core(self) -> dict[str, object]:
        if self._database.is_symlink() or not self._database.is_file():
            raise OperationError("database is missing or unsafe")
        connection = sqlite3.connect(
            f"{self._database.resolve().as_uri()}?mode=ro", uri=True
        )
        try:
            integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
            version = int(
                connection.execute(
                    "SELECT COALESCE(MAX(version), 0) FROM schema_migrations"
                ).fetchone()[0]
            )
        finally:
            connection.close()
        if integrity != "ok" or version != SCHEMA_VERSION:
            raise OperationError("database health failed")
        return {"status": "ok", "schema_version": version}

    def _vless(self) -> dict[str, object]:
        if self._vless_evidence.is_symlink() or not self._vless_evidence.is_file():
            raise OperationError("VLESS evidence is missing")
        raw = self._vless_evidence.read_bytes()
        if not raw or len(raw) > 4096:
            raise OperationError("VLESS evidence is invalid")
        value = json.loads(raw)
        observed = value.get("observed_at_epoch") if isinstance(value, dict) else None
        now = time.time()
        if (
            not isinstance(value, dict)
            or value.get("status") != "ok"
            or value.get("route") != "vless"
            or not isinstance(observed, (int, float))
            or now - float(observed) > self._max_evidence_age
            or float(observed) > now + 60
        ):
            raise OperationError("VLESS evidence is stale or invalid")
        return {"status": "ok"}

    def _backup(self) -> dict[str, object]:
        if self._backup_evidence.is_symlink() or not self._backup_evidence.is_file():
            raise OperationError("backup evidence is unavailable")
        raw = self._backup_evidence.read_bytes()
        if not raw or len(raw) > 4096:
            raise OperationError("backup evidence is invalid")
        metadata = json.loads(raw)
        if (
            not isinstance(metadata, dict)
            or set(metadata) != {"created_at", "format", "status"}
            or metadata.get("format") != 1
            or metadata.get("status") != "ok"
        ):
            raise OperationError("backup evidence is invalid")
        created = datetime.strptime(str(metadata["created_at"]), "%Y%m%dT%H%M%SZ").replace(
            tzinfo=UTC
        )
        age = (datetime.now(UTC) - created).total_seconds()
        if age < -60 or age > self._max_backup_age:
            raise OperationError("latest backup is stale")
        return {"status": "ok", "created_at": metadata["created_at"]}


@dataclass
class Runtime:
    config: dict[str, Any]
    operations: AudiobookOperations
    adapter: MCPAdapter
    status: RuntimeStatus
    bearer: str

    def close(self) -> None:
        self.operations.close()


def build_runtime(config_path: Path) -> Runtime:
    config = load_config(config_path)
    abs_token = read_secret(config.get("abs_api_token_file"), "ABS API token")
    prowlarr_key = read_secret(
        config.get("prowlarr_api_key_file"), "Prowlarr API key"
    )
    transmission_password = read_secret(
        config.get("transmission_password_file"), "Transmission password"
    )
    bearer = read_secret(config.get("mcp_bearer_file"), "MCP bearer")
    route_guard = HTTPVlessRouteGuard(str(config.get("vless_route_health_url", "")))
    prowlarr_http = ProwlarrHTTPClient(str(config.get("prowlarr_url", "")), prowlarr_key)
    release_adapter = ProwlarrReleaseAdapter(prowlarr_http, route_guard)
    abs_http = AudiobookshelfHTTPClient(str(config.get("abs_url", "")), abs_token)
    cover_fetcher = CoverFetcher(
        PinnedHTTPSCoverHTTP(),
        SystemResolver(),
        SubprocessImageDecoder(
            str(config.get("ffprobe_bin", "/usr/bin/ffprobe")),
            str(config.get("ffmpeg_bin", "/usr/bin/ffmpeg")),
        ),
        route_guard,
    )
    catalog_adapter = AudiobookshelfAdapter(abs_http, cover_fetcher)
    transmission_rpc = TransmissionHTTPRPC(
        str(config.get("transmission_url", "")),
        str(config.get("transmission_username", "audiobook-ops")),
        transmission_password,
    )
    database = expanded_path(config.get("database_path"), "database path")
    status = RuntimeStatus(
        database=database,
        abs_http=abs_http,
        prowlarr_http=prowlarr_http,
        transmission_rpc=transmission_rpc,
        vless_evidence=expanded_path(
            config.get("vless_evidence_file"), "VLESS evidence file"
        ),
        backup_evidence=expanded_path(
            config.get("backup_evidence_file"), "backup evidence file"
        ),
    )
    operations = AudiobookOperations.open(
        database,
        release_adapter=release_adapter,
        catalog_adapter=catalog_adapter,
        status_adapter=status,
    )
    return Runtime(config, operations, MCPAdapter(operations), status, bearer)
