# goar-team VLESS node

Independent Ubuntu 24.04 VPS for the Goar team, serving pure VLESS+Reality over
TCP 443 with `www.google.com` camouflage. Clients use its IP directly. It has
its own new REALITY keys, short_id, service_path and UUIDs. It has no London
SOCKS routing and no WireGuard `wg0` hub. Existing Frankfurt users stay unchanged.

## Deployment order

1. Human: create a Hosting-VDS VM in Frankfurt #2, plan HVDS-4G-EU
   (2 vCPU / 4 GiB / 35 GiB NVMe / 4 TB), Ubuntu 24.04; pay and record the IP.
2. Human: verify SSH host key through the provider console and obtain root SSH
   access. Ensure outbound HTTPS/apt access and no other service using TCP 80/443.
3. Orchestrator, from this checkout: run the provisioning bundle with the new IP:

   ```sh
   REMOTE=root@<IP> SSH_KEY="$HOME/.ssh/id_rsa_1" \
     hosts/goar-team/ubuntu/provision/provision.sh
   REMOTE=root@<IP> SSH_KEY="$HOME/.ssh/id_rsa_1" \
     hosts/goar-team/ubuntu/host-baseline/apply.sh
   ```

4. Human: establish firewall policy allowing TCP 22/80/443 in the provider
   firewall and host firewall. Preserve SSH access, including tailnet administration.
   Check Docker's published-port rules as well as host INPUT rules (UFW alone
   does not control Docker published ports). Configure Tailscale-required network
   access. This ticket's baseline automates only swap and timer masking.
5. Human: join Tailscale as `goar-team` using `tailscale up --hostname=goar-team
   --auth-key=<key>` on the VPS, or supply `TAILSCALE_AUTHKEY` when provisioning.
   Missing key gives a warning; it does not make the join complete. Verify
   `tailscale status` and administrative reachability from a tailnet peer.
6. Human: inspect `docker ps`, `docker logs --tail 100 reality-ezpz-engine-1`,
   published ports and the image/config. Target known-good image is
   `gzxhwq/sing-box:1.13.5`; upstream installer versions can differ. If migrating,
   validate with the target image, resolve deprecated fields/env/mount compatibility
   before recreating the container, and preserve identity. Validate a real client
   handshake and exit IP before handing out profiles (ticket 02).
7. Human/orchestrator: capture exact `config`, `engine.conf`, `docker-compose.yml`
   and `users` from `/opt/reality-ezpz/` into `secrets/proxy/goar-team/`, with
   encrypted `notes.md` recording IP, firewall, actual image/digest and compatibility
   settings. Confirm git-crypt is active before staging. Preserve `private_key`,
   `public_key`, `short_id`, `service_path` and UUIDs; refresh after every change.

## Operations and recovery

Use `/opt/reality-ezpz/reality-user list`, `add <name>`, and `show <name>` on the
new VPS. Add validates and backs up the engine/users but does not restart it;
apply validated user changes deliberately and refresh the DR bundle. QR output
requires separately installed `qrencode`. Do not copy Frankfurt state.

On replacement, restore goar-team's exact DR state before running the provisioner
so the existing directory prevents identity regeneration. Confirm the recorded
image and Compose settings, validate config, then start the restored stack with
`docker compose -p reality-ezpz up -d` from `/opt/reality-ezpz`. The provisioner
checks running state but does not restart a stopped existing stack. Reapply
baseline, firewall and Tailscale; verify client connectivity and update the IP
in client profiles if it changed.

## Live state (2026-10-15)

VM `148.253.210.41` is provisioned. Root SSH accepts the owner's `id_rsa_1`
key and rejects password authentication. UFW allows TCP 22/80/443, UDP 41641,
and tailnet ingress; swap and timer baseline are applied. The engine runs
`gzxhwq/sing-box:1.13.5`. Four owner accounts (`nik-ios`, `nik-android`,
`nik-macos`, `nik-windows`) retain their original UUIDs. Five named team
accounts cover Goar and her mother (iPhone), nanny, driver and housekeeper
(Android); five further colleagues have unspecified devices and no accounts yet.
Encrypted DR files and client profiles are in `secrets/proxy/goar-team/` and
`secrets/vless/`. The owner has four full `nik-*.json` sing-box profiles and
individual VLESS link/QR imports for `nik-ios` and `nik-android`; each
named team member has a distinct `.vless.txt` link and `.qr.png` for import into
their existing app. Host-side sing-box runtime tests for all nine identities
reached the new exit IP. See the encrypted DR notes for exact image
digest and recovery details. Tailscale is joined as `goar-team`
(`100.93.226.82`); tailnet ping and key-based root SSH from `zenbook` passed.
The owner tested `nik-ios` in Incy on an iPhone and confirmed working traffic.
On the owner's Android phone, Incy imported `nik-android` and measured latency
but did not initiate an Android VPN permission request or connect. The same
identity connected through Hiddify; the phone's external IP was verified as
`148.253.210.41`. Hiddify's locally cached import has auto-update disabled;
it will need re-import after an app reinstall or server identity change.

On 2026-10-15, the five named team QR codes were sent privately to the owner
in Telegram as five separate image messages with device labels. They have not
been sent to the individual team members by the operator, and import on their
devices remains unverified. The five colleagues without specified devices
still have no profiles.

## LTE failure on 2026-10-17: Chrome TLS fingerprint blocked on the mobile path

The owner's iPhone on Megafon (`31.173.82.54`) stopped passing traffic through
Incy: the app showed "connected", nothing loaded. Both `nik-ios` and the team
node profile failed the same way, which pointed away from a single profile.

Server-side and config-side causes were excluded by running, not by reasoning:
the container was up, `engine.conf` matched the DR capture byte for byte, the
REALITY public key was derived from the private key and matched, and both
`sing-box` and `Xray 26.10.10` (the core inside Incy) reached
`148.253.210.41` with the owner's profile.

A server-side packet capture showed 20 of 25 connections delivering exactly
1288 bytes of ClientHello and then going silent - no retransmit, no second
segment. The three connections that completed had a **valid** REALITY
authorization (decoded from the capture with the server private key: correct
`short_id`, timestamp within 0.72 s). Clamping MSS to 1240 shifted the cut to
1228 bytes and did not fix anything, so the boundary follows TCP
segmentation and the stall is a client-side decision, not packet loss.

The cause is a blocked **Chrome TLS fingerprint** on the mobile path. The
owner's A/B test settled it: the original profile worked over Wi-Fi, and the
same server with a **Firefox** fingerprint worked over LTE. That isolates the
mobile carrier path as the blocker for the `chrome` uTLS fingerprint
specifically, while the server, keys, UUID, flow, SNI and port are unchanged.

`secrets/vless/nik-ios.json`, `nik-ios.vless.txt` and `nik-ios.qr.png` now use
`fp=firefox`; the regenerated QR decodes byte for byte to the link, and a
host-side `sing-box` run reached the exit IP with HTTP 200 from Google. Rotate
the remaining iPhone profiles to Firefox if they show the same symptom on
mobile data. Do not change the server for this: it is client-side only.
