from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from audiobook_ops.http_server import create_server
from audiobook_ops.interface import OperationError
from audiobook_ops.runtime import build_runtime


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(prog="audiobook-ops")
    result.add_argument(
        "--config",
        type=Path,
        default=Path(
            os.environ.get(
                "AUDIOBOOK_OPS_CONFIG", "/etc/audiobook-ops/config.json"
            )
        ),
    )
    subcommands = result.add_subparsers(dest="command", required=True)
    health = subcommands.add_parser("health")
    health.add_argument(
        "component",
        choices=("core", "catalog", "external-search", "acquisition", "backup"),
    )
    server = subcommands.add_parser("serve")
    server.add_argument("--host", default="127.0.0.1")
    server.add_argument("--port", type=int, default=8000)
    return result


def main() -> int:
    arguments = parser().parse_args()
    runtime = None
    try:
        runtime = build_runtime(arguments.config)
        if arguments.command == "health":
            document = runtime.status.component(arguments.component)
            print(json.dumps(document, separators=(",", ":"), sort_keys=True))
            return 0 if document["status"] == "ok" else 1
        server = create_server(
            runtime.adapter,
            runtime.status,
            bearer=runtime.bearer,
            host=arguments.host,
            port=arguments.port,
        )
        try:
            server.serve_forever()
        finally:
            server.server_close()
        return 0
    except (OSError, TypeError, ValueError, OperationError) as error:
        print(
            json.dumps(
                {"event": "startup_error", "reason": str(error)},
                separators=(",", ":"),
            )
        )
        return 1
    finally:
        if runtime is not None:
            runtime.close()


if __name__ == "__main__":
    raise SystemExit(main())
