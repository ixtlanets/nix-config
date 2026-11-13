# Independent VPN-node acceptance — November 2026

## Practical progress — 2026-11-12 (Europe/Moscow)

The owner confirmed UK, France and Italy are free for this work and authorized
root resets, keys and installation. Preserve existing VPNs and start issuing
configs promptly **after acceptance**. The historical test-only gates and
results below describe earlier phases, not the current France deployment.

- **France — working minimal release:** `194.87.166.59`, product `380799`,
  Ubuntu 24.04 x86_64. Root reset succeeded; the owner's SSH key is installed
  and key-only login verified. `eth0` uses /24, gateway `194.87.166.1`.
  New `awg-fr` is active/running (PID 1488, Result=success), **boot-enabled after
  acceptance**: `awgfr`, `10.214.59.0/24`, UDP 49381, MTU 1280. Only scoped
  IPv4 forwarding prerequisites were deliberately enabled on this free server.
  No server reboot or service restart was performed.
- Both pinned binaries were copied read-only from Frankfurt; SHA256 matched.
  All server/client keys, PSKs and HPK are fresh; only 13 nonsecret compatible
  parameters were reused. Separate acceptance, `user-001` and `user-002` peers
  are active; the two end-user configs are mode 0600 outside Git, ready for
  private handoff. Client private keys were not copied to the VPS.
  The [France AWG bundle](../hosts/france/ubuntu/awg/) passes 33 offline tests.
- **Both actual end-user configs passed direct home native E2E separately** in
  disposable user/network/private-mount namespaces, with pasta outbound sockets
  bound to `wlo1`. Server peer endpoints match the physical-home positive control,
  not the old VPN exit. Fresh handshakes, bidirectional traffic, France HTTPS
  exit, tunneled DNS and certificate-verified named HTTPS passed. Private tunnel
  SSH/home gateway probes were blocked; IPv6 negative and shutdown fail-closed
  probes passed within the isolated test. Three protected local services,
  routes/rules and firewall matched before/after; `zenawg` remained present.
  Evidence: [private release acceptance](</home/nik/.local/state/nikcode-network/node-acceptance-20261112-0119/france-bootstrap/release-acceptance.json>).
- **Limits:** Android import and Wi-Fi/cellular switching were not newly tested;
  IPv6 negative testing lacked a native-IPv6 positive control. No device-wide
  persistent kill-switch, reboot recovery or continuous zero-packet-loss claim.
  Offline issuer supports new independent profiles, but automated live-add/revoke
  is not implemented; the two delivered profiles are already installed and tested.
- **UK:** root reset succeeded, but home access to ports 22 and 443 is
  unavailable; no deployment or key authentication. **Italy:** free reserve;
  SSH port 22 is reachable through the existing VPN but times out from home;
  not reinstalled. Neither is accepted.
- London remains Sergey's personal fallback only, not for users, and unchanged.
  Existing Frankfurt, Goar, Warsaw and Poland were not restarted or changed.
  No financial changes were made.

## Authorization and invariant (historical test phase)

On 2026-11-12 the owner authorized isolated temporary VPN services on all eight
inventory candidates. Existing working VPN connections must remain intact.
London is Oracle Cloud Always Free, confirmed by the owner on that date.
The owner subsequently excluded London from equal-node acceptance: it remains
his personal fallback only; do not add VPN services or change its configuration.
The independent-node test scope is therefore seven paid VPS, not London.
No purchases, renewals, cancellation changes, DNS cutovers or client migrations
are authorized by this test.

## Candidates and billing evidence

| Candidate | Previously documented paid day / billing | Provider-panel “Оплачен до”, read 2026-11-12 | Existing role |
|---|---|---|---|
| Frankfurt, Hosting-VDS | 2026-11-13; non-renewal request outstanding | Not checked in this panel session | Existing VLESS and accepted S22 AWG |
| Goar, Hosting-VDS | 2026-11-14; non-renewal request outstanding | Not checked in this panel session | Existing team VLESS and AWG |
| Warsaw, Hosting-VDS | 2026-11-30 | Not checked in this panel session | Protected rollback |
| Poland Start, AdminVPS | 2026-12-04 | 2026-12-05 | Protected primary |
| UK Promo, AdminVPS | 2026-12-06 | 2026-12-07 | Previously tested relay candidate |
| France Promo, AdminVPS | 2026-12-06 | 2026-12-07 | Previously tested egress candidate |
| Italy Promo, AdminVPS | 2026-12-06 | 2026-12-07 | Previously tested candidate |
| London, Oracle | Always Free, owner-confirmed; no paid-through date | Not applicable | Owner-only fallback and application host; excluded from equal nodes |

Exact addresses, credentials and raw evidence remain in private state outside Git.
The authenticated AdminVPS server list was read through the owner's paired
Chromium on 2026-11-12 (Europe/Moscow); no billing actions were taken. The
one-day difference from the previously recorded dates is preserved rather than
silently treating an invoice-period end and the panel's date as interchangeable.
Neither source establishes the cutoff hour or guarantees access until that hour.
No Hosting-VDS dates were reverified by this AdminVPS login.

## Acceptance contract

A full node must independently receive an authenticated encrypted VPN/proxy
connection and provide public internet egress without another managed VPN exit.
Verify expected exit identity, DNS, several HTTPS destinations, bounded data
transfer and fresh reconnects. Test from the physical home uplink and cellular
where safe isolation can prove the actual network used. A listening socket, SSH
login, successful server-side curl or an inter-server test alone is insufficient.

Record each vantage and transport separately. A userspace proxy test is evidence
of the server transport, not certification of client TUN routing, leak prevention,
kill switch, Wi-Fi/cellular handoff, reboot survival or long-term throughput.
Do not mark an untested vantage as passed, or a relay-only server as a full node.

## Execution and safety gates

1. Verify existing trusted SSH identities. Do not auto-accept unknown/changed keys.
2. Capture service PID/start identities, listeners, routes/rules and firewall
   fingerprints; retain a local-uplink and existing-VPN baseline.
3. Prefer an existing authenticated service for the first end-to-end test.
   Otherwise add only an exclusively named, authenticated, resource-limited
   temporary userspace service on an unused port. Validate configuration first.
4. Do not restart/reload/reconfigure existing services; do not modify production
   listeners, routes, DNS, forwarding sysctls, Docker/Tailscale or shared firewall
   chains. Do not stop/switch active VPN clients or toggle phone radios.
5. Bind test clients per socket to the physical uplink; avoid TUN/default-route
   changes. Reuse no production credential in a new public service. Restrict new
   services from reaching host/private networks and require encryption/auth.
6. Keep traffic bounded; no stress tests, packages/upgrades or reboots. Stop on
   any baseline regression. A blocked identity/port/network is a documented limit,
   not permission to weaken trust or alter production networking.
7. Remove only artifacts owned by this acceptance run, using exact ownership
   checks; compare the protected baseline and verify continuing existing traffic.
8. Record results in the private active-node register only after testing. Separate
   full nodes, auxiliary-only capacity and unaccepted candidates. Preserve billing
   deadlines and open blockers rather than converting partial results into passes.

## Provisional results — 2026-11-12 (Europe/Moscow)

This is test evidence, **not a production cutover or final active-node register**.
Existing roles, including Warsaw rollback-only, remain unchanged. London stays
outside equal-node acceptance as the owner's personal fallback.

| Paid candidate | Observed functional result | Boundary |
|---|---|---|
| Frankfurt Hosting-VDS | **Home passed**, existing VLESS Reality **TCP 24443**, both original Chrome and Firefox fingerprints. | Port 443 timed out despite bare TCP success. Existing owner-accepted S22 AWG remains untouched. |
| Goar Hosting-VDS | **Home passed**, already-running AmneziaWG on `zenawg`. | Direct VLESS TCP 443/24443 timed out from this home uplink. No stop/restart test of production AWG. |
| Warsaw Hosting-VDS | **Home passed**, existing VLESS Reality TCP 443. | Technical capability does not promote the protected rollback host. |
| Poland AdminVPS Start | **Direct home entry unconfirmed.** Physical TCP 22/443/24443/49443 timed out; direct VLESS and Naive did not establish usable connections. **Nested VLESS control through Goar AWG passed.** | Working own internet exit from another vantage is not independent home-entry acceptance, nor evidence the server is globally down. |
| UK AdminVPS Promo | **Unverified:** no previously trusted SSH host pin located. | No first-use SSH acceptance, service deployment or node acceptance. |
| France AdminVPS Promo | **Unverified:** no previously trusted SSH host pin located. | No first-use SSH acceptance, service deployment or node acceptance. |
| Italy AdminVPS Promo | **Unverified:** no previously trusted SSH host pin located. | No first-use SSH acceptance, service deployment or node acceptance. |

Each passed functional set includes expected own public exit, UDP DNS, two HTTPS
sites, TLS 1.3 Cloudflare trace, exact bounded 1 MiB and fresh reconnection.
Isolated VLESS clients bound outer sockets to physical `wlo1`; existing Goar AWG
was explicitly tested as its own existing tunnel. The physical home control and
existing default VPN exit were consistent before and after the run. Nested
Frankfurt control also passed, but does not count as independent home entry.

Current mounted Frankfurt/Goar server config was inspected read-only: selected
owner UUID, flow, Reality public key, short ID and SNI match the existing clients.
Do not rotate credentials or infer bad authentication from network timeouts.

A bounded read-only Poland policy check found an empty native nftables ruleset
and wildcard TCP listeners on 22/443/24443 (none on 49443). No explicit host-side
source ban was established. Legacy kernel firewall state and provider/upstream
policy remain unverified: this is **not proof of ISP or provider blocking**.

### Preservation and cleanup

- Final comparison on Frankfurt, Goar, Warsaw, Poland, London and zenbook found
  **no changes** to protected service PID/start identity, restart count, active
  state, routes/rules, container identities or listeners.
- Successful IPv4/IPv6 firewall snapshots were unchanged on Frankfurt, Goar,
  London and zenbook. **Warsaw/Poland lack iptables-save/ip6tables-save:** their
  matching failed reads do not establish unchanged firewall state. No firewall
  modifications were performed in this run.
- London comparison uses its successful supplemental baseline; the first
  observation failed authentication with an incorrect username.
- Working existing default VPN still exits through Goar. No production VPN was
  switched, stopped, restarted, reloaded or reconfigured.
- Isolated VLESS post-stop canaries failed at their stopped loopback proxies as
  expected. Reported owned process groups and temporary files were cleaned.
- No new remote service, listener, firewall rule or credential was deployed.
  No route, DNS, sysctl, Docker or Tailscale configuration was changed.

### Mobile boundary

Read-only USB S22 inspection found Android 16/API 36, existing Wi-Fi and active
AmneziaWG VPN (the Frankfurt S22 profile), but **no already-existing CELLULAR
Network**. Its VPN reports `bypassable=false` and includes shell UID 2000.
Always-on/lockdown being off is not permission to bypass it. No cellular helper
was built/launched, and no app, setting, network request, profile, radio or ADB
forward/reverse was changed. **Fresh cellular acceptance remains unperformed**
rather than risking the working connection. Prior owner acceptance of Frankfurt
AWG is distinct from a fresh all-node mobile run.

### Evidence and runner verification

Private evidence, redacted reports and protected before/after snapshots remain
outside Git. A private provisional register records all seven candidates,
limitations, paid-through dates and report hashes; **it is not the final
active-node register**. Credential manifests remain private, outside Git.

The first four-node attempt was **invalid as network acceptance**: unsupported
curl `--fresh-connect` returned code 2 before requests.
It must not count as four failed nodes. The option was removed; separate curl
processes and disabled transport pooling provide freshness. Only corrected
functional reports establish the results above.

The standalone [runner](../tools/vpn-node-acceptance/) has **22 local tests
passing**, independently rerun by the lead. These include installed curl against
a loopback-only SOCKS fixture, UDP DNS parsing, negative canary, SIGTERM and
owned-resource cleanup. They test the runner, not VPS acceptance. No TUN policy,
leak, kill-switch, reboot, handoff, sustained-load or speed certification is made.

### Remaining gates at that earlier phase (superseded for France and UK)

1. Obtain independently trusted SSH host fingerprints for UK/France/Italy from
   the provider console. Historical local/omarchy records and four trusted VPS
   supplied no pins; do not substitute acceptance of a fresh scan.
2. Test those three hosts only after trusted identity and safety baselines.
3. Resolve/characterize Poland direct home entry and test cellular only through
   a safe available path, without switching the current VPN.
4. Review results and agree the active-node register. No financial or server
   configuration actions were taken in provider panels; billing dates above
   preserve the distinction between earlier documents and the authenticated list.

### Authenticated provider-console follow-up, 2026-11-12

The owner's Chromium login persisted. UK, France and Italy each exposed the
AdminVPS HTML VNC view, but each ended at **Server disconnected (code: 1006)**,
without a guest terminal or independently trusted SSH fingerprints. The initial
“noVNC ready” screen was not counted as a connection. This is a console-access
blocker, not proof that the VPS or its VPN is down; its root cause is unknown.
No password was revealed or entered, no terminal commands were sent, and no
power/reboot, SSH-key management, network, service or billing controls were used.
Unknown SSH identities remain blocked; do not replace verification with TOFU.

Private screenshots and an observation record supplement the original evidence.
The subsequent local read-only preservation check found the same PID/start/restart
identities for all three baseline-protected local services, the same readable
iptables/ip6tables hashes and the same functioning Goar exit. However, the raw
local network snapshot was **not identical**: three IPv6 link-local/local/multicast
routes for `docker0` appeared. No routes were removed; IPv4 routes and both policy
rule sets matched. The cause of these Docker-interface additions is unestablished;
no repair or rollback was attempted. Remote preservation was not remeasured in
this browser-only phase. These checks do not prove continuous zero packet loss.

The next dependency at that time was a working authenticated provider console, or independently
verified host-key fingerprints supplied through another trusted owner/provider
channel. Until then, UK/France/Italy are unaccepted, and the seven-node objective
remains incomplete. London remains excluded and unchanged by this phase.

### Four-node personal-pool preparation, 2026-11-13

The owner selected one equal France/Frankfurt/Poland/Italy URLTest pool, not
primary/standby tiers. This follow-up is **partial, not a published cutover**.

- Existing pinned owner-key SSH access to Poland was verified. A new dedicated
  `nikcode-singbox-pilot.service` was staged and temporarily started on
  `193.124.205.153:34443`, using the verified official sing-box 1.14.4 binary.
  Its upstream Reality handshake passed certificate/hostname verification,
  TLS 1.3 and X25519 checks from Poland.
- Isolated workstation probes bound to physical `wlo1` passed with **each of the
  six new Poland device credentials**: expected own exit on separate HTTPS
  connections, Cloudflare trace, two HTTPS sites, exact bounded 1 MiB, UDP DNS,
  fresh reconnection and the stopped-local-proxy negative canary. Existing
  France and Frankfurt credentials passed the same run. All eight probe process
  groups and temporary directories were confirmed cleaned. These are credential
  and workstation-uplink tests, **not tests performed on six physical phones**.
- Poland's protected SSH, Naive-Caddy, HAProxy and legacy sing-box service
  PID/start/restart identities, observed existing configuration hashes, routes,
  policy rules and successful nftables configuration snapshots matched before
  and after. nftables counters were excluded from configuration comparison.
  This does not establish unobserved iptables state or continuous zero loss.
- The new Poland unit was then deliberately **stopped and left disabled** while
  Italy's identity was still unverified at that checkpoint. Its staged files are retained; no old
  service was stopped/restarted and no shared network policy was changed.
- A four-node candidate preserves all pre-existing state fields and six stable
  subscription identities, adds twelve unique device/node UUIDs and independent
  new Reality identities, and fits the raw projection cap at **3655 bytes**.
  Candidate state/key material was encrypted and read-back verified outside Git.
  Canonical operator entries and the live UK projection were **not changed**;
  delivered personal subscriptions still contain France/Frankfurt only.
- Source checks passed: six server-renderer tests including native 1.14.4 checks,
  ten manager Python tests, 32 subscription JavaScript tests and 22 acceptance
  runner tests. The JavaScript suite requires `umask 022` for its existing
  intentionally unsafe-file fixture. `pilot-project` now uses compact JSON;
  other command output formatting and private exclusive-write behavior remain.
- At that preparation checkpoint Italy lacked an independently trusted SSH
  fingerprint. Provider-console verification and access were still pending;
  the subsequent results below supersede that blocker.

#### Italy verification and six-profile preservation, 2026-11-13

- An authenticated provider guest console confirmed Italy's hostname, global
  address `81.29.155.74` and ED25519 host fingerprint. The strict host-pinned owner
  key was not accepted; the existing provider password then established root SSH.
  No password, authorized key, SSH configuration or canonical known-hosts entry
  was changed. The owner was informed of the earlier credential-output incident;
  password rotation has not been authorized or performed.
- The isolated Italy pilot was installed on free TCP `34443` using the pinned
  1.14.4 binary and an independently generated Reality identity. Its six actual
  device credentials and two unchanged France/Frankfurt controls passed physical
  `wlo1` acceptance: exact initial/reconnected IPv4 exit, Cloudflare TLS 1.3,
  example/Wikipedia HTTPS, exact 1 MiB transfer, SOCKS UDP DNS and owned-proxy-kill
  controls, with owned client cleanup. These are workstation results, not phone,
  TUN, censorship, leak, reboot or seamless-existing-session certification.
- Italy's additional bad-UUID control used a native-valid globally nonmember UUID,
  an actual failed tunneled request and exactly one additional server unknown-UUID
  rejection, with valid egress before/after. An owned server-loopback nonce HTTP
  canary was reachable locally before/after but rejected through sole VLESS without
  a client DIRECT exception. The canary process/thread/socket were cleaned up.
- Italy was verified **inactive/dead, disabled, MainPID 0, NRestarts 0**, with its
  pilot and canary ports free and no autostart symlink. Staged files/account remain.
  Stable existing-service PID/start/restart/state, configuration hashes, IPv4/IPv6
  routes/rules and observed nft/iptables/ip6tables/ufw state were preserved. Full
  snapshot equality is not claimed: DHCP lifetime countdown, transient root-login
  units and an inactive periodic sysstat timestamp were classified separately.
- All six **actual candidate subscription profiles**, rendered by `singBoxPilot`
  without forcing inline rules or removing Tailscale, passed native 1.14.4 checks.
  Five retain inline RU rules, S22 retains remote rules and the first three retain
  Tailscale. Fresh comparison with canonical state/keys preserved all old fields,
  metadata, tokens, revocation state, twelve old UUIDs and old Reality identities;
  only two nodes, twelve new unique UUIDs and two independent identities were added.
  Both original encrypted backups matched their current canonical ciphertexts.
  Compact projection is 3654 JSON bytes plus one newline, within the unchanged
  5000-byte cap. Canonical entries and live delivery remain unchanged.

- Poland's additional controls subsequently passed in one bounded v3 run: a
  globally nonmember native-valid UUID caused curl 35 with zero body bytes and
  exactly one current-invocation unknown-UUID rejection; valid HTTPS before/after
  returned the expected Poland exit. An owned nonce loopback canary was locally
  reachable before/after but rejected through sole VLESS (curl 52, zero bytes).
  Its thread, socket and process were closed, and its port was independently free.
  All five owned client groups and temporary files were cleaned. Final independent
  audit confirmed pilot inactive/dead, disabled, MainPID 0, NRestarts 0 and free
  TCP 34443; installed hashes and the authoritative protected-service/network/
  configuration baseline matched exactly. The earlier redacted start-RPC failure
  remains unexplained; the later multiline start/stop and negative tests succeeded.

Four-node live delivery, real Poland/Italy pool failover and fresh native mobile
acceptance remained **unperformed** at that checkpoint. A preliminary failover-runner
audit exposed an insufficient generic-curl-error all-down oracle; it is not accepted
as live fail-closed evidence. The integrated test below supersedes only the pool
failover gap, not publication or mobile acceptance.

#### Integrated four-exit pool acceptance, 2026-11-13

**Accepted for the isolated integrated pool test, not publication or delivery.**
The native sing-box 1.14.4 userspace run used physical `wlo1`, a real
production-derived Goar inline clone, four owned authenticated gates and numeric
foreign pins. It used neither a shortened interval nor a forced selector. The
same-pin checks succeeded before and after; all owned gate, core and file cleanup
checks were true. The eight exact stages passed:

| Stage | Observed result |
|---|---|
| `baseline` | France |
| `poland_only` | Poland |
| `poland_to_italy` | Italy |
| `italy_to_poland` | Poland |
| `new_nodes_down` | France |
| `adminvps_down` | Frankfurt |
| `all_down` | `validated_four_edge_cut` |
| `restored` | Frankfurt |

Native evidence: [pool-result-live.json](</home/nik/.local/state/nikcode-reserves-20261113/pool-result-live.json>),
SHA256 `3ebffd595621bf4069bec1c69363050f2a022c0ddee4472a44343e0f8ac913b2`.
The earlier generic-curl-error oracle is not the evidence for this all-down result.

The wrapper `pool-live-run-v2-results.json` remains **`accepted:false`** because
its broad Poland global-units snapshot differed; it is not overwritten or
relabelled. Its Italy and local preservation checks passed. The independent
`pool-poland-final-audit.json` establishes that the four original protected
services (SSH, Naive-Caddy, HAProxy and legacy sing-box) retained their
PID/start/NRestarts and configuration, and routes, rules and nftables were
unchanged; post-test the pilot was stopped and disabled, PID 0, with TCP 34443
free. Root runtime/user manager stopped and restarted during the interval, a
plausible cause of the broad mismatch, but the exact lost global-snapshot diff
is **not reconstructable**. Acceptance explicitly combines the native eight-stage
result with independent protected-production preservation, **not exact global-unit
equality**; it does not claim continuous zero packet loss.

#### Production publication and delivered-profile acceptance, 2026-11-13

**Published and verified for all six existing subscriptions.** Poland and Italy
now run the dedicated pinned 1.14.4 pilot on TCP 34443, active/running and enabled,
with the expected listener PID and zero restarts. Final enabling used
`systemctl enable --no-reload` followed by a start of only the new unit. Existing
running services, network/firewall configuration, accounts, boot identity and
installed configuration passed before/after preservation guards. Poland's four
original protected services also matched the authoritative predeployment baseline.
The earlier rejected enable-attempt artifacts remain unchanged; one broad-unit
comparison observed `apt-daily.service` activating, not a protected proxy restart.
Global equality of every maintenance/session unit is not claimed.

Canonical encrypted state and node keys were updated and decrypted readback matched
the candidate exactly. Removing only the two added nodes, twelve credentials and
their twelve `not-requested` server-revocation entries reproduces the original
state and keys. Verified encrypted rollback copies were saved before either write.
Existing identities, tokens, revocation state, metadata and rule-set modes remain
unchanged: five inline profiles and the Galaxy S22 remote-rule profile.

The UK origin projection was atomically replaced by the compact 3655-byte candidate
under the unchanged 5000-byte cap, preserving owner/group/mode. Readback and temporary
file cleanup passed; all installed source hashes, three protected service snapshots,
and before/after routes, rules and firewall snapshots matched. No shared-service
restart, Worker publication, or `SERVICE_CONFIG` change was performed.

All six devices were downloaded over verified HTTPS using **both** existing URL
forms (twelve configurations). Each origin response was HTTP 200, exactly equal to
its candidate and passed native sing-box 1.14.4 `check`. All twelve legacy requests
returned exactly the expected HTTP 307 to the same path on the existing origin.
The flat France/Frankfurt/Poland/Italy URLTest pool retains the native one-minute
interval, 100 ms tolerance, `interrupt_exist_connections=false`, final `proxy`,
existing exceptions and no DIRECT fallback for non-exempt foreign traffic.

Evidence: [enable and preservation](</home/nik/.local/state/nikcode-reserves-20261113/production-enable-v3-results.json>),
[canonical readback](</home/nik/.local/state/nikcode-reserves-20261113/canonical-publication-results.json>),
[atomic origin publication](</home/nik/.local/state/nikcode-reserves-20261113/uk-projection-publish-result.jsonl>),
and [six-device delivery](</home/nik/.local/state/nikcode-reserves-20261113/delivery-check-aef7b23af08d9537180ed2cfeb191d81/summary.json>).
These evidence reports contain no subscription tokens or profile payloads.
A final [postpublication traffic smoke](</home/nik/.local/state/nikcode-reserves-20261113/postpublication-delivered-profile-smoke.json>)
used the actually downloaded Goar inline profile with the same isolated physical
`wlo1` harness and all four gates healthy. Two consecutive foreign-probe rounds
passed through France (7.86 seconds); owned core/gate/file cleanup passed. This was
explicitly a baseline-only check, not a replacement or rerun of the eight-stage
failover evidence above.

Rollback remains a guarded atomic restoration of the saved origin projection,
followed by restoration/readback of the original canonical entries and stopping and
disabling only the two new units; no rollback was needed for the successful cutover.

**Physical phones must refresh their subscriptions.** Installed-client refresh,
native phone TUN/DNS/leak behaviour, reboot and Wi-Fi/cellular switching remain
**unproven**. The userspace failover test and delivered native syntax checks do not
establish those mobile properties or seamless survival of existing TCP sessions.
