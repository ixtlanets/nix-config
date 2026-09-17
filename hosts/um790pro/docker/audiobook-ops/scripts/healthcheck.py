#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from audiobook_ops.interface import OperationError
from audiobook_ops.runtime import load_config


def http_status(url: str) -> dict[str, object]:
    request = Request(url, headers={"Accept": "application/json"})
    try:
        response = urlopen(request, timeout=15)
    except HTTPError as error:
        response = error
    except (URLError, TimeoutError, ValueError) as error:
        raise OperationError("health endpoint is unavailable") from error
    try:
        raw = response.read(64 * 1024 + 1)
    finally:
        response.close()
    if len(raw) > 64 * 1024:
        raise OperationError("health response is oversized")
    try:
        value = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise OperationError("health response is invalid") from error
    if not isinstance(value, dict) or value.get("status") not in {
        "ok",
        "degraded",
        "failed",
    }:
        raise OperationError("health response is invalid")
    return {"status": value["status"]}


def container_status(
    docker_bin: str,
    name: str,
    *,
    attempts: int = 7,
    interval_seconds: float = 5.0,
) -> dict[str, object]:
    for attempt in range(attempts):
        result = subprocess.run(
            [
                docker_bin,
                "inspect",
                "--format",
                "{{.State.Running}}|{{if .State.Health}}{{.State.Health.Status}}{{end}}",
                name,
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
        state = result.stdout.strip()
        if result.returncode != 0 or not state.startswith("true|"):
            return {"status": "failed"}
        health = state.split("|", 1)[1]
        if health in {"", "healthy"}:
            return {"status": "ok"}
        if attempt + 1 < attempts:
            time.sleep(interval_seconds)
    return {"status": "failed"}


def publisher_status(config: dict[str, object]) -> dict[str, object]:
    command = config.get("publisher_status_command")
    if not isinstance(command, list) or any(not isinstance(value, str) for value in command):
        raise OperationError("publisher health command is invalid")
    result = subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
        timeout=60,
    )
    if result.returncode != 0:
        return {"status": "failed"}
    try:
        value = json.loads(result.stdout)
    except json.JSONDecodeError:
        return {"status": "failed"}
    publication = value.get("publication") if isinstance(value, dict) else None
    return {
        "status": "degraded"
        if isinstance(publication, dict) and publication.get("last_error")
        else "ok"
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Structured audiobook-ops health check")
    parser.add_argument("--config", required=True, type=Path)
    arguments = parser.parse_args()
    try:
        config = load_config(arguments.config)
        docker_bin = str(config.get("docker_bin", "/usr/bin/docker"))
        containers = config.get("containers")
        if not isinstance(containers, list) or any(
            not isinstance(value, str) or not value for value in containers
        ):
            raise OperationError("health container list is invalid")
        components: dict[str, object] = {
            f"container:{name}": container_status(docker_bin, name)
            for name in containers
        }
        base_url = str(config.get("control_url", "")).rstrip("/")
        for name in ("core", "catalog", "external-search", "acquisition", "backup"):
            try:
                components[name] = http_status(f"{base_url}/health/{name}")
            except OperationError:
                components[name] = {"status": "failed"}
        components["publisher"] = publisher_status(config)
        critical = {
            key: value
            for key, value in components.items()
            if key != "external-search"
        }
        failed = any(
            isinstance(value, dict) and value.get("status") != "ok"
            for value in critical.values()
        )
        external = components["external-search"]
        overall = (
            "failed"
            if failed
            else "degraded"
            if isinstance(external, dict) and external.get("status") != "ok"
            else "ok"
        )
        print(
            json.dumps(
                {"components": components, "event": "health", "status": overall},
                separators=(",", ":"),
                sort_keys=True,
            )
        )
        return 1 if failed else 0
    except (OSError, TypeError, ValueError, OperationError) as error:
        print(
            json.dumps(
                {"event": "health", "reason": str(error), "status": "failed"},
                separators=(",", ":"),
            )
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
