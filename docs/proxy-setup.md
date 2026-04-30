# Proxy Setup

Transparent proxy for bypassing geo-restrictions, using VLESS+Reality for most traffic and a
London SOCKS5 relay for traffic that needs a UK exit IP (`google.com`, `elevenlabs.io`).

## Architecture

```
  ┌─────────────────────────────────────┐   ┌─────────────────────────────────────┐
  │ NixOS client                        │   │ macOS client (m1max)                │
  │ (zenbook/x13/x1carbon/um960pro)     │   │                                     │
  │ sing-box (TUN mode, auto_route)     │   │ sing-box GUI (TUN mode, auto_route) │
  │   ├─ private / Russian IPs ► direct │   │   ├─ UDP 443 ────────────► block    │
  │   ├─ google.com / elevenlabs.io ─► london │   │   ├─ private / Russian IPs ► direct │
  │   └─ everything else ─────► proxy   │   │   └─ everything else ──► proxy      │
  └──────────┬──────────────┬───────────┘   └──────────────────┬──────────────────┘
             │ VLESS+Reality │ SOCKS5 over                      │ VLESS+Reality
             │ port 443      │ Tailscale                        │ port 443
             │               │                                  │
             ▼               │                                  │
   ┌────────────────────────────────────────────────────────────────────────────┐
   │ Frankfurt: wire.nikcode.xyz / 31.58.85.163                                 │
   │ sing-box in Docker (reality-ezpz)                                           │
   │   ├─ geosite-google UDP 443 ───────────────► block                          │
   │   ├─ geosite-google TCP ───────────────────► london                         │
   │   ├─ elevenlabs.io UDP 443 ────────────────► block                          │
   │   ├─ elevenlabs.io TCP ────────────────────► london                         │
   │   └─ everything else ──────────────────────► direct                         │
   └───────────────────────────────┬──────────────────────────────┬──────────────┘
                                   │                              │ SOCKS5 port 1080
                                   │                              │ (public)
                                   ▼                              │
                      ┌────────────────────┐                      │
                      │ London             │◄─────────────────────┘
                      │ 132.145.52.74      │
                      │ 100.119.182.9      │
                      │ microsocks :1080   │
                      └─────────┬──────────┘
                                │
                                ▼
                             internet
```

All machines (NixOS clients, Frankfurt, London) are on the same Tailscale network (`tailf108.ts.net`).

## Traffic routing rules

### NixOS clients

| Traffic | Outbound | Path |
|---------|----------|------|
| Private IPs (RFC1918, loopback) | `direct` | Local network |
| Russian IPs (`geoip-ru`) | `direct` | Local ISP |
| `*.google.com` / `google.com` | `london` | Tailscale → London microsocks → internet |
| `*.elevenlabs.io` / `elevenlabs.io` | `london` | Tailscale → London microsocks → internet |
| Everything else | `proxy` | VLESS+Reality → Frankfurt → internet |

### macOS client (m1max)

| Traffic | Outbound | Path |
|---------|----------|------|
| UDP port 443 (QUIC/HTTP3) | `block` | Dropped — forces TCP fallback |
| Private IPs (RFC1918, loopback) | `direct` | Local network |
| Russian IPs (`geoip-ru`) | `direct` | Local ISP |
| Everything else | `proxy` | VLESS+Reality → Frankfurt → internet |

Google and ElevenLabs traffic are routed to London at the Frankfurt level (see Frankfurt section).

### Frankfurt sing-box (applies to all clients)

| Traffic | Outbound | Path |
|---------|----------|------|
| `geosite-google` UDP 443 | `block-quic` | Dropped |
| `geosite-google` IPv6 TCP | `internet` | Direct from Frankfurt; London SOCKS has no public IPv6 |
| `geosite-google` TCP | `london` | London microsocks → internet |
| `*.elevenlabs.io` / `elevenlabs.io` UDP 443 | `block-quic` | Dropped |
| `*.elevenlabs.io` / `elevenlabs.io` IPv6 TCP | `internet` | Direct from Frankfurt; London SOCKS has no public IPv6 |
| `*.elevenlabs.io` / `elevenlabs.io` TCP | `london` | London microsocks → internet |
| Everything else | `internet` | Direct → internet |

## Components

### NixOS clients

Managed by this repo. Affected hosts: `zenbook`, `x13`, `x1carbon`, `um960pro`.

**Module**: `modules/nixos/vless.nix`

**sing-box config** (per-host JSON in `secrets/vless/<host>.json`):
- Inbound: TUN (`nekoray-tun`, `auto_route: true`, `strict_route: true`, `auto_redirect: true`)
- Inbound: Mixed SOCKS5/HTTP on `127.0.0.1:2080` (for manual use / testing)
- `route_exclude_address` includes `100.64.0.0/10` (Tailscale CGNAT — bypasses TUN so
  connections to Tailscale peer IPs go directly through the `tailscale0` interface)
- Outbound `proxy`: VLESS+Reality to Frankfurt
- Outbound `london`: SOCKS5 to `100.119.182.9:1080`, `bind_interface: tailscale0`
- Outbound `direct`: plain direct connection
- System DNS is pinned to local `dnsmasq` on `127.0.0.1`; `dnsmasq` filters public AAAA
  answers and forwards `*.tailf108.ts.net` to Tailscale DNS (`100.100.100.100`) so MagicDNS
  continues to work.

**Key config detail — `bind_interface: tailscale0` on the `london` outbound**:
sing-box uses `auto_detect_interface: true`, which binds all outbound sockets to the default
internet interface (e.g. `wlo1`). The Tailscale peer IP `100.119.182.9` is not reachable via
`wlo1` — it requires `tailscale0`. Without `bind_interface`, connections to the London SOCKS5
time out. With it, sing-box explicitly uses the Tailscale interface for this outbound.

**Consequence**: the `london` outbound silently fails (per-connection error, not a service
crash) when Tailscale is not running. All other traffic continues to work via VLESS.

**IPv6 policy**: NixOS VLESS clients are intentionally IPv4-only for public traffic. Kernel IPv6
stays enabled for local/Tailscale needs, but public AAAA answers are filtered before applications
see them. This avoids failures where glibc picks an IPv6 result while the host has no usable
public IPv6 default route. Tailscale DNS injection is disabled with `--accept-dns=false`; MagicDNS
is preserved by split DNS in local `dnsmasq`.

**IPv6/DNS diagnostics**:
```bash
getent ahosts youtube.com          # should return IPv4 only
ping youtube.com                   # should pick IPv4
ping -6 youtube.com                # expected to fail without public IPv6
getent ahosts london.tailf108.ts.net # should resolve via MagicDNS
```

**NixOS host config snippet** (same for all four hosts):
```nix
services.vless = {
  enable = true;
  configPath = "/home/nik/nix-config/secrets/vless/<host>.json";
  configUser = "nik";
};
```

### macOS client (m1max)

**sing-box GUI app**: `io.nekohasekai.sfavt` (sing-box for Apple platforms)

**Config**: `secrets/vless/m1max-gui.json` — load manually in the sing-box GUI app.

**Key differences from NixOS clients**:
- Google and ElevenLabs routing are handled at Frankfurt, not on the client — the Mac config has no `london` outbound
- UDP 443 (QUIC/HTTP3) is blocked at the client to force TCP, enabling domain sniffing at Frankfurt
- No Tailscale dependency — London is reached via Frankfurt over the public internet
- Keep config syntax aligned with the sing-box version bundled in the GUI app; older app builds may reject newer config fields

**macOS + Tailscale conflict**: macOS only allows one active VPN Network Extension at a time.
sing-box GUI and Tailscale.app both use Network Extensions and cannot run simultaneously.
This is why the Mac config offloads London routing to Frankfurt instead of using Tailscale directly.

### Frankfurt — VLESS+Reality server

**Host**: `wire.nikcode.xyz` / `31.58.85.163`
**Tailscale IP**: `100.76.253.85`
**SSH**: `ssh -i ~/.ssh/id_rsa_1 root@wire.nikcode.xyz`

Deployed with **[reality-ezpz](https://github.com/aleskxyz/reality-ezpz)**, a shell-script
installer that creates a Docker Compose stack running `sing-box` as a VLESS+Reality server.

**Config location**: `/opt/reality-ezpz/`

**Encrypted disaster-recovery bundle**: `secrets/proxy/frankfurt/`
- Store exact copies of live Frankfurt recovery files here:
  - `secrets/proxy/frankfurt/config`
  - `secrets/proxy/frankfurt/engine.conf`
  - `secrets/proxy/frankfurt/docker-compose.yml`
  - `secrets/proxy/frankfurt/users`
- These paths are intended to hold the like-for-like recovery state for a replacement VPS while keeping secrets under git-crypt.
- Status: populated from live Frankfurt host on `2026-04-22`.

**Current status note (2026-04-22)**: the Frankfurt server was upgraded from
`sing-box 1.8.14` to `1.13.5` after users across multiple ISPs and OSes reported VLESS
failures. Keeping the same REALITY identity (`private_key`, `short_id`, UUIDs,
`server_name`) and upgrading the server restored connectivity for at least one previously
failing client (`zenbook`). Treat server/core version skew as first suspect if a broad
multi-client outage happens again.

**Current status note (2026-04-26)**: running `./realityez` on Frankfurt regenerated
`engine.conf` and `docker-compose.yml`, which reintroduced removed legacy inbound fields,
dropped the London routing rules, and reverted the compose image/env settings. The container
then restarted under `sing-box 1.13.5` with:
`decode config at config.json: inbounds[1]: legacy inbound fields are deprecated ... removed in sing-box 1.13.0`.
Recovery was to remove those inbound fields again, restore London routing, restore compose to
`gzxhwq/sing-box:1.13.5`, and force-recreate the container.

Key files:
- `config` — reality-ezpz parameters (actual secret values live on the Frankfurt host in `/opt/reality-ezpz/config`)
- `engine.conf` — sing-box JSON config. **Manually maintained** — `./realityez -m` rewrites this file from reality-ezpz templates and user list, which drops the manually added London routing rules.
- `docker-compose.yml` — Docker Compose stack definition

**Manual compatibility changes currently present**:
- `docker-compose.yml` sets `ENABLE_DEPRECATED_LEGACY_DNS_SERVERS="true"`
- `docker-compose.yml` sets `ENABLE_DEPRECATED_MISSING_DOMAIN_RESOLVER="true"`
- `docker-compose.yml` runs `sing-box run -c /config.json` and mounts `./engine.conf` at
  `/config.json`; the image creates an anonymous volume at `/etc/sing-box`, which can mask
  `/etc/sing-box/config.json` if the config is mounted there
- `engine.conf` had deprecated inbound fields removed from the VLESS inbound so `sing-box 1.13.5` would start:
  `sniff`, `sniff_override_destination`, `domain_strategy`

These compatibility env vars are temporary migration aids for the old reality-ezpz-generated
config. If the config is fully migrated to modern sing-box syntax later, remove them.

**Manually added to `engine.conf`** (beyond what reality-ezpz generates):
- Outbound `london`: SOCKS5 to `132.145.52.74:1080` with auth
- Outbound `block-quic`: block type
- Rule set `geosite-google` from SagerNet/sing-geosite
- Rule: `geosite-google` + UDP 443 → `block-quic`
- Rule: `geosite-google` → `london`
- Rule: `domain_suffix: elevenlabs.io` + UDP 443 → `block-quic`
- Rule: `domain_suffix: elevenlabs.io` → `london`

To apply config-only changes: `docker restart reality-ezpz-engine-1`

To apply Compose/image/env/command changes:
```bash
cd /opt/reality-ezpz
docker compose up -d --force-recreate --no-deps engine
```

Backups:
- historical backup: `/opt/reality-ezpz/engine.conf.bak`
- before 1.13.5 migration: `/opt/reality-ezpz/engine.conf.pre-1.13-fix-<timestamp>`
- before compose edits: `/opt/reality-ezpz/docker-compose.yml.bak-<timestamp>`

**Operational warning**: adding users with `./realityez -m` preserves the VLESS user list but regenerates `/opt/reality-ezpz/engine.conf`. After running it, re-apply the manual `london` / `block-quic` / `geosite-google` / `elevenlabs.io` sections before restarting the container.

**Preferred user-management workflow**: do **not** use `./realityez -m` for this host anymore. Use the repo-managed helper script instead, which edits `engine.conf` in place and keeps `/opt/reality-ezpz/users` synced without touching the custom London routing.

Deploy helper to Frankfurt:
```bash
scp -i ~/.ssh/id_rsa_1 scripts/reality-user.py root@wire.nikcode.xyz:/opt/reality-ezpz/reality-user
ssh -i ~/.ssh/id_rsa_1 root@wire.nikcode.xyz 'chmod +x /opt/reality-ezpz/reality-user'
```

Usage on Frankfurt:
```bash
# List users
/opt/reality-ezpz/reality-user list

# Add new user, validate engine.conf, print share URL
/opt/reality-ezpz/reality-user add alice

# Show share URL for existing user
/opt/reality-ezpz/reality-user show alice

# Show share URL and terminal QR code
/opt/reality-ezpz/reality-user show alice --qr
```

`add` creates timestamped backups of `engine.conf` and `users`, validates the updated config with `sing-box check`, and aborts with rollback on validation failure. It does **not** restart the container.

**`/opt/reality-ezpz/config`**:
```
core=sing-box
security=reality
service_path=455adfc9
public_key=NE0dmwv1gVoxgOUdkxIUWYsnfDkQbfHJ5xaruyYTHTo
private_key=<stored-on-frankfurt-host>
short_id=cef91402cd7d7755
transport=tcp
domain=www.google.com
server=31.58.85.163
port=443
safenet=OFF
warp=OFF
```

**Docker container**: `gzxhwq/sing-box:1.13.5`, named `reality-ezpz-engine-1`
- Listens on `0.0.0.0:443` (host) → container port `8443` (VLESS+Reality)
- Listens on `0.0.0.0:80` (host) → container port `8080` (HTTP redirect / camouflage)

**Upgrade caveat**: `1.13.x` is stricter than `1.8.x`. A straight image bump from
`1.8.14` caused startup failures until deprecated config paths were handled. Typical symptoms:
- `legacy DNS servers is deprecated`
- `missing route.default_domain_resolver or domain_resolver in dial fields is deprecated`
- `legacy inbound fields are deprecated ... and removed in sing-box 1.13.0`

If the container restarts in a loop after upgrade, inspect with:
```bash
cd /opt/reality-ezpz
docker logs --tail 100 reality-ezpz-engine-1
docker run --rm \
  -e ENABLE_DEPRECATED_LEGACY_DNS_SERVERS=true \
  -e ENABLE_DEPRECATED_MISSING_DOMAIN_RESOLVER=true \
  -v /opt/reality-ezpz/engine.conf:/etc/sing-box/config.json \
  gzxhwq/sing-box:1.13.5 check -c /etc/sing-box/config.json
```

**To recover from scratch**:
```bash
# Install reality-ezpz
bash <(curl -sL https://raw.githubusercontent.com/aleskxyz/reality-ezpz/master/reality-ezpz.sh) \
  --transport tcp \
  --domain www.google.com \
  --port 443

# After install, restore the real config values from `/opt/reality-ezpz/config`
# on the Frankfurt host so existing client configs continue to work, then restart:
cd /opt/reality-ezpz && docker compose down && docker compose up -d
```

Also install Tailscale and join the tailnet (see Tailscale section below).

**Why VLESS+Reality?** VLESS+Reality uses TLS 1.3 with a real server's certificate
(www.google.com) as camouflage, making the traffic indistinguishable from normal HTTPS to
deep-packet-inspection systems.

## Troubleshooting notes

### Broad VLESS outage checklist

If multiple users on different ISPs and OSes report that VLESS stopped working, check in this order:

1. Compare client and server sing-box versions first.
2. Keep REALITY identity unchanged during diagnosis:
   `private_key`, `public_key`, `short_id`, UUIDs, `server_name`.
3. Correlate server and client logs for same client attempt.
4. Only after version/config issues are ruled out, spend time on ISP/DPI theories.

### Log patterns and likely meaning

| Signal | Where | Usually means |
|--------|-------|---------------|
| `REALITY: processed invalid connection` | Frankfurt server | Server rejected handshake bytes; suspect client/server mismatch, stale profile, or network-path interference |
| `reality verification failed` | Client | Client could connect to server socket but REALITY proof/handshake did not validate |
| Both above at same time for same client | Both ends | Strong signal of handshake-level failure, not simple IP routing failure |
| `i/o timeout` to `31.58.85.163:443` | Client | Packet path problem, reachability issue, or heavy filtering |

### What 2026-04-22 incident taught

Before server upgrade:
- Frankfurt server: `sing-box 1.8.14`
- zenbook client: `sing-box 1.13.5`
- server logs: `REALITY: processed invalid connection`
- client logs: `reality verification failed`
- multiple users reported breakage

After upgrading Frankfurt to `1.13.5` while keeping the same REALITY identity:
- zenbook recovered without client config changes
- this strongly suggests server version/config compatibility was at least a major part of the outage
- nationwide VPN interference remained possible, but was no longer best first explanation

### Future diagnosis workflow

1. Check Frankfurt container status and logs.
2. Confirm current sing-box image version on server.
3. Compare one failing client's logs with server logs from same timestamp.
4. If server is much older than clients, upgrade server before changing REALITY keys.
5. After upgrade, retest one known failing client immediately.
6. If failures persist across modern versions, then test alternate networks (home ISP vs hotspot) and only then escalate DPI/interference hypothesis.

### London — SOCKS5 relay

**Host**: `132.145.52.74` (Oracle Cloud, Ubuntu)
**Tailscale IP**: `100.119.182.9`
**SSH**: `ssh ubuntu@132.145.52.74`

Runs `microsocks` — a minimal single-binary SOCKS5 server.
The actual SOCKS password is stored in the per-host client configs under
`secrets/vless/<host>.json` and in the live unit on the London host at
`/etc/systemd/system/microsocks.service`.

**Encrypted disaster-recovery bundle**: `secrets/proxy/london/`
- Store the current `microsocks.service` unit here.
- Store any firewall/security-list notes that are required for rebuild in `notes.md`.
- Status: populated from live London host on `2026-04-22`.

**`/etc/systemd/system/microsocks.service`**:
```ini
[Unit]
Description=microsocks SOCKS5 proxy (tailnet only)
After=network-online.target
Wants=network-online.target

[Service]
ExecStart=/usr/bin/microsocks -p 1080 -u socks -P <stored-in-secrets-vless-and-london-unit>
Restart=on-failure
RestartSec=5
DynamicUser=yes
NoNewPrivileges=yes
PrivateTmp=yes

[Install]
WantedBy=multi-user.target
```

Listens on `0.0.0.0:1080` with username/password authentication.

**Network access**:
- NixOS clients connect via Tailscale (`100.119.182.9:1080`)
- Frankfurt Docker container connects via public IP (`132.145.52.74:1080`) — Oracle Cloud security list and host iptables both have port 1080 open. The iptables rule is persisted via `netfilter-persistent`.
- The macOS client connects to London indirectly — via Frankfurt (VLESS) → London (SOCKS5)

**To recover from scratch**:
```bash
# Install microsocks
sudo apt install microsocks

# Create the systemd unit (contents above)
sudo nano /etc/systemd/system/microsocks.service

# Enable and start
sudo systemctl daemon-reload
sudo systemctl enable --now microsocks

# Verify
systemctl status microsocks
ss -tlnp | grep 1080
```

Also install Tailscale and join the tailnet (see Tailscale section below).

## Tailscale network

**Tailnet**: `tailf108.ts.net`

| Node | Hostname | Tailscale IP | Role |
|------|----------|-------------|------|
| zenbook | zenbook | 100.73.33.90 | NixOS client |
| x13 | x13 | — | NixOS client |
| x1carbon | x1carbon | — | NixOS client |
| um960pro | um960pro | — | NixOS client |
| Frankfurt | frankfurt | 100.76.253.85 | VLESS server |
| London | london | 100.119.182.9 | SOCKS5 relay |

**To add a new node to the tailnet**:
```bash
# Install
curl -fsSL https://tailscale.com/install.sh | sh
# Join
sudo tailscale up --authkey <reusable-auth-key-from-admin-console>
```

If provider-specific DNS cutover notes or tokens are needed for recovery, store them in the
encrypted bundle under `secrets/proxy/dns/` rather than in this document.

Current state:
- `secrets/proxy/dns/wire.nikcode.xyz.md` contains current hostname/IP mapping and cutover requirements.
- DNS provider-specific control-plane details still need to be filled in manually because they cannot be recovered from the VPS hosts.

## Design decisions

### Why not Tailscale exit node for the London path?

The original approach used `tailscale set --exit-node=london`, which made Tailscale route all
system traffic through London. This conflicted with sing-box's TUN transparent proxy:

- Tailscale's exit node adds a `0.0.0.0/0` route to its ip routing table at **rule priority 1**
- sing-box's auto_route rules operate at priorities 9000+ and 32768
- Rule priority 1 intercepts **all** traffic before sing-box can see it, completely bypassing the
  VLESS proxy
- Additionally, `tailscale set` is persistent — the exit node is re-activated on every boot,
  breaking the setup even before sing-box starts

### Why not chain through Frankfurt for NixOS clients (zenbook → VLESS → Frankfurt → London)?

Frankfurt's sing-box runs inside Docker, which does not share the host's Tailscale network
namespace. The container cannot reach `100.119.182.9` (London's Tailscale IP). NixOS clients
therefore connect to London directly over Tailscale.

For the macOS client, this constraint is handled differently: London's public port 1080 was
opened (Oracle Cloud security list + host iptables), allowing Frankfurt's Docker container to
reach London via its public IP. The macOS client routes all traffic through VLESS to Frankfurt,
where `geosite-google` and `elevenlabs.io` traffic are forwarded to London over the public internet.

### Why `bind_interface: tailscale0`?

sing-box's `auto_detect_interface: true` detects the default internet interface (`wlo1`) and
binds all outbound sockets to it. `100.119.182.9` is a Tailscale CGNAT address, only reachable
via `tailscale0`. Without an explicit `bind_interface`, the connection times out because the
packet is sent out through `wlo1` where there is no route to `100.64.0.0/10`.

### Why microsocks with password auth?

Port 1080 is now open to the public internet (required for Frankfurt's Docker container to reach
London). Password authentication prevents the proxy from being used as an open relay.
