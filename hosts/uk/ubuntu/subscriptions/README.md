# Direct HTTPS subscription origin on UK

Approved host: `91.108.225.14`, Ubuntu 24.04 x86_64, previously unused for VPN.
`subscriptions.nikcode.xyz` is a DNS-only A record managed separately by the owner.
Existing France/Frankfurt VPNs, Warsaw and London remain untouched.

Two dedicated new services:

- `nikcode-subscriptions.service`: Node 24 LTS adapter, loopback `127.0.0.1:8787`.
- `nikcode-subscriptions-https.service`: Caddy TCP80/443, Let's Encrypt ACME,
  HTTP/1.1 and HTTP/2, no public admin endpoint or request access log.

Caddy excludes `http.log.error` from its default logger because upstream errors
can contain the bearer-token request URI; TLS/ACME startup logs remain available.

Official archive checksums, immutable rules digest and extracted runtime hashes
are in [pin.json](pin.json). Do not substitute moving `latest` runtimes.

## Private projection and staging

Only the server-side pilot projection goes on UK. It contains device token hashes
and per-node credentials needed to render configurations, **no operator tokens,
Cloudflare API keys, Reality private keys or whole pass catalog**.
Backend reads `/etc/nikcode-subscriptions/pilot.json` per request (root:service
`0640`); validated replacement can take effect without restarting it.

Required projection settings:

```json
{
  "subscription_hosts": ["config.nikcode.xyz", "subscriptions.nikcode.xyz"],
  "rules_url": "https://subscriptions.nikcode.xyz/rules/geoip-ru-bdca5cdb44cdcf0940001e5952386822a6f4ffa8b2c8eea00340aa6f585c7f9d.srs"
}
```

Keep other validated projection fields and identities unchanged. Device rules
mode is owned by subscription management; do not change it in this host bundle.

Root-only staging directory contains pinned `node`, `caddy`, `package.json`,
`src/{server.js,worker.js,geoip-ru.js}`, verified `geoip-ru.srs` and private
`pilot.json`. Software comes from `tools/nikcode-network`; review its tests before
starting the backend. Copy this bundle separately; then:

```sh
bash /private/bundle/install.sh /private/stage
systemctl start nikcode-subscriptions.service nikcode-subscriptions-https.service
curl --retry 8 --retry-connrefused --retry-delay 1 --max-time 3 --fail \
  http://127.0.0.1:8787/healthz
```

Installation refuses existing owned paths and verifies host address, runtime/rules
hashes and free ports. It creates only the two dedicated accounts, its own files
and units; no firewall, SSH configuration, network restart or Docker change.
Start/enable are separate, explicit operations. Pin root-only staging permissions
and never print private requests, tokens or configurations.

## Acceptance and rollback

Check loopback `/healthz`, public certificate-verified HTTPS `/healthz`, valid
personal subscription retrieval and exact public SRS digest. Test from the
affected Android physical network without VPN: full EOF and complete size must
replace the observed Cloudflare 16 KiB stall. Test subscription refresh and new
rules download before final handoff. Enable the two new units after acceptance.

Preserve original UK `ssh.service` PID851/NRestarts0 and route/firewall baseline;
re-read identities before changes. Normal HTTP traffic changes counters only.
Rollback stops/disables only these two units; preserve configuration/evidence.
DNS rollback belongs to the owner. Do not remove any old VPN or rollback host.

## Observed deployment, 2026-11-12

Official pinned Node24.22.3 and Caddy2.11.9 are installed. The four HTTP adapter
tests also passed with this exact Node24 runtime. The two new units are running
and enabled after native phone acceptance. Let's Encrypt issued a trusted certificate.
Public `/healthz` returned HTTP200/42 bytes, TLS verification successful, direct
peer `91.108.225.14` with no Cloudflare proxy in the serving path.

The S22 personal remote profile returned HTTP200, complete EOF, 6616 bytes after
the direct rule-download fix. Its immutable own-origin SRS returned HTTP200,
complete EOF, 50096 bytes and the exact digest from `pin.json`. Rule downloads
use a DIRECT HTTP client to avoid depending on VPN startup. These are transport
checks from the workstation. On the USB-connected S22, native sing-box 1.14.4
then created the Remote profile with VPN off, started it, and passed HTTPS egress
checks on Wi-Fi and cellular. A native subscription update also passed over
cellular with VPN off. Original SSH PID851/restart count stayed unchanged.

The same phone switched automatically from France to Frankfurt in 32 seconds
with the delivered one-minute URLTest interval. With both new proxy listeners
stopped, a fresh Chrome foreign fetch failed, native subscription refresh and
profile restart succeeded, and fresh RU navigation returned HTTP200 without
browser cache or service worker. Both listeners were restored. The phone was
left running its Remote `NikCode-S22` profile with Wi-Fi and mobile data enabled.

The three personal compatibility URLs at `config.nikcode.xyz` return a small 307
to this origin; the 22 legacy subscription bodies remain unchanged. Both iPhone
profiles initially used the small own-origin profile and own immutable RU rule
file. After the spare iPhone's packet-tunnel startup timed out fetching that
file, its delivery mode was switched back to inline. The own-origin spare
response completed at 361,396 bytes and passed core 1.14.4 validation; no token,
UUID, service or node change was required. The owner confirmed successful VPN
startup and Internet on the spare. Primary iPhone now also receives inline rules
(361,402-byte complete response, core 1.14.4 check passed); its native acceptance
and the spare's cellular check were subsequently confirmed by the owner: both
iPhones work, including cellular. S22 delivery is unchanged.

## Secure access

UK ED25519 fingerprint was identical from local and trusted Frankfurt network:
`SHA256:LbdM3ZoMOEPEg+i1fSI2zbmOYKzCr02+eGkqsVrj9Eg`.
The existing owner public key was appended without replacing authorized_keys.

```sh
ssh -F /dev/null -o BatchMode=yes -o StrictHostKeyChecking=yes \
  -o UserKnownHostsFile=/home/nik/.local/state/nikcode-singbox-pilot-20261112/uk-known-hosts \
  -o GlobalKnownHostsFile=/dev/null -o IdentitiesOnly=yes -i ~/.ssh/id_rsa_1 \
  root@91.108.225.14
```
