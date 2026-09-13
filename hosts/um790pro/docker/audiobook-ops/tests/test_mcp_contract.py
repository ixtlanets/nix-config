from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
import tempfile
import unittest

from audiobook_ops.contract import tool_contracts
from audiobook_ops.interface import AudiobookOperations, OperationError
from audiobook_ops.mcp_adapter import MCPAdapter

from test_domain_interface import (
    FakeCatalogAdapter,
    FakeClock,
    FakeExternalActionAdapter,
    FakeReleaseAdapter,
)


EXPECTED_READ_ONLY = {
    "library_audit",
    "library_item_get",
    "library_search",
    "metadata_plan",
    "notification_list",
    "release_inspect",
    "release_search",
    "request_plan",
    "system_status",
    "task_get",
    "task_list",
}
EXPECTED_WRITE = {
    "metadata_apply",
    "metadata_undo",
    "request_apply",
    "task_cancel",
    "task_retry",
}


class FakeStatusAdapter:
    def status(self) -> dict[str, object]:
        return {
            "core": {"status": "ok", "schema_version": 4},
            "external-search": {"status": "degraded"},
        }
FORBIDDEN_ARGUMENT_NAMES = {
    "command",
    "cookie",
    "credential",
    "endpoint",
    "magnet",
    "magnet_uri",
    "path",
    "raw_payload",
    "shell",
    "url",
}


def property_names(schema: dict[str, object]) -> set[str]:
    found: set[str] = set()
    properties = schema.get("properties", {})
    if isinstance(properties, dict):
        for name, child in properties.items():
            found.add(name)
            if isinstance(child, dict):
                found.update(property_names(child))
                items = child.get("items")
                if isinstance(items, dict):
                    found.update(property_names(items))
    return found


class MCPContractTests(unittest.TestCase):
    def test_contract_has_the_exact_approved_surface_and_annotations(self) -> None:
        contracts = {tool["name"]: tool for tool in tool_contracts()}

        self.assertEqual(set(contracts), EXPECTED_READ_ONLY | EXPECTED_WRITE)
        for name in EXPECTED_READ_ONLY:
            self.assertEqual(contracts[name]["annotations"], {"readOnlyHint": True})
        for name in EXPECTED_WRITE:
            self.assertEqual(contracts[name]["annotations"], {"readOnlyHint": False})
        for tool in contracts.values():
            schema = tool["inputSchema"]
            self.assertEqual(schema["type"], "object")
            self.assertFalse(schema["additionalProperties"])
            self.assertTrue(tool["outputSchema"]["type"] in {"object", "array"})
            self.assertFalse(property_names(schema) & FORBIDDEN_ARGUMENT_NAMES)

    def test_apply_cancel_retry_and_undo_have_idempotency_keys(self) -> None:
        contracts = {tool["name"]: tool for tool in tool_contracts()}
        for name in EXPECTED_WRITE:
            self.assertIn("idempotency_key", contracts[name]["inputSchema"]["properties"])

    def test_metadata_changes_require_provenance(self) -> None:
        metadata = {
            tool["name"]: tool for tool in tool_contracts()
        }["metadata_plan"]["inputSchema"]["properties"]["changes"]
        for change in metadata["properties"].values():
            self.assertEqual(
                set(change["required"]),
                {"operation", "source", "observed_at", "confidence"},
            )

    def test_mcp_adapter_calls_the_domain_interface_and_preserves_write_gate(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            operations = AudiobookOperations.open(
                Path(temporary_directory) / "state.sqlite3",
                clock=FakeClock(datetime(2026, 9, 13, tzinfo=UTC)),
                release_adapter=FakeReleaseAdapter(),
                external_action_adapter=FakeExternalActionAdapter(),
                catalog_adapter=FakeCatalogAdapter(),
            )
            try:
                adapter = MCPAdapter(operations)
                self.assertEqual(
                    adapter.call("task_list", {}),
                    operations.invoke("task_list", {}),
                )
                with self.assertRaisesRegex(
                    OperationError, "mutation requires execution gate"
                ):
                    adapter.call(
                        "task_cancel",
                        {
                            "task_id": "opaque-task",
                            "expected_revision": 1,
                            "idempotency_key": "opaque-key",
                        },
                    )
            finally:
                operations.close()

    def test_unconfigured_release_adapter_fails_through_the_domain_error(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            operations = AudiobookOperations.open(
                Path(temporary_directory) / "state.sqlite3"
            )
            try:
                with self.assertRaisesRegex(OperationError, "adapter is unavailable"):
                    operations.invoke("release_search", {"queries": ["Кроткая"]})
            finally:
                operations.close()

    def test_system_status_uses_the_runtime_status_adapter(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            operations = AudiobookOperations.open(
                Path(temporary_directory) / "state.sqlite3",
                status_adapter=FakeStatusAdapter(),
            )
            try:
                result = MCPAdapter(operations).call("system_status", {})
            finally:
                operations.close()

        self.assertEqual(result["core"], {"status": "ok", "schema_version": 4})
        self.assertEqual(result["external-search"], {"status": "degraded"})


if __name__ == "__main__":
    unittest.main()
