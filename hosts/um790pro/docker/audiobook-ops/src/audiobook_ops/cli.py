from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from audiobook_ops.interface import AudiobookOperations, OperationError


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(prog="audiobookctl")
    result.add_argument("--database", type=Path, required=True)
    groups = result.add_subparsers(dest="group", required=True)

    task = groups.add_parser("task")
    task_commands = task.add_subparsers(dest="task_command", required=True)
    task_commands.add_parser("list")
    show = task_commands.add_parser("show")
    show.add_argument("task_id")
    for name in ("cancel", "retry"):
        mutation = task_commands.add_parser(name)
        mutation.add_argument("task_id")
        mutation.add_argument("--expected-revision", type=int, required=True)
        mutation.add_argument("--idempotency-key", required=True)
        mutation.add_argument("--execute", action="store_true")

    notifications = groups.add_parser("notification")
    notification_commands = notifications.add_subparsers(
        dest="notification_command", required=True
    )
    list_events = notification_commands.add_parser("list")
    list_events.add_argument("--after-event-id", type=int, default=0)
    list_events.add_argument("--limit", type=int, default=100)
    return result


def _call(arguments: argparse.Namespace, operations: AudiobookOperations) -> dict[str, object]:
    if arguments.group == "task" and arguments.task_command == "list":
        return operations.invoke("task_list", {})
    if arguments.group == "task" and arguments.task_command == "show":
        return operations.invoke("task_get", {"task_id": arguments.task_id})
    if arguments.group == "task" and arguments.task_command in {"cancel", "retry"}:
        if not arguments.execute:
            raise OperationError("--execute is required for mutations")
        return operations.invoke(
            f"task_{arguments.task_command}",
            {
                "task_id": arguments.task_id,
                "expected_revision": arguments.expected_revision,
                "idempotency_key": arguments.idempotency_key,
            },
            mutation_authorized=True,
        )
    if arguments.group == "notification" and arguments.notification_command == "list":
        return operations.invoke(
            "notification_list",
            {
                "after_event_id": arguments.after_event_id,
                "limit": arguments.limit,
            },
        )
    raise OperationError("unsupported emergency CLI operation")


def main() -> int:
    arguments = parser().parse_args()
    operations = AudiobookOperations.open(arguments.database)
    try:
        result = _call(arguments, operations)
    except OperationError as error:
        print(json.dumps({"error": str(error)}, separators=(",", ":")), file=sys.stderr)
        return 2
    finally:
        operations.close()
    print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
