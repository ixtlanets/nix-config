# macOS Lima Router VM Design

Date: 2026-06-02
Updated: 2026-06-03

## Summary

The proposed macOS proxy architecture moves the full Linux routing stack into a small
NixOS VM managed by Lima. The first canary targets `m1max` only. macOS stops running
sing-box GUI as a Network Extension while this design is enabled and
instead sends routed traffic to the VM. The VM runs `tailscaled`, `sing-box`, DNS
policy, and eventually Docker, so it can reproduce the current NixOS client behavior:

- local/private traffic goes direct
- Russian geoip traffic goes direct
- Google traffic goes to London over Tailscale
- all remaining public traffic goes to Frankfurt over VLESS+Reality
- Docker container traffic follows the same policy as host traffic in a later phase
- tailnet peers can reach selected services running on the Mac through explicit
  forwarding from the VM

This design intentionally does not make the Mac itself a full Tailscale node. The VM
is the Tailscale node. The Mac is reachable behind it through explicit forwarded
ports rather than through the Mac's current LAN address.
This avoids the macOS limitation where Tailscale.app and sing-box GUI both compete for
the single active VPN Network Extension slot.

## Goals

- Replace the current macOS sing-box GUI client with a Linux router VM.
- Keep routing behavior aligned with existing NixOS clients.
- Allow macOS applications to use the VM as their internet gateway.
- Allow tailnet peers to connect to selected services running on macOS, starting with
  SSH and HTTP-style services.
- Make the setup reproducible from this repository as much as practical.
- Keep Docker traffic on the same routing policy path in phase 5, including
  `google.com -> London`.
- Prefer a lightweight, CLI-first virtualization stack.
- Provide a simple disable path so the user can return to the current sing-box GUI
  setup when the canary misbehaves.

## Non-Goals

- Do not require macOS to appear as its own Tailscale device.
- Do not require Tailscale ACL identity to distinguish Mac traffic from VM traffic.
- Do not use Tailscale exit node mode for the London path.
- Do not depend on the macOS sing-box GUI Network Extension.
- Do not automatically start or manage the sing-box GUI fallback. The router VM
  scripts should restore ordinary macOS routing and leave GUI activation manual.
- Do not depend on the Mac's current Wi-Fi, Ethernet, or LTE LAN address for inbound
  tailnet access. That address is not stable enough for advertised subnet routes.
- Do not include Docker Engine in the first canary; it remains phase 5 work.
- Do not solve all VM image lifecycle automation in the first canary. The first design
  should prove routing, DNS, rollback, and inbound reachability before polishing image
  rebuild/import workflows or Docker.

## Recommended Approach

Use Lima as the macOS VM orchestrator and run a small NixOS router guest.

Lima is preferred over VMware Fusion for this project because it is lighter, CLI-first,
and easier to represent as repo-managed configuration. The first canary should try a
Lima network mode that gives the Mac and VM stable reachability across Wi-Fi, Ethernet,
and LTE changes. If Lima's default networking cannot be used as a Mac gateway, test
`vzNAT` and then `socket_vmnet` shared/bridged modes before falling back to VMware
Fusion. Root-owned helpers and launchd services are acceptable because the setup is
installed through `sudo darwin-rebuild switch --flake ~/nix-config/.#m1max`.

VMware Fusion remains a fallback because its bridged networking is mature and already
present on `m1max`, but it is a heavier and less declarative fit for a small always-on
router VM. OrbStack is likely the lightest product for general Linux machines, but its
networking model is more product-managed and less suitable for a transparent router
canary.

## High-Level Architecture

```text
macOS host
  local connected networks  -> native macOS route, direct
  selected bypass routes    -> native macOS route, direct
  default public traffic    -> Lima router VM LAN IP
  DNS                       -> Lima router VM DNS listener
  router control            -> macos-router-vm enable/disable/status/panic

Lima NixOS router VM
  eth0                      -> Lima/vmnet network toward macOS/LAN
  tailscale0                -> tailnet reachability and London SOCKS path
  sing-box TUN              -> transparent policy routing for VM and Docker traffic
  dnsmasq/sing-box DNS      -> IPv4-only public DNS and MagicDNS split handling
  forwarded ports           -> tailnet peer access to selected Mac services
  docker0/br-*              -> phase 5 container traffic intercepted by sing-box

Frankfurt
  VLESS+Reality server      -> default public exit

London
  microsocks on tailnet     -> Google and other London-routed destinations

tailnet peers
  reach Mac services        -> VM tailnet IP or MagicDNS name, forwarded to Mac
```

## Traffic Policy

The VM should reproduce the NixOS client routing shape from `secrets/vless/zenbook.json`
and `modules/nixos/vless.nix`.

| Traffic | VM outbound | Path |
|---------|-------------|------|
| RFC1918/private/link-local/loopback/multicast | `direct` | local network |
| Tailscale CGNAT `100.64.0.0/10` | kernel route/direct | `tailscale0` |
| WireGuard host overlay `198.18.77.0/24` | kernel route/direct | existing overlay route if enabled |
| Russian IPs (`geoip-ru`) | `direct` | local ISP |
| `google.com` and `*.google.com` | `london` | `tailscale0 -> London microsocks -> internet` |
| future London domains such as `elevenlabs.io` | `london` | `tailscale0 -> London microsocks -> internet` |
| all other public traffic | `proxy` | `VLESS+Reality -> Frankfurt -> internet` |

The VM should keep `route_exclude_address` aligned with Linux clients:

```json
[
  "127.0.0.0/8",
  "::1/128",
  "10.0.0.0/8",
  "172.16.0.0/12",
  "192.168.0.0/16",
  "100.64.0.0/10",
  "169.254.0.0/16",
  "224.0.0.0/4",
  "198.18.77.0/24"
]
```

The London outbound should keep the Linux-specific Tailscale binding:

```json
{
  "tag": "london",
  "type": "socks",
  "server": "100.119.182.9",
  "server_port": 1080,
  "username": "socks",
  "password": "$SOCKS_PASSWORD_FROM_ENCRYPTED_SECRETS",
  "bind_interface": "tailscale0"
}
```

The `proxy` outbound remains VLESS+Reality to Frankfurt. Secret values and user UUIDs
must stay in encrypted `secrets/**` material, not in this design document.

## macOS Host Routing

The Mac should use the Lima VM as the gateway for public internet traffic while keeping
local connected networks direct.

Expected routing shape:

```text
default                     -> $VM_LAN_IP
100.64.0.0/10               -> $VM_LAN_IP
connected LAN prefix        -> native macOS interface
loopback/link-local         -> native macOS routes
```

The exact route management should be done by a repo-managed script or launchd job on
macOS. The script should:

1. discover or read the VM LAN IP
2. add or replace the default route through the VM
3. add `100.64.0.0/10` through the VM for tailnet peer access
4. leave connected LAN routes intact
5. set DNS to the VM DNS listener
6. provide a rollback command that restores the original gateway and DNS

The Mac's connected LAN route is more specific than `default`, so local LAN traffic
continues to go directly through Wi-Fi/Ethernet. If additional direct bypass prefixes
are needed later, they should be represented explicitly in the host route script.

## DNS Design

DNS should be centralized in the VM. The Mac should point system DNS to the VM.

The VM should preserve the Linux policy:

- public AAAA answers are filtered or rejected for IPv4-only proxy behavior
- MagicDNS for `tailf108.ts.net` resolves through Tailscale DNS `100.100.100.100`
- regular public DNS uses the same bootstrap/remote split as the NixOS sing-box config
- DNS traffic from applications and containers is hijacked by sing-box where possible

This avoids a failure mode where macOS resolves a domain itself, sends the connection to
the VM by IP, and sing-box no longer has enough domain information to route
`google.com -> London`. SNI sniffing helps, but DNS centralization makes the route
decision more deterministic.

## Inbound Access to Mac Services

The VM should be the Tailscale node and expose selected Mac services through explicit
port forwarding. Tailnet peers should connect to the VM's Tailscale IP or MagicDNS
name, and the VM should forward approved ports to the Mac's stable host-side Lima/vmnet
address.

Initial canary model:

```text
tailnet peer -> m1router.tailf108.ts.net:$PORT -> VM port forward -> Mac host-side VM link IP:$PORT
```

This avoids advertising the Mac's current LAN IP. `m1max` moves between Wi-Fi, LTE, and
other networks, so a `/32` route for the current LAN address would be unstable and may
need repeated Tailscale admin approval. The first forwarded ports should cover SSH and
HTTP-style services; additional ports can be added explicitly after the core path is
validated.

Port forwarding should be owned by the VM configuration where possible. If a host-side
packet filter rule is needed, it must be installed and removed by the same
`macos-router-vm` control script used for routing rollback.

The Mac services must listen on the host-side Lima/vmnet address or on all interfaces.
Services that bind only to `127.0.0.1` will not be reachable from the VM unless a
separate local forwarding rule is added on macOS.

Subnet route advertisement for the Mac can be revisited later if full routed access is
needed. It is not part of the canary.

## Docker Design

Docker Desktop on macOS is a risk because it runs containers in its own VM. Its egress
may or may not follow the macOS system default route in the same way as regular macOS
applications. That makes it a poor source of truth for policy routing.

Recommended model:

- keep Docker out of the first canary
- in phase 5, run Docker Engine inside the Lima NixOS router VM
- expose Docker access to macOS through the Docker CLI context or socket forwarding
- route container traffic through the same sing-box TUN path as VM host traffic

This reproduces the current NixOS behavior:

```text
container -> docker0/br-* -> sing-box auto_redirect -> routing policy
```

Required VM-side behavior:

- `virtualisation.docker.enable = true`
- sing-box TUN uses Linux `auto_route`, `auto_redirect`, and `strict_route`
- firewall permits Docker bridge traffic to the sing-box redirect port, matching
  `modules/nixos/vless.nix`

Expected Docker examples:

| Container request | Expected path |
|-------------------|---------------|
| `curl https://google.com` | London SOCKS over Tailscale |
| `curl https://youtube.com` | Frankfurt VLESS unless matched by Google rules |
| `curl https://ifconfig.me` | Frankfurt VLESS |
| `curl http://192.168.x.x` | direct local network |
| Russian geoip target | direct local ISP |

Docker Desktop can be tested as a fallback, but the design should not depend on it.
Until phase 5, Docker validation commands are out of scope for the canary.

## Lima Management Model

The host side should be represented in nix-darwin/Home Manager as:

- packages or Homebrew formulae needed for Lima and networking helpers
- Lima VM YAML template generated into the user config directory
- root-owned launchd daemon or agent to start the router VM at login or boot
- root-owned launchd daemon/script to apply host routes, DNS, and optional pf rules
  after the VM is reachable
- rollback script for routes, DNS, and forwarding rules
- health check script for VM, sing-box, tailscale, and DNS
- user-facing `macos-router-vm` control CLI with `enable`, `disable`, `status`, and
  `panic` commands

The guest side should be represented as a normal NixOS host, likely a new host such as
`hosts/m1router/nixos/configuration.nix` rather than overloading `hosts/vmmac`.

Guest responsibilities:

- enable Tailscale with `--accept-dns=false`
- enable forwarding
- run sing-box via the existing `services.vless` module or a router-specific variant
- run DNS policy compatible with current Linux clients
- expose selected forwarded ports from tailnet to the Mac host-side VM link address
- leave Docker disabled until phase 5
- expose SSH for management from the Mac

## Control and Rollback

The router canary must be easy to disable before it is allowed to replace the current
sing-box GUI workflow. The host-side control command should be:

```bash
macos-router-vm enable
macos-router-vm disable
macos-router-vm status
macos-router-vm panic
```

`enable` should:

1. start or verify the Lima VM
2. wait for VM health checks to pass
3. save current macOS default gateway, DNS settings, and relevant pf state to a state file
4. apply the VM DNS and routing changes
5. apply forwarding rules only after the VM and target Mac address are reachable

`disable` should:

1. disable automatic route application by launchd
2. restore the saved default gateway and DNS settings
3. remove explicit routes such as `100.64.0.0/10` if they were added
4. remove router-owned pf or forwarding rules
5. leave the VM running for diagnostics unless an explicit stop flag is used

`panic` should be a minimal emergency rollback path. It must not depend on the VM being
reachable. It should restore route and DNS state from the last saved state file and
remove router-owned pf anchors or routes with conservative shell commands. This command
is the path to run before manually re-enabling the current sing-box GUI configuration.

`status` should show whether the router is enabled, whether launchd auto-apply is
active, the current default gateway, current DNS servers, VM reachability, Tailscale
status, `vless-sing-box` status, and active forwarded ports.

The control script should not start sing-box GUI automatically. Fallback remains manual:

```text
macos-router-vm disable
verify default route and DNS are restored
start sing-box GUI manually
```

## Canary Plan

Phase 1: VM networking and host routing

- create Lima NixOS VM
- confirm Mac can reach VM and VM can reach internet
- implement `macos-router-vm status`, `disable`, and `panic` before touching the Mac
  default route
- route only `100.64.0.0/10` through VM first
- verify Mac can reach tailnet nodes through VM
- rollback route cleanly

Phase 2: sing-box policy in VM

- enable sing-box with Linux-style config
- verify VM host traffic:
  - private IP direct
  - geoip-ru direct
  - Google through London
  - default through Frankfurt
- verify MagicDNS
- verify public AAAA filtering/IPv4-only behavior

Phase 3: macOS default route through VM

- make `enable` refuse to change the default route unless VM health checks pass
- set Mac default route to VM
- set Mac DNS to VM
- verify Safari/curl behavior
- verify local LAN access remains direct
- verify tailnet access from Mac
- verify `disable` and `panic` rollback while the VM is healthy and after the VM is
  stopped

Phase 4: inbound Mac services

- configure explicit VM forwarding for SSH and HTTP-style service ports
- from another tailnet node, connect to the VM Tailscale IP or MagicDNS name on those
  ports
- verify the Mac service receives the connection through the host-side VM link
- verify forwarded ports are removed by `disable` and `panic`

Phase 5: Docker

- run Docker Engine inside the Lima VM
- point macOS Docker CLI at the VM engine
- verify container requests follow policy
- only then decide whether Docker Desktop should be removed, ignored, or kept for
  unrelated workflows

## Validation Commands

Run these on the VM:

```bash
tailscale status
ip route
ip rule
systemctl status vless-sing-box
systemctl status tailscaled
resolvectl status || cat /etc/resolv.conf
curl -4 https://icanhazip.com
curl -4 https://ifconfig.me
curl -4 https://www.google.com --head
getent ahosts google.com
getent ahosts london.tailf108.ts.net
docker run --rm curlimages/curl:latest -4 https://icanhazip.com
docker run --rm curlimages/curl:latest -4 https://www.google.com -I
```

Skip Docker commands until phase 5.

Run these on macOS:

```bash
macos-router-vm status
route -n get default
netstat -rn -f inet
scutil --dns
curl -4 https://icanhazip.com
curl -4 https://www.google.com -I
ping $TAILNET_NODE_IP
macos-router-vm disable
route -n get default
scutil --dns
```

Run these from another tailnet node:

```bash
tailscale status
ssh -p $FORWARDED_SSH_PORT $MAC_USER@$M1ROUTER_TAILNET_NAME
curl http://$M1ROUTER_TAILNET_NAME:$FORWARDED_HTTP_PORT
```

## Rollback

The host route script must support rollback before the default route canary is used.
Rollback is a release blocker, not an operational improvement.

Rollback should:

- restore the original macOS default gateway
- restore the original DNS settings
- remove explicit `100.64.0.0/10` route through the VM if added
- remove router-owned forwarding rules and pf anchors
- stop using the VM as Docker context
- leave the VM running for diagnostics unless explicitly stopped
- work even when the Lima VM is stopped or broken

The current macOS sing-box GUI config should remain available until the Lima design is
validated. The router control script should restore normal macOS routing so the user can
manually start the sing-box GUI after `disable` or `panic`.

## Risks and Open Questions

- Lima network mode must support the required gateway shape. If Lima's
  default networking is insufficient, test vmnet/socket_vmnet modes before falling back
  to VMware Fusion.
- The VM's own internet egress must not recursively depend on the Mac's default route
  after the Mac points its default route at the VM. This must be tested before default
  route canary.
- macOS host services may bind only to loopback. Those services will not be reachable
  from tailnet peers through the VM unless they bind to the host-side VM link address or
  all interfaces, or macOS runs a separate local forwarder.
- macOS firewall rules may block inbound traffic arriving from the VM/LAN path.
- Forwarded ports are less general than subnet routing. This is intentional for the
  canary; full routed access can be revisited later.
- Docker Desktop behavior should not be assumed. Prefer Docker Engine inside the router
  VM for deterministic policy routing, but only in phase 5.
- Domain routing depends on DNS/sniffing visibility. Mac DNS should point to the VM to
  reduce surprises.
- IPv6 should stay conservative initially. Match current Linux client behavior:
  public IPv4-only, while preserving local/Tailscale needs.
- The fallback path must stay boring: `macos-router-vm disable` or `panic`, verify
  routes and DNS, then manually start sing-box GUI.

## References

- Main proxy documentation: `docs/proxy-setup.md`
- Current Linux client config example: `secrets/vless/zenbook.json`
- Current macOS GUI config: `secrets/vless/m1max-gui.json`
- NixOS sing-box module: `modules/nixos/vless.nix`
- Existing VMware guest host: `hosts/vmmac/nixos/configuration.nix`
- Lima docs: https://lima-vm.io/docs/
- Lima VMNet docs: https://lima-vm.io/docs/config/network/vmnet/
- Tailscale subnet routers: https://tailscale.com/kb/1019/subnets
- Tailscale with other VPNs: https://tailscale.com/docs/reference/faq/other-vpns
- sing-box TUN inbound: https://sing-box.sagernet.org/configuration/inbound/tun/
