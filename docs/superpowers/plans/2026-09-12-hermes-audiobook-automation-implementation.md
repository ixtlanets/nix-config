# Hermes audiobook automation: implementation and cutover checklist

**Status:** proposed execution plan for the approved design

**Design:**
[`2026-09-12-hermes-audiobook-automation-design.md`](../specs/2026-09-12-hermes-audiobook-automation-design.md)

This checklist is intentionally ordered so no production mutation or RMAB
removal occurs until the replacement has deterministic tests and a rehearsed
cutover. Checked boxes must be backed by a command result, test, or owner
verification recorded in the implementation handoff.

## 0. Protect current state

- [ ] Record `git status` and preserve unrelated worktree changes.
- [ ] Capture live container images, Compose rendering, systemd unit/timer state,
      publisher status, ledger summary, Transmission queue, and ABS service
      baseline.
- [ ] Confirm no acquisition or publication is active.
- [ ] Inventory the three active legacy publications and exact ABS item IDs.
- [ ] Do not start, delete, or reconfigure production services in this phase.

## 1. Create the new repository bundle

- [ ] Create `hosts/um790pro/docker/audiobook-ops/` without reusing RMAB names in
      new source code.
- [ ] Preserve the existing Prowlarr, Transmission, downloads, gateway, and
      FlareSolverr bind mounts.
- [ ] Add a digest-pinned Python image for `audiobook-ops`.
- [ ] Add a neutral control-plane state root and SQLite database.
- [ ] Add a Compose healthcheck that distinguishes core/catalog health from
      external search health.
- [ ] Keep the MCP port bound only to the UM790Pro Tailscale address.
- [ ] Render and validate Compose without launching it.

## 2. Implement and test the domain core

- [ ] Define opaque identifiers and schemas for work, audio edition, release
      candidate, acquisition task, managed audiobook, and metadata plan.
- [ ] Implement the approved task state machine and legal transitions.
- [ ] Implement 24-hour plans, source revisions, idempotency keys, and exact
      duplicate keys.
- [ ] Implement one-active-task queueing, three transient retries, cancellation,
      and restart reconciliation.
- [ ] Implement durable events and cursor-based notification reads.
- [ ] Test through the domain interface with in-memory/fake adapters; tests assert
      outcomes, not internal implementation.

## 3. Implement external adapters

### Audiobookshelf

- [ ] Read libraries, items, authors, and series from the pinned ABS 2.36.0.
- [ ] Search and audit across all accessible book libraries.
- [ ] Build partial field patches with explicit clear semantics.
- [ ] Validate exact library/item/path revision before every write.
- [ ] Implement combined metadata+cover plan, snapshot, apply, reread, verify,
      compensating rollback, and 30-day undo.
- [ ] Reconcile an acknowledged publication by exact ABS media path, bind its
      immutable item identity, and idempotently apply the approved acquisition
      metadata before recording `verified`.
- [ ] Reject global series rename, Quick Match, fuzzy write targets, delete, and
      admin scan.
- [ ] Add contract tests against a disposable/rehearsal ABS instance.

### Prowlarr and RuTracker

- [ ] Search raw Cyrillic queries and normalize results behind opaque candidate
      IDs.
- [ ] Deduplicate by topic ID/infohash without returning magnet URIs.
- [ ] Inspect one topic through the existing restricted gateway.
- [ ] Rank results without making the final selection.
- [ ] Verify RuTracker fails closed when the VLESS route is unavailable.

### Transmission and media validation

- [ ] Submit only an internally resolved candidate.
- [ ] Reconcile progress and completion after process/host restart.
- [ ] Enforce release/working-set/free-space limits.
- [ ] Reject multi-book, archive, executable, special-file, symlink, and traversal
      cases.
- [ ] Validate all supported audio streams and stable SHA-256 manifests.
- [ ] Preserve audio bytes without conversion or embedded-tag writes.
- [ ] Implement verified cleanup and pre-publication cancellation.

### Cover fetch

- [ ] Implement HTTPS-only SSRF-safe fetch and redirect validation.
- [ ] Enforce byte, dimension, and decoded-pixel limits.
- [ ] Decode and normalize JPEG/PNG/WebP; reject polyglot/invalid content.
- [ ] Record source and checksum without logging content or sensitive URL data.

## 4. Generalize the publisher

- [ ] Remove all RMAB API/request/job assumptions.
- [ ] Claim one `ready_to_publish` task atomically from SQLite.
- [ ] Preserve local/remote manifest, `ffprobe`, stability, space, known-host,
      restricted-key, hidden incoming, remote verification, and atomic rename
      protections.
- [ ] Record publication and exact final path transactionally with the task.
- [ ] Generalize the Moscow forced-command wrapper names without widening its
      allowed operations or roots.
- [ ] Import the immutable legacy ledger and map three active records to exact ABS
      items; retain the original ledger as a read-only artifact.
- [ ] Test publisher crash/retry at claim, transfer, remote verify, promote, and
      task-ack boundaries.

## 5. MCP and Hermes skills

- [ ] Expose only the approved task-oriented MCP tools with stable JSON schemas.
- [ ] Mark only observation/planning tools `readOnlyHint=true`.
- [ ] Verify `*_apply`, cancel, retry, and undo trigger native approval when the
      server is configured `untrusted`.
- [ ] Create the `audiobooks` workflow skill with natural Russian examples and
      explicit MCP-only mutation rules.
- [ ] Create the separate `audiobook-admin` skill.
- [ ] Configure an explicit MCP tool include list in the existing Hermes profile.
- [ ] Add one Hermes notification polling job and prove event-ID deduplication.
- [ ] Run `hermes mcp test`, inspect the loaded tool schemas, and verify the
      Telegram approval experience.

## 6. Production operations

- [ ] Replace RMAB-specific preflight, healthcheck, backup, restore rehearsal,
      cleanup, publisher, and policy units with neutral equivalents.
- [ ] Pin every OCI image digest.
- [ ] Install credentials as root-owned mode `0600` files, one secret per file.
- [ ] Verify no secret appears in Compose config, argv, logs, SQLite, plan output,
      MCP output, or test artifacts.
- [ ] Add structured bounded logs and 30-day retention.
- [ ] Add daily backup and disposable restore rehearsal.
- [ ] Verify every service and required timer starts correctly after reboot.

## 7. Owner gate: Audiobookshelf credential

Stop implementation and ask the owner to:

1. create a dedicated ABS automation user;
2. grant access to all book libraries plus update/upload, without admin/delete;
3. create a revocable API key;
4. store it at `pass api/audiobookshelf/audiobook-ops`;
5. confirm completion without pasting the key into chat.

- [ ] Install the key into the root-only runtime secret after confirmation.
- [ ] Prove reads and one disposable metadata/cover rehearsal through the adapter.

## 8. Rehearse the service cutover

- [ ] Restore copies of current Prowlarr/Transmission/control state into a
      disposable destination.
- [ ] Start the new bundle against the disposable state.
- [ ] Import and reconcile the legacy publisher ledger.
- [ ] Exercise startup with VLESS available/unavailable.
- [ ] Verify the old Compose can still be restored before production acceptance.
- [ ] Produce a cutover command list with exact resolved paths and rollback
      commands; no wildcards or broad deletion targets.

## 9. Owner gate: production cutover

Stop and ask the owner to run/approve the required privileged commands. During
the approved window:

- [ ] Confirm no active Transmission or publisher work.
- [ ] Capture the final consistent RMAB snapshot.
- [ ] Stop the old Compose project.
- [ ] Install the generalized Moscow forced-command entry.
- [ ] Start the new Compose project and host units.
- [ ] Run core, catalog, Prowlarr, Transmission, publisher, and backup health
      checks.
- [ ] If pre-acceptance checks fail, stop and restore the old Compose; do not
      improvise a mixed deployment.

## 10. Owner gates: production acceptance

- [ ] Owner selects an existing low-risk ABS item.
- [ ] Produce and approve a metadata+cover plan for that item.
- [ ] Verify metadata/cover in ABS and playback/progress in Absorb.
- [ ] Undo the change and verify the original state and progress.
- [ ] Owner selects one missing, single-book RuTracker release.
- [ ] Complete search, request approval, download, validation, publication,
      metadata application, ABS verification, cleanup, and Hermes notification.
- [ ] Exercise duplicate blocking and a cancelled pre-publication task.
- [ ] Restart the control plane during a disposable task and verify reconciliation.
- [ ] Run the production backup and disposable restore rehearsal.

## 11. Remove ReadMeABook

Only after every production acceptance item passes:

- [ ] Remove the RMAB container and local image.
- [ ] Remove RMAB PostgreSQL/Redis/application state using explicit resolved
      targets from the cutover manifest.
- [ ] Remove RMAB-only runtime secrets and encrypted/pass entries.
- [ ] Remove RMAB Dockerfile, entrypoint, Transmission patch, manual-request
      client, API integration, tests, docs, and obsolete systemd assumptions.
- [ ] Preserve generalized Prowlarr, Transmission, gateway, publisher, policy,
      health, backup, and restore assets under the new bundle.
- [ ] Rename the ABS library display name to `Загруженные книги` without moving
      its media folder.
- [ ] Confirm no live configuration references RMAB APIs, PostgreSQL, Redis, or
      removed credentials.
- [ ] Retain the final consistent RMAB snapshot for 30 days, then remove that
      exact snapshot through a separately reviewed cleanup step.

## Definition of done

- [ ] All acceptance checks in the approved design pass.
- [ ] Audiobookshelf and Absorb retain their existing identities and progress.
- [ ] Hermes is the primary functional interface and emergency CLI operations use
      the same domain module.
- [ ] No production ReadMeABook process, database, application state, secret, or
      code dependency remains.
- [ ] Operator documentation matches the installed paths, units, commands, and
      recovery procedures.
