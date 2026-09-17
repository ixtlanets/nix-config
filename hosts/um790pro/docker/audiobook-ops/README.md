# Audiobook Ops on UM790Pro

> Production operator documentation. The bundle, domain core, acquisition,
> publisher, legacy-history importer, Audiobookshelf 2.36.0 adapter, Streamable
> HTTP transport, Hermes skills/notifications, health, policy, backup, restore,
> and host service assets are deployed and acceptance-tested.

`audiobook-ops` is the deterministic control plane behind the owner's Hermes
audiobook workflow. It reads and updates Audiobookshelf, searches RuTracker via
Prowlarr, drives a dedicated Transmission, validates one logical audiobook, and
hands it to the hardened publisher for atomic publication on `moscow`.

The approved design is
[`docs/superpowers/specs/2026-09-12-hermes-audiobook-automation-design.md`](../../../../docs/superpowers/specs/2026-09-12-hermes-audiobook-automation-design.md).
The execution checklist is
[`docs/superpowers/plans/2026-09-12-hermes-audiobook-automation-implementation.md`](../../../../docs/superpowers/plans/2026-09-12-hermes-audiobook-automation-implementation.md).

## Service inventory

| Unit | Responsibility |
|---|---|
| `audiobook-ops` | MCP, task state, adapters, background reconciliation |
| Prowlarr | tracker search |
| RuTracker gateway | restricted FlareSolverr compatibility path |
| FlareSolverr | Cloudflare browser session |
| dedicated Transmission | temporary acquisition downloads |
| publisher systemd unit | verified atomic transfer to Moscow |
| policy systemd unit | queue, disk, and cleanup enforcement |
| backup/health systemd units | operations and recovery evidence |

## Repository bundle

The bundle provides:

- `docker-compose.yml` with the target five-service topology and retained
  Prowlarr, Transmission, download, FlareSolverr, and gateway state paths;
- a digest-pinned `linux/amd64` Python base in `Dockerfile`;
- `src/audiobook_ops/interface.py`, the shared SQLite-backed domain seam;
- `src/audiobook_ops/contract.py`, the explicit typed MCP tool allowlist;
- `src/audiobook_ops/mcp_adapter.py` and `bin/audiobookctl`, thin adapters over
  the same domain seam;
- `src/audiobook_ops/http_server.py`, the bearer-authenticated Streamable HTTP
  MCP endpoint at `/mcp` with a serialized tool execution boundary;
- `hermes/`, the exact untrusted MCP allowlist, normal/admin skills, durable
  event poller, profile install/rollback runbook, and installed-Hermes rehearsal;
- `config/audiobook-ops.example.json`, containing policy and endpoint examples
  but no credential values;
- neutral Compose/systemd policy, worker, publisher, cleanup, health, backup,
  and restore assets under root-owned production paths;
- retained neutral gateway and Transmission entrypoint scripts;
- `tests/run.sh`, which renders Compose without launching it and checks the
  private bind, state roots, image pins, secret files, transport, backups, and
  operational invariants.

The MCP endpoint accepts JSON-RPC POSTs only at `/mcp`, requires an exact bearer,
rejects browser `Origin` requests, validates calls against the exported tool
schemas, and never exposes arbitrary URLs, paths, magnets, or shell input.
Health is split into `core`, `catalog`, `external-search`, `acquisition`, and
`backup`; a failed VLESS observation degrades external search without hiding a
healthy catalog. The VLESS and capacity evidence files expire after 15 minutes.

The acquisition module sends raw Unicode query variants to Prowlarr, accepts
only exact internal RuTracker topic URLs, returns opaque candidates, and keeps
magnet resolution inside the worker boundary. Search and topic inspection call
a live VLESS route-health endpoint before every upstream operation; the exact
endpoint is wired by the production bundle and must return
`{"status":"ok","route":"vless"}`. Any missing, redirected, oversized, or
negative response fails closed.

The host policy probe separately requires the sing-box unit and TUN interface,
then fetches its HTTPS probe through sing-box's loopback mixed proxy. Binding
the probe socket to the auto-routed TUN interface would re-enter the TUN instead
of exercising its outbound and therefore fails closed as a timeout.

Dedicated Transmission jobs use task-derived labels for restart-safe
reconciliation. Completed releases are stream-probed with `ffprobe`, checked by
two stable sorted SHA-256 manifests, and copied byte-for-byte into task staging.
Safe `.cue`, `.nfo`, `.txt`, JPEG, PNG, and WebP ancillary files are ignored
only within the configured count and byte limits. Bundled images are not
published or treated as an approved cover; cover selection and validation stay
in the separate cover workflow. Cleanup completion is recorded in SQLite, so
one old terminal task cannot starve later cleanup after a restart.

The Audiobookshelf adapter reads every accessible book library and paginates its
items, authors, and series without mirroring the catalog in SQLite. Search is
Unicode-aware across titles, authors, narrators, and series; audits report
missing authors/narrators, incomplete series, and suspected duplicates. Exact
item reads include a path-bound revision and cover checksum.

Metadata plans support the pinned ABS 2.36.0 book shape, including multiple
authors, narrators, series memberships, and string sequences such as `4.5` and
`1-2`. Apply sends only changed fields to `PATCH /api/items/:id/media`, uploads
or clears only the exact item's cover, rereads the item, and compensates a
partial failure. Durable intent makes both pre-write restart and lost database
ack replay-safe. Successful changes retain an internal cover snapshot for
30-day undo; snapshot bytes never enter MCP results.

Cover fetches require live VLESS evidence before every request and redirect.
DNS answers are checked for loopback, private, link-local, tailnet, metadata,
reserved, and multicast addresses, then the TLS connection is pinned to the
validated address to prevent DNS rebinding. Bodies, redirects, dimensions, and
decoded pixels are capped; `ffprobe` plus a full `ffmpeg` decode validates
JPEG/PNG/WebP content.

The publisher atomically claims one `ready_to_publish` task from the shared
SQLite store. Its durable checkpoints are `claimed`, `validated`, `prepared`,
`transferred`, `remote_verified`, `promoted`, and `acknowledged`; the final
checkpoint moves the task to `awaiting_abs` in the same transaction. Every
restart revalidates the immutable local audio manifest before replaying a
remote action. Publication retains `ffprobe`, two-pass stability, SHA-256,
local and remote free-space reserves, a dedicated SSH identity, pinned known
hosts, a hidden incoming directory, exact remote verification, and atomic
rename. It never transcodes or rewrites audio bytes and exposes no delete or
unpublish operation.

The acquisition worker also owns post-publication reconciliation. It scans all
book libraries for the one item whose ABS media path exactly equals the
acknowledged publication path under `/readmeabook`; title similarity is never a
write target. The worker binds that immutable identity, creates one
deterministic internal metadata plan from the already approved acquisition
fields, applies it through the normal snapshot/apply/reread verifier, and only
then records `verified`. Both the plan and apply idempotency identities survive
process restarts, including a crash immediately before or after the ABS write.

The Moscow forced command accepts only `capacity`, `prepare`, receive-only
`rsync-receive`, `verify`, and `promote`. It confines writes to the retained
`/media/disk1/media/.readmeabook-incoming` and
`/media/disk1/media/ReadMeABook` roots, rejects traversal and symlink escapes,
and blocks an existing final path unless it is an exact replay of the same
verified manifest.

The adapter contract is version-isolated to Audiobookshelf 2.36.0. Its route and
payload fixtures follow the upstream
[`ApiRouter.js`](https://github.com/advplyr/audiobookshelf/blob/v2.36.0/server/routers/ApiRouter.js),
[`LibraryItemController.js`](https://github.com/advplyr/audiobookshelf/blob/v2.36.0/server/controllers/LibraryItemController.js),
and [`Book.js`](https://github.com/advplyr/audiobookshelf/blob/v2.36.0/server/models/Book.js).
Run the full contract suite before changing the pinned ABS image. The upgrade
gate also requires `tests/rehearsal_abs_2360.py` against a disposable,
loopback-only ABS instance that the owner has initialized. Prepare two book
libraries with a distinct searchable item in each plus a PNG cover fixture,
then run:

```bash
cd hosts/um790pro/docker/audiobook-ops
ABS_REHEARSAL_URL=http://127.0.0.1:32768 \
ABS_REHEARSAL_TOKEN_FILE=/tmp/audiobook-ops-abs-2360-owner-gate/access-token \
ABS_REHEARSAL_COVER_FILE=/tmp/audiobook-ops-abs-2360-owner-gate/rehearsal-cover.png \
ABS_REHEARSAL_PRIMARY_QUERY=Мастер \
ABS_REHEARSAL_SECONDARY_QUERY=Пикник \
PYTHONPATH=src python tests/rehearsal_abs_2360.py
```

The script refuses a non-loopback target, verifies catalog reads across the two
libraries, exercises exact metadata/cover set and clear operations through the
domain interface, tests idempotent replay and undo, and restores the selected
item's starting snapshot even if an assertion fails.

Render it safely with an explicit private address. This reads files only and
does not start containers:

```bash
AUDIOBOOK_OPS_TAILSCALE_IP=100.95.213.117 \
  docker compose \
    -f hosts/um790pro/docker/audiobook-ops/docker-compose.yml \
    config

hosts/um790pro/docker/audiobook-ops/tests/run.sh
```

Build the reviewed local application image without starting production:

```bash
cd /home/nik/nix-config/hosts/um790pro/docker/audiobook-ops
docker build --platform linux/amd64 \
  --tag localhost/audiobook-ops:0.2.0-ticket9 .
docker image inspect localhost/audiobook-ops:0.2.0-ticket9 \
  --format '{{.Id}} {{.Architecture}}'
```

The result must contain one `sha256:` image ID and `amd64`. Put that exact image
ID in the owner-reviewed production `compose.env`; the Compose file does not
contain a mutable fallback tag and does not build at service start.

Production changes to the Compose project remain owner-gated. Run preflight and
the full local test suite before replacing the pinned application image.

## Fixed topology

- Control host: `um790pro` (CachyOS).
- Catalog/media host: `moscow` (Ubuntu).
- Access: Tailscale private access path only.
- Public tracker/cover egress: existing VLESS route, fail closed.
- Existing reusable state (the physical parent name is retained for a safe,
  no-copy migration):
  `/home/nik/services/readmeabook/{flaresolverr,prowlarr,transmission,downloads}`.
- New control state: `/home/nik/services/audiobook-ops/`.
- Runtime secrets: `/etc/audiobook-ops/secrets/`, root-owned mode `0600`.
- Encrypted recovery copies of reused credentials:
  `secrets/audiobook-ops/um790pro/`; RMAB-only credentials are removed.
- Backups: `/var/backups/audiobook-ops/`.
- Final media root: `/media/disk1/media/ReadMeABook` on `moscow`.
- Audiobookshelf display name: `Загруженные книги`.

The control container keeps those host secrets root-only. Its minimal bootstrap
starts with only `CHOWN`, `SETGID`, and `SETUID`, validates the exact root-owned
mounts, copies config and secrets into a per-container tmpfs as mode `0400`
files owned by UID 1000, clears supplementary groups, drops to UID/GID 1000,
and then replaces itself with the control process. The long-running process has
no effective capabilities; secret values never enter Compose environment or
the image filesystem.

## Normal use through Hermes

Examples of intended requests:

```text
Покажи книги Вадима Панова в моей библиотеке.

Проверь книги серии «Анклавы»: где отсутствует номер серии или чтец?

У этой книги неверный чтец. Найди подтверждение и покажи план исправления.

Замени обложку этой книги, но сначала покажи старую и новую.

Найди на RuTracker «Трудно быть богом» Стругацких и покажи лучшие пять вариантов.

Скачай выбранный вариант после проверки автора, серии, чтеца и обложки.

Какой статус у моих загрузок?
```

Search, inspection, audit, and plan generation do not require approval. Creating
or cancelling a task, applying or undoing metadata, and administrative retry
use the native Hermes approval prompt.

## Emergency CLI contract

The current CLI calls the same domain module as MCP for durable task and event
operations:

```text
audiobookctl --database <sqlite-file> task list
audiobookctl --database <sqlite-file> task show <task-id>
audiobookctl --database <sqlite-file> task cancel <task-id> \
  --expected-revision <number> --idempotency-key <key> --execute
audiobookctl --database <sqlite-file> task retry <task-id> \
  --expected-revision <number> --idempotency-key <key> --execute
audiobookctl --database <sqlite-file> notification list \
  --after-event-id <number> --limit <number>
```

Additional adapter-specific read and metadata commands arrive with their owning
tickets. Mutating commands require an expected revision, an idempotency key, and
an explicit execution flag. The CLI does not offer arbitrary upstream URLs, ABS
endpoints, filesystem paths, shell fragments, magnets, or raw proxy commands.

## Expected task states

```text
draft -> awaiting_approval -> queued -> downloading -> validating
      -> ready_to_publish -> publishing -> awaiting_abs
      -> applying_metadata -> verified
```

Exceptional states are `needs_input`, `failed`, and `cancelled`. Transient errors
receive at most three retries. Another release candidate is never substituted
without a new plan and approval.

## Common incident interpretation

- Catalog works but release search fails: inspect VLESS, gateway, FlareSolverr,
  and Prowlarr; do not restart Audiobookshelf.
- Task is `needs_input`: inspect its semantic conflict and create a revised plan;
  do not bypass validation through Transmission or the filesystem.
- Task is `awaiting_abs`: verify the exact final path and ABS watcher/periodic
  scan; do not grant the service an admin key merely to force a scan.
- Task is `applying_metadata`: retry the same idempotent plan. Published media is
  not automatically removed.
- Metadata apply is partial: inspect compensating rollback and retained snapshot
  before making another change.
- Publisher is blocked: resolve the exact ledger/task conflict before retrying;
  never edit SQLite or the ledger by hand.

## Safety invariants

- All writes target opaque IDs resolved by the backend.
- Existing books are never moved to reflect metadata changes.
- One task is active at a time.
- One release contains exactly one logical audiobook.
- No transcoding or embedded-tag rewrite occurs.
- No published-book deletion exists in the first version.
- Exact topic/infohash duplicates are blocked.
- Fuzzy duplicates require a new explicit approval.
- Publisher writes only through the restricted Moscow forced command.
- Credentials, cookies, magnet URIs, and upstream bodies do not enter logs or
  MCP results.

## Backup and upgrades

Daily backup includes SQLite, operator configuration, publication history,
metadata/cover undo snapshots, and required secrets. Restore rehearsal uses only
a disposable destination and rejects production paths, checksum changes,
unexpected files, symlinks, and replay over an existing destination. Scheduled
mutations and backup share `/run/audiobook-ops/operations.lock`; the backup then
pauses all five containers, takes the SQLite online snapshot, copies retained
configuration, writes exact SHA-256 checksums, atomically publishes the backup,
and emits only a non-secret health timestamp into control state.

Preview and execute a disposable restore as follows; `--production-path` may be
repeated and must name every live state root:

```bash
PYTHONPATH=src python scripts/backup.py \
  --config config/backup.example.json

PYTHONPATH=src python scripts/restore-rehearsal.py \
  --backup /var/backups/audiobook-ops/20260913T120000Z \
  --destination /var/tmp/audiobook-ops-restore-20260913T120000Z \
  --production-path /home/nik/services/audiobook-ops \
  --production-path /home/nik/services/readmeabook
```

Both commands above are previews and make no changes. Add `--execute` only in an
owner-approved rehearsal. Full installation, start, verification, rollback, and
restore commands are in [`PRODUCTION-RUNBOOK.md`](PRODUCTION-RUNBOOK.md).

All OCI images are digest-pinned. Before changing the Audiobookshelf 2.36.0 pin,
run the adapter contract suite against an upgrade rehearsal because the upstream
API specification does not cover every metadata/cover endpoint used here.

## Legacy publication history

The migration mapping pins the immutable production ledger checksum
`a20f20e3c7df929eac479b1d9be94a59f82ffe9bae15eafe4e33fc28382f37e8`
and maps its three active publications to their exact Audiobookshelf library,
item, and media IDs. The fourth tombstoned record is retained without an ABS
mapping. Import creates publication history only; it does not invent acquisition
tasks or republish/unpublish media.

Keep the source ledger as a mode `0400` artifact and run the importer only with
an explicit execution flag:

```bash
cd hosts/um790pro/docker/audiobook-ops
PYTHONPATH=src python scripts/import-legacy-ledger.py \
  --database /home/nik/services/audiobook-ops/audiobook-ops.sqlite3 \
  --ledger /home/nik/services/audiobook-ops/migration/readmeabook-ledger.json \
  --mapping migration/readmeabook-publication-mapping.json \
  --execute
```

The first production import must report `imported: 4`, `unchanged: 0`, and
`total: 4`; an immediate replay must report `imported: 0`, `unchanged: 4`, and
`total: 4`. A disposable rehearsal against an owner-read copy produced both
exact results and retained three published plus one unpublished record without
creating tasks.

## Publisher installation and recovery gate

Do not run these commands or change the production key without owner approval.
On `moscow`, install the reviewed wrapper as the unprivileged `nik` user:

```bash
install -Dm0755 remote-wrapper.py \
  /home/nik/.local/libexec/audiobook-ops-remote-wrapper.py
```

Replace only the forced-command prefix of the existing dedicated publisher key
with the exact line in `moscow/authorized-key-command.example`, then append the
unchanged existing `ssh-ed25519 ...` public-key fields. Expected result: that
key remains restricted and can reach only the two retained media roots through
the five allowlisted operations.

From `um790pro`, verify the dedicated identity and pinned known-host file:

```bash
ssh -T -i "$CREDENTIALS_DIRECTORY/publisher-ssh-key" \
  -o BatchMode=yes -o ClearAllForwardings=yes \
  -o StrictHostKeyChecking=yes \
  -o UserKnownHostsFile=/home/nik/.ssh/known_hosts \
  -o UpdateHostKeys=no nik@100.81.67.47 capacity

ssh -T -i "$CREDENTIALS_DIRECTORY/publisher-ssh-key" \
  -o BatchMode=yes -o ClearAllForwardings=yes \
  -o StrictHostKeyChecking=yes \
  -o UserKnownHostsFile=/home/nik/.ssh/known_hosts \
  -o UpdateHostKeys=no nik@100.81.67.47 'sh -c id'
```

The first command must return one JSON `free_bytes` integer. The second must
fail with `command is not allowed`; it must not execute `id`.

## Owner-only operations

Stop and request owner action before:

- creating or rotating the dedicated Audiobookshelf automation API key;
- installing privileged files or starting/stopping production systemd units;
- changing the Moscow forced-command authorized key;
- choosing production metadata/cover and acquisition acceptance items;
- declaring progress preserved in Absorb;
- deleting the final 30-day RMAB snapshot.

Never paste a credential into this README, Compose YAML, logs, command arguments,
or chat.
