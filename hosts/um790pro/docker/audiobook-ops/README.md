# Audiobook Ops on UM790Pro

> Target-state operator documentation. The non-production bundle and domain
> core are implemented, but the external adapters and Streamable HTTP transport
> are not yet complete and nothing here has been deployed. Until service
> cutover, use the current production documentation under `../readmeabook/`.

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

## Repository scaffold

The bundle currently provides:

- `docker-compose.yml` with the target five-service topology and retained
  Prowlarr, Transmission, download, FlareSolverr, and gateway state paths;
- a digest-pinned `linux/amd64` Python base in `Dockerfile`;
- `src/audiobook_ops/interface.py`, the shared SQLite-backed domain seam;
- `src/audiobook_ops/contract.py`, the explicit typed MCP tool allowlist;
- `src/audiobook_ops/mcp_adapter.py` and `bin/audiobookctl`, thin adapters over
  the same domain seam;
- `config/audiobook-ops.example.json`, containing policy and endpoint examples
  but no credential values;
- retained neutral gateway and Transmission entrypoint scripts;
- `tests/run.sh`, which renders Compose without launching it and checks the
  private bind, state roots, image pins, secret files, and scaffold health.

Render it safely with an explicit private address. This reads files only and
does not start containers:

```bash
AUDIOBOOK_OPS_TAILSCALE_IP=100.95.213.117 \
  docker compose \
    -f hosts/um790pro/docker/audiobook-ops/docker-compose.yml \
    config

hosts/um790pro/docker/audiobook-ops/tests/run.sh
```

The Compose project must not be started against the retained production paths
until the owner-approved cutover.

## Fixed topology

- Control host: `um790pro` (CachyOS).
- Catalog/media host: `moscow` (Ubuntu).
- Access: Tailscale private access path only.
- Public tracker/cover egress: existing VLESS route, fail closed.
- Existing reusable state:
  `/home/nik/services/readmeabook/{prowlarr,transmission,downloads}`.
- New control state: `/home/nik/services/audiobook-ops/`.
- Runtime secrets: `/etc/audiobook-ops/secrets/`, root-owned mode `0600`.
- Backups: `/var/backups/audiobook-ops/`.
- Final media root: `/media/disk1/media/ReadMeABook` on `moscow`.
- Audiobookshelf display name: `Загруженные книги`.

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
a disposable destination and must reject production paths.

All OCI images are digest-pinned. Before changing the Audiobookshelf 2.36.0 pin,
run the adapter contract suite against an upgrade rehearsal because the upstream
API specification does not cover every metadata/cover endpoint used here.

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
