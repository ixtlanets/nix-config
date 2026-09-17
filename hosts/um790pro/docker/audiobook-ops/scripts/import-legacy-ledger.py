#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from audiobook_ops.interface import AudiobookOperations, OperationError
from audiobook_ops.legacy import import_legacy_ledger


def main() -> int:
    parser = argparse.ArgumentParser(description="Import immutable publication history")
    parser.add_argument("--database", required=True, type=Path)
    parser.add_argument("--ledger", required=True, type=Path)
    parser.add_argument("--mapping", required=True, type=Path)
    parser.add_argument("--execute", action="store_true")
    arguments = parser.parse_args()
    if not arguments.execute:
        print("legacy import requires --execute", file=sys.stderr)
        return 2
    operations = None
    try:
        operations = AudiobookOperations.open(arguments.database)
        result = import_legacy_ledger(
            operations, arguments.ledger, arguments.mapping
        )
        print(json.dumps(result, sort_keys=True))
        return 0
    except (OSError, ValueError, OperationError) as error:
        print(f"legacy import error: {error}", file=sys.stderr)
        return 1
    finally:
        if operations is not None:
            operations.close()


if __name__ == "__main__":
    raise SystemExit(main())
