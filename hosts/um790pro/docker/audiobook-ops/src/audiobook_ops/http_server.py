from __future__ import annotations

import hmac
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import sys
from threading import RLock
from typing import Protocol

from audiobook_ops.interface import OperationError


MAX_REQUEST_BYTES = 1024 * 1024
HEALTH_COMPONENTS = frozenset(
    {"core", "catalog", "external-search", "acquisition", "backup", "vless-route"}
)


class RPCError(OperationError):
    def __init__(self, code: int, message: str) -> None:
        super().__init__(message)
        self.code = code


def validate_schema(schema: object, value: object) -> None:
    if not isinstance(schema, dict):
        raise OperationError("tool schema is invalid")
    expected = schema.get("type")
    if expected is None:
        return
    expected_types = expected if isinstance(expected, list) else [expected]
    matches = False
    for item_type in expected_types:
        if item_type == "null" and value is None:
            matches = True
        elif item_type == "object" and isinstance(value, dict):
            matches = True
        elif item_type == "array" and isinstance(value, list):
            matches = True
        elif item_type == "string" and isinstance(value, str):
            matches = True
        elif item_type == "integer" and isinstance(value, int) and not isinstance(value, bool):
            matches = True
        elif item_type == "boolean" and isinstance(value, bool):
            matches = True
    if not matches:
        raise OperationError("tool arguments do not match the declared schema")
    if "enum" in schema and value not in schema["enum"]:
        raise OperationError("tool arguments do not match the declared schema")
    if isinstance(value, str):
        if len(value) < int(schema.get("minLength", 0)) or len(value) > int(
            schema.get("maxLength", 1024 * 1024)
        ):
            raise OperationError("tool arguments do not match the declared schema")
    if isinstance(value, int) and not isinstance(value, bool):
        if value < int(schema.get("minimum", value)):
            raise OperationError("tool arguments do not match the declared schema")
        if value > int(schema.get("maximum", value)):
            raise OperationError("tool arguments do not match the declared schema")
    if isinstance(value, list):
        if len(value) < int(schema.get("minItems", 0)) or len(value) > int(
            schema.get("maxItems", 100_000)
        ):
            raise OperationError("tool arguments do not match the declared schema")
        item_schema = schema.get("items")
        if item_schema is not None:
            for item in value:
                validate_schema(item_schema, item)
    if isinstance(value, dict):
        properties = schema.get("properties", {})
        required = schema.get("required", [])
        if not isinstance(properties, dict) or not isinstance(required, list):
            raise OperationError("tool schema is invalid")
        if any(name not in value for name in required):
            raise OperationError("tool arguments do not match the declared schema")
        if schema.get("additionalProperties") is False and any(
            name not in properties for name in value
        ):
            raise OperationError("tool arguments do not match the declared schema")
        for name, child in value.items():
            if name in properties:
                validate_schema(properties[name], child)


class ToolAdapter(Protocol):
    def list_tools(self) -> list[dict[str, object]]: ...

    def call(
        self,
        name: str,
        arguments: dict[str, object],
        *,
        mutation_authorized: bool = False,
    ) -> dict[str, object]: ...


class StatusProvider(Protocol):
    def status(self) -> dict[str, object]: ...


class AudiobookHTTPServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(
        self,
        address: tuple[str, int],
        adapter: ToolAdapter,
        status: StatusProvider,
        bearer: str,
    ) -> None:
        if not bearer or len(bearer.encode()) > 4096:
            raise OperationError("MCP bearer is missing or invalid")
        super().__init__(address, AudiobookRequestHandler)
        self.adapter = adapter
        self.status_provider = status
        self.bearer = bearer
        self.operation_lock = RLock()


class AudiobookRequestHandler(BaseHTTPRequestHandler):
    server: AudiobookHTTPServer
    server_version = "AudiobookOps"
    sys_version = ""

    def do_HEAD(self) -> None:
        status = HTTPStatus.METHOD_NOT_ALLOWED if self.path == "/mcp" else HTTPStatus.NOT_FOUND
        self._response_status = int(status)
        self.send_response(status)
        self.send_header("Content-Length", "0")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()

    def do_GET(self) -> None:
        if self.path.startswith("/health/") or self.path == "/vless-route/health":
            self._health()
            return
        if self.path == "/mcp":
            self._send(HTTPStatus.METHOD_NOT_ALLOWED, {"error": "GET is not available"})
            return
        self._send(HTTPStatus.NOT_FOUND, {"error": "not found"})

    def do_POST(self) -> None:
        if self.path != "/mcp":
            self._send(HTTPStatus.NOT_FOUND, {"error": "not found"})
            return
        if self.headers.get("Origin") is not None:
            self._send(HTTPStatus.FORBIDDEN, {"error": "browser origins are forbidden"})
            return
        authorization = self.headers.get("Authorization", "")
        expected = f"Bearer {self.server.bearer}"
        if not hmac.compare_digest(authorization, expected):
            self._send(
                HTTPStatus.UNAUTHORIZED,
                {"error": "unauthorized"},
                {"WWW-Authenticate": "Bearer"},
            )
            return
        if self.headers.get_content_type() != "application/json":
            self._send(HTTPStatus.UNSUPPORTED_MEDIA_TYPE, {"error": "JSON required"})
            return
        try:
            declared = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            self._send(HTTPStatus.BAD_REQUEST, {"error": "invalid content length"})
            return
        if declared < 1 or declared > MAX_REQUEST_BYTES:
            self._send(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, {"error": "request too large"})
            return
        raw = self.rfile.read(declared)
        try:
            request = json.loads(raw)
        except (UnicodeDecodeError, json.JSONDecodeError):
            self._rpc_error(None, -32700, "parse error")
            return
        if not isinstance(request, dict) or request.get("jsonrpc") != "2.0":
            self._rpc_error(None, -32600, "invalid request")
            return
        request_id = request.get("id")
        method = request.get("method")
        params = request.get("params", {})
        if not isinstance(method, str) or not isinstance(params, dict):
            self._rpc_error(request_id, -32600, "invalid request")
            return
        if request_id is None:
            if method in {"notifications/initialized", "notifications/cancelled"}:
                self.send_response(HTTPStatus.ACCEPTED)
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            self.send_response(HTTPStatus.ACCEPTED)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        try:
            result = self._dispatch(method, params)
        except RPCError as error:
            self._rpc_error(request_id, error.code, str(error))
            return
        except OperationError as error:
            self._rpc_error(request_id, -32602, str(error))
            return
        self._send(HTTPStatus.OK, {"jsonrpc": "2.0", "id": request_id, "result": result})

    def _dispatch(self, method: str, params: dict[str, object]) -> dict[str, object]:
        if method == "initialize":
            protocol = params.get("protocolVersion")
            if not isinstance(protocol, str) or not 1 <= len(protocol) <= 64:
                raise OperationError("invalid MCP protocol version")
            return {
                "protocolVersion": protocol,
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": "audiobook-ops", "version": "0.2.0"},
            }
        if method == "ping":
            return {}
        if method == "tools/list":
            if any(name != "_meta" for name in params):
                raise OperationError("tools/list accepts only MCP metadata")
            if "_meta" in params and not isinstance(params["_meta"], dict):
                raise OperationError("tools/list metadata must be an object")
            return {"tools": self.server.adapter.list_tools()}
        if method == "tools/call":
            name = params.get("name")
            arguments = params.get("arguments", {})
            allowlist = {
                str(tool["name"]): tool for tool in self.server.adapter.list_tools()
            }
            if not isinstance(name, str) or name not in allowlist:
                raise OperationError("tool is not in the audiobook allowlist")
            if not isinstance(arguments, dict):
                raise OperationError("tool arguments must be an object")
            validate_schema(allowlist[name].get("inputSchema"), arguments)
            annotations = allowlist[name].get("annotations", {})
            if not isinstance(annotations, dict):
                raise OperationError("tool annotations are invalid")
            try:
                with self.server.operation_lock:
                    output = self.server.adapter.call(
                        name,
                        arguments,
                        mutation_authorized=annotations.get("readOnlyHint") is False,
                    )
            except OperationError as error:
                return {
                    "content": [{"type": "text", "text": str(error)}],
                    "isError": True,
                }
            text = json.dumps(output, ensure_ascii=False, separators=(",", ":"))
            return {
                "content": [{"type": "text", "text": text}],
                "structuredContent": output,
                "isError": False,
            }
        raise RPCError(-32601, "method not found")

    def _health(self) -> None:
        component = (
            "vless-route"
            if self.path == "/vless-route/health"
            else self.path.removeprefix("/health/")
        )
        if component not in HEALTH_COMPONENTS:
            self._send(HTTPStatus.NOT_FOUND, {"error": "not found"})
            return
        component_method = getattr(self.server.status_provider, "component", None)
        if callable(component_method):
            value = component_method(component)
        else:
            value = self.server.status_provider.status().get(component)
        if not isinstance(value, dict) or value.get("status") not in {
            "ok",
            "degraded",
            "failed",
        }:
            self._send(HTTPStatus.NOT_FOUND, {"error": "not found"})
            return
        status = str(value["status"])
        code = HTTPStatus.OK if status == "ok" else HTTPStatus.SERVICE_UNAVAILABLE
        if component == "vless-route":
            self._send(code, {"route": "vless", "status": status})
        else:
            self._send(code, {"component": component, "status": status})

    def _rpc_error(self, request_id: object, code: int, message: str) -> None:
        self._send(
            HTTPStatus.OK,
            {
                "jsonrpc": "2.0",
                "id": request_id,
                "error": {"code": code, "message": message},
            },
        )

    def _send(
        self,
        status: HTTPStatus,
        payload: dict[str, object],
        headers: dict[str, str] | None = None,
    ) -> None:
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()
        self._response_status = int(status)
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        for name, value in (headers or {}).items():
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, _format: str, *_arguments: object) -> None:
        event = {
            "event": "http_request",
            "method": getattr(self, "command", None),
            "path": getattr(self, "path", None),
            "status": getattr(self, "_response_status", None),
        }
        print(json.dumps(event, separators=(",", ":")), file=sys.stderr)


def create_server(
    adapter: ToolAdapter,
    status: StatusProvider,
    *,
    bearer: str,
    host: str,
    port: int,
) -> AudiobookHTTPServer:
    return AudiobookHTTPServer((host, port), adapter, status, bearer)
