from __future__ import annotations

from contextlib import redirect_stderr
from http.client import HTTPConnection
import io
import json
import threading
import unittest

from audiobook_ops.http_server import AudiobookRequestHandler, create_server
from audiobook_ops.interface import OperationError


class FakeAdapter:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, object], bool]] = []

    def list_tools(self) -> list[dict[str, object]]:
        return [
            {
                "name": "task_list",
                "description": "List tasks.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "states": {"type": "array", "items": {"type": "string"}}
                    },
                    "additionalProperties": False,
                },
                "outputSchema": {"type": "object"},
                "annotations": {"readOnlyHint": True},
            },
            {
                "name": "task_retry",
                "description": "Retry a task.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "fail": {"type": "boolean"},
                        "limit": {"type": "integer", "minimum": 1, "maximum": 100},
                    },
                    "additionalProperties": False,
                },
                "outputSchema": {"type": "object"},
                "annotations": {"readOnlyHint": False},
            },
        ]

    def call(
        self,
        name: str,
        arguments: dict[str, object],
        *,
        mutation_authorized: bool = False,
    ) -> dict[str, object]:
        self.calls.append((name, arguments, mutation_authorized))
        if name == "task_retry" and arguments.get("fail"):
            raise OperationError("bounded failure")
        return {"name": name, "arguments": arguments}


class FakeStatus:
    def status(self) -> dict[str, object]:
        return {
            "core": {"status": "ok", "schema_version": 4},
            "catalog": {"status": "ok", "libraries": 1},
            "external-search": {"status": "degraded"},
        }


class HTTPTransportTests(unittest.TestCase):
    def setUp(self) -> None:
        self.adapter = FakeAdapter()
        self.server = create_server(
            self.adapter,
            FakeStatus(),
            bearer="test-bearer-value",
            host="127.0.0.1",
            port=0,
        )
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.port = self.server.server_address[1]

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)

    def request(
        self,
        method: str,
        path: str,
        payload: dict[str, object] | None = None,
        *,
        authorized: bool = False,
        origin: str | None = None,
    ) -> tuple[int, dict[str, object] | None, dict[str, str]]:
        connection = HTTPConnection("127.0.0.1", self.port, timeout=5)
        headers = {"Accept": "application/json"}
        body = None
        if payload is not None:
            body = json.dumps(payload).encode()
            headers["Content-Type"] = "application/json"
        if authorized:
            headers["Authorization"] = "Bearer test-bearer-value"
        if origin is not None:
            headers["Origin"] = origin
        connection.request(method, path, body=body, headers=headers)
        response = connection.getresponse()
        raw = response.read()
        response_headers = {key.casefold(): value for key, value in response.getheaders()}
        connection.close()
        return (
            response.status,
            json.loads(raw) if raw else None,
            response_headers,
        )

    def rpc(self, method: str, params: dict[str, object]) -> dict[str, object]:
        status, payload, _headers = self.request(
            "POST",
            "/mcp",
            {"jsonrpc": "2.0", "id": 1, "method": method, "params": params},
            authorized=True,
        )
        self.assertEqual(status, 200)
        assert payload is not None
        return payload

    def test_mcp_requires_exact_bearer_and_rejects_browser_origins(self) -> None:
        initialize = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {"protocolVersion": "2025-03-26"},
        }

        unauthenticated = self.request("POST", "/mcp", initialize)
        browser = self.request(
            "POST", "/mcp", initialize, authorized=True, origin="https://evil.test"
        )

        self.assertEqual(unauthenticated[0], 401)
        self.assertEqual(unauthenticated[2]["www-authenticate"], "Bearer")
        self.assertEqual(browser[0], 403)

    def test_initialize_list_and_call_use_bounded_json_responses(self) -> None:
        initialized = self.rpc("initialize", {"protocolVersion": "2025-03-26"})
        listed = self.rpc("tools/list", {})
        called = self.rpc(
            "tools/call", {"name": "task_list", "arguments": {"states": []}}
        )

        self.assertEqual(initialized["result"]["protocolVersion"], "2025-03-26")
        self.assertEqual(
            {tool["name"] for tool in listed["result"]["tools"]},
            {"task_list", "task_retry"},
        )
        self.assertEqual(called["result"]["structuredContent"]["name"], "task_list")
        self.assertFalse(called["result"]["isError"])
        self.assertEqual(self.adapter.calls[-1][2], False)

    def test_tools_list_accepts_sdk_metadata_but_no_other_parameters(self) -> None:
        listed = self.rpc("tools/list", {"_meta": {"progressToken": "probe"}})
        rejected = self.rpc("tools/list", {"arbitrary": True})

        self.assertEqual(len(listed["result"]["tools"]), 2)
        self.assertEqual(rejected["error"]["code"], -32602)

    def test_head_preflight_and_incomplete_request_logging_are_bounded(self) -> None:
        status, payload, _headers = self.request("HEAD", "/mcp")
        incomplete = object.__new__(AudiobookRequestHandler)
        stderr = io.StringIO()

        with redirect_stderr(stderr):
            incomplete.log_message("ignored")

        self.assertEqual((status, payload), (405, None))
        event = json.loads(stderr.getvalue())
        self.assertEqual(event["method"], None)
        self.assertEqual(event["path"], None)

    def test_write_call_marks_the_domain_execution_gate_as_authorized(self) -> None:
        called = self.rpc("tools/call", {"name": "task_retry", "arguments": {}})

        self.assertFalse(called["result"]["isError"])
        self.assertEqual(self.adapter.calls[-1], ("task_retry", {}, True))

    def test_tool_errors_are_mcp_results_without_tracebacks(self) -> None:
        failed = self.rpc(
            "tools/call",
            {"name": "task_retry", "arguments": {"fail": True}},
        )

        self.assertTrue(failed["result"]["isError"])
        self.assertEqual(failed["result"]["content"], [{"type": "text", "text": "bounded failure"}])
        self.assertNotIn("traceback", json.dumps(failed).casefold())

    def test_tool_arguments_reject_undeclared_fields(self) -> None:
        failed = self.rpc(
            "tools/call",
            {"name": "task_list", "arguments": {"arbitrary": "value"}},
        )

        self.assertEqual(failed["error"]["code"], -32602)
        self.assertEqual(self.adapter.calls, [])

    def test_tool_arguments_enforce_integer_maximum(self) -> None:
        failed = self.rpc(
            "tools/call",
            {"name": "task_retry", "arguments": {"limit": 101}},
        )

        self.assertEqual(failed["error"]["code"], -32602)
        self.assertEqual(self.adapter.calls, [])

    def test_health_components_remain_independent(self) -> None:
        core = self.request("GET", "/health/core")
        catalog = self.request("GET", "/health/catalog")
        external = self.request("GET", "/health/external-search")

        self.assertEqual(core[0], 200)
        self.assertEqual(catalog[0], 200)
        self.assertEqual(external[0], 503)
        self.assertEqual(external[1], {"component": "external-search", "status": "degraded"})
        self.assertEqual(self.request("GET", "/health/arbitrary")[0], 404)


if __name__ == "__main__":
    unittest.main()
