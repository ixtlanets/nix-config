#!/usr/bin/env python3
"""Deliver durable audiobook outcomes without involving an LLM."""

from __future__ import annotations

import argparse
import ipaddress
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from typing import NoReturn
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener


PROTOCOL_VERSION = "2026-07-28"
MAX_RESPONSE_BYTES = 1024 * 1024
MAX_REASON_CHARS = 1000
OUTCOME_LABELS = {
    "verified": "Аудиокнига проверена и опубликована",
    "needs_input": "Нужно ваше решение по аудиокниге",
    "failed": "Обработка аудиокниги завершилась ошибкой",
}
ENV_NAME = re.compile(r"^[A-Z_][A-Z0-9_]*$")
TELEGRAM_TARGET = re.compile(r"^telegram:-?[1-9][0-9]*(?::[1-9][0-9]*)?$")
PRIVATE_NETWORKS = tuple(
    ipaddress.ip_network(network)
    for network in (
        "10.0.0.0/8",
        "100.64.0.0/10",
        "127.0.0.0/8",
        "169.254.0.0/16",
        "172.16.0.0/12",
        "192.168.0.0/16",
        "::1/128",
        "fc00::/7",
        "fe80::/10",
    )
)


class PollerError(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *_args: object, **_kwargs: object) -> None:
        return None


def fail(code: str) -> NoReturn:
    raise PollerError(code)


def private_mcp_url(value: object) -> str:
    if not isinstance(value, str):
        fail("private_mcp_url_required")
    parsed = urlsplit(value)
    if (
        parsed.scheme not in {"http", "https"}
        or parsed.path != "/mcp"
        or parsed.query
        or parsed.fragment
        or parsed.username
        or parsed.password
        or not parsed.hostname
    ):
        fail("private_mcp_url_required")
    try:
        address = ipaddress.ip_address(parsed.hostname)
    except ValueError:
        fail("private_mcp_url_required")
    if not any(address.version == network.version and address in network for network in PRIVATE_NETWORKS):
        fail("private_mcp_url_required")
    return value


def load_config(path: Path) -> dict[str, object]:
    try:
        payload = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        fail("invalid_config")
    if not isinstance(payload, dict):
        fail("invalid_config")
    required = {
        "mcp_url",
        "bearer_env",
        "cursor_file",
        "hermes_bin",
        "allowed_origins",
        "timeout_seconds",
        "page_size",
    }
    if set(payload) != required:
        fail("invalid_config")
    payload["mcp_url"] = private_mcp_url(payload["mcp_url"])
    env_name = payload["bearer_env"]
    if not isinstance(env_name, str) or not ENV_NAME.fullmatch(env_name):
        fail("invalid_config")
    origins = payload["allowed_origins"]
    if (
        not isinstance(origins, list)
        or not origins
        or any(not isinstance(item, str) or not TELEGRAM_TARGET.fullmatch(item) for item in origins)
        or len(set(origins)) != len(origins)
    ):
        fail("invalid_config")
    timeout = payload["timeout_seconds"]
    page_size = payload["page_size"]
    if not isinstance(timeout, int) or not 1 <= timeout <= 60:
        fail("invalid_config")
    if not isinstance(page_size, int) or not 1 <= page_size <= 100:
        fail("invalid_config")
    return payload


def read_cursor(path: Path) -> int:
    try:
        value = path.read_text().strip()
    except FileNotFoundError:
        return 0
    except OSError:
        fail("cursor_read_failed")
    if not value.isascii() or not value.isdigit():
        fail("invalid_cursor")
    return int(value)


def write_cursor(path: Path, value: int) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent, prefix=f".{path.name}.", delete=False
        ) as handle:
            temporary = Path(handle.name)
            os.chmod(temporary, 0o600)
            handle.write(f"{value}\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    except OSError:
        try:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
        except OSError:
            pass
        fail("cursor_write_failed")


def rpc(url: str, bearer: str, timeout: int, request_id: int, method: str, params: dict[str, object]) -> dict[str, object]:
    body = json.dumps(
        {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params},
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode()
    request = Request(
        url,
        data=body,
        headers={
            "Authorization": f"Bearer {bearer}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "MCP-Protocol-Version": PROTOCOL_VERSION,
        },
        method="POST",
    )
    try:
        with build_opener(NoRedirect).open(request, timeout=timeout) as response:
            raw = response.read(MAX_RESPONSE_BYTES + 1)
            if len(raw) > MAX_RESPONSE_BYTES:
                fail("mcp_response_too_large")
            payload = json.loads(raw)
    except HTTPError:
        fail("mcp_http_failed")
    except (URLError, TimeoutError, OSError):
        fail("mcp_unreachable")
    except (UnicodeDecodeError, json.JSONDecodeError):
        fail("invalid_mcp_response")
    if not isinstance(payload, dict) or payload.get("id") != request_id:
        fail("invalid_mcp_response")
    if "error" in payload:
        fail("mcp_rpc_failed")
    result = payload.get("result")
    if not isinstance(result, dict):
        fail("invalid_mcp_response")
    return result


def list_events(config: dict[str, object], bearer: str, cursor: int) -> list[dict[str, object]]:
    url = str(config["mcp_url"])
    timeout = int(config["timeout_seconds"])
    initialized = rpc(
        url,
        bearer,
        timeout,
        1,
        "initialize",
        {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {},
            "clientInfo": {"name": "audiobook-notifications", "version": "1.0"},
        },
    )
    if initialized.get("protocolVersion") != PROTOCOL_VERSION:
        fail("mcp_protocol_mismatch")
    called = rpc(
        url,
        bearer,
        timeout,
        2,
        "tools/call",
        {
            "name": "notification_list",
            "arguments": {"after_event_id": cursor, "limit": int(config["page_size"])},
        },
    )
    if called.get("isError") is not False:
        fail("notification_list_failed")
    output = called.get("structuredContent")
    if not isinstance(output, dict) or not isinstance(output.get("events"), list):
        fail("invalid_notification_page")
    events = output["events"]
    expected = cursor
    for event in events:
        if not isinstance(event, dict):
            fail("invalid_notification_event")
        event_id = event.get("event_id")
        if not isinstance(event_id, int) or isinstance(event_id, bool) or event_id <= expected:
            fail("invalid_notification_order")
        expected = event_id
    if output.get("cursor") != expected:
        fail("invalid_notification_cursor")
    return events


def clean_text(value: object) -> str:
    if not isinstance(value, str):
        fail("invalid_notification_event")
    return " ".join(value.split())[:MAX_REASON_CHARS]


def origin_allowed(origin: str, allowed_origins: object) -> bool:
    if not isinstance(allowed_origins, list):
        return False
    return any(
        origin == allowed
        or (isinstance(allowed, str) and allowed.count(":") == 1 and origin.startswith(f"{allowed}:"))
        for allowed in allowed_origins
    )


def deliver(config: dict[str, object], event: dict[str, object], bearer_env: str) -> None:
    event_id = event.get("event_id")
    task_id = clean_text(event.get("task_id"))
    kind = event.get("kind")
    origin = event.get("origin_conversation_id")
    if kind not in OUTCOME_LABELS or not isinstance(origin, str):
        fail("invalid_notification_event")
    raw_reason = event.get("reason")
    reason = None if raw_reason is None else clean_text(raw_reason)
    if kind != "verified" and not reason:
        fail("invalid_notification_event")
    if not origin_allowed(origin, config["allowed_origins"]):
        fail("origin_not_allowed")
    message = (
        f"{OUTCOME_LABELS[kind]} (event #{event_id}).\n"
        f"Задача: {task_id}."
    )
    if reason:
        message += f"\nРезультат: {reason}"
    child_env = os.environ.copy()
    child_env.pop(bearer_env, None)
    try:
        result = subprocess.run(
            [str(Path(str(config["hermes_bin"])).expanduser()), "send", "--to", origin, message],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=int(config["timeout_seconds"]),
            env=child_env,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        fail("delivery_failed")
    if result.returncode != 0:
        fail("delivery_failed")


def run(config_path: Path) -> None:
    config = load_config(config_path)
    bearer_env = str(config["bearer_env"])
    bearer = os.environ.get(bearer_env, "")
    if not bearer or len(bearer.encode()) > 4096:
        fail("bearer_unavailable")
    cursor_path = Path(str(config["cursor_file"])).expanduser()
    cursor = read_cursor(cursor_path)
    for _page in range(10):
        events = list_events(config, bearer, cursor)
        for event in events:
            deliver(config, event, bearer_env)
            cursor = int(event["event_id"])
            write_cursor(cursor_path, cursor)
        if len(events) < int(config["page_size"]):
            return
    fail("page_limit_reached")


def default_config_path() -> Path:
    profile = os.environ.get("HERMES_HOME", "").strip()
    return (
        Path(profile).expanduser() / "audiobook-notifications.json"
        if profile
        else Path.home() / ".hermes" / "audiobook-notifications.json"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default=default_config_path(), type=Path)
    args = parser.parse_args(argv)
    try:
        run(args.config)
    except PollerError as error:
        print(json.dumps({"event": "audiobook_notification_poll_failed", "code": error.code}), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
