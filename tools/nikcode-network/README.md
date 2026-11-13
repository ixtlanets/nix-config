# Nik Code subscription source

Reviewed source snapshot from `zenbook:~/.local/share/nikcode-network` as of
2026-11-06. The live workspace remains at that path; committing this directory
does not deploy it or change running clients.

- `src/worker.js` renders profiles and authenticates subscription fetch tokens.
- `scripts/manage.py` reads encrypted state from pass and manages the Worker.
- `scripts/t14s_client.py` is the installed t14s subscription adapter source.
- `test/` covers the renderer and the secret-binding projection.

Secrets, private state, exported profiles, QR codes and certificate archives stay
outside Git. The catalog remains in `pass nikcode.xyz/config/service-state` on
zenbook. Never put its decrypted JSON into this directory.

From this directory:

```sh
node --test test/*.test.js
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s test -p 'test_*.py'
```

Only deploy from a reviewed workspace with the current pass state. `publish`
updates code while preserving bindings; `deploy` has broader infrastructure
effects. See [the operational runbook](../../docs/nikcode-network.md).

The t14s DNS guard and bounded policy installer are maintained separately under
[`scripts/t14s-vpn-dns.py`](../../scripts/t14s-vpn-dns.py) and
[`scripts/t14s-public-ipv4.py`](../../scripts/t14s-public-ipv4.py) at repository root.
Do not rerun the one-off installer against an already accepted backup directory.

## Two-device SFI pilot

The pilot requires SFI core **1.14 or later**. It uses a separate `PILOT_CONFIG`
Worker secret; the legacy `SERVICE_CONFIG` catalog and responses remain unchanged.
Pilot URLs are `/s/p_<43 URL-safe characters>` (optionally `/sing-box-ios`). The
different token length prevents revoked or malformed pilot requests from using
legacy credentials. Missing/invalid pilot bindings return 503; revoked devices
and unknown tokens return 404. Every device/server pair has a distinct UUID.

Prepare a private specification outside Git with `magic_dns_suffix` and `nodes`.
Each node requires `id`, `enabled`, `protocol` (`vless`), `host`, `port`,
`server_name`, `public_key`, and `short_id`. Use the independently accepted
servers' actual public Reality parameters. **No Reality private key belongs in
this specification or the Worker.** Other node fields are excluded by projection.

```sh
python3 scripts/manage.py pilot-init --input /private/pilot-spec.json --output /private/pilot-state.json
python3 scripts/manage.py pilot-validate --input /private/pilot-state.json
python3 scripts/manage.py pilot-project --input /private/pilot-state.json --output /private/PILOT_CONFIG.json
python3 scripts/manage.py pilot-users --input /private/pilot-state.json --node france --output /private/france-users.json
python3 scripts/manage.py pilot-export --input /private/pilot-state.json --label nik-iphone-primary --output /private/primary-local.json
python3 scripts/manage.py pilot-export --input /private/pilot-state.json --label nik-iphone-primary --node frankfurt --output /private/primary-fallback.json
```

These actions make no network changes. Outputs use mode 0600, must remain outside
the repository, and never overwrite existing files. Save the full state encrypted
as `pass nikcode.xyz/config/pilot-state`; retain an encrypted backup before edits.
The projection strips raw fetch tokens and operator revocation metadata and
enforces a 5000-byte binding budget. Keep any future device secrets in encrypted
state, never command arguments or logs.

The two generated device IDs are `nik-iphone-primary` and `nik-iphone-spare`.
Profiles contain a VPN-only URLTest pool, with existing connections retained
when latency changes the selected node. All public traffic outside declared
exceptions goes through this pool; DIRECT is never a pool member. This defines
routing while SFI is running, not an operating-system kill switch after SFI stops.
The exact subscription hostname has bootstrap DNS and a TCP/443 DIRECT route.
LAN/private addresses, `.local`/`.lan`/`home.arpa`, Russian domains and Russian IP
ranges use DIRECT. Additional known Russian domains can be supplied in
`ru_domains`. An unknown non-Russian-suffix domain needs working proxy DNS before
its Russian destination IP can be classified during a total pool outage.

Integrated Tailscale uses a stable, distinct hostname/state directory per device,
with interactive login and no embedded auth key. Tailnet routes and MagicDNS
precede private-address DIRECT and public AAAA suppression. Authenticate the
phone to the intended tailnet in SFI; the separate iOS Tailscale VPN cannot run
concurrently. The profile does not accept subnet routes or a Tailscale exit node.

The pilot embeds public Russian GeoIP rules from
[SagerNet/sing-geoip](https://github.com/SagerNet/sing-geoip) in
`src/geoip-ru.js`, so profile startup requires no rule-set download. Its header
records source URL, fetch date, binary SHA256 and decompiler version; the upstream
license is retained in `src/geoip-ru.LICENSE`. Refresh this generated public data
deliberately. Existing legacy profiles retain their existing remote rule sets.
`publish` includes both JavaScript modules and preserves existing secret bindings.

An optional per-device `rule_set_mode: "remote"` makes the Remote response small
(the S22 profile is below 8 KiB), while omission or `"inline"` preserves the full
inline response. Enable it on the S22 canary first without changing its URL,
credentials, Tailscale state directory or cache ID. The default remote variant downloads
a commit-pinned public SagerNet RU binary through the VPN-only pool using the
explicit 1.14 HTTP client. The approved own-host variant below uses DIRECT.
Its tag and exact URL stay stable so the cached rules
can be reused. `pilot-export` always embeds the full inline rules, including when
exporting a device whose normal subscription uses remote rules.

Remote rules persist with `experimental.cache_file.enabled` and the device's
stable `cache_id`. A valid cached set is loaded before a network fetch; failed
background updates retain it. Without a valid cached set or `initial_path`, an
unreachable initial download prevents core startup. Thus a first start needs a
reachable rule source (and a working VPN node for the upstream variant);
app-data deletion, a changed rule URL or a changed cache namespace
can require another first download. Keep the full Local fallback prereceived.
Starting an inline Local profile does not itself seed the remote rule-set cache.
These behaviors follow the
[1.14 remote rule-set loader](https://github.com/SagerNet/sing-box/blob/v1.14.3/route/rule/rule_set_remote.go)
and [cache configuration](https://sing-box.sagernet.org/configuration/experimental/cache-file/).

### Own HTTPS subscription backend

`src/server.js` is a Node 24 adapter for a TLS reverse proxy. It imports the same
Worker authentication and renderer, but receives **only** the pilot projection.
It cannot serve the 22 legacy subscriptions. Install `package.json` and
`src/{server,worker,geoip-ru}.js` preserving their relative paths. Copy the public
`data/geoip-ru.srs` and upstream `src/geoip-ru.LICENSE` alongside the deployment.
No npm dependencies are required.

```sh
node /opt/nikcode-subscriptions/src/server.js \
  /etc/nikcode-subscriptions/pilot.json \
  /opt/nikcode-subscriptions/geoip-ru.srs 8787
```

The listener binds **127.0.0.1 only**. Caddy serves
`https://subscriptions.nikcode.xyz` and proxies to this listener, preserving
Host. The adapter accepts this hostname, its explicit HTTPS port, and its own
loopback address. It normalizes pilot requests to the Worker's canonical host
internally. Do not enable request/access logging containing private URL paths.
The adapter itself never logs requests or configuration.

The private file is `pilot_projection(state)`, not the complete operator state:
raw fetch tokens are rejected. Use root:service ownership with mode 0640, or an
owner-readable 0600/0400 credential file. World access and group write/execute
are rejected. The file is read on every request, so atomic replacement applies
catalog updates and revocation without restarting. It must fit the existing
5000-byte projection budget. Add these delivery settings to encrypted state
before projecting:

```json
{
  "subscription_hosts": ["config.nikcode.xyz", "subscriptions.nikcode.xyz"],
  "rules_url": "https://subscriptions.nikcode.xyz/rules/geoip-ru-bdca5cdb44cdcf0940001e5952386822a6f4ffa8b2c8eea00340aa6f585c7f9d.srs"
}
```

These options are strict: only the two owned hostnames and the exact immutable
HTTPS rule URL are allowed. Missing options preserve existing Worker profiles.
The own adapter requires both own-host settings. Profiles get narrow TCP/443
DIRECT and bootstrap-DNS exceptions for both subscription names. Downloads from
the exact approved own rule URL also use DIRECT with bootstrap DNS, so loading
the initial RU rules does not require either VPN node. Other public traffic
retains its VPN-only final route. The default upstream SagerNet URL still uses
the VPN pool. Local exports remain inline.

`/healthz` returns 200 only with a valid private projection. Pilot GET/HEAD uses
the existing `/s/p_<token>` paths. All legacy token paths return 404. The public
hash-named rule path returns exactly **50096 bytes**, SHA256
`bdca5cdb44cdcf0940001e5952386822a6f4ffa8b2c8eea00340aa6f585c7f9d`, with
immutable caching, ETag and Content-Length. The adapter verifies this public
binary before listening. Its immutable source is
[SagerNet commit eb32cd6](https://raw.githubusercontent.com/SagerNet/sing-geoip/eb32cd6ed4a16fcb3bf9a36ccebf28e45716ae84/geoip-ru.srs).

Only after own TLS, profile and rule downloads pass, optionally set the
Cloudflare binding `PILOT_ORIGIN` to exactly
`https://subscriptions.nikcode.xyz`. Matching pilot GET/HEAD requests receive a
small no-store **307**, preserving their entire path and personal token. The own
adapter authenticates the redirected token; it receives no `PILOT_ORIGIN`, so
there is no redirect loop. Invalid origins fail closed. Legacy URLs, public
pages and all 22 legacy response bodies remain unchanged. No binding means the
existing pilot-rendering behavior. Test native refresh through an old URL before
enabling the redirect for other devices.

Deploy server users and verify each independent physical-uplink path first.
Publish reviewed Worker code, then update **only** the separate `PILOT_CONFIG`
secret with the validated projection. Do not invoke broad `deploy` to update a
pilot binding. Test both stable personal URLs, import native SFI Remote profiles,
enable hourly updates, and keep each phone's prereceived Local fallback available.
Local exports contain full routing/DNS/GeoIP and do not auto-update.

### Device revocation

```sh
python3 scripts/manage.py pilot-revoke --input /private/pilot-state.json --label nik-iphone-primary --output /private/pilot-state-revoked.json
```

This marks fetch disabled and every node's `server_revocation` as
`pending-removal`. It does **not** claim server revocation succeeded. Project and
publish the new binding, then regenerate each server's `pilot-users` list from
the revoked state, validate and apply it to the additive pilot service only.
Confirm the removed UUID is rejected on **every** server while the other phone
continues working. Record completion in encrypted operator state and back it up.
Previously downloaded profiles retain access until this server-side step is
complete. Old Warsaw, London and existing production services are outside this
workflow.

### Owner rollout — 2026-11-12

Native S22 acceptance exposed a gap in the initial workstation checks: the
first Remote import cannot use the profile's DNS/routing before downloading it.
On that phone's Wi-Fi path, Cloudflare returned HTTP200 but stopped after exactly
16,384 encoded body bytes, both without compression and with raw gzip. The
361,312-byte inline profile never reached EOF; `/healthz` completed in 326ms.
This establishes the transfer failure, not the identity of the limiting party.

Personal delivery now runs on `https://subscriptions.nikcode.xyz` (UK,
`91.108.225.14`), DNS-only with trusted Let's Encrypt TLS. The Node/Caddy bundle is
in `hosts/uk/ubuntu/subscriptions/`; both services are enabled. Personal Remote
profiles are about 6.6KB. The immutable 50,096-byte RU rule file is served from
the same own origin and fetched through DIRECT with bootstrap DNS, so its initial
download does not require working VPN nodes. Local/fallback exports retain inline
rules. All three personal compatibility URLs retain their tokens and redirect
from Cloudflare to the own origin; all 22 legacy response bodies still match.

The connected Galaxy S22 (`nik-galaxy-s22`, sing-box 1.14.4) passed native Remote
creation with VPN off, Wi-Fi/cellular HTTPS egress, and native cellular refresh
with VPN off. Its actual one-minute URLTest switched France to Frankfurt in
32 seconds. With both new proxy listeners stopped, fresh foreign Chrome fetch
failed, native subscription refresh and profile restart succeeded, and fresh
RU navigation returned HTTP200 without browser cache/service worker. Services
were restored; the selected Remote `NikCode-S22` remains running. Integrated
Tailscale authorization and acceptance on the actual iPhones remain outstanding.
Private evidence is in `~/.local/state/nikcode-singbox-pilot-20261112/s22/`.

The spare iPhone subsequently imported the Remote profile but failed to start:
its packet-tunnel router timed out connecting to the own rule-file server over
`en0` during initial rule-set loading. Unlike Android acceptance, this exposed a
remaining startup dependency. `nik-iphone-spare` now receives inline rules again
from the own origin: 361,396-byte HTTP200 response, 10,894 CIDRs, no rule-file URL,
validated with core 1.14.4. Its token, node membership and UUIDs are unchanged.
The owner confirmed that the spare iPhone now starts and provides Internet.
The primary iPhone has also been switched to inline delivery (361,402-byte
complete response, core 1.14.4 validation passed). The owner then confirmed that
both iPhones work, including cellular. S22 remains in its previously accepted
remote-rule mode. No tokens, UUIDs, node membership or services changed during
these mode switches. Evidence is private in
`~/.local/state/nikcode-singbox-pilot-20261112/spare-inline-acceptance/`.

The first deployed pool is France `194.87.166.59:443` and Frankfurt
`31.58.85.163:34443`, both running the additive
`nikcode-singbox-pilot.service` with pinned sing-box 1.14.4. Existing AWG,
Docker, Tailscale, Warsaw and London services are preserved. Both new units are
enabled. Frankfurt is a temporary independent reserve pending renewal and
acceptance of another node.

Encrypted operator state is `pass nikcode.xyz/config/pilot-state`; separate
Reality identities are `pass nikcode.xyz/config/pilot-node-keys`. Personal
subscription entries are `nik-iphone-primary` and `nik-iphone-spare` beneath
`nikcode.xyz/config/`. Private delivery files and QR codes are under
`~/.local/share/nikcode-network/pilot-delivery-20261112/`. Do not copy these
files into Git.

Integration checked both devices' credentials against both servers using
certificate-verified HTTPS with outer connections bound to physical `wlo1`.
An adaptation of the issued profile to a local SOCKS listener passed automatic
France-to-Frankfurt fallback; with both new services stopped, foreign HTTPS
failed while the personal subscription and `ya.ru` remained accessible directly.
The harness used a 10-second URLTest interval; delivered profiles use one minute.
Old service/container PIDs and start times remained unchanged, and all 22 old
subscription bodies matched their captured baseline after initial publication.
Evidence is private under `~/.local/state/nikcode-singbox-pilot-20261112/`.
Server-side device revocation was also exercised on both nodes: removing the
primary phone's UUID rejected that phone while the spare remained usable. The
original configurations and primary access were restored after each check.

DIRECT outbounds and the integrated Tailscale endpoint explicitly use the
bootstrap DNS resolver. Otherwise they inherit the proxied default resolver and
subscription updates fail during a pool outage. The opt-in regression check
exercises this with public fixtures and unavailable loopback nodes, and removes
the resolver override as a negative control:

```sh
python3 test/check-outage-bootstrap.py --sing-box /path/to/sing-box --interface wlo1
```

Device acceptance remains: import each Remote QR into the matching iPhone,
verify Wi-Fi and cellular, authorize the integrated Tailscale endpoint, and
verify update application plus tailnet identity persistence. SFI automatic
refresh is subject to iOS background scheduling. Russian domains outside the
configured suffix/list still need proxy DNS before GeoIP can classify their
destination during a complete outage.

Rollout order: both owner's iPhones, then all owner's computers including
Proxmox workloads, then active users after inventory. Frankfurt/Goar renewal is
authorized but secondary to the working configuration; existing non-renewal
requests and cancelled invoices must be checked before treating payment as a
completed renewal.
The attempted Hosting-VDS login was blocked by an actual verification-code
error. Current billing and cancellation status remain unverified until the
owner completes reCAPTCHA; no support messages or payments have been sent.

### Goar's two iPhones — 2026-11-12

Before computer rollout, the owner requested two Goar phones and confirmed both
use sing-box 1.14 or newer. `goar-iphone-primary` and `goar-iphone-second` each have
an independent subscription token and distinct UUID on each node. Both receive
inline RU rules and no integrated Tailscale endpoint. Private QR, Local/fallback
and verification files are in
`~/.local/share/nikcode-network/goar-phones-20261112/`.

After explicit permission for possible brief reconnects, Frankfurt was updated
and verified before France. All four new physical-uplink HTTPS paths and the
existing primary credential through both nodes passed. Old protected services
and route/firewall baselines stayed unchanged. Both own-origin subscriptions
returned complete profiles and passed core 1.14.4 checks; the three earlier
personal response bodies stayed identical. Actual Goar phone acceptance remains
pending. Computers remain deferred at the owner's request.

### Andrey Maksimov's iPhone — 2026-11-12

`andrey-maksimov-iphone` is the sixth personal device, with its own token,
per-node UUIDs, inline rules and no integrated Tailscale. The new secret entry is
`pass nikcode.xyz/config/pilot/andrey-maksimov-iphone`; existing legacy Andrey
iPhone/Mac entries are retained. Private QR, Local/fallback and verification
files are in `~/.local/share/nikcode-network/andrey-maksimov-iphone-20261112/`.

Rolling activation used Frankfurt first, with new and existing credential
checks before France. Both new physical-uplink paths and four continuity
checks passed; protected services and network baselines were preserved.
The own-origin profile returned complete HTTP200, passed core 1.14.4 validation,
and left all five earlier profile bodies unchanged. France had initial
unclassified probe/access failures followed by successful fresh checks; no
underlying cause or repair is asserted. Native phone acceptance is pending.
