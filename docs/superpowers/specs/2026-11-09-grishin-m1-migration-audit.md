# Grishin M1 Max → dedicated Linux/x86_64 VM: source audit

Date: 2026-11-09, Europe/Moscow. **Read-only assessment; no migration performed.**

## Decision in brief

**Feasible for the server/work-data layer; full desktop equivalence remains conditional.** The authoritative work source is **M1 Max, 192.168.1.174, user nik**, not the local Zenbook. OpenClaw, the work vault/dashboard, GR News/PostgreSQL and their consumers are real running workloads. This is a new Linux installation plus a consistent data migration, not a binary clone of macOS.

- Background-only viable minimum, subject to rehearsal: **4 shared vCPU, 8 GiB RAM, 160 GiB disk**, no local LLM. This is a floor, not a measured peak requirement.
- Practical full-work candidate: **4–6 vCPU, 12 GiB RAM, 256 GiB thin disk**; consider 16 GiB only after desktop/concurrency measurement and a host-memory decision.
- Observed server/project/media data: **75.60 GiB core**, **102.57 GiB including related GR media roots**, excluding venvs/node_modules and not following symlinks. This is **not a complete desktop subtotal**. Separately, the lead reports approximately 51 GiB additional Codex/agent desktop state, bringing its preliminary full-desktop estimate to about 154 GiB before Linux/dependencies; see [desktop scope](<docs/superpowers/specs/2026-11-09-grishin-vm-feasibility.md#L40>). Browser/bridge home measurements below also require work/personal filtering and an overlap-aware manifest. A 128 GiB disk is insufficient for full desktop scope; 160 GiB is only a deliberately reduced service scope.
- After successful offline rehearsal: assume **30–60 minutes background-service interruption; reserve 1–2 hours for complete GUI/auth acceptance**. These are planning estimates, not measured downtime or a promise. First-time Apple bridge/browser-auth replacement has no bounded estimate yet.
- Keep llama-server/model execution on M1 unless separately requested; its model storage and compute are not included in VM sizing. Retaining an Apple browser/desktop bridge would mean a **hybrid**, not a completed move leaving only inference on M1.

Host budget is taken from the lead's independently checked [PVE feasibility report](<docs/superpowers/specs/2026-11-09-grishin-vm-feasibility.md#L19-L44>), not inferred from M1 or Zenbook: running allocations total 38 GiB; stopped Windows has another 12 GiB. Adding 12 GiB yields 50 GiB running allocations, but starting Windows would raise that to 62 GiB before overhead, above the reported 61.60 GiB physical memory. Keep Windows stopped or rebudget explicitly. Thin pool has approximately 372 GiB physical free; a new 256 GiB virtual disk is not a reservation of that much safe usable capacity. Preserve shared-pool growth/snapshot headroom.

## Evidence and safety boundary

All primary host observations used the required connection:

~~~sh
ssh -o BatchMode=yes -o ConnectTimeout=12 -o ProxyJump=none m1max 'python3 -'
~~~

The remote clock reports UTC; add three hours for the report's Moscow date. Host identity was sampled at **2026-11-08T21:11:44Z = 2026-11-09 00:11:44 MSK**: hostname m1max, Darwin arm64, user nik. Commands were inventory-only: Python filesystem metadata/whitelisted JSON/plist parsing, process and socket listings, launchctl list/print, and crontab listing. No process start/restart, configuration change, network change, inference, API probe, message send or other external action was performed. No raw config, environment values, token values, conversation bodies or business records are reproduced.

| Evidence | Remote sample time (UTC, 2026-11-08) | Primary source and method |
|---|---|---|
| E1 | 21:11:44; 21:12:05 | Host identity; launch-agent plists, directory metadata, launchctl list, user crontab |
| E2 | 21:12:33; 21:15:44; 21:16:51 | Whitelisted [OpenClaw configuration](<ssh://nik@192.168.1.174/Users/nik/.openclaw/openclaw.json>), entrypoint references, installed-package metadata |
| E3 | 21:12:57–21:13:32 | Persistent-byte/count walk of OpenClaw, work vault, GR repositories and related home roots; zero reported file stat errors |
| E4 | 21:13:43; 21:15:01 | [Gateway SQLite](<ssh://nik@192.168.1.174/Users/nik/.openclaw/state/openclaw.sqlite>) schema plus committed-WAL in-memory snapshot, whitelisted cron/task/channel status only |
| E5 | 21:14:13 onward; 21:16:51 | Scoped production-code dependency markers, actual executable architectures, skill symlink targets |
| E6 | 21:15:44; 21:16:51; 21:18:04 | Process parentage/cwd, local listening sockets and selected launchctl runtime fields; no raw argument/environment dump in this report |
| E7 | 21:16:10–21:16:46; 21:17:28–21:17:52 | Detailed vault/project/session-store size breakdown |
| E8 | 21:16:51 | Passive retained [gateway log](<ssh://nik@192.168.1.174/Users/nik/Library/Logs/openclaw/gateway.log>) signal counts/timestamps, never message text |
| E9 | 21:18:37–21:19:03 | Auxiliary browser/bridge home sizes and large workflow-directory categories; metadata only |

SQLite safety matters: the first immutable base-file schema view omitted its live 64 MiB WAL and was **not** used as final live scheduler evidence. For E4, Python read the database and WAL bytes without opening either for writes, checked unchanged inode/size/mtime across the bounded read, applied matching-salt frames through the latest committed frame **only in RAM**, deserialized into an in-memory SQLite connection, and obtained quick_check=ok. Nineteen committed frames were applied. No checkpoint, backup-to-disk, scheduler API or production SQLite connection capable of creating/updating SHM was used. This is a coherent sampled view, not a guarantee of state at a future cutover.

## Actual services and consumers

| Component | Observed state and ownership | Migration consequence |
|---|---|---|
| OpenClaw gateway | ai.openclaw.gateway running, PID 81280; one launch since load, no recorded exit. Installed OpenClaw 2026.10.10 with Node 24.21.0. RSS approximately **2.28–2.46 GiB** across samples. LAN listener 18789, loopback 18799. [Entrypoint](<ssh://nik@192.168.1.174/Users/nik/.openclaw/service-env/ai.openclaw.gateway-env-wrapper.sh>) loads service env without exposing its values. | Dedicated Linux service, same compatible package/data schema initially, correct working directory and secret provider. RSS alone rules out an attractive-but-unrealistic 2–4 GiB whole-VM budget. |
| Work agents/workspaces | Main agent uses [OpenClaw workspace](<ssh://nik@192.168.1.174/Users/nik/.openclaw/workspace/>); linkedin/funding use [work vault](<ssh://nik@192.168.1.174/Users/nik/obsidian-vault/>). A benchmark agent/workspace also exists. | Preserve distinct workspaces and per-agent state. Rewrite absolute macOS home paths; do not substitute a local Zenbook vault. |
| GR dashboard | com.grishinrobotics.dashboard running: launcher PID 2938, Node child 2945, 127.0.0.1:8787; [launcher](<ssh://nik@192.168.1.174/Users/nik/obsidian-vault/.opencode/tools/dashboard/bin/start-cloudflare.mjs>) and a live cloudflared child. launchctl reports **86,666 runs**, last terminating signal 15. | Separate from gateway. Preserve current ingress requirements, but do not blindly reproduce unexplained historical launch churn. No ingress changes were made or tested. |
| GR News app/database/workers | Live Next server on port 3000, **two** Node processes executing [worker entrypoint](<ssh://nik@192.168.1.174/Users/nik/pro/GR/gr-news/scripts/run-worker.ts>) (PIDs 16302/16327), PostgreSQL **16.11** PID 4188 at 127.0.0.1:5432. [Repository](<ssh://nik@192.168.1.174/Users/nik/pro/GR/gr-news/>) includes .devenv PostgreSQL state and substantial data. | Treat web app, both workers, queues/scheduler ownership and database as one consistency group. Raw macOS PostgreSQL data-directory copy is not a Linux migration method: rehearse logical dump/restore (including roles/extensions as required). No DB content was queried here. |
| Telegram | Enabled allowlisted channel in gateway config; Telegram ingress records exist. Retained logs include polling/getUpdates signals and provider starts. No independent standalone Telegram process was identified in scoped inventory. | Gateway owns an observed Telegram consumer path. **Never run old/new production pollers concurrently.** This passive evidence does not prove current API health or rule out consumers on other hosts. |
| A2A tunnel | ai.openclaw.a2a-tunnel running, PID 60238, loopback listener 18902; 551 launches and last exit 255. Config has an enabled A2A channel/Zenbook peer. | Work/personal boundary and reachability must be deliberately recreated or omitted; do not inherit personal cross-host trust automatically. Existing tunnel failure history predates migration. |
| LinkedIn native bridge | Live native-mcp-bridge Node process (PID 37243), listener 127.0.0.1:4318, installed under [LinkedIn helper releases](<ssh://nik@192.168.1.174/Users/nik/.local/share/linkedin-helper/>). A launch-agent environment helper plist exists. | Additional deployed runtime outside GR repository/OpenClaw. Preserve protocol, local-auth provisioning and chosen working browser; repository copy alone is insufficient. |
| Hermes | A custom gateway plist exists, but no live matching gateway; launchctl print returns 113 (label not loaded), consistent with its absence in launchctl list. | Do not convert a historical plist into a newly active consumer. Hermes-related workflow code/data still requires scope review. |
| Adjacent, not automatically GR | indexary service/listener 4185, local llama-server; llama-dashboard on 8081/8082; transient hyperframes listeners 3027/3028. Multiple CLI/MCP/browser descendants also exist. | Do not stop, copy or re-enable every user process indiscriminately. Llama is explicitly excluded from VM compute sizing. Confirm whether indexary is a required work dependency. |

Custom launchd metadata also contains a GH-delete polling helper and a LinkedIn environment helper; their presence is not proof of an active desired production daemon. Existing launchd scheduling/KeepAlive semantics must be reviewed before translating to systemd. **No user crontab exists** (crontab exit 1 explicitly reports no crontab); this does not imply no automation.

### Where the CRM/bots/database work really is

There were no standalone home-level work/workspace/crm/db/bots directories in the requested exact-name scan. Instead, the real work roots are the vault, OpenClaw workspaces and **38 project directories** under [GR repositories](<ssh://nik@192.168.1.174/Users/nik/pro/GR/>), plus related GR media/mail roots. This is not evidence that the business has no CRM or bots: those are implemented within projects/skills and data stores, not necessarily a directory or daemon named crm.

Observed workflow families include funding discovery/intake/backlog/queue, LinkedIn discovery/helpers, Gmail inbox handling, calendar statistics, news processing, Slack/affinity-related projects and media tooling. Code scans found SQLite references in funding workflow code. Filesystem/database-format metadata was inspected; business records, credentials and session conversations were not. Old repositories such as Slack/affinity projects are **inventory, not proven live services**. The verified long-running GR server group is gateway + dashboard/ingress + GR News/PostgreSQL/workers + LinkedIn bridge.

## Scheduler and in-flight state

At **21:15:01Z / 00:15:01 MSK**, committed scheduler metadata contained **9 declarations: 6 enabled, 3 disabled**. Names, prompts, recipient IDs and result bodies were intentionally omitted. Rows below are report-local ordinals, not persistent identifiers.

| Row | Enabled | Agent | Schedule | Last recorded outcome / caveat |
|---:|:---:|---|---|---|
| 1 | yes | default/unspecified | cron 0 3 * * *; no timezone in schedule object | ok; last 2026-11-08 03:00Z; 0 consecutive errors |
| 2 | yes | main | every 30 minutes | ok; last 2026-11-08 21:05:14Z; 0 consecutive errors |
| 3 | no | linkedin | daily 10:00 Europe/London | ok historically; keep disabled |
| 4 | yes | main | every 10 minutes, Europe/London | last recorded ok **2026-10-12**, although next-run field is current: status is stale, not proof of current success |
| 5 | no | funding | daily 19:30 Europe/London | last error, 1 consecutive error; keep disabled |
| 6 | yes | default/unspecified | every 24 hours, anchored | last ok; 0 consecutive errors |
| 7 | yes | main | every 2 minutes, anchored | last error **2026-10-29**; consecutiveErrors=0; next-run field already near/past sampling time: inconsistent/stale history needs review |
| 8 | no | linkedin | weekdays 08:00 Europe/London | last error, 1 consecutive error; keep disabled |
| 9 | yes | linkedin | minute 17 hourly, Europe/London | last run ok 2026-11-08 20:17Z; delivery marked not-delivered |

Task-run rows: **2,981 succeeded, 18 failed, 1 timed_out; no running status**. The timed_out row is terminal, not an active task. Ingress: **8 Telegram records, all completed**. Delivery queue: **16 completed, 2 failed**. Local worker-placement metadata: 292 rows, not 292 live operating-system workers. No scheduler runningAtMs marker appeared in the whitelisted job state. These observations do not cover work in arbitrary browser tabs or separate GR News/PostgreSQL queues.

Telegram passive evidence: last retained polling signal was 2026-11-05; provider-start signals include 2026-11-07 16:35Z; a historical conflict signal dated 2026-11-01 was found. The log tail also contains webhook references, so this report does **not** assert a verified current webhook/poll mode from configuration defaults. No getMe/getWebhookInfo/getUpdates or test send was performed. Preserve channel offsets/deduplication state and enforce single-consumer ownership regardless of transport.

Before future cutover, recheck all job/queue states, drain the active writers, explicitly decide missed-job catch-up and failed-delivery policy, preserve disabled declarations, and prohibit blanket replay. Current clean task-run status is not permission to cut over without this gate.

## Persistent storage inventory

Numbers below are **logical regular-file bytes**, converted to GiB (2^30), sampled while the services continued running. They are not filesystem-free space, backup size or guaranteed rsync byte count. Symlinks were counted but **not followed**, avoiding double-counting while exposing missing dependencies. All listed sizes exclude directories named .venv, venv, env, node_modules, __pycache__, .mypy_cache, .pytest_cache, .ruff_cache, .tox, .next. Root OpenClaw tools/Node package data remaining outside node_modules is reported, but should be rebuilt rather than copied as a Linux runtime. Other scratch/media/history was conservatively retained, **not** silently declared disposable.

| Scope | Bytes | GiB | Notes |
|---|---:|---:|---|
| Work vault | 53,425,114,507 | 49.76 | 656,986 regular files; excludes venv/node_modules; 8 symlinks not followed |
| GR project tree | 16,671,846,260 | 15.53 | 57,238 files; 49 symlinks not followed; 38 project directories |
| OpenClaw total | 11,082,768,657 | 10.32 | Sum of top-level inventories/root files; live-tree approximation |
| **Core subtotal** | **81,179,729,424** | **75.60** | Three scopes above, no double-counted subsets |
| Related GR media/mail/project home roots | 28,949,740,643 | 26.96 | Includes several grx media working roots and a tiny agent-mail root; exact scope needs owner decision |
| **Full inventoried subtotal** | **110,129,470,067** | **102.57** | Does not include arbitrary home, external browser profiles, GPG/pass stores or model files |

Additional E9 measurements outside the 102.57 GiB service/project/media subtotal:

| External location | Bytes | GiB | Scope warning |
|---|---:|---:|---|
| [Deployed LinkedIn helper](<ssh://nik@192.168.1.174/Users/nik/.local/share/linkedin-helper/>) | 4,131,003,856 | 3.85 | Runtime/releases outside GR repository; reinstall native components and preserve needed deployment/config metadata |
| [Brave browser home](<ssh://nik@192.168.1.174/Users/nik/Library/Application%20Support/BraveSoftware/Brave-Browser/>) | 9,842,244,811 | 9.17 | Entire user browser home, **not proven exclusively GR** |
| [Chrome browser home](<ssh://nik@192.168.1.174/Users/nik/Library/Application%20Support/Google/Chrome/>) | 8,463,616,505 | 7.88 | Entire user browser home, **not proven exclusively GR** |

The LinkedIn helper config directory contains only 215 bytes across two files; no values were displayed. E9 excludes .git as well as standard rebuildable directories. These three external homes total approximately **20.90 GiB**; adding all of them would bring this audit's own gross scope to **123.46 GiB**, but that is neither an approved work-only manifest nor a complete desktop total. The lead's additional ~51 GiB desktop-state figure is separately sourced; do not add browser/Codex scope without checking overlap. Do not migrate personal profiles to the work VM.

Within the 32.18 GiB workflow work tree, large E9 categories are funding batches (~18.80 GiB), accelerator lead discovery (~5.23 GiB), funding discovery (~3.54 GiB), and funding publication (~2.65 GiB). These labels and file counts are workflow metadata, not inspected business contents; they explain why treating the entire tree as a dependency cache would be unsafe.

Important **subsets**, not amounts to add again:

| Subset | Approximate GiB | Why it matters |
|---|---:|---|
| OpenClaw agents | 3.36 | Main 2.61 GiB, linkedin 0.36, funding 0.28, benchmark 0.10; per-agent SQLite/Codex/session stores |
| OpenClaw browser profiles | 2.48 | 31,099 files; credentials/cookies are not guaranteed portable |
| OpenClaw state | 0.49 | Gateway database/WAL and other durable task/channel/runtime state |
| OpenClaw workspace | 0.13 | 1,496 files; no projects subdirectory found at the requested exact location |
| OpenClaw tmp | 3.58 | 163,059 files even after standard exclusions; review before deleting or excluding |
| OpenClaw media | 0.09 | Distinct from the much larger related GR media roots |
| Work-vault .git | 2.97 | Local history is persistent; retain without publishing a remote |
| Work-vault .opencode | 32.48 | Primarily work: **32.18 GiB**, 275,599 files; not merely installed tool dependencies |
| Work-vault .scratch | 10.76 | 292,604 files; potential reduction only after owner classification |
| GR News repository | 14.28 | Dominates GR project storage |
| GR News data | 8.56 | Persistent application working data |
| GR News .devenv | 5.59 | Includes actual PostgreSQL data, not all rebuildable environment machinery |
| GR News PostgreSQL data directory | 3.93 | 4,215,647,760 bytes; logical export size/restore time not measured |

Legacy session export metadata: **180 JSONL files, 393,986,440 bytes**, across five session directories. That is **not the entire session history**: the main agent also has a roughly 600.7 MB SQLite store plus its companions, Codex-home databases and other agent state. Preserve agents/state together; do not infer session count from JSONL count or migrate only JSONL files. OpenClaw's top-level zero-byte legacy agent database is not the authoritative main agent store.

The skill directories contain **49 symlinks** into sibling agent/Claude skill trees; plugin-skills also contains symlinks. [Shared agent skills](<ssh://nik@192.168.1.174/Users/nik/.agents/skills/>) and [Claude skills](<ssh://nik@192.168.1.174/Users/nik/.claude/skills/>) must be explicitly included/relinked. Their measured non-followed trees are small (~22 MiB for the agent tree, ~9 MiB for Claude skills), but essential. Do not use dereference-all copying without reviewing whether symlinks cross work/personal boundaries.

## Apple/architecture dependencies and portability gates

| Area | Primary evidence | Assessment / required future proof |
|---|---|---|
| Native architecture | file inspection: bundled Node, Homebrew Node, cloudflared and [openclaw-mac](<ssh://nik@192.168.1.174/Applications/OpenClaw.app/Contents/MacOS/openclaw-mac>) are **Mach-O arm64**. OpenClaw package declares Node >=24.16 <25 or >=26.1. | Reinstall Linux/x86_64 Node, cloudflared and native packages; rebuild venvs/npm native addons. Do not rsync Homebrew/Nix store/venvs/node_modules as executable environments. Keep OpenClaw data schema compatible before considering upgrades. |
| Desktop host | desktop.host.enabled=true; OpenClaw mac command links into the macOS app. | macOS desktop-control binary cannot run in Linux. Demonstrate Linux desktop bridge, GUI interaction, browser control and human takeover before declaring full equivalence. A macOS bridge retained remotely is a hybrid exception. |
| Pass/GPG secrets | secrets provider source=exec, [resolver](<ssh://nik@192.168.1.174/Users/nik/.openclaw/bin/openclaw-pass-resolver>) uses pass; environment-name allowlist includes GNUPGHOME/PASSWORD_STORE_DIR/PASS_BIN. GPG and password-store locations exist. | Portable in principle, but encrypted-store/key/passphrase provisioning and unattended decryption require an explicit secure plan. Values were neither printed nor decrypted by this audit. Changing paths alone is insufficient. |
| Keychain/browser cookies | Brave profile helper contains a Keychain reference; work browser profiles exist in OpenClaw and external Brave/Chrome homes. | Do not assume macOS cookie encryption/Keychain material is Linux-portable. Prefer new dedicated Linux work profiles and supervised login/reauthorization, or retain a Mac bridge until replaced. No cookie database content was opened. |
| LinkedIn native bridge | Deployed bridge uses Node20; [project package metadata](<ssh://nik@192.168.1.174/Users/nik/pro/GR/gr-linkedin-helper/package.json>) requires Node >=20 <21, unlike gateway Node24. | Maintain per-service runtime versions, reinstall native messaging/browser integration, prove functionality with a non-production test before switching the real browser consumer. |
| Mail | [Native Gmail runner](<ssh://nik@192.168.1.174/Users/nik/obsidian-vault/.opencode/skills/gmail-inbox-processing/scripts/native-mail-run.py>) has Gmail API references; Node bridge calls Python runners. | The word native does not prove Apple Mail automation. OAuth/browser grants may still need reauthorization. No mail API call or mail content was read. |
| Calendar | [Calendar-stat project](<ssh://nik@192.168.1.174/Users/nik/pro/GR/gr-cal-stats/>) metadata/code has Google Calendar API references. | Not evidence of Apple Calendar dependence. Tokens/grants require secure preservation/renewal. |
| Direct Apple Mail/Calendar automation | No osascript/AppleScript/EventKit/ScriptingBridge markers were found in the scoped work-vault production scripts/skills scans; broader GR source scans did not establish a live Apple Mail/Calendar daemon. | **Not observed, not proven absent globally**: GUI app automation, unscanned user scripts and desktop features remain a gate. Installed apps/capabilities alone are not evidence a workflow uses them. |
| Absolute paths / launchd | Many macOS home/Homebrew paths, launch-agent programs, local sockets and symlinks are present. | Map to a dedicated Linux work user/home and systemd services/timers; review bind addresses, restart policy, schedule timezone and work/personal A2A links. No network migration is authorized by this audit. |

## Staging, downtime assumptions and rollback

This is a future authorized plan, **not commands executed by the audit**.

1. Build a clean dedicated Linux guest and work-only identity/profiles. Install x86_64 dependencies with required per-service Node versions. Seed data while M1 continues serving; include repositories, local history, SQLite companion stores, deployed bridge assets and reviewed symlink targets. Do not clone the personal VM/home.
2. Keep production Telegram/A2A ingress, mail/send capabilities, GR News workers and scheduled tasks disabled on the staging guest. Test restored copies with isolated/explicitly non-production fixtures; do not grant a second writer merely to check startup.
3. Rehearse logical PostgreSQL restore, OpenClaw SQLite/state recovery, Linux GUI/browser/human takeover, secret-provider unlock and all essential workflows. Separately validate reachability to retained M1 inference only under future explicit authorization; no inference was attempted here.
4. In an agreed window, recheck in-flight work, drain/stop **all** owning work writers/consumers on M1 and prevent old auto-restart. Include gateway timers/channel ownership, both GR News workers, web writes, PostgreSQL consistency and any bridge-owned actions. Leave unrelated/personal services and llama-server alone.
5. Perform final delta plus consistent application SQLite snapshot/export (including all relevant WAL data) and logical PostgreSQL export/import. Never copy a live SQLite main file alone or raw running PostgreSQL directory across OS/architecture.
6. Start exactly one new owner per queue/channel/timer; verify internal readiness before authorizing external business actions. Check missed timers and failed delivery entries individually rather than replaying everything. Keep original M1 data and rollback path until acceptance.
7. For rollback, fence the new writers first. Reconcile any writes/deliveries made after switch before re-enabling old owners; otherwise rollback is a stale-state restore with duplicate-action risk, not zero-loss recovery.

**Assumptions behind the estimate:** complete staging/auth/GUI rehearsal before outage; compatible package/schema versions; final mutable delta modest relative to initial seed; no unexpectedly long running job; PostgreSQL export/import and acceptance each take minutes rather than hours; a usable network path and separate backup/restore test already exist. No transfer benchmark, DB dump/restore timing or Linux GUI rehearsal was performed.

Planning formula:

~~~text
outage = drain + final_delta / measured_effective_throughput
       + consistent_database_export_restore + startup + acceptance
~~~

Illustrative **unmeasured** transfer assumptions: at 20–60 MiB/s effective throughput, initial 102.57 GiB bulk data alone is about **29–88 minutes**; a 1–5 GiB final delta is about **17 seconds–4.3 minutes**. The many small files, permissions, encryption, checksums, DB exports and Wi-Fi contention can make wall-clock time materially longer. Initial seed and dependency installation are advance preparation, not inherently downtime. If final delta is 20 GiB, it alone is roughly 6–17 minutes at those assumed rates. Hence the provisional **30–60 minute** server cutover and **1–2 hour** complete-work reserve are plausible only after rehearsal, not derived from a measured migration.

## Explicit remaining gates

- Define full work scope versus archive/media/scratch exclusions; do not erase or omit the 32 GiB workflow work tree based on its name.
- Verify Linux replacement for macOS host-control/GUI and work browser cookies/auth; otherwise accept a documented hybrid rather than claiming M1 is inference-only.
- Resolve desired ownership of the two GR News consumers, LinkedIn deployed bridge, indexary dependency, A2A link and historical helper launch agents.
- Reconcile stale/error cron declarations and failed deliveries; preserve the three disabled schedules.
- Measure VM peak RAM during representative browser/agent concurrency; 8 GiB is a minimum background floor, not a desktop guarantee.
- Rehearse PostgreSQL logical restore and complete OpenClaw/agent session recovery; test backup independently of the shared thin pool.
- Measure real data-transfer throughput and final-change rate; then book the outage window and rollback deadline.

Only this audit document was written by this delegated audit. M1 production and its configuration remain unchanged.
