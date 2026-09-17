"""Owner-gated contract rehearsal against a disposable Audiobookshelf 2.36.0.

The target must be loopback-only and already contain two book libraries with a
searchable item in each. The script mutates only the first selected item and
restores its exact starting snapshot before exiting.
"""

from __future__ import annotations

import base64
from copy import deepcopy
from datetime import UTC, datetime
import hashlib
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import urlparse
from urllib.request import urlopen

from audiobook_ops.audiobookshelf import (
    AudiobookshelfAdapter,
    AudiobookshelfHTTPClient,
)
from audiobook_ops.interface import AudiobookOperations, OperationError


COVER_SOURCE_URL = "https://rehearsal.invalid/ticket-7-cover.png"


class FixtureCoverFetcher:
    def __init__(self, path: Path) -> None:
        self._path = path

    def fetch(self, source_url: str) -> dict[str, object]:
        if source_url != COVER_SOURCE_URL:
            raise OperationError("unexpected rehearsal cover URL")
        body = self._path.read_bytes()
        if not body:
            raise OperationError("empty rehearsal cover")
        return {
            "source_url": source_url,
            "final_url": source_url,
            "checksum": hashlib.sha256(body).hexdigest(),
            "mime_type": "image/png",
            "filename": "cover.png",
            "width": 600,
            "height": 900,
            "_content_b64": base64.b64encode(body).decode(),
        }


def metadata_change(operation: str, value: object = None) -> dict[str, object]:
    change: dict[str, object] = {
        "operation": operation,
        "source": "Audiobookshelf 2.36.0 disposable rehearsal fixture",
        "confidence": "high",
        "observed_at": datetime.now(UTC).isoformat(),
    }
    if operation == "set":
        change["value"] = value
    return change


def exact_target(item: dict[str, object]) -> dict[str, object]:
    return {
        key: item[key]
        for key in ("library_id", "item_id", "path", "revision")
    }


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> None:
    base_url = os.environ["ABS_REHEARSAL_URL"].rstrip("/")
    token_path = Path(os.environ["ABS_REHEARSAL_TOKEN_FILE"])
    cover_path = Path(os.environ["ABS_REHEARSAL_COVER_FILE"])
    primary_query = os.environ["ABS_REHEARSAL_PRIMARY_QUERY"]
    secondary_query = os.environ["ABS_REHEARSAL_SECONDARY_QUERY"]
    parsed = urlparse(base_url)
    require(
        parsed.scheme == "http"
        and parsed.hostname in {"127.0.0.1", "localhost", "::1"},
        "rehearsal target must be loopback-only HTTP",
    )
    require(token_path.stat().st_mode & 0o777 == 0o600, "token file must be 0600")
    with urlopen(base_url + "/status", timeout=5) as response:
        status = json.loads(response.read(64 * 1024 + 1))
    require(
        status.get("serverVersion") == "2.36.0" and status.get("isInit") is True,
        "rehearsal target must be initialized Audiobookshelf 2.36.0",
    )

    adapter = AudiobookshelfAdapter(
        AudiobookshelfHTTPClient(base_url, token_path.read_text().strip()),
        FixtureCoverFetcher(cover_path),
    )
    primary = adapter.search(primary_query)[0]
    secondary = adapter.search(secondary_query)[0]
    require(
        primary["library_id"] != secondary["library_id"],
        "queries must select items from two different book libraries",
    )
    exact = adapter.get_item(str(primary["library_id"]), str(primary["item_id"]))
    require(exact["revision"] == primary["revision"], "list/exact revision mismatch")
    original = adapter.snapshot_exact(exact_target(exact))

    set_changes = {
        "title": metadata_change("set", "Мастер и Маргарита — rehearsal"),
        "subtitle": metadata_change("set", "Проверка ABS 2.36.0"),
        "authors": metadata_change(
            "set", ["Михаил Булгаков", "Редактор Rehearsal"]
        ),
        "narrators": metadata_change("set", ["Чтец Один", "Чтец Два"]),
        "series": metadata_change(
            "set",
            [
                {"name": "Русская классика", "sequence": "1.5"},
                {"name": "Романы", "sequence": "том 2"},
            ],
        ),
        "genres": metadata_change("set", ["Роман", "Классика"]),
        "tags": metadata_change("set", ["ticket-7", "rehearsal"]),
        "published_year": metadata_change("set", "1967"),
        "published_date": metadata_change("set", "1967-01-01"),
        "publisher": metadata_change("set", "Rehearsal Publisher"),
        "description": metadata_change(
            "set", "Временная проверка metadata и undo."
        ),
        "isbn": metadata_change("set", "9780000000001"),
        "asin": metadata_change("set", "REHEARSAL01"),
        "language": metadata_change("set", "ru"),
        "explicit": metadata_change("set", False),
        "abridged": metadata_change("set", False),
        "cover": metadata_change("set", {"source_url": COVER_SOURCE_URL}),
    }

    with TemporaryDirectory(prefix="audiobook-ops-abs-2360-") as directory:
        operations = AudiobookOperations.open(
            Path(directory) / "state.sqlite3", catalog_adapter=adapter
        )
        try:
            first_plan = operations.invoke(
                "metadata_plan",
                {
                    "library_id": exact["library_id"],
                    "item_id": exact["item_id"],
                    "item_revision": exact["revision"],
                    "changes": set_changes,
                },
            )
            first_apply = operations.invoke(
                "metadata_apply",
                {
                    "plan_id": first_plan["plan_id"],
                    "revision": first_plan["revision"],
                    "idempotency_key": "abs-2360-set-one",
                },
                mutation_authorized=True,
            )
            replay = operations.invoke(
                "metadata_apply",
                {
                    "plan_id": first_plan["plan_id"],
                    "revision": first_plan["revision"],
                    "idempotency_key": "abs-2360-set-one",
                },
                mutation_authorized=True,
            )
            require(replay == first_apply, "metadata apply replay changed result")
            require(
                first_apply["item"]["item_id"] == exact["item_id"]
                and first_apply["item"]["path"] == exact["path"],
                "metadata apply changed item identity",
            )
            require(
                first_apply["item"]["metadata"]["series"]
                == [
                    {"name": "Русская классика", "sequence": "1.5"},
                    {"name": "Романы", "sequence": "том 2"},
                ],
                "multiple series did not round-trip",
            )
            first_undo = operations.invoke(
                "metadata_undo",
                {
                    "change_id": first_apply["change_id"],
                    "revision": first_apply["revision"],
                    "idempotency_key": "abs-2360-undo-one",
                },
                mutation_authorized=True,
            )
            require(
                first_undo["item"]["metadata"] == original["metadata"]
                and first_undo["item"]["cover"] == original["cover"],
                "metadata and cover undo did not restore the starting snapshot",
            )

            current = adapter.get_item(str(exact["library_id"]), str(exact["item_id"]))
            second_plan = operations.invoke(
                "metadata_plan",
                {
                    "library_id": current["library_id"],
                    "item_id": current["item_id"],
                    "item_revision": current["revision"],
                    "changes": set_changes,
                },
            )
            second_apply = operations.invoke(
                "metadata_apply",
                {
                    "plan_id": second_plan["plan_id"],
                    "revision": second_plan["revision"],
                    "idempotency_key": "abs-2360-set-two",
                },
                mutation_authorized=True,
            )
            clear_plan = operations.invoke(
                "metadata_plan",
                {
                    "library_id": second_apply["item"]["library_id"],
                    "item_id": second_apply["item"]["item_id"],
                    "item_revision": second_apply["item"]["revision"],
                    "changes": {
                        field: metadata_change("clear")
                        for field in ("subtitle", "narrators", "series", "tags", "cover")
                    },
                },
            )
            clear_apply = operations.invoke(
                "metadata_apply",
                {
                    "plan_id": clear_plan["plan_id"],
                    "revision": clear_plan["revision"],
                    "idempotency_key": "abs-2360-clear",
                },
                mutation_authorized=True,
            )
            cleared = clear_apply["item"]
            require(
                cleared["metadata"]["subtitle"] is None
                and cleared["metadata"]["narrators"] == []
                and cleared["metadata"]["series"] == []
                and cleared["metadata"]["tags"] == []
                and cleared["cover"] is None,
                "explicit clear did not round-trip",
            )
            require(
                cleared["metadata"]["title"]
                == second_apply["item"]["metadata"]["title"]
                and cleared["metadata"]["authors"]
                == second_apply["item"]["metadata"]["authors"]
                and cleared["metadata"]["publisher"]
                == second_apply["item"]["metadata"]["publisher"],
                "explicit clear changed omitted metadata",
            )
            clear_undo = operations.invoke(
                "metadata_undo",
                {
                    "change_id": clear_apply["change_id"],
                    "revision": clear_apply["revision"],
                    "idempotency_key": "abs-2360-undo-clear",
                },
                mutation_authorized=True,
            )
            require(
                clear_undo["item"]["metadata"]
                == second_apply["item"]["metadata"]
                and clear_undo["item"]["cover"]["checksum"]
                == second_apply["item"]["cover"]["checksum"],
                "clear undo did not restore metadata and cover",
            )
        finally:
            try:
                current = adapter.get_item(
                    str(exact["library_id"]), str(exact["item_id"])
                )
                rollback = adapter.snapshot_exact(exact_target(current))
                adapter.apply_exact(
                    exact_target(current), deepcopy(original), rollback
                )
            finally:
                operations.close()

    restored = adapter.get_item(str(exact["library_id"]), str(exact["item_id"]))
    require(restored["metadata"] == original["metadata"], "fixture metadata not restored")
    require(restored["cover"] == original["cover"], "fixture cover not restored")
    audit = adapter.audit([])
    require(len(audit["library_ids"]) >= 2, "full multi-library audit did not run")
    print(
        json.dumps(
            {
                "server_version": "2.36.0",
                "catalog_libraries": len(audit["library_ids"]),
                "list_exact_revision": "stable",
                "metadata_set": "verified",
                "explicit_clear": "verified",
                "cover_set_clear": "verified",
                "undo": "verified",
                "idempotent_replay": "verified",
                "item_id_path": "unchanged",
                "fixture": "restored",
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
