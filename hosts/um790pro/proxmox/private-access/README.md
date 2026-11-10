# Proxmox: private domain and HTTPS

Target: **https://pve.nikcode.xyz**, physical `pve-um790` (not the old `um790pro` guest alias). Tailscale IPv4: **100.99.139.46**.

## Architecture

- Cloudflare **DNS-only** A record points to the physical host's Tailscale IPv4. No proxy, Tunnel, Funnel, public IP or router forwarding.
- Official stable Tailscale on PVE; `--accept-dns=false --accept-routes=false --netfilter-mode=off --ssh=false`. No exit node, advertised routes or guest networking changes.
- Because Tailscale control/DERP is subject to TSPU interference, the daemon's HTTP(S) transport uses the existing `http://10.77.6.1:2081` mixed proxy. Its public destinations go through the existing `pveawg` VPN, with private/Russian destinations following the unchanged existing proxy policy. No guest VPN service/configuration is modified or restarted. The direct UDP/peer path remains available; remote peers can fall back to DERP over the VPN-backed proxy. If the VPN/proxy fails, HTTP(S) does not silently fall back to a direct connection, although cached/direct peer connections may survive.
- `TS_FORCE_NOISE_443=true` additionally avoids the observed post-handshake TCP/80 control-stream blackhole. It forces the supported HTTPS underlay without weakening Noise security. Direct control initially intermittently worked, but stalled maps with zero peers were observed; direct initial-handshake success was not sufficient evidence of stability.
- Native PVE ACME DNS-01 plugin `cloudflare-nikcode`, account `pve-nikcode`, domain `pve.nikcode.xyz`. PVE terminates TLS and renews the certificate.
- [pve-private-https.socket.in](<hosts/um790pro/proxmox/private-access/pve-private-https.socket.in>) renders a socket listening **only** on `<PVE-Tailscale-IPv4>:443`. `systemd-socket-proxyd` forwards bytes to `127.0.0.1:8006`; no second certificate or nginx/Caddy required. WebSocket transport remains native PVE. PVE sees loopback as the forwarded client's source IP, so use the firewall as the source-address boundary.
- Dedicated `inet pve_private_access` input policy admits only explicit personal admin IPv4 addresses in [pve-private-access.nft](<hosts/um790pro/proxmox/private-access/pve-private-access.nft>). It drops all other Tailscale ingress, including IPv6. This is narrower than the shared tailnet membership and does not alter its global ACLs. Existing LAN access remains unchanged.
- Tailscale automatic router port mapping is disabled with `TS_DISABLE_PORTMAPPER=true`; no manual router forwarding is required.

A public DNS record for a Tailscale IP does not publish the service. It does disclose the private address; the name is also visible in certificate transparency. DNS rebinding protection in a resolver may require a narrow exception for `pve.nikcode.xyz`. Do not turn on Cloudflare proxy to work around that.

## Deployment/reproduction

1. Confirm pinned root SSH to physical PVE and preserve LAN recovery.
2. Install Tailscale from its official Debian trixie repository. Use a targeted apt update for that source if unrelated PVE enterprise repositories return 401; do not silently change subscription/repository policy.
3. Install/check/start the dedicated firewall **before** joining Tailscale. Install its tailscaled unit drop-in, then reload systemd. The firewall unit deliberately omits default dependencies to avoid a `basic.target`/`sockets.target` boot cycle.
4. Authenticate the PVE node as the owner with:

   ```sh
   tailscale up --hostname=pve-um790 --accept-dns=false --accept-routes=false --netfilter-mode=off --ssh=false
   ```

   Use the generated login URL; do not reuse an unrelated machine's auth key. Check that the owner/tailnet is correct, not just that login succeeded. The node's key expiry still applies; review it in Tailscale administration before relying on unattended long-term recovery.
5. Copy this directory to physical PVE, then run `bash deploy.sh <PVE-Tailscale-IPv4>`. It requires the existing guest VPN/proxy, validates hostname/address and proxy reachability, tests nftables/systemd units, and enables the dedicated firewall/socket. It installs [tailscaled-vpn-egress.conf](<hosts/um790pro/proxmox/private-access/tailscaled-vpn-egress.conf>) and restarts only Tailscale if that drop-in changed. Existing firewall rules reload atomically without restarting Tailscale. No guest service or network restart.
6. Configure native PVE ACME using Cloudflare `CF_Token` and `CF_Zone_ID`. Read the DNS token from `pass` into memory and pass it over pinned SSH to `pvenode acme plugin add dns cloudflare-nikcode --api cf --data /dev/stdin --nodes pve-um790 --validation-delay 60`. Never put token values in command arguments, output or Git. PVE stores plugin data under `/etc/pve/priv/acme/` (base64 is **not** encryption). Prefer a token limited to DNS editing in the required zone; the existing token's precise Cloudflare permission scope has not been audited.
7. Set `--acmedomain0 domain=pve.nikcode.xyz,plugin=cloudflare-nikcode`, register the ACME account, select `--acme account=pve-nikcode` and order a certificate. Use staging first; only replace an existing custom certificate after confirming what it is. Changing the external domain does **not** require renaming the PVE node.
8. Create the exact Cloudflare A record with `proxied=false`, TTL 300. Refuse unexpected existing records rather than replacing unrelated data. Do not create AAAA/CNAME records.

## Renewal and checks

PVE's enabled daily `pve-daily-update.timer` runs `pveupdate`, which checks the ACME certificate and renews within 30 days of expiry. Its package-index update and certificate renewal are separate guarded operations: enterprise apt 401 errors do not themselves stop ACME renewal. Certificate installation reloads/restarts only pveproxy. The transparent forwarder needs no renewal hook.

From an approved admin client:

```sh
python3 verify.py --vmid 103
```

This checks trusted TLS/name, GUI HTTP 200, password login via `pass`, authenticated node status, and an authenticated VM noVNC WebSocket with a native RFB greeting. It does not render a graphical browser or type into the guest. For LAN verification while preserving name validation:

```sh
python3 verify.py --connect-address 192.168.1.241 --port 8006 --vmid 103
```

Check enabled/active firewall/socket, exact listener address, Tailscale preferences, DNS answers, renewal timer, rejected peer/IPv6 traffic and unchanged guest firewall/services. Do not reboot production guests merely to test this setup.

## Approved devices and recovery

The firewall file documents each approved admin IP. Shared Goar devices and server/guest nodes are intentionally not admitted just because they share the owner's Tailscale identity. New/reinstalled devices fail closed; update the list, syntax-check, deploy and reload the dedicated firewall. Review identity and device ownership before adding an address.

LAN recovery remains **https://192.168.1.241:8006** plus existing pinned root SSH. A certificate for `pve.nikcode.xyz` does not validate the numerical LAN IP; that browser warning is expected. The LAN address is DHCP and its router reservation is still a separate task.

To remove the new entry without affecting LAN:

```sh
systemctl disable --now pve-private-https.socket
systemctl stop pve-private-https.service
```

Keep the dedicated firewall in place while Tailscale is active. Its stop intentionally does not flush the policy. For full rollback, first stop/disable Tailscale and the private socket, then remove only `inet pve_private_access` and its explicitly named unit/drop-in files. Do not flush the global ruleset, edit guest VPN rules or remove PVE's internal cluster certificates.

Wi-Fi, power, firmware, a broken OS or Tailscale control-plane/authentication problems still need LAN/physical/out-of-band recovery.

## Acceptance status (2026-11-10, complete)

- Physical PVE authorized in the correct tailnet as `pve-um790`, IPv4 `100.99.139.46`. Exact DNS-only A record created/read back through Cloudflare; normal client DNS resolution verified. No AAAA/CNAME or Cloudflare proxy enabled.
- Trusted TLS chain/name, UI HTTP 200, root@pam login/authenticated node status and VM103 noVNC WebSocket 101/native RFB greeting passed through **https://pve.nikcode.xyz** and separately through LAN port 8006.
- Actual relay acceptance also passed: temporarily blocked PVE's direct Tailscale UDP in an isolated test table, observed a DERP pong and 80 dropped direct UDP packets, then passed the same TLS/UI/API/noVNC checks. Removed the test table in a `finally` cleanup and verified its absence. This exercises VPN-backed DERP, not only a same-LAN direct peer path.
- After configuring the proxy, PVE stayed online with a live (not cached) map of 29 peers beyond the previous two-minute failure interval. Current Tailscale TCP sockets all connected to `10.77.6.1:2081`; daemon logs confirmed DERP HTTP CONNECT 200 and disabled port mapping.
- Negative test: temporarily removed Zenbook from the admin set, verified a new TCP443 connection timed out with a dedicated nft drop-counter increase, and restored the exact entry via pinned LAN SSH before repeating the passing end-to-end check. Tailscale IPv6 to port8006 was independently dropped. No reachable listener at the LAN address on port443; live socket binds only `100.99.139.46:443`.
- Staging DNS-01 and production Let's Encrypt issuance succeeded; challenge TXT removed. Certificate valid until **2027-02-08 08:11:19 UTC**. Native daily renewal timer enabled/active; non-forced renewal correctly reported the fresh certificate does not expire within 30 days. A later real renewal is not yet observable.
- Original three nftables tables structurally unchanged (apart from runtime counters). Guest VPN/AWG/DHCP activation timestamps/restart counts and VM/container states exactly match the pre-change baseline. No guest VPN or network service restart.
- Tailscale, dedicated firewall/socket and daily renewal timer enabled/active; systemd unit/dependency verification passed. No production-host reboot or graphical browser rendering was performed.
- **Maintenance:** PVE's current Tailscale authentication key expires **2027-05-09 09:20:36 UTC**. Reauthenticate before then or explicitly review/disable this server's key expiration in Tailscale administration. Certificate auto-renewal does not renew Tailscale authentication.
- Existing unrelated PVE/ceph enterprise apt sources still return 401 without a subscription; their policy was not changed.

Sources: [Proxmox certificates](https://pve.proxmox.com/wiki/Certificate_Management), [pvenode CLI](https://pve.proxmox.com/pve-docs/pvenode.1.html), [DNS-01](https://letsencrypt.org/docs/challenge-types/), [Tailscale 1.104.5 HTTPS Noise override](https://raw.githubusercontent.com/tailscale/tailscale/v1.104.5/control/controlhttp/client.go), [Tailscale port-mapping disable switch](https://raw.githubusercontent.com/tailscale/tailscale/v1.104.5/net/portmapper/portmapper.go).
