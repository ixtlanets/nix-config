from __future__ import annotations

from audiobook_ops.contract import tool_contracts
from audiobook_ops.interface import AudiobookOperations, OperationError


class MCPAdapter:
    """Transport-neutral MCP adapter over the domain module interface."""

    def __init__(self, operations: AudiobookOperations) -> None:
        self._operations = operations
        self._tools = {tool["name"]: tool for tool in tool_contracts()}

    def list_tools(self) -> list[dict[str, object]]:
        return tool_contracts()

    def call(
        self,
        name: str,
        arguments: dict[str, object],
        *,
        mutation_authorized: bool = False,
    ) -> dict[str, object]:
        if name not in self._tools:
            raise OperationError("tool is not in the audiobook allowlist")
        return self._operations.invoke(
            name, arguments, mutation_authorized=mutation_authorized
        )
