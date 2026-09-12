from __future__ import annotations

import argparse
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from typing import NoReturn


HEALTH = {
    "core": "ok",
    "catalog": "unconfigured",
    "external-search": "unconfigured",
}


def health_document(component: str) -> dict[str, str]:
    return {"component": component, "status": HEALTH[component]}


class ScaffoldHandler(BaseHTTPRequestHandler):
    server_version = "AudiobookOps"
    sys_version = ""

    def do_GET(self) -> None:
        component = self.path.removeprefix("/health/")
        if component not in HEALTH or self.path != f"/health/{component}":
            self._send(HTTPStatus.NOT_FOUND, {"error": "not found"})
            return
        status = HTTPStatus.OK if HEALTH[component] == "ok" else HTTPStatus.SERVICE_UNAVAILABLE
        self._send(status, health_document(component))

    def log_message(self, _format: str, *_args: object) -> None:
        return

    def _send(self, status: HTTPStatus, payload: dict[str, str]) -> None:
        body = json.dumps(payload, separators=(",", ":")).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)


def serve(host: str, port: int) -> NoReturn:
    server = ThreadingHTTPServer((host, port), ScaffoldHandler)
    try:
        server.serve_forever()
    finally:
        server.server_close()
    raise SystemExit(0)


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(prog="audiobook-ops")
    subcommands = result.add_subparsers(dest="command", required=True)
    health = subcommands.add_parser("health")
    health.add_argument("component", choices=tuple(HEALTH))
    server = subcommands.add_parser("serve")
    server.add_argument("--host", default="127.0.0.1")
    server.add_argument("--port", type=int, default=8000)
    return result


def main() -> int:
    arguments = parser().parse_args()
    if arguments.command == "health":
        document = health_document(arguments.component)
        print(json.dumps(document, separators=(",", ":")))
        return 0 if document["status"] == "ok" else 1
    serve(arguments.host, arguments.port)


if __name__ == "__main__":
    raise SystemExit(main())
