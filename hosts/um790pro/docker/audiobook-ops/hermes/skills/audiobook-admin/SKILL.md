---
name: audiobook-admin
description: Diagnose failed audiobook tasks, health, and recovery.
version: 0.1.0
author: nix-config maintainers
license: UNLICENSED
platforms: [linux]
metadata:
  hermes:
    tags: [audiobooks, diagnostics, recovery, operations]
    related_skills: [audiobooks]
---

# Audiobook administration

## When to Use

- The user explicitly asks to investigate a failed or needs-input task.
- The user asks for audiobook service health, reconciliation, retry, backup,
  restore, or recovery.
- Do not use this skill for ordinary discovery, adding a book, or playback.

Stay inside the `audiobook-ops` MCP boundary. Begin with observation:
`system_status`, `task_list`, `task_get`, `library_audit`, and exact item reads.
Summarize the failed component, current task revision, transition history, and
safe next action before proposing any mutation.

Use `task_retry` only for a failed or needs-input task with its current revision
and a new stable idempotency key. Use `task_cancel` only before publication.
Both are mutations and must pass Hermes native approval. Never bypass the MCP
control plane with direct process, host, downloader, database, filesystem, or
Audiobookshelf changes.

Backup inspection is read-only through `system_status`. Restore, production
restart/cutover, credential work, and ReadMeABook removal are owner-gated:
identify the exact matching repo runbook step, state the expected result, and
wait for the owner. Do not execute it. After an owner action, re-observe health
and affected records before declaring success.
