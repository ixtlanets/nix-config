# Frankfurt: isolated S22 AmneziaWG test

**Deployed and accepted on 2026-11-11 (Europe/Moscow).** The new service is
running and enabled at boot; Galaxy S22 passed Wi-Fi and cellular acceptance.
See [live acceptance](#live-acceptance-2026-11-11) for the checks and limitations.
Separate endpoint on existing Ubuntu x86_64 VM `root@31.58.85.163`, not a replacement
for any VPN/proxy. Do not run this bundle on Goar, London, or a client.

| Resource | Fixed value |
|---|---|
| Unit / private directory | `awg-s22-test.service` / `/etc/awg-s22-test` |
| Userspace TUN / UAPI | `awgs22` / `/run/amneziawg/awgs22.sock` |
| Outer endpoint | `31.58.85.163:49380/UDP`, IPv4 only |
| Inner subnet | `10.213.211.0/30`: server `.1`, S22 `.2` |
| MTU | `1280` |
| Public interface / gateway | `eth0`, `31.58.85.163/32`, via `10.0.0.1` |

The supplied lead observations supersede stale `wg0` descriptions in
[proxy-setup.md](../../../../docs/proxy-setup.md). No live `wg0` was observed.
Existing Docker VLESS TCP 443/24443, Docker chains, Tailscale policy rules and all
other services must remain untouched. There is no generic installer change.

## Trusted inputs (lead responsibility)

Copy these **exact existing linux-amd64 executables read-only from working Goar**;
no builds, upgrades, downloads, or changes to Goar:

| Installed filename | SHA-256 |
|---|---|
| `awg` (reported version `v3.1.20260812`) | `1ac92ba760092d805907a322f539c923673f5924666978612c3e85c0981bb005` |
| `amneziawg-go` | `b53961c848acdc18f36ebd60f7a3f900a0e195be8e582eb721c05fa9ec6b2273` |

Binaries are deliberately not checked in. There are no keys, PSKs, server config,
client config, QR codes or generated secrets in this bundle.

Lead privately provisions `/etc/awg-s22-test/server.conf`, native **`awg setconf`**
format: one `[Interface]` with private key and `ListenPort = 49380`, matching
trusted AWG obfuscation parameters, and one `[Peer]` with the S22 public key,
optional PSK and **exactly** `AllowedIPs = 10.213.211.2/32`. Do not include
`Address`, `MTU`, `DNS`, `Table`, `FwMark`, `Endpoint` or quick-script directives.
No `awg-quick` is used. Do not print config/keys or use `showconf`/config dumps.
The helper validates structure; the pinned `awg` and daemon validate native
semantics. **Omit `AdvancedSecurity` in both configs:** Android rejects that Peer
attribute on import, and the pinned server daemon rejected the otherwise
CLI-parseable native config until that optional peer attribute was removed.
The accepted profile retains matching `Jc/Jmin/Jmax`, `S1`–`S4`, `H1`–`H4`,
`HeaderProtectionKey`, `ContentPaddingAddition = 4-28`, and `RandomTrailers = on`.
Fresh independent server/client keys, PSK and header key were generated privately.

Client provisioning is **outside this bundle**. Lead must set client address
`10.213.211.2/32`, MTU 1280, endpoint above, matching AWG parameters, and full-tunnel
`AllowedIPs = 0.0.0.0/0, ::/0`, with suitable public DNS reachable through the
IPv4 tunnel. `::/0` must remain captured to prevent native IPv6 leaks: this server
intentionally drops all inner IPv6 and does not provide IPv6 egress. No Tailscale,
LAN or host-private DNS through this endpoint. Android always-on/lockdown settings
were not changed; a kill-switch outside the active tunnel was not accepted/tested.
The IPv6 negative probe and its positive-control limitation are recorded below.

## Minimal deploy (lead only, on the approved Frankfurt VM)

Prerequisites must **already** exist: Python 3 (stdlib only), systemd, iproute2
(`ip`, `ss`), `iptables` and `ip6tables` with comment/conntrack/MASQUERADE support,
`/dev/net/tun`, normal `/var/run -> /run`, IPv4 forwarding already `1`. The VM
observations were 7 GB free RAM / 64 GB free disk; resources are not changed.
No `apt`, kernel/module changes, sysctl writes, default routes or policy rules.

Isolation assumes exclusive ownership of the `awgs22` name/subnet/port/comment,
no concurrent process recreating that interface during a lifecycle action, and
no firewall manager moving/replacing rules above these head-inserted guards.
Do not reload firewalls or reconfigure Docker/Tailscale while running this test.
The trusted userspace daemon is expected to create a down TUN until the helper
brings it up. Existing production flows must be independently checked by lead;
these offline assets cannot establish the live service baseline.

After staging only this directory's reviewed public assets and the trusted
executables/private config in a root-only staging directory on Frankfurt,
run locally there (paths below are relative to that staging directory):

```sh
set -eu
# Refuse to overwrite a previous bundle/unit: review separately if this fails.
test ! -e /etc/awg-s22-test && test ! -L /etc/awg-s22-test
test ! -e /etc/systemd/system/awg-s22-test.service
test ! -L /etc/systemd/system/awg-s22-test.service
install -d -o root -g root -m 0700 /etc/awg-s22-test
install -o root -g root -m 0700 awg amneziawg-go /etc/awg-s22-test/
install -o root -g root -m 0600 server.conf /etc/awg-s22-test/server.conf
install -o root -g root -m 0600 control.py /etc/awg-s22-test/control.py
install -o root -g root -m 0644 awg-s22-test.service /etc/systemd/system/awg-s22-test.service
systemctl daemon-reload
systemctl start awg-s22-test.service
systemctl is-active awg-s22-test.service
```

Do not use a broad firewall reload/save/restore, networking restart, Docker
restart, Tailscale restart or other service restart. `daemon-reload` rereads unit
metadata, **not** a service restart. Start only the new unit; do not enable it
at boot until lead accepts the test. If accepted, optional enable is scoped:
`systemctl enable awg-s22-test.service`.

Preflight checks root-owned `0700` private directory and executables, `0600`
config, pinned executable hashes, expected eth0 address, forwarding already on,
unused interface/socket/UDP port and subnet overlap against every IPv4 address
and non-default route in all tables. Defaults are intentionally exempt from the
overlap check. It does not adopt an existing interface or stale invocation marker.
It also refuses stale exact commented firewall rules and verifies both firewall
frontends can perform scoped checks before claiming ownership. The service runs
`amneziawg-go -f awgs22` in the foreground. Socket + interface
readiness is polled locally for at most 10 seconds; no network packets are sent.

Startup installs IPv4/IPv6 interface-specific DROP guards **before** native
`setconf`, address/MTU/link-up and route checks. Guards remain fail-closed until
those steps pass. Only the connected `10.213.211.0/30` route is created implicitly
by assigning the interface address. Read-only route lookups require the client
return path via `awgs22` and three public forward destinations via approved
`eth0`/gateway. They are sample policy checks, not proof about every destination;
`-o eth0` prevents forwarding via any other interface regardless.

Rules are inserted at chain head and contain comment `awg-s22-test`:

- INPUT: drop everything from `awgs22` (both families); allow IPv4 UDP49380 on
  eth0. Drop IPv6 UDP49380 on eth0, leaving the public endpoint IPv4-only.
- FORWARD: drop non-public IPv4 destinations from `awgs22` before accepting
  **only** source `10.213.211.2/32` to eth0. This additionally blocks RFC1918,
  CGNAT/Tailscale, loopback/link-local, documentation/benchmark, multicast and
  reserved ranges even if they otherwise use eth0. Drop all other traffic from
  or to `awgs22`; all inner IPv6 is dropped.
- Return: allow only eth0 -> awgs22, destination client/32,
  conntrack `ESTABLISHED,RELATED`.
- NAT: only client/32 leaving eth0 gets MASQUERADE.

No shared chains are flushed, replaced, created, saved or restored. Each owned
rule is checked with exact `-C` before `-I` or `-D`; every command uses `-w 5`.
Other rules retain their relative order. Lifecycle operations are locally
flock-serialized. Service requires NET_ADMIN/NET_RAW, TUN, shared UAPI directory,
netlink and iptables access; hardening deliberately permits those and does not
manage the lifetime of `/run/amneziawg`. Only its own runtime directory is managed.
Normal daemon/command output is suppressed, including potentially secret-bearing
parse failures. The root-only runtime file `last-error.json` records the action
and a fixed, sanitized failure reason, not command output or configuration.
Treat it as failure evidence, not a current health check; it may outlive a later
successful start. Do not publish raw daemon/config dumps or enable journal tracing.
The temporary root-only diagnostic override used during initial compatibility
checks was removed; the accepted unit has null stdout/stderr and no drop-ins.

## Rollback / failure

```sh
systemctl stop awg-s22-test.service
# Only if it was explicitly enabled:
systemctl disable awg-s22-test.service
```

`ExecStopPost` also handles failed startup. It removes only the interface owned
by the **current systemd invocation**, then exact commented IPv4/IPv6 rules,
including duplicate exact matches. A second successful cleanup is a no-op. It
does not delete private config, binaries, keys, shared UAPI directory or any
other interface/service. The daemon normally removes its own UAPI socket.

If interface-down/delete fails, rules are retained; if rule cleanup fails, the
ownership marker is retained in `/run/awg-s22-test/owned`. RuntimeDirectoryPreserve
keeps this evidence across stops. Do not erase a stale marker or blindly restart:
lead must inspect the scoped interface/rules, finish scoped cleanup using the
recorded invocation identity, and resolve the cause. Failed preflight does not
clean up a previous invocation. No global firewall recovery command is appropriate.

## Live acceptance: 2026-11-11

Device: Samsung Galaxy S22 SM-S901B, Android 16, AmneziaWG 3.1.4;
backend `v3.1.20260814`. Separate imported profile: **`fra-s22-test`**.
The old `goar` and `GoarAWG31` profiles were preserved and never activated or edited.
Frankfurt was selected for its independent reachable public IP and spare capacity;
London and Warsaw remain untouched reserve/rollback hosts, Poland remains primary.

| Check | Wi-Fi | Cellular |
|---|---|---|
| Fresh handshake after enabling the new profile | Pass, including after server stop/start | Pass after Wi-Fi disabled |
| HTTP exit identity | `31.58.85.163` | `31.58.85.163` |
| Public DNS + IPv4 ICMP | Pass | Pass |
| Chrome ipify / example / Google generate_204 | 200 / 200 / 204, HTTP/2, TLS 1.3 | 200 / 200 / 204, HTTP/2, TLS 1.3 |
| HTTPS ipify identity | Expected Frankfurt IP confirmed | Expected Frankfurt IP confirmed |
| Numeric IPv6 HTTP attempt | No response through tunnel | No response through tunnel |

Further checks:

- MTU is 1280. Cellular nonfragmenting IPv4 ping with 1252-byte payload
  (`ping -M do`) returned 2/2 replies, 0% loss. No throughput benchmark was run.
- Cellular TCP connection attempts to the tunnel server's private SSH address,
  provider gateway, Docker private address, Tailscale address and LAN router all
  timed out; no private connection succeeded. These attempts match the scoped
  INPUT/FORWARD destination-drop policy.
- Stopping **only** the new service restored every captured firewall rule,
  IPv4 route and IPv4/IPv6 policy rule exactly to baseline. Existing production
  service identities and the Frankfurt VLESS container identity/PID/start time/
  restart count stayed unchanged. The new service then started successfully;
  Wi-Fi handshake, exit identity, DNS and packet tests passed again.
- Final comparison excluding only `awg-s22-test` rules preserved all existing
  firewall rules and policy rules. Goar's active m3max and zenbook peers continued
  exchanging traffic with fresh handshakes (69 s / 43 s at the final sample).
  Their receive/transmit counters grew; the old S22 peer counters and handshake
  were unchanged. No Goar, Docker, Tailscale or other existing service was restarted.
- The accepted new service is **active + enabled**. Boot ordering waits for
  `network-online.target`; a host reboot was deliberately not tested.
- Phone restored: Wi-Fi on, mobile data on, airplane mode off, all three VPN
  profiles off, USB settings in foreground. To use the endpoint, enable only
  `fra-s22-test` in AmneziaWG. Diagnostic Chrome tabs and their own USB forwarding
  ports were removed; no existing browser tab was closed.

Limitations and diagnostic notes:

- IPv6 internet egress is intentionally unavailable. `::/0` remains captured and
  server inner-IPv6 INPUT/FORWARD is dropped. Negative probes observed no IPv6
  egress, but a usable native-IPv6 positive control was not established; this is
  not a full leak certification across other IPv6-capable networks.
- Reusing the pre-handoff background Chrome tab failed navigation after switching
  radios. A fresh foreground diagnostic tab passed all three cellular HTTPS
  checks. The cause of that old-tab failure was not established; browser settings
  and background restrictions were not changed.
- The initial Wi-Fi runner misclassified the log text `Received handshake response`
  because it expected `Receiving`; corrected matching and a fresh post-restart
  Wi-Fi acceptance passed. The initial cellular off-tunnel probe ran during radio
  handoff and returned network-unreachable; it is not evidence of ISP blocking.
- This is a new IP **and** fresh profile/keys/parameters, not an IP-only experiment.
  Success does not prove DPI or establish why the old Goar destination failed.

Key-redacted local evidence is under
`/tmp/awg-s22-endpoint-20261111/` (ephemeral, not a backup). Configs and credentials
are outside Git, root-only on the VM; the temporary plaintext phone import file
was removed after checksum ownership verification. Preserve the private configs
securely if disaster recovery is required. The public bundle alone cannot
reconstruct keys or re-import the phone profile.

## Offline checks

From repository root, without root/network privileges:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s hosts/frankfurt/ubuntu/awg-s22-test/tests -v
python3 -c 'import ast,pathlib; ast.parse(pathlib.Path("hosts/frankfurt/ubuntu/awg-s22-test/control.py").read_text())'
```

Tests use a mocked command runner and disposable local filesystem, never the
host network. Unit syntax can also be checked with `systemd-analyze verify` in
a temporary staged unit root; missing target binaries in this checkout are
expected until lead privately provisions the VM.
