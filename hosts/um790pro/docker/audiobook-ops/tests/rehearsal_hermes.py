#!/usr/bin/env python3
"""Rehearse this bundle against an installed Hermes without changing its profile."""

from __future__ import annotations

import argparse
from http.server import ThreadingHTTPServer
import json
from pathlib import Path
import secrets
import sys
from threading import Thread
from unittest.mock import patch

from audiobook_ops.contract import tool_contracts
from audiobook_ops.http_server import AudiobookHTTPServer


BUNDLE = Path(__file__).resolve().parents[1]


class Adapter:
    def list_tools(self) -> list[dict[str, object]]:
        return tool_contracts()

    def call(
        self,
        _name: str,
        _arguments: dict[str, object],
        *,
        mutation_authorized: bool = False,
    ) -> dict[str, object]:
        return {"mutation_authorized": mutation_authorized}


class Status:
    def status(self) -> dict[str, object]:
        return {"core": {"status": "ok"}}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--hermes-source", required=True, type=Path)
    args = parser.parse_args()
    sys.path.insert(0, str(args.hermes_source.resolve()))

    from tools import mcp_tool

    bearer = secrets.token_urlsafe(32)
    server: ThreadingHTTPServer = AudiobookHTTPServer(
        ("127.0.0.1", 0), Adapter(), Status(), bearer
    )
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        fragment = json.loads(
            (BUNDLE / "hermes" / "mcp" / "audiobook-ops.json").read_text()
        )["mcp_servers"]["audiobook-ops"]
        config = dict(fragment)
        config["url"] = f"http://127.0.0.1:{server.server_port}/mcp"
        config["headers"] = {"Authorization": f"Bearer {bearer}"}

        registered = set(mcp_tool.register_mcp_servers({"audiobook-ops": config}))
        expected = {
            mcp_tool.mcp_prefixed_tool_name("audiobook-ops", str(tool["name"]))
            for tool in tool_contracts()
        }
        if registered != expected:
            raise RuntimeError("installed Hermes registered a different MCP surface")

        read_only = {
            str(tool["name"])
            for tool in tool_contracts()
            if tool["annotations"] == {"readOnlyHint": True}
        }
        write_capable = {
            str(tool["name"])
            for tool in tool_contracts()
            if tool["annotations"] == {"readOnlyHint": False}
        }
        with patch("tools.approval.request_elicitation_consent", return_value="deny") as approval:
            for name in read_only:
                if mcp_tool._trust_gate_check("audiobook-ops", name) is not None:
                    observed = mcp_tool._tool_read_only_hints.get("audiobook-ops", {})
                    raise RuntimeError(
                        f"read-only tool was approval-gated: {name}; hints={observed!r}"
                    )
            if approval.call_count:
                raise RuntimeError("read-only tools invoked native approval")
            for name in write_capable:
                if mcp_tool._trust_gate_check("audiobook-ops", name) is None:
                    raise RuntimeError(f"write tool bypassed approval: {name}")
            if approval.call_count != len(write_capable):
                raise RuntimeError("write tools did not all invoke native approval")

        print(
            json.dumps(
                {
                    "registered_tools": len(registered),
                    "read_only_without_prompt": len(read_only),
                    "write_tools_prompted": len(write_capable),
                    "live_profile_changed": False,
                },
                sort_keys=True,
            )
        )
    finally:
        mcp_tool.shutdown_mcp_servers()
        server.shutdown()
        server.server_close()
        thread.join()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
