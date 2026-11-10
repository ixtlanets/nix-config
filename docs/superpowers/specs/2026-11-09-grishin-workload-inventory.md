# Grishin workload inventory — zenbook

**Read-only assessment: 2026-11-09, 00:11–00:20 MSK.** Only this report was authored. No migrations, service/container actions, application launches, configuration changes, database connections, OAuth refreshes or Telegram API calls were performed. Secret values and mailbox/task payloads are omitted from this report.

## Decision summary

- **The principal Grishin agent is not proven to run on zenbook.** The local [agent-mail contract:5–7](</home/nik/gr-agent-mail/README.md#L5-L7>) assigns default Grishin Robotics work to **m1max**, while zenbook defaults to the **personal vault**. This is documented intent, not a remote runtime check. Current m1max ownership/queues remain a capacity and cutover gate.
- **Previous VM103 transfers deliberately excluded Grishin.** The [worktree exclusion:1](</home/nik/migration/pro-worktrees-vm103-2026-11-07/excludes.txt#L1>) excludes the GR tree. The [Brave audit:7–11](</home/nik/migration/brave-profile-2026-11-07/audit.md#L7-L11>) identifies Profile 1 as **GR**; [independent verification:5](</home/nik/migration/brave-profile-2026-11-07/verification.md#L5>) confirms the target contains only Personal/Default.
- **No directly attributable local GR daemon was found.** This is not proof of an empty remote queue or zero downtime. Work source, browser identity and external-service access are the strongest identified local dependencies.
- Identified allocation: GR tree **1,852,063,744 bytes (1.73 GiB)** + GR browser **594,624,512 bytes (0.55 GiB)** + coordinator **30,855,168 bytes** + mailbox **12,288 bytes** = **about 2.31 GiB**, before OS, images, headroom, backups and unknown remote data. Much is rebuildable cache/dependencies. These measurements do **not** establish VM RAM/vCPU requirements.

## Runtime evidence

Observed using systemctl user/system services and timers, Docker ps/inspect, ss listening metadata, and scoped /proc process-cwd symlinks. Final sample: **2026-11-09T00:19:54+03:00**, host **zenbook**. These are snapshots, not continuous monitoring.

| Observation | Interpretation |
| --- | --- |
| No readable process cwd under GR, work, mailbox or coordinator | No directly attributable process found. Final scan could not read **522** process cwd entries; cwd also misses processes launched elsewhere. |
| No Grishin/news/dmarc-named service detected; **0 user timers** | No local systemd GR scheduler identified. Does not exclude in-process or cloud schedulers. |
| Hermes gateway **active/running**, PID 2450566, cwd [personal Hermes home](</home/nik/.hermes>), unit **disabled** | Disabled does **not** mean stopped. Preserve it; do not clone its Telegram identity into a work VM. Start timestamp was 00:12:44 MSK, illustrating runtime changes during assessment. |
| Hermes dashboard, OpenClaw gateway and tg-userbot units inactive/dead | Unit observations only, not proof that all independent consumers or historical state are absent. |
| **23 running Docker containers**, none identified as GR/news/dmarc; no matching named volume identified | MetaArena/Supabase, invoice demo, mail-exchange storage and personal Bot API are not automatically Grishin capacity. |
| Personal Telegram Bot API: loopback **8081**, persistent [data mount](</var/lib/telegram-bot-api>), owned by [personal Compose directory](</home/nik/.hermes/tg-bot-api>) | API server is not itself a polling consumer. Keep personal infrastructure separate. |
| Invoice app has host networking and Compose ownership [mail-processor](</home/nik/pro/mail-processor>) | Separate invoice demo, not proven GR. [README:3–15](</home/nik/pro/mail-processor/README.md#L3-L15>) describes SQL/S3/LLM and port 3000. Do not absorb or stop it on name similarity. |
| Final listeners: host **3000**, loopback **8081**, host **8082**; no **5432**, **8080**, **9222** in final sample | Port 3000 ownership not proven by socket metadata. Earlier 9222 belonged to Brave but disappeared before final sample. A listener is not GR attribution. |
| Crontab utility absent; no cron spool; hourly directory contains only snapper | Traditional user crontab could not be enumerated. Application/cloud schedulers remain possible. |

The [Hermes unit:15–25](</home/nik/.config/systemd/user/hermes-gateway.service#L15-L25>) specifies automatic restart and a 70-second stop timeout. No stop/start was attempted. Personal/shared services must not become collateral cutover targets.

## Persistence inventory

Sizes are allocated du -sx -B1 measurements, rounded to MiB. They include repositories and build products, not only business records. No database rows, mail messages, cookies or history were queried; credential-bearing files were limited to configuration/dependency inspection, with values excluded from this report.

| Component | Local allocation | Persistent-state interpretation |
| --- | --- | --- |
| [GR tree](</home/nik/pro/GR>) | **1,766 MiB**, 16 projects | Preserve local work/repositories; do not treat every project as a running service. |
| [gr-news](</home/nik/pro/GR/gr-news>) | 425 MiB; build cache 390 MiB; [local PostgreSQL directory](</home/nik/pro/GR/gr-news/data/postgres>) **0 allocated bytes** | Current [environment:10–11](</home/nik/pro/GR/gr-news/.env#L10-L11>) points DATABASE_URL and DIRECT_URL to **managed Supabase**. Remote DB/queue size and activity unknown. [Compose:2–12](</home/nik/pro/GR/gr-news/docker-compose.yml#L2-L12>) nevertheless defines Postgres16/host5432 with bind-mounted data; web uses host3000. Empty local files are not the business dataset. |
| [gr-newsletter](</home/nik/pro/GR/gr-newsletter>) | 729 MiB; dependencies 371 MiB, build cache 271 MiB | Draft lives in browser localStorage under newsletter-markdown: [page:34–40](</home/nik/pro/GR/gr-newsletter/app/page.tsx#L34-L40>). Source transfer misses the draft and browser origin. |
| [gr-dmarc](</home/nik/pro/GR/gr-dmarc>) | 246 MiB; GeoIP 133 MiB, Git 94 MiB | [Compose:2–19](</home/nik/pro/GR/gr-dmarc/docker-compose.yml#L2-L19>) defines Postgres15 named volume db, web and a Gmail worker. No corresponding active container/volume identified. Current database URL is loopback; authoritative data location unverified. OAuth token exists, 546 bytes. |
| [LinkedIn helper](</home/nik/pro/GR/gr-linkedin-helper>) / [agent](</home/nik/pro/GR/gr-linkedin-agent>) | 88 MiB / 316 KiB | Browser-extension scraping/autopilot and logged-in LinkedIn identity. Helper environment references managed Supabase. Agent requires Node22/Bun, LLM access and a Playwright extension token: [requirements:50–61](</home/nik/pro/GR/gr-linkedin-agent/README.md#L50-L61>). |
| [GR Brave profile](</home/nik/.config/BraveSoftware/Brave-Browser/Profile%201>) | **567 MiB** | Work browser state retained locally; currently open profile/active browser tasks not established. Preserve OS-backed decryption and identity, not merely files. Prior [audit:32–37](</home/nik/migration/brave-profile-2026-11-07/audit.md#L32-L37>) covers shared state, extensions, sessions and keyring dependency; completed migration was Personal-only. |
| [gr-firestore](</home/nik/pro/GR/gr-firestore>) / [gr-processor](</home/nik/pro/GR/gr-processor>) | 7 MiB / 2.2 MiB | Cloud Firestore/storage and CRM integrations; source schedules do not prove local processes or deployed cloud status. |
| Other GR projects | startups-sight 135 MiB; website 61 MiB; founder directory 51 MiB; cbhelper 20 MiB; remainder small | Mainly code/extensions/sites. Only discovered GR SQLite is founder-directory **Wrangler/Miniflare cache**, main file 4 KiB plus WAL/SHM; not an established business DB. No scoped GR files matching *.db found. |
| [Mailbox](</home/nik/gr-agent-mail>) / [coordinator](</home/nik/hermes-work-coordinator>) | 12 KiB / 29 MiB | Historical mailbox files not opened. Coordinator is not itself a scheduler: [README:33–42](</home/nik/hermes-work-coordinator/README.md#L33-L42>). |

The separate [work tree](</home/nik/work>) is about 9.6 GiB; 8.8 GiB is LBRAND, documented as GOAR in its [instructions](</home/nik/work/LBRAND/AGENTS.md>). Dashboard (135 MiB) and img2stl (692 MiB) are not proven GR workloads and are not included in GR allocation. Adjacent applications need explicit ownership before inclusion.

## Queues and duplicate-execution risk

- **News:** database-backed LIGHT/BROWSER queues. [Claiming:135–154](</home/nik/pro/GR/gr-news/lib/tasks/worker-runner.ts#L135-L154>) conditionally changes PENDING to RUNNING within a transaction. This reduces competing claims but is not end-to-end exactly-once execution. [Heartbeat/stale threshold:24–25](</home/nik/pro/GR/gr-news/lib/tasks/worker-runner.ts#L24-L25>) and [requeue:76–84](</home/nik/pro/GR/gr-news/lib/tasks/worker-runner.ts#L76-L84>) can requeue work after **15 minutes**. Fence old workers before restore/restart. No live Supabase pending/running counts obtained. [Development configuration:82–85](</home/nik/pro/GR/gr-news/devenv.nix#L82-L85>) starts web **and worker**; launching development is not a harmless smoke test.
- **DMARC:** [worker:15–19](</home/nik/pro/GR/gr-dmarc/scripts/worker.ts#L15-L19>) requests Gmail read/modify scopes, persists OAuth state and defaults to **30-minute / batch10** polling. [Scheduling:88–93](</home/nik/pro/GR/gr-dmarc/scripts/worker.ts#L88-L93>) is inside the process, not systemd. Two workers can duplicate ingestion/Gmail effects. Mailbox backlog was not queried.
- **Firestore:** source defines daily notes digest at **01:00 UTC** and missing-file processing **every four hours**: [daily function:76](</home/nik/pro/GR/gr-firestore/functions/src/index.ts#L76>) and [four-hour function:183](</home/nik/pro/GR/gr-firestore/functions/src/index.ts#L183>). Treat as cloud deployment ownership. Do not redeploy or add equivalent VM cron jobs during a file copy.
- **LinkedIn:** [autopilot:169–170](</home/nik/pro/GR/gr-linkedin-helper/README.md#L169-L170>) navigates a queue and waits for scraping completion. An authorized work-browser procedure must drain/pause it; do not run the same account/queue from two desktops.
- **Coordinator/Hermes:** pending state belongs in private profile plugin data; project artifacts live in project-specific work directories. Six JSON artifacts exist in [personal plugin data](</home/nik/.hermes/plugin-data/two-step-work>), **not classified as active jobs**. Bounded one-line reads prevented complete safe metadata parsing. Personal [cron state](</home/nik/.hermes/cron>) and multiple SQLite/WAL stores also exist; GR ownership/backlog not established. Copying the coordinator checkout is insufficient, but cloning all personal agent state is the wrong ownership boundary.
- **Telegram:** [mailbox contract:23–38](</home/nik/gr-agent-mail/README.md#L23-L38>) expects both hosts to check work and send summaries; that does not establish bot identities or authorize duplicate consumers. No Grishin-specific local polling/webhook ownership verified. Fence the actual old consumer/scheduler before another instance; preserve the active personal gateway.

## Authentication, browser and network dependencies

Paths identify dependencies; values must not enter reports, command lines or Git.

- [News environment](</home/nik/pro/GR/gr-news/.env>): database URLs, OpenRouter, NextAuth and Google OAuth. [Auth:20–22](</home/nik/pro/GR/gr-news/lib/auth.ts#L20-L22>) uses the Google client. Local base-URL/callback configuration requires review if origins change.
- [DMARC environment](</home/nik/pro/GR/gr-dmarc/.env>), [local override](</home/nik/pro/GR/gr-dmarc/.env.local>) and [OAuth token](</home/nik/pro/GR/gr-dmarc/token.json>) are secret dependencies. Its [worker:16–17](</home/nik/pro/GR/gr-dmarc/scripts/worker.ts#L16-L17>) uses the token and localhost:8080 OAuth redirect.
- [Newsletter environment](</home/nik/pro/GR/gr-newsletter/.env>), [helper environment](</home/nik/pro/GR/gr-linkedin-helper/.env>), [agent environment](</home/nik/pro/GR/gr-linkedin-agent/.env>) and existing [GR MCP configuration](</home/nik/pro/GR/.cursor/mcp.json>) require protected handling. MCP values were not inspected. Browser drafts, extension stores and identity require the intended profile, origin and OS keyring; cookie/login/history contents were not read.
- [Processor environment:1](</home/nik/pro/GR/gr-processor/.env#L1>) and [legacy entrypoint:7](</home/nik/pro/GR/gr-processor/index.js#L7>) reference the absolute Firebase service-account path `/home/nik/.ssh/info-d4648-firebase-adminsdk-rhmpa-c8d123315f.json`. **That exact referenced file is absent.** The legacy entrypoint also contains an embedded credential: do not execute it or print source as a smoke test. Repair/rotation is a gate, not a functioning dependency proven present.
- Existing inspected environment files and DMARC token have mode **0644**. No permissions changed. Future transfer needs an explicitly authorized protected channel/access-policy review.
- Host tailscaled, zenbook-awg and AWG policy were active; VLESS sing-box unit inactive. [VPN policy:2–9](</etc/systemd/system/zenbook-awg-policy.service#L2-L9>) explicitly routes new zenbook internet connections through Goar and binds policy to AWG. The protected [AWG directory](</etc/zenbook-awg>) was not opened. [Sing-box directory](</etc/sing-box>) exists, but is not proof of an active GR path. Shared host VPN is not a dedicated Grishin appliance to clone or restart.

## Gates before a separately authorized cutover

1. **Identify actual Grishin ownership on m1max**, exact bot/consumer identity, deployed cloud schedules and authoritative Supabase/Firestore/DMARC stores. Obtain queue status/counts without exporting payloads. Zenbook alone cannot settle this.
2. **Separate work from personal state.** Preserve GR browser/work artifacts; do not transplant Personal/Default, every Hermes profile, personal Telegram identity or unrelated Docker stacks by default.
3. **Fence producers/consumers, drain running work, then snapshot consistently.** Never rsync live PostgreSQL files. Use a database-consistent export/snapshot if actually in scope. For SQLite-backed agent/browser state, use an authorized consistent backup or quiescence including WAL handling, not main-file-only copying. Personal SQLite stores are a separate ownership boundary.
4. **Validate browser decryption, OAuth, extension identity and connectivity** without automatically resuming scraping, Gmail polling, cloud cron or Telegram. Resolve/reserve ports 3000, 5432 and OAuth 8080 rather than assuming they are free or GR-owned.
5. **Resume only the selected new owner; retain fenced rollback.** Directory copying does not provide exactly-once execution. Work-browser pause and consumer handoff require explicit downtime approval. No measured downtime bound or zero-downtime claim is supported.

**Capacity conclusion:** evidence supports a work browser/development environment plus about **2.31 GiB** of identified source/profile/coordinator/mailbox allocation, not migrating every zenbook service. Additional RAM/vCPU, browser working set, images, remote databases and principal agent load remain unmeasured. Keep headroom; do not mistake an empty local database directory for the business dataset.

## Limits

After an initial migration glob encountered a mounted read-only tree and permission errors, subsequent migration inspection was explicit-file only; no broad home/mount recursion followed. Protected VPN paths and inaccessible process entries were not bypassed. One-line browser/plugin JSON could not be completely parsed through bounded text reads; no unverified parsing result is asserted. Traditional crontab inspection was unavailable. No remote host, cloud database, deployed function, Telegram webhook or Gmail state was queried. Source declarations, historical transfer evidence and current runtime observations are distinguished; none alone proves business readiness.
