# Hermes audiobook automation: approved target design

**Date:** 2026-09-12

**Status:** approved; documentation only; implementation not started

**Supersedes:**
[`2026-09-11-readmeabook-um790pro-design.md`](./2026-09-11-readmeabook-um790pro-design.md)

**Related research:**
[`ReadMeABook Russian discovery`](./2026-09-12-readmeabook-russian-discovery-integrations-research.md),
[`Russian audiobook manager alternatives`](./2026-09-12-russian-audiobook-manager-alternatives-research.md)

## Goal

Use the owner's existing Hermes agent as the primary interface for the complete
audiobook acquisition and maintenance cycle:

1. inspect every book library visible in Audiobookshelf;
2. search, browse, and audit books, authors, narrators, and series;
3. propose and apply reviewed metadata and cover corrections to existing items;
4. search RuTracker through Prowlarr using natural Russian requests;
5. create, download, validate, and publish one selected audio edition;
6. verify the exact new item in Audiobookshelf and notify the originating Hermes
   conversation.

Audiobookshelf on `moscow` remains the source of truth for the published catalog.
Absorb remains an unchanged Audiobookshelf client, and playback progress must
survive every metadata operation.

## Non-goals for the first version

- No dedicated request-manager web UI.
- No multi-user request or approval model; only the owner may mutate state.
- No deletion or physical reorganization of an already published book.
- No batch metadata writes; one Audiobookshelf item is changed per plan.
- No automatic selection of a release candidate.
- No automatic fallback to another torrent after failure.
- No multi-book torrent splitting.
- No audio conversion or rewriting of embedded audio tags.
- No full local mirror of the Audiobookshelf catalog.
- No public ingress.

## Topology

```text
existing Hermes profile (Zenbook / Telegram / desktop)
├── audiobooks skill
├── audiobook-admin skill
└── untrusted Streamable HTTP MCP over Tailscale
                    │
                    ▼
um790pro: repository-managed Compose bundle
├── audiobook-ops: Python + SQLite + background worker
├── Prowlarr
├── RuTracker compatibility gateway
├── FlareSolverr
└── dedicated Transmission
                    │
                    ▼
um790pro: hardened systemd publisher
├── media validation and SHA-256 manifest
├── immutable publication ledger in the shared task store
└── restricted SSH/rsync over Tailscale
                    │
                    ▼
moscow
├── hidden incoming root
├── /media/disk1/media/ReadMeABook
├── Audiobookshelf 2.36.0
└── Absorb
```

`audiobook-ops` is the deep module. Hermes, the emergency CLI, Prowlarr,
Transmission, Audiobookshelf, and the publisher meet at its small domain
interface; none of their native interfaces is exposed through MCP.

## Deployment and retained state

The target bundle lives at:

```text
hosts/um790pro/docker/audiobook-ops/
```

`um790pro` runs CachyOS, so deployment remains Docker Compose plus repository-
managed host systemd units. It is not expressed as a NixOS configuration.

The first service cutover preserves these existing data paths to avoid an
unrelated migration:

```text
/home/nik/services/readmeabook/prowlarr
/home/nik/services/readmeabook/transmission
/home/nik/services/readmeabook/downloads
```

New control-plane state uses a neutral root:

```text
/home/nik/services/audiobook-ops/
```

The Moscow media path stays `/media/disk1/media/ReadMeABook`. Its user-visible
Audiobookshelf name becomes **Загруженные книги**. Moving the three existing
items would risk recreating their Audiobookshelf identities and detaching Absorb
progress, so a physical rename is explicitly deferred.

## Domain model

The control plane keeps these concepts separate:

- **Audiobook work**: bibliographic work requested by the listener.
- **Audio edition**: a particular narration/recording of that work.
- **Release candidate**: one tracker topic/infohash that may supply one audio
  edition.
- **Acquisition task**: one approved candidate progressing through download and
  publication.
- **Managed audiobook**: the resulting exact Audiobookshelf item in the managed
  media tree.
- **Metadata plan**: immutable before/after proposal tied to a known item or
  candidate revision.

An audiobook work may have multiple authors and series memberships. An audio
edition may have multiple narrators. Series sequence is stored as a string so
values such as `4`, `4.5`, and `1-2` retain their meaning.

Changing the release candidate creates a new acquisition task. A confirmed task
never silently changes its source identity.

## Hermes interface

### Skills

The normal `audiobooks` skill teaches Hermes to:

- distinguish a work request from a requested audio edition;
- search the existing library before RuTracker;
- produce Russian query variants, including author/title, series/sequence, and
  `е`/`ё` variants;
- present and explain candidates rather than choose silently;
- research uncertain metadata from the RuTracker topic and ordinary web sources;
- include per-field provenance and confidence;
- call only the domain MCP tools for audiobook mutations;
- request one native confirmation for each complete plan.

The separate `audiobook-admin` skill covers diagnostics, retries, restore
rehearsals, and task reconciliation. It is not loaded for ordinary book requests.

Skills contain workflow instructions, not credentials, validation, state
transitions, filesystem operations, or upstream API logic.

### MCP transport and trust

- Long-lived Streamable HTTP MCP server on `um790pro`.
- Bind only to the private access path; require a dedicated bearer even on the
  tailnet.
- Configure the server as `untrusted` in Hermes.
- Register only an explicit tool allowlist.
- Mark observation and planning tools with `readOnlyHint=true`.
- Leave every `*_apply`, cancel, retry, and undo operation write-capable so Hermes
  displays its native approval UI.
- Never accept arbitrary shell fragments, filesystem paths, upstream endpoints,
  ABS payloads, cookies, credentials, or magnet URIs from the model.

The existing general Hermes profile is used for the first version. This is a
convenience choice, not a strict sandbox: that profile already owns terminal and
SSH-capable tools. A dedicated profile remains a future hardening option.

### MCP tool surface

The initial interface is task-oriented:

| Tool | Effect |
|---|---|
| `library_search` | Read-only search across every accessible book library |
| `library_item_get` | Read one exact item, metadata, path revision, and cover identity |
| `library_audit` | Read-only audit for missing authors/narrators, incomplete series, and suspected duplicates |
| `release_search` | Search Prowlarr/RuTracker and return deduplicated candidates |
| `release_inspect` | Fetch normalized details for one opaque candidate ID |
| `request_plan` | Produce an immutable acquisition preview and revision |
| `request_apply` | Create the acquisition task from an unexpired plan |
| `task_get` / `task_list` | Observe queue and lifecycle state |
| `task_cancel` | Cancel only a task that has not entered publication |
| `metadata_plan` | Produce one combined text-and-cover before/after diff |
| `metadata_apply` | Apply one unexpired plan to one exact ABS item |
| `metadata_undo` | Restore one retained metadata/cover snapshot |
| `system_status` | Read service, adapter, quota, and backup health |
| `notification_list` | Return durable events after a caller-supplied cursor |

Planning may persist an immutable plan record but has no effect on external
systems. A plan expires after 24 hours and becomes invalid immediately when its
source revision changes. Apply calls require both the plan ID/revision and an
idempotency key.

The notification polling job retains its delivery cursor on the Hermes side;
event IDs make repeat delivery harmless without introducing a write-capable
notification acknowledgment prompt.

## Audiobookshelf adapter

The adapter reads libraries, items, authors, and series directly from ABS for
each interaction. SQLite does not mirror the catalog in the first version.

Writes use a dedicated non-admin automation user restricted to book libraries:

- library access: all book libraries;
- update: allowed;
- upload: allowed only because the ABS cover endpoint requires it;
- admin: denied;
- delete: denied.

The adapter exposes the credential to no caller. It always writes to an exact
`library_id + item_id`, and checks the expected media path and revision before
applying a plan. Fuzzy matches are never write targets.

Supported fields are the full ABS book metadata shape: title, subtitle, authors,
narrators, series and sequence, genres, tags, published year/date, publisher,
description, language, ISBN, ASIN, explicit, abridged, and cover. Omitted fields
remain unchanged; a distinct explicit operation clears a field.

Corrections use `PATCH /api/items/:id/media`, which updates the existing item and
causes ABS to persist `metadata.json`. The design does not use global series
rename, whole-library match, or Quick Match. It does not move the underlying
folder merely to reflect corrected metadata.

The ABS API is not a stable complete contract. The adapter targets the pinned
2.36.0 behavior and must pass contract tests against an upgrade rehearsal before
the pinned ABS image changes.

Official references:

- [book metadata and local precedence](https://audiobookshelf.org/docs/documentation/libraries/book-library/book-metadata/)
- [book directory structure](https://audiobookshelf.org/docs/documentation/libraries/book-library/directory-structure/)
- [API keys](https://audiobookshelf.org/docs/documentation/server-management/api-keys/)
- [user permissions](https://audiobookshelf.org/docs/documentation/server-management/user-management/)

## Metadata and cover workflow

Hermes may infer proposed values from the selected RuTracker topic, the existing
ABS catalog, and ordinary web research. Each proposed field records final value,
source URL/identifier, observation time, and confidence. The backend validates
shape and invariants; it does not treat model confidence as authorization.

Minimum publication gate:

- exact title;
- at least one author;
- when a series is present, both series name and sequence;
- narrator value or an explicit reviewed `unknown` result.

Description, genres, dates, publisher, language, ISBN, and ASIN are optional.

One metadata plan may change text fields and cover together. Before apply, the
adapter snapshots the current metadata and cover. It applies, rereads, and
verifies the exact item. On a partial failure it attempts compensating restore
and leaves an actionable `needs_attention` record. A successful change may be
undone for 30 days.

For a new book, the approved cover is fetched and validated before publication,
then published with the audio folder. After ABS discovers the exact new item, the
adapter applies the approved text metadata. ABS DB plus its generated
`metadata.json` becomes canonical; the system does not maintain competing NFO or
OPF sidecars.

Cover fetches:

- accept only HTTPS;
- resolve and reject loopback, private, link-local, tailnet, and metadata-service
  destinations before every request and redirect;
- cap redirects, response bytes, dimensions, and decoded pixels;
- require a supported image MIME and successful JPEG/PNG/WebP decode;
- strip unsafe filenames and publish a normalized cover name;
- retain source URL and content checksum without logging response bodies.

## Search and acquisition workflow

1. Hermes searches ABS first and warns when the requested work or audio edition
   may already exist.
2. Hermes builds multiple Russian query variants.
3. `release_search` queries Prowlarr, merges results, and deduplicates them by
   topic ID/infohash.
4. Up to five candidates are presented first, ranked by work match, narrator,
   format, seeders, and size. Remaining candidates stay available.
5. The owner selects a candidate.
6. Hermes inspects the topic, researches missing metadata, and calls
   `request_plan`.
7. The preview includes release identity, target work/audio edition, metadata,
   cover, file/resource expectations, duplicates, and provenance.
8. One native Hermes approval calls `request_apply`.
9. The background worker submits the internally held magnet to Transmission.
10. Completed content is validated and organized into staging.
11. A semantic conflict in author, work, series, sequence, narrator, or logical
    book count moves the task to `needs_input`. Codec, bitrate, and duration may
    be accepted as derived technical facts.
12. Publisher claims exactly one `ready_to_publish` task and atomically transfers
    it to Moscow.
13. The worker waits for the exact final path to appear in ABS, applies approved
    text metadata, and verifies the result.
14. The task becomes `verified`; its Transmission task and local download data
    are removed.
15. Hermes delivers the durable completion event to the originating conversation.

An exact topic/infohash duplicate is blocked. A fuzzy work/edition match produces
a separate warning and approval rather than preventing legitimate alternate
narrations.

## Acquisition lifecycle

```text
draft
  -> awaiting_approval
  -> queued
  -> downloading
  -> validating
  -> ready_to_publish
  -> publishing
  -> awaiting_abs
  -> applying_metadata
  -> verified
```

Exceptional terminal or waiting states are `needs_input`, `failed`, and
`cancelled`. A task may be cancelled only before publication begins; cancellation
removes its Transmission job and staging content. Published media is never
automatically unpublished after a metadata failure.

Transient network and service errors receive at most three delayed retries.
Semantic errors, authentication failures, revision conflicts, validation
failures, and exhausted retries require attention. Restart reconciliation resumes
from durable state and observable upstream identities rather than repeating the
last command blindly.

## Media validation and paths

The first version permits exactly one logical audiobook per release and one
active acquisition at a time. Accepted audio extensions are `.m4b`, `.m4a`,
`.mp3`, and `.flac`. It preserves source audio without transcoding.

The validator:

- rejects symlinks, devices, sockets, executables, archives, path traversal, and
  content outside the claimed download root;
- ignores bounded safe `.cue`, `.nfo`, `.txt`, JPEG, PNG, and WebP ancillary
  files rather than publishing them as authoritative metadata or an unapproved
  cover;
- validates every audio stream with `ffprobe` and requires positive duration;
- validates the one selected cover separately;
- requires two identical sorted size/SHA-256 manifests across a stability
  interval;
- caps one release at 20 GiB and the total working set at 50 GiB;
- requires at least 100 GiB free on `um790pro` and 200 GiB free on `moscow`.

The target path is derived only from validated metadata:

```text
{Primary Author}/{Series}/{NN - Title}
{Primary Author}/{Title}                 # no series
```

Every segment is normalized and containment-checked. Existing published paths
are not renamed when metadata later changes.

## Publisher

The hardened publisher remains a host systemd job so its SSH credential stays in
a systemd credential rather than in the control-plane container. It claims one
`ready_to_publish` row from the shared SQLite store, performs the existing
manifest/`ffprobe`/free-space checks, copies into the hidden incoming root,
verifies the remote manifest, and atomically renames into the managed tree.

Publisher claims, attempts, final path, manifest, timestamps, and exact ABS item
mapping become durable publication records. The current immutable publisher
ledger is imported as legacy history: its three active publications are mapped
to exact ABS items; historical acquisition tasks are not invented.

The Moscow forced-command SSH wrapper remains the only filesystem write path. It
is generalized from RMAB naming but continues to reject arbitrary shell, path,
delete, and writes outside hidden incoming/final managed roots.

## Network and secrets

- MCP has no public ingress and is reachable only through the private access
  path.
- Public egress for RuTracker and cover fetches must use the existing UM790Pro
  VLESS route. If VLESS is unavailable, these operations fail closed without
  direct Internet fallback.
- Tailscale traffic between Hermes, UM790Pro, and Moscow remains available.
- RuTracker traffic continues through Prowlarr, the restricted compatibility
  gateway, and FlareSolverr; the MCP server does not expose the gateway.

Plaintext secrets are installed as root-owned mode `0600` files under
`/etc/audiobook-ops/secrets`. Credentials are separate for MCP, ABS, Prowlarr,
Transmission, and publisher SSH. They never appear in argv, Compose environment,
tool results, logs, plans, or SQLite. The authoritative encrypted/pass-backed
material remains outside runtime state.

## Operations

- Compose images are pinned by platform digest.
- `audiobook-ops`, publisher, policy, backup, and health checks start after boot.
- Logs contain task/item/topic IDs and state transitions, not credentials,
  cookies, magnet URIs, or complete upstream responses.
- Normal logs retain 30 days; debug logging is explicit and bounded.
- Daily backup covers SQLite, configuration, publication history, metadata/cover
  undo data, and required secrets.
- Automated restore rehearsal never accepts production paths as its destination.
- Search/download health is separate from catalog-read health so a VLESS outage
  does not make the whole MCP appear unavailable.

One Hermes polling job reads notification events after its retained cursor and
delivers only `verified`, `needs_input`, and final `failed` events. Routine
progress does not generate chat messages.

## ReadMeABook removal and service cutover

ReadMeABook is absent from the target architecture. The service cutover is not a
multi-day parallel run:

1. build and test the new bundle without changing production state;
2. record the service baseline and take the final consistent RMAB snapshot;
3. stop the old Compose project;
4. start the new Compose project against the retained Prowlarr and Transmission
   state;
5. verify MCP, search, Transmission, publisher, ABS reads, and reconciliation;
6. before acceptance, restore the old Compose only if the new bundle cannot meet
   its baseline;
7. after acceptance, delete the RMAB container/image, PostgreSQL/Redis state,
   application configuration, obsolete code, and RMAB-only secrets;
8. retain the final RMAB snapshot for 30 days and then remove it.

The target repository removes the RMAB Dockerfile, compatibility patch,
entrypoint, manual-request client, API integration, RMAB tests, and RMAB-specific
systemd assumptions. It retains and renames the generalized Prowlarr,
Transmission, gateway, publisher, policy, backup, healthcheck, and restore
assets.

## Production acceptance

The target is production-ready only when all of the following pass:

- service startup and task reconciliation after host reboot;
- full ABS library enumeration and exact item lookup;
- Cyrillic author/title/series search through RuTracker;
- duplicate warning and exact duplicate blocking;
- cancellation before publication with no residual download/staging data;
- one MP3 and one M4B validation path;
- one complete acquisition through `verified` and Hermes notification;
- one existing-item metadata+cover change and successful undo;
- unchanged Audiobookshelf item identity and preserved Absorb progress;
- simulated transient retry and semantic `needs_input` behavior;
- daily backup and disposable restore rehearsal;
- no live RMAB container, database, application state, or credentials.

## Required owner intervention

Implementation must stop and provide exact instructions before each of these:

1. create the dedicated Audiobookshelf automation user and API key, then store it
   at `pass api/audiobookshelf/audiobook-ops`;
2. approve privileged installation/service-cutover commands on `um790pro` and
   the generalized forced-command key entry on `moscow`;
3. select the existing item used for metadata/cover/undo acceptance;
4. select and approve the new single-book release used for end-to-end acceptance;
5. verify playback and saved progress in Absorb before RMAB cleanup is finalized.

No implementation step may infer these approvals from approval of this design.
