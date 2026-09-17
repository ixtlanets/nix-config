---
name: audiobooks
description: Find, add, or correct books in Audiobookshelf.
version: 0.1.0
author: nix-config maintainers
license: UNLICENSED
platforms: [linux]
metadata:
  hermes:
    tags: [audiobooks, audiobookshelf, rutracker, russian]
    related_skills: [audiobook-admin]
---

# Audiobooks

## When to Use

- The user asks to find or add an audiobook, including a Russian request.
- The user wants to inspect or correct Audiobookshelf metadata or a cover.
- The user wants to undo an audiobook metadata/cover change or cancel an add.
- For failed-task diagnosis, retry, health, or recovery, use
  `audiobook-admin` instead.

Natural Russian triggers include «Найди аудиокнигу Лема», «Добавь эту книгу в
Audiobookshelf», «Исправь автора и обложку» and «Отмени последнее изменение».

Treat Audiobookshelf as the source of truth and use only `audiobook-ops` MCP
tools for audiobook reads and mutations. Never construct raw network, shell,
Transmission, filesystem, or Audiobookshelf API mutations.

Handle Russian (русские) requests in Russian and preserve Cyrillic search terms.

## Find or add a book

1. Search the library first with `library_search`, including the original title,
   author, and series terms supplied by the user. If an adequate edition is
   already present, show it and stop unless the user explicitly wants another
   edition.
2. If absent, generate a small set of normalized RuTracker queries for
   `release_search`: preserve Cyrillic; try `author title`, `title author`, and
   useful series/narrator variants. Do not transliterate unless the user supplied
   a transliteration or Cyrillic variants returned no candidates.
3. Inspect plausible results with `release_inspect`. Present a short candidate
   list with title, author, narrator, format/bitrate, size, seed state, and any
   ambiguity. Do not expose opaque acquisition material.
4. Before `request_plan`, obtain the exact conversation origin by running
   `${HERMES_SKILL_DIR}/scripts/origin.py`. If it cannot determine a supported
   origin, ask the user to continue from Telegram; never invent an origin.
5. Call `request_plan` with normalized work/edition facts and that
   `origin_conversation_id`. Show the immutable plan, its provenance, and any
   confidence or unknown fields. Planning is read-only.
6. Only after the user has reviewed the plan, call `request_apply` with a new
   stable idempotency key. This is a mutation: Hermes must display its native
   approval prompt. Never describe chat consent as a substitute for that prompt.
7. Report the task ID and current state. Durable `verified`, `needs_input`, or
   final `failed` events are delivered later by the polling job.

## Inspect or edit metadata and cover

Use `library_search` and `library_item_get` to resolve one exact item and its
revision. For every proposed field in `metadata_plan`, include provenance
(`source`, `observed_at`) and `confidence`; use clear rather than guessed values.
Show the combined metadata/cover plan before calling `metadata_apply`. Applying
and `metadata_undo` are mutations and must pass a native Hermes approval prompt.
After an apply or undo, re-read the item and report the observed result.

## Task control

Use `task_get`/`task_list` for status. Cancellation is only through
`task_cancel`; it requires the current revision, an idempotency key, and native
approval. Use the rare `audiobook-admin` skill for failed-task diagnosis/retry,
reconciliation, or backup/restore operations.

Success means the backend reports a durable verified result; a queued or
downloading task is not complete. Keep responses in the user's language.
