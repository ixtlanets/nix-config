# Nik Code VPN network

> **Sanitized snapshot, 2026-11-06.** This document records the current
> production topology and the verified server/DNS migration outcome. It contains
> no public server IPs, credentials, deployable configuration, or secrets. The
> operational source of truth is private: `~/.local/share/nikcode-network` on
> `zenbook` and the private Vault documentation.

Reviewed subscription source is versioned under
[`tools/nikcode-network`](../tools/nikcode-network/README.md). The t14s policy
installer and DNS guard are under `scripts/`; their rollback regression tests
cover a stuck lock holder, process identity checks, per-interface IPv6 recovery,
and failure reporting. This source review does not claim a production rollback
was exercised. Private state and deployed recovery snapshots remain outside Git.

## Current roles and DNS

- `notes.nikcode.xyz` has a stable DNS-only A record pointing to the AdminVPS
  primary with TTL 60 seconds.
- AdminVPS Poland, plan **Start**, is the primary VPN server.
- The old Hosting-VDS Warsaw server remains online as rollback-only capacity. It
  has not been cancelled and must not be repurposed or removed while it is the
  rollback target.
- London is unchanged and remains a reserve/rollback hop. This migration did
  not change its proxy services.
- The Cloudflare Worker is independent of the VPN server migration.

Client profiles address the service by hostname, so changing DNS and reconnecting
moves them without a subscription refresh. Android SFA and the isolated zenbook
Naive pilot reconnected to the new primary. The main zenbook tunnel has not yet
reconnected and remains on its established old-Warsaw session; see
[Pending zenbook cutover](#pending-zenbook-cutover).

## Primary server

The primary runs Debian 13 with the following network path:

```text
client
  |
  | TCP 443
  v
HAProxy 3.0.11 (TCP SNI mux)
  |-- Naive SNI --> Naive-Caddy 2.11.7-naive2 on loopback:8443
  `-- Reality SNI -> sing-box 1.14.3 on loopback:8444

client -- VLESS/Reality legacy TCP 24443 --> sing-box 1.14.3
client -- HTTP TCP 80 --------------------> Naive-Caddy / ACME
```

The Naive-Caddy build is `klzgrad` version `2.11.7-naive2`. The existing Caddy
certificate and state were transferred to the primary. sing-box `1.14.3` serves
Reality behind HAProxy on loopback port 8444 and directly on public port 24443.

| Exposure | Purpose |
|---|---|
| Public TCP 22 | SSH administration |
| Public TCP 80 | HTTP and Caddy certificate operations |
| Public TCP 443 | HAProxy SNI mux for Naive and VLESS/Reality |
| Public TCP 24443 | Legacy direct VLESS/Reality listener |
| Loopback TCP 8443 | Naive-Caddy behind HAProxy |
| Loopback TCP 8444 | sing-box Reality behind HAProxy |

Naive carries TCP traffic. VLESS carries TCP and UDP traffic through both VPN
entry ports; 24443 is retained for legacy profiles. BBR is enabled with
`fq_codel`.

This migration did not add host-firewall hardening, and the collected state does
not document root password login as disabled. Do not describe the primary as
hardened without a new, explicit audit and change.

## SSH limitation and rollback access

Outbound TCP 22 from the AdminVPS network is observed blocked: connections to
both the old Warsaw server and `github.com:22` timed out, while
`github.com:443` worked. Public SSH destinations therefore cannot currently be
reached through this VPN exit. This observation does not remove the primary's
inbound public SSH listener.

The old management path was verified through unchanged London. `zenbook` uses
its London key only for the forwarding hop; the old-Warsaw key and pinned
known-hosts file remain local to `zenbook`. Obtain the old address from the
private Vault; never substitute an address copied from public documentation.

```bash
ssh \
  -o 'ProxyCommand=ssh -o BatchMode=yes -o ConnectTimeout=10 -i ~/.ssh/id_rsa ubuntu@london -W %h:%p' \
  -i ~/.ssh/id_rsa_1 \
  -o UserKnownHostsFile=~/.ssh/known_hosts-warsaw-pilot \
  -o StrictHostKeyChecking=yes \
  root@<old-warsaw-ip-from-private-vault>
```

## Encrypted state and backups

Only the following encrypted `pass` references may be used to locate credentials
and recovery state; this repository must not contain their values:

- `adminvps.ru`
- `adminvps.ru/root`
- `nikcode.xyz/entry/server-backup`
- `nikcode.xyz/entry/caddy-state-backup`
- `nikcode.xyz/config/service-state`
- `nikcode.xyz/config/iphone-legacy-2`
- `hosting-vds.com/warsaw/root`

The server backup contains the service configuration, site content, and BBR
configuration. The separate Caddy state backup is a `tar.xz` payload represented
as base64 with SHA metadata. Verify the recorded SHA before extracting or using
the archive. The transferred live Caddy state and both backups must be retained
while old Warsaw is the rollback target.

The full encrypted service state retains operator-only metadata, including the
label and raw token that are deliberately omitted from the Worker binding. The
public repository is not a recovery source and does not yet contain a deployable
AdminVPS bundle or its secrets.

## Cloudflare Worker and catalog

The independent Worker catalog has 22 enabled entries. Its first binding update
exceeded Cloudflare's size limit with error `10054`; that transaction rolled
back. The accepted `worker_state` omits the operator-only label and raw token,
reducing the binding from 5179 to 4680 bytes. The complete values remain only in
the encrypted `pass` state.

Verification after the accepted update passed 11 Python tests, 15 Worker tests,
and HTTP 200 checks for all 22 catalog entries.

### `iphone-legacy-2`

`iphone-legacy-2` is a JSON-only local-import profile for sing-box 1.11.4. It
uses the legacy DNS shape and VLESS/Reality with Firefox fingerprint and `xudp`;
it contains no Naive configuration. A real sing-box 1.11.4 binary passed config
checking, Google returned HTTP 204 through the profile, and the observed exit was
WAW/PL.

Import on the actual phone is still pending. The local JSON does not auto-update;
future server identity or profile changes require another private import.

### Public VPN traffic uses IPv4 (2026-11-06)

The published Worker now applies an IPv4-only public-traffic policy to its seven
sing-box JSON variants. Public AAAA queries handled by these profiles receive an
empty successful DNS answer (`NOERROR`); A queries remain available. The legacy
1.11 profile uses `rcode://success`. Routing permits private IPv6 and multicast
before promptly rejecting public IPv6, avoiding a delayed public IPv6 attempt.
This does not disable IPv6 in the operating system or remove Tailscale/LAN IPv6.

Desktop profiles resolve `ts.net` through Tailscale before the AAAA suppression
rule, retaining tailnet AAAA answers. TUN exclusions retain ULA, link-local and
multicast IPv6. Mobile and base profiles do not acquire a new Tailscale resolver;
arbitrary LAN AAAA queries sent through their proxy DNS are also suppressed.

The update passed 18 Worker tests and 11 Python tests, full configuration checks
with real sing-box 1.14.3 and legacy 1.11.4 cores, and DNS probes for all seven
JSON variants. All 22 live subscription URLs returned HTTP 200 after source-only
publication. These checks verify generated profiles, not receipt on every client.
Clients must refresh and apply the JSON; an existing offline import does not
auto-update. Raw Incy/Happ/Throne links and `/outbounds` contain proxy nodes only
and cannot enforce this DNS/routing policy.

The t14s main-host rollout was accepted under a 240-second rollback safeguard;
the rollback timer is now inactive. An initial attempt rejected an old propagated
profile during preflight before changing the host; the fresh profile then applied.
The host fix replaces the TUN's old `revert-resolved` start hook with link-scoped
DNS `198.19.0.2`, route domain `~.`, and `DNSOverTLS=no`: global opportunistic
DNS-over-TLS otherwise bypasses DNS hijacking. More-specific Tailscale DNS domains
remain in effect. Both system and TUN DNS returned A `NOERROR` with one answer
and AAAA `NOERROR` with no answers. Ordinary HTTP/HTTPS reached AdminVPS without
forcing `-4`; forced IPv6 hostname lookup failed as intended, and a literal public
IPv6 destination was rejected promptly through SOCKS.

Kernel IPv6 is enabled for `all`, `default` and every current interface. Restoring
the kernel setting alone did not recreate Tailscale's deleted IPv6 address and
routes; restarting local `tailscaled` restored them while preserving state and
preferences. Real tailnet IPv6 ping and SSH from t14s to Goar's Mac passed, fresh
tailnet IPv4 SSH to t14s passed, and Tailscale reported Running with no health
issues. LAN link-local multicast received router/peer replies and a direct
link-local ping to Android and the router passed. Fresh LAN SSH and system UDP/STUN
also passed. Explicit public IPv6 failed in about 39 ms through the system path
and 28 ms through SOCKS. An actual root subscription refresh reported the profile
unchanged, retained the service InvocationID and TUN DNS policy, and left the
refresh timer active. Native tailnet IPv6 to zenbook did not pass in either
direction; successful Goar-Mac tests establish t14s IPv6 operation, not every
peer's IPv6 health. No zenbook peer fix was attempted. The root acceptance record is
`/var/lib/nikcode-network/t14s/public-ipv4-20261106/result.json`. Reboot and automatic
rollback execution were not exercised by these acceptance checks.

## Migration acceptance record

Before the DNS change, three fresh Android Wi-Fi runs exercised ordinary HTTPS,
Naive, VLESS on 443, and legacy VLESS on 24443. VLESS UDP worked through both
entry ports, and invalid Naive credentials were rejected.

After the DNS change:

- three independent resolvers returned the primary address;
- the site presented trusted TLS;
- the isolated `warsaw-naive-pilot` listener on `zenbook` reached the new WAW/PL
  exit after restart;
- Android SFA reached the new WAW/PL exit; and
- Goar's MacBook SFM 1.14.4 cutover was accepted on 2026-11-06: system and
  local-proxy HTTPS, Google HTTP 204, and UDP/STUN reached AdminVPS WAW/PL;
  fresh SSH through zenbook and London, separate CLI Tailscale, and MagicDNS
  passed. Its narrow watchdog completed as accepted and was unloaded. The
  existing profile was retained; reboot and automatic failover were not tested.

These results accept the recorded server and DNS migration; the main zenbook
client cutover remains incomplete. They are not continuous monitoring and do
not prove hardening beyond the checks listed here.

### Pending zenbook cutover

The main `vless-sing-box.service` on `zenbook` started on 2026-11-05 at 15:07,
before the final DNS cutover. At the latest audit, both ordinary `curl` and its
mixed listener on port 2080 still exited through old Hosting-VDS Warsaw. Only the
isolated `warsaw-naive-pilot` mixed listener on port 21894 was restarted and
confirmed on AdminVPS.

This is client-side operational drift, not evidence that current DNS points to
the old server. A fresh main connection should resolve the primary hostname, but
the main service must not be restarted merely to make the documentation match.
Its cutover and verification remain pending an explicitly authorized client
restart.

## Recovery and rollback

### Fast DNS rollback to old Warsaw

1. Confirm that the incident is on the primary path and record current DNS,
   service status, and client symptoms in the private operational workspace.
2. Confirm old Warsaw is healthy through the London management path above.
3. From the private Vault, obtain the rollback address and the exact private DNS
   procedure. Change only the DNS-only A record for `notes.nikcode.xyz`; preserve
   TTL 60.
4. Wait for fresh answers from three resolvers, reconnect test clients, and
   verify site TLS, Naive, VLESS 443, VLESS 24443, and UDP through both VLESS
   entries.
5. Keep the failed primary and London unchanged for evidence and recovery. Do
   not cancel old Warsaw after rollback.

Because profiles use the hostname, this rollback normally requires DNS
propagation and reconnection, not a subscription refresh. Confirm each long-lived
client actually reconnected: the current main zenbook tunnel demonstrates that a
pre-change session can persist. The local-only `iphone-legacy-2` profile still
does not auto-update its JSON.

### Rebuild or replacement recovery

1. Start from the private operational source and provider credentials in
   `pass`; do not reconstruct deployment material from this sanitized snapshot.
2. Restore the server backup, including service configuration, site content,
   and BBR/`fq_codel` settings.
3. Decode the Caddy state backup privately, verify its SHA metadata, and restore
   the archive with its original ownership and permissions.
4. Validate HAProxy, Caddy, and sing-box configuration before starting them.
   Confirm loopback listeners 8443/8444 and public listeners 22/80/443/24443.
5. Run the pre-DNS acceptance checks against the candidate. Change DNS only
   after they pass, then repeat the post-DNS checks.

London and old Warsaw are preservation points, not migration workspaces. Any
restart, reconfiguration, removal, or cancellation of either requires an
explicitly scoped task.

## Plan limits

AdminVPS **Start** includes 10 TB per month, resetting monthly. The recorded plan
policy suspends service at 100% usage; additional traffic is priced at
100 RUB/TB. Whether to downgrade is undecided. Treat capacity or plan changes as
a separate decision, not a migration cleanup step.
