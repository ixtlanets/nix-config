# Private Proxmox access: pve.nikcode.xyz

## Authorized outcome

Configure the physical `pve-um790` host for `https://pve.nikcode.xyz` using a private access path through Tailscale. No public ingress, no Cloudflare proxy/Tunnel/Funnel, no router forwarding changes. Retain existing direct LAN management at `https://192.168.1.241:8006` (IP certificate warning is expected).

## Observed baseline (2026-11-10)

- Physical PVE 9.2.2 at 192.168.1.241 on pvewifi0; root SSH with dedicated pinned host identity works.
- No Tailscale, custom pveproxy certificate, ACME account/plugin or existing DNS record for pve.nikcode.xyz.
- Guest network/vpn services are active and must not be changed/restarted.
- Existing nftables tables: inet pve_guest_vpn, inet pve_home, ip pve_gui_lan_access; INPUT iptables policy ACCEPT. No global IPv6 address observed.
- Root account is root@pam. Cloudflare zone nikcode.xyz is active; DNS token exists in pass (value never written to this repository).

## Design

1. Install official stable Tailscale on the physical host, user-authenticated into the owner's tailnet. Keep DNS/routes/SSH/exit-node features off; avoid interference with existing guest VPN and nftables. Following the user's confirmation that TSPU blocks Tailscale, route its HTTP(S) control/DERP traffic through the already-running VPN-backed mixed proxy at 10.77.6.1:2081. Force the supported HTTPS Noise underlay and disable automatic router port mapping. No guest configuration or service restart.
2. DNS-only Cloudflare A record pve.nikcode.xyz points to host Tailscale IPv4. Do not add AAAA/CNAME or public origin address. This public DNS record discloses the name/private IP but does not publish the service. Some resolvers may require a DNS-rebinding exception for this name.
3. Native PVE ACME Cloudflare DNS-01 plugin issues/renews a Let's Encrypt certificate. DNS token stays in PVE's root-only private ACME configuration; no secret values in Git, command arguments or terminal output. Cloudflare proxy remains off. DNS-01 needs no inbound listener.
4. A systemd socket listens only on the specific Tailscale IPv4:443, with FreeBind for boot ordering. systemd-socket-proxyd transparently forwards TCP to 127.0.0.1:8006. PVE handles TLS and WebSocket normally; renewal needs no second certificate copy. No wildcard or public 443 binding. Proxy loses original source IP; authorization is enforced before it.
5. An independent nftables input chain limits Tailscale ingress to explicitly approved personal admin device IPs; no flush/rewrite of existing tables or changes to central tailnet policy. New peers fail closed until approved. IPv6 Tailscale ingress is denied unless explicitly configured. LAN fallback is untouched.
6. Keep tailnet authentication separate from PVE login. Do not silently enable 2FA or change credentials while configuring connectivity.

## Acceptance

- Verified TLS chain/SAN and HTTPS 200 from a Tailscale client using the requested name, including authenticated API and a real WebSocket console path where feasible.
- A record resolves to PVE Tailscale IPv4; no unintended records or Cloudflare proxy.
- Native ACME configuration and scheduled renewal enabled; renewal/no-op path checked.
- Dedicated :443 socket only at Tailscale address; LAN :8006 remains working.
- Non-admin Tailscale traffic blocked; no new public listeners/port forwards, no changes to guest VPN services.
- Services enabled and safe boot ordering checked without rebooting production guests.

## Recovery and constraints

Disable the dedicated socket to remove the portless entry; remove only the dedicated nftables table to roll back its access policy. Existing LAN SSH/UI are the recovery path. A Tailscale outage, Wi-Fi failure or unbootable host still requires local/out-of-band access. No reboot or unrelated service restart is authorized by this plan.

## Progress

Completed and accepted on 2026-11-10. DNS-only A points to 100.99.139.46; production Let's Encrypt certificate and daily native renewal are configured. Trusted TLS/UI/login/API/VM103 noVNC checks passed through the exact domain, through LAN recovery and through VPN-backed DERP with direct UDP temporarily blocked. Unapproved-source and IPv6 denial were verified, and test policies were removed. Guest services/VMs and original nft tables match the baseline. Enabled services and systemd dependencies verified without reboot.

[Runbook and acceptance evidence](<hosts/um790pro/proxmox/private-access/README.md>) record the approved devices, certificate expiry, Tailscale key expiry, recovery and unverified limits. Direct control initially stalled after the TCP/80 handshake; the existing VPN proxy and HTTPS-only Noise underlay fixed the live map/peer reachability. No central tailnet ACL, guest VPN configuration, public HTTPS listener or manual router forwarding was introduced.
