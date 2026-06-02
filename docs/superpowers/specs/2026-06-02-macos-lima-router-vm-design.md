# macOS Lima Router VM Design

Date: 2026-06-02

## Summary

The proposed macOS proxy architecture moves the full Linux routing stack into a small
NixOS VM managed by Lima. macOS stops running sing-box GUI as a Network Extension and
instead sends routed traffic to the VM. The VM runs `tailscaled`, `sing-box`, DNS
policy, and optionally Docker, so it can reproduce the current NixOS client behavior:

- local/private traffic goes direct
- Russian geoip traffic goes direct
- Google traffic goes to London over Tailscale
- all remaining public traffic goes to Frankfurt over VLESS+Reality
- Docker container traffic follows the same policy as host traffic
- tailnet peers can reach services running on the Mac through the VM as a Tailscale
  subnet router

This design intentionally does not make the Mac itself a full Tailscale node. The VM
is the Tailscale node. The Mac is reachable behind it through a routed or NATed path.
This avoids the macOS limitation where Tailscale.app and sing-box GUI both compete for
the single active VPN Network Extension slot.

## Goals

- Replace the current macOS sing-box GUI client with a Linux router VM.
- Keep routing behavior aligned with existing NixOS clients.
- Allow macOS applications to use the VM as their internet gateway.
- Allow tailnet peers to connect to services running on macOS.
- Make the setup reproducible from this repository as much as practical.
- Keep Docker traffic on the same routing policy path, including `google.com -> London`.
- Prefer a lightweight, CLI-first virtualization stack.

## Non-Goals

- Do not require macOS to appear as its own Tailscale device.
- Do not require Tailscale ACL identity to distinguish Mac traffic from VM traffic.
- Do not use Tailscale exit node mode for the London path.
- Do not depend on the macOS sing-box GUI Network Extension.
- Do not solve all VM image lifecycle automation in the first canary. The first design
  should prove routing, DNS, Docker, and inbound reachability before polishing image
  rebuild/import workflows.

## Recommended Approach

Use Lima as the macOS VM orchestrator and run a small NixOS router guest.

Lima is preferred over VMware Fusion for this project because it is lighter, CLI-first,
and easier to represent as repo-managed configuration. VMware Fusion remains a fallback
because its bridged networking is mature and already present on `m1max`, but it is a
heavier and less declarative fit for a small always-on router VM. OrbStack is likely the
lightest product for general Linux machines, but its networking model is more
product-managed and less suitable for a transparent router/subnet-router canary.

## High-Level Architecture

```text
macOS host
  local connected networks  -> native macOS route, direct
  selected bypass routes    -> native macOS route, direct
  default public traffic    -> Lima router VM LAN IP
  DNS                       -> Lima router VM DNS listener

Lima NixOS router VM
  eth0                      -> Lima/vmnet network toward macOS/LAN
  tailscale0                -> tailnet reachability and London SOCKS path
  sing-box TUN              -> transparent policy routing for VM and Docker traffic
  dnsmasq/sing-box DNS      -> IPv4-only public DNS and MagicDNS split handling
  docker0/br-*              -> container traffic intercepted by sing-box

Frankfurt
  VLESS+Reality server      -> default public exit

London
  microsocks on tailnet     -> Google and other London-routed destinations

tailnet peers
  reach Mac services        -> Tailscale route advertised by Lima VM
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

The VM should be the Tailscale node and advertise reachability to the Mac.

Initial canary model:

```text
tailscale up --accept-dns=false --advertise-routes=$MAC_LAN_IP/32
```

Tailnet peers then connect to services on the Mac using the Mac's LAN IP. The packets
arrive at the VM over Tailscale and are forwarded to the Mac over the local network.

Start with Tailscale subnet-route SNAT enabled, because it is simpler:

- tailnet peers do not need special return routes
- the Mac sees connections as coming from the VM or the VM-side route path
- Tailscale ACL identity is the VM, which is acceptable because ACLs are not used here

If Mac services later need to see the real tailnet source IP, test disabling SNAT.
That requires the Mac to route replies to `100.64.0.0/10` through the VM and may require
macOS firewall adjustments. This should be a second-phase optimization, not the canary.

## Docker Design

Docker Desktop on macOS is a risk because it runs containers in its own VM. Its egress
may or may not follow the macOS system default route in the same way as regular macOS
applications. That makes it a poor source of truth for policy routing.

Recommended model:

- run Docker Engine inside the Lima NixOS router VM
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

## Lima Management Model

The host side should eventually be represented in nix-darwin/Home Manager as:

- packages or Homebrew formulae needed for Lima and networking helpers
- Lima VM YAML template generated into the user config directory
- launchd agent to start the router VM at login or boot
- launchd agent/script to apply host routes and DNS after the VM is reachable
- rollback script for routes and DNS
- health check script for VM, sing-box, tailscale, and DNS

The guest side should be represented as a normal NixOS host, likely a new host such as
`hosts/m1router/nixos/configuration.nix` rather than overloading `hosts/vmmac`.

Guest responsibilities:

- enable Tailscale with `--accept-dns=false`
- enable forwarding
- run sing-box via the existing `services.vless` module or a router-specific variant
- run DNS policy compatible with current Linux clients
- optionally run Docker Engine
- expose SSH for management from the Mac

## Canary Plan

Phase 1: VM networking and host routing

- create Lima NixOS VM
- confirm Mac can reach VM and VM can reach internet
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

- set Mac default route to VM
- set Mac DNS to VM
- verify Safari/curl behavior
- verify local LAN access remains direct
- verify tailnet access from Mac
- verify rollback

Phase 4: inbound Mac services

- advertise `$MAC_LAN_IP/32` from VM through Tailscale
- approve route in Tailscale admin console if needed
- from another tailnet node, connect to Mac services by Mac LAN IP
- start with SNAT enabled
- record whether Mac service logs show VM source or tailnet source

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

Run these on macOS:

```bash
route -n get default
netstat -rn -f inet
scutil --dns
curl -4 https://icanhazip.com
curl -4 https://www.google.com -I
ping $TAILNET_NODE_IP
```

Run these from another tailnet node:

```bash
tailscale status
ping $MAC_LAN_IP
curl http://$MAC_LAN_IP:$SERVICE_PORT
```

## Rollback

The host route script must support rollback before the default route canary is used.

Rollback should:

- restore the original macOS default gateway
- restore the original DNS settings
- remove explicit `100.64.0.0/10` route through the VM if added
- stop using the VM as Docker context
- leave the VM running for diagnostics unless explicitly stopped

The current macOS sing-box GUI config should remain available until the Lima design is
validated, but it should not run at the same time as Tailscale.app if that conflict is
still present.

## Risks and Open Questions

- Lima network mode must support the required gateway/subnet-router shape. If Lima's
  default networking is insufficient, test vmnet/socket_vmnet modes before falling back
  to VMware Fusion.
- macOS host services may bind only to loopback. Those services will not be reachable
  from tailnet peers through the VM unless they bind to the Mac LAN address or all
  interfaces.
- macOS firewall rules may block inbound traffic arriving from the VM/LAN path.
- If SNAT is disabled for Tailscale subnet routing, return routing from macOS to
  `100.64.0.0/10` must be explicit and reliable.
- Docker Desktop behavior should not be assumed. Prefer Docker Engine inside the router
  VM for deterministic policy routing.
- Domain routing depends on DNS/sniffing visibility. Mac DNS should point to the VM to
  reduce surprises.
- IPv6 should stay conservative initially. Match current Linux client behavior:
  public IPv4-only, while preserving local/Tailscale needs.

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
