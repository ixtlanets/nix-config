# Audiobook RuTracker search recovery - 2026-11-04

## Completed authentication recovery

The owner explicitly authorized repairing access, deploying the fix and completing
recovery autonomously. The authentication recovery ran on `um790pro` without
changing VLESS routes, public exposure, Audiobookshelf, Transmission or the
FlareSolverr service. Only the RuTracker gateway was recreated for the new cookie.

A disposable JavaScript-enabled Chromium ran inside the existing
`audiobook-ops-flaresolverr` container and used its actual network route. A direct
visit to the fixed upstream index with the old cookie showed no authenticated
marker. The browser passed the provider's Cloudflare page and reached the native
login page. Its hidden `login-form-quick` and visible `login-form-full` coexist;
the visible canonical full form was selected and its fixed login target checked.
The earlier static, JavaScript-disabled owner helper was not used for this
recovery and is not evidence of working production authentication.

Existing credentials came from
`/home/nik/services/readmeabook/prowlarr/prowlarr.db`, table `Indexers`, RuTracker
`Settings.username` and `Settings.password`. They were read only into process
memory and sent to the disposable browser over a private pipe, never through
command arguments, environment variables or stored credential exports.

There were two bounded form submissions, without credential guessing. The first
run ended before retaining its browser cookies; the second waited for navigation
and succeeded. No CAPTCHA was presented. Future provider challenges may differ;
this result does not guarantee a CAPTCHA-free refresh.

Before publication, a fresh direct browser visit to
`https://rutracker.org/forum/index.php` confirmed the canonical
`logged-in-username` marker and an exact match to the intended principal. The
browser was then closed. Credentials, cookie values and raw page HTML are not
part of this handoff.

## Publication and live acceptance

After coordinator approval, the replacement flat JSON cookie object was written
atomically to `/etc/audiobook-ops/secrets/gateway-session-cookie`, retaining the
original root:nik ownership (`0:1000`) and mode `0640`. A root-private rollback
copy was retained at
`/etc/audiobook-ops/secrets/rutracker-recovery-20261104-rollback/`.

Only the gateway was recreated:

```sh
sudo -n docker compose \
  --env-file /etc/audiobook-ops/config/compose.env \
  -f /usr/local/lib/audiobook-ops/docker-compose.yml \
  up -d --no-deps --force-recreate rutracker-gateway
```

The recreated gateway was healthy, started at `2026-11-04T11:13:50.727690258Z`,
and its `/run/secrets/gateway_session_cookie` bytes matched the host replacement.
The native Prowlarr `POST /api/v1/indexer/test` returned HTTP 200 in 16.06 seconds.
Following real searches, `GET /api/v1/indexerstatus` returned an empty list, so
transient indexer backoff was cleared without manually editing status records.
At that point Prowlarr health retained only an unrelated `UpdateCheck` warning;
authentication and upstream search were working.

All three requested books returned candidates through the production MCP
`release_search`, followed by successful `release_inspect` calls:

| Book | RuTracker topic | Narrator | Seeders | Search duration |
| --- | --- | --- | --- | --- |
| Дроздов - Пистоль и шпага | 6054728 | Петров Никита (Петроник) | 22 | 26.60 s |
| Дроздов - Кровь на эполетах | 6089710 | Петров Никита (Петроник) | 17 | 26.97 s |
| Конофальский - Нечто из Рютте | 6233599 | Андрей Новокрещенов | 101 | 26.00 s |

These are single-book MP3 releases. Search/inspection acceptance does not itself
establish completed acquisition or publication in Audiobookshelf.

## Deployed control-plane fixes

The control container was replaced under the existing operations lock with
`sha256:1cf0d3f2c0eb88e72b16148db123b73671d9b0c6d949e7ae05df79c98c29afdf`
at `2026-11-04T11:21:06Z`. Its source is the repository bundle, with the same
`acquisition.py` installed under `/usr/local/lib/audiobook-ops/src/`.

- Empty search responses now check the enabled RuTracker indexer and its live
  backoff deadline instead of reporting an unavailable tracker as no matches.
- External-search health ignores only the unrelated `UpdateCheck` warning and
  independently checks RuTracker availability. Other health problems still fail.
- Topic evidence excludes script, style, form and explicitly hidden content.
  Rotating service tokens do not enter the excerpt or its revision.
- The notification poller supports explicitly configured exact `silent_origins`.
  The current Codex origin is silent; allowed Telegram delivery is unchanged,
  and unknown origins remain rejected. Silent events advance the durable cursor.

All five MCP health components returned `ok`. The installed startup verifier
passed for the five containers, service and six enabled/active timers.
`TMPDIR=/tmp ./tests/run.sh` passed all 321 tests, including the red/green
regressions for unavailable search, health warnings, sanitized topic evidence
and silent-origin notification handling.

Control rollback assets are private under
`/etc/audiobook-ops/config/codex-search-recovery-20261104-rollback/`.
The local poller/config rollback is private under
`/home/nik/tmp/audiobook-ops-codex-20261104-local-rollback/`.

## Recovery evidence

The temporary engineering recovery source remains on `um790pro` at
`/home/nik/tmp/rutracker-recovery-20261104.py`; a local copy was retained at
`/tmp/rutracker-recovery-20261104.py`. It records the working browser mechanism,
not a supported production utility or scheduled login service. It must be
reviewed against current runtime and provider behavior before reuse.

Safe inspected candidate metadata is retained locally at
`/home/nik/tmp/rutracker-recovery-inspects-20261104.json`. The
`release_inspect.topic_excerpt` field was omitted because upstream script text
can contain session material; never persist or print that field without
sanitization. All other retained candidate metadata fields are unchanged.

The staged candidate cookie, temporary browser script and disposable browser
profile were removed. The private rollback copy remains available.

See the [production session-refresh procedure](../../hosts/um790pro/docker/audiobook-ops/PRODUCTION-RUNBOOK.md#rutracker-session-refresh-owner-gate).

## Completed acquisition acceptance

All three books completed the normal MCP plan/apply, download, validation,
publication and metadata workflow. Every task is `verified`; its acknowledged
publication path equals the exact Audiobookshelf item path.

| Book | Task ID | Audiobookshelf item ID | Audio files |
| --- | --- | --- | --- |
| Пистоль и шпага | `9b32b186-a2f1-480e-9e64-84b386f29e32` | `ea1598ce-a2b1-4adf-842d-8bce0a673d26` | 16 |
| Кровь на эполетах | `394c3c2e-d043-4e9e-a443-16454aa8648b` | `298a8c83-54b2-4bb2-92dd-fb4406276575` | 18 |
| Нечто из Рютте | `938a9d2d-0000-4b34-8869-557282ef9d81` | `c68bb8bd-e8bb-4364-9baa-591c0de81955` | 34 |

The library ID is `47e465fa-78b1-44bb-a697-98fc02bd8596`. Authors, narrators
and series/sequence values matched the approved release metadata. Every audio
file had a positive duration and no reported audio errors. A real first-track
Range request returned HTTP 206 and audio bytes for each book. The final MCP
task-list check found all three verified and no unfinished tasks. All five
health components were still `ok` after the last transfer.

Detailed secret-free evidence is retained at
`/home/nik/tmp/audiobook-acquisition-evidence-20261104.json`.

The existing notification cron job was already disabled and remained disabled.
A one-off poller check first confirmed that all pending events 5-7 belonged to
the exact configured silent Codex origin. It consumed those events and advanced
the cursor from 4 to 7 without sending messages; subprocess delivery was also
blocked during this acceptance invocation. No recurring schedule was changed.
