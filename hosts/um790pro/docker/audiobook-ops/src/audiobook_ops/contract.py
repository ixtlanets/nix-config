from __future__ import annotations

from copy import deepcopy
from typing import Any


JSONSchema = dict[str, Any]


def _object(
    properties: dict[str, JSONSchema] | None = None,
    required: tuple[str, ...] = (),
) -> JSONSchema:
    schema: JSONSchema = {
        "type": "object",
        "properties": properties or {},
        "additionalProperties": False,
    }
    if required:
        schema["required"] = list(required)
    return schema


STRING: JSONSchema = {"type": "string", "minLength": 1}
IDEMPOTENCY: JSONSchema = {"type": "string", "minLength": 8, "maxLength": 200}
REVISION: JSONSchema = {"type": "string", "minLength": 1, "maxLength": 200}
TASK_REVISION: JSONSchema = {"type": "integer", "minimum": 0}
OUTPUT_OBJECT: JSONSchema = {"type": "object", "additionalProperties": True}

SERIES_MEMBERSHIP = _object(
    {"name": STRING, "sequence": {"type": "string", "minLength": 1}},
    ("name", "sequence"),
)
WORK = _object(
    {
        "title": STRING,
        "authors": {"type": "array", "items": STRING, "minItems": 1},
        "series": {"type": "array", "items": SERIES_MEMBERSHIP},
    },
    ("title", "authors", "series"),
)
AUDIO_EDITION = _object(
    {
        "narrators": {"type": "array", "items": STRING},
        "narrator_unknown": {"type": "boolean"},
        "abridged": {"type": ["boolean", "null"]},
        "publisher": {"type": ["string", "null"]},
        "recording_year": {"type": ["string", "null"]},
    },
    ("narrators",),
)
CHANGE = _object(
    {
        "operation": {"type": "string", "enum": ["set", "clear"]},
        "value": {},
        "source": {"type": "string"},
        "observed_at": {"type": "string", "format": "date-time"},
        "confidence": {"type": "string", "enum": ["low", "medium", "high"]},
    },
    ("operation", "source", "observed_at", "confidence"),
)
METADATA_FIELDS = (
    "title",
    "subtitle",
    "authors",
    "narrators",
    "series",
    "genres",
    "tags",
    "published_year",
    "published_date",
    "publisher",
    "description",
    "language",
    "isbn",
    "asin",
    "explicit",
    "abridged",
    "cover",
)


def _spec(
    name: str,
    description: str,
    input_schema: JSONSchema,
    *,
    read_only: bool,
    output_schema: JSONSchema | None = None,
) -> dict[str, object]:
    return {
        "name": name,
        "description": description,
        "inputSchema": input_schema,
        "outputSchema": output_schema or OUTPUT_OBJECT,
        "annotations": {"readOnlyHint": read_only},
    }


_TOOLS = (
    _spec(
        "library_search",
        "Search all accessible Audiobookshelf book libraries.",
        _object({"query": STRING}, ("query",)),
        read_only=True,
    ),
    _spec(
        "library_item_get",
        "Read one exact Audiobookshelf item.",
        _object({"library_id": STRING, "item_id": STRING}, ("library_id", "item_id")),
        read_only=True,
    ),
    _spec(
        "library_audit",
        "Audit accessible book libraries without changing them.",
        _object({"library_ids": {"type": "array", "items": STRING}}),
        read_only=True,
    ),
    _spec(
        "release_search",
        "Search RuTracker through normalized Cyrillic query variants.",
        _object(
            {"queries": {"type": "array", "items": STRING, "minItems": 1, "maxItems": 12}},
            ("queries",),
        ),
        read_only=True,
    ),
    _spec(
        "release_inspect",
        "Inspect one opaque release candidate.",
        _object({"candidate_id": STRING}, ("candidate_id",)),
        read_only=True,
    ),
    _spec(
        "request_plan",
        "Create a 24-hour immutable acquisition plan.",
        _object(
            {
                "candidate_id": STRING,
                "candidate_revision": REVISION,
                "work": WORK,
                "audio_edition": AUDIO_EDITION,
                "origin_conversation_id": STRING,
            },
            (
                "candidate_id",
                "candidate_revision",
                "work",
                "audio_edition",
                "origin_conversation_id",
            ),
        ),
        read_only=True,
    ),
    _spec(
        "request_apply",
        "Create an acquisition task from an immutable plan.",
        _object(
            {"plan_id": STRING, "revision": REVISION, "idempotency_key": IDEMPOTENCY},
            ("plan_id", "revision", "idempotency_key"),
        ),
        read_only=False,
    ),
    _spec(
        "task_get",
        "Read one exact acquisition task.",
        _object({"task_id": STRING}, ("task_id",)),
        read_only=True,
    ),
    _spec(
        "task_list",
        "List acquisition tasks.",
        _object({"states": {"type": "array", "items": STRING}}),
        read_only=True,
    ),
    _spec(
        "task_cancel",
        "Cancel one acquisition task before publication.",
        _object(
            {
                "task_id": STRING,
                "expected_revision": TASK_REVISION,
                "idempotency_key": IDEMPOTENCY,
            },
            ("task_id", "expected_revision", "idempotency_key"),
        ),
        read_only=False,
    ),
    _spec(
        "task_retry",
        "Retry one failed or needs-input acquisition task.",
        _object(
            {
                "task_id": STRING,
                "expected_revision": TASK_REVISION,
                "idempotency_key": IDEMPOTENCY,
            },
            ("task_id", "expected_revision", "idempotency_key"),
        ),
        read_only=False,
    ),
    _spec(
        "metadata_plan",
        "Create one combined metadata and cover plan for an exact item.",
        _object(
            {
                "library_id": STRING,
                "item_id": STRING,
                "item_revision": REVISION,
                "changes": _object({field: CHANGE for field in METADATA_FIELDS}),
            },
            ("library_id", "item_id", "item_revision", "changes"),
        ),
        read_only=True,
    ),
    _spec(
        "metadata_apply",
        "Apply one immutable metadata and cover plan.",
        _object(
            {"plan_id": STRING, "revision": REVISION, "idempotency_key": IDEMPOTENCY},
            ("plan_id", "revision", "idempotency_key"),
        ),
        read_only=False,
    ),
    _spec(
        "metadata_undo",
        "Undo one retained metadata and cover change.",
        _object(
            {"change_id": STRING, "revision": REVISION, "idempotency_key": IDEMPOTENCY},
            ("change_id", "revision", "idempotency_key"),
        ),
        read_only=False,
    ),
    _spec(
        "system_status",
        "Read core, catalog, acquisition, and backup health.",
        _object(),
        read_only=True,
    ),
    _spec(
        "notification_list",
        "Read durable notification events after a cursor.",
        _object(
            {
                "after_event_id": {"type": "integer", "minimum": 0},
                "limit": {"type": "integer", "minimum": 1, "maximum": 100},
            },
            ("after_event_id",),
        ),
        read_only=True,
    ),
)


def tool_contracts() -> list[dict[str, object]]:
    """Return a caller-safe copy of the stable MCP tool contract."""

    return deepcopy(list(_TOOLS))
