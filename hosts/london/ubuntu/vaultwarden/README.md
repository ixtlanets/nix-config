# London Vaultwarden

Reproducible Ubuntu-managed Vaultwarden deployment for `london`.

This host is not NixOS. The repo owns the service bundle in this directory, while host state lives under `/opt/vaultwarden` and encrypted backup artifacts under `/var/backups/vaultwarden`.

## Layout

- `docker-compose.yml` runs Vaultwarden and Caddy.
- `Caddyfile` exposes `https://vault.nikcode.xyz` and proxies
  `https://books.nikcode.xyz` to Moscow Audiobookshelf over Tailscale.
- `systemd/` contains the host units and timers copied to `/etc/systemd/system`.
- `scripts/deploy.sh` copies the bundle and encrypted repo secrets to `ubuntu@london`.
- `scripts/backup.sh` runs on `london` and writes encrypted `.age` backup artifacts.
- `scripts/cloudflare-dns-upsert.sh` updates the Cloudflare DNS record as a separate step.

## Secrets

Secrets are stored under `secrets/vaultwarden/london/` and protected by git-crypt:

- `vaultwarden.env` is copied to `/opt/vaultwarden/vaultwarden.env` with mode `0600`.
- `backup.env` is copied to `/opt/vaultwarden/backup.env` with mode `0600`.

The private age identity for decrypting backups must not be stored on `london` or in this repo. Store it in `pass`, for example `infra/vaultwarden/backup-age-identity`.

## Initial Deploy

Prerequisites:

- `vault.nikcode.xyz` points at the public IP for `london`.
- `books.nikcode.xyz` is a Cloudflare-managed DNS-only A record pointing at the
  same public IP. Keep the record unproxied: Audiobookshelf's primary traffic is
  large audio files, which must not traverse Cloudflare's self-service CDN.
- Oracle Cloud ingress allows TCP `443` to the instance. TCP `80` is recommended for plain-HTTP redirects and HTTP-01 ACME validation, but Caddy can still issue certificates via TLS-ALPN-01 on `443`.
- `ubuntu@london` has sudo access.
- Docker and Docker Compose are installed on `london`.
- the local checkout is unlocked with `git-crypt unlock`; `deploy.sh` refuses to
  copy encrypted secret blobs to the host.
- `secrets/vaultwarden/london/vaultwarden.env` and `backup.env` exist locally.

Update DNS if needed:

```sh
hosts/london/ubuntu/vaultwarden/scripts/cloudflare-dns-upsert.sh <london-public-ip>

RECORD_NAME=books.nikcode.xyz \
  hosts/london/ubuntu/vaultwarden/scripts/cloudflare-dns-upsert.sh \
  <london-public-ip>
```

Deploy:

```sh
hosts/london/ubuntu/vaultwarden/scripts/deploy.sh
```

On the first managed deploy, an existing `/opt/vaultwarden/vw-data` directory is renamed to a timestamped archive and a new clean data directory is created. Archived directories are never deleted by the deploy script.

Observed deployment note: public HTTPS works via `443`; if public `http://vault.nikcode.xyz` returns an empty reply or times out, open TCP `80` in Oracle Cloud to enable the HTTP redirect path.

## Public Audiobookshelf ingress

The public path is:

```text
client
  -> books.nikcode.xyz (Cloudflare authoritative DNS, proxied=false)
  -> london Caddy:443
  -> Moscow Audiobookshelf over Tailscale
```

There is no home-router port forward. Caddy terminates public TLS and preserves
WebSocket upgrades and HTTP range requests through its standard `reverse_proxy`.
Cloudflare serves DNS only; changing the record to proxied would put audiobook
delivery behind Cloudflare's large-file/CDN restrictions.

Moscow currently runs EOL Ubuntu 21.10. The accepted interim risk is bounded by
keeping the Raspberry Pi off the public network and allowing public requests to
reach only Audiobookshelf through this reverse-proxy path. Do not attempt a
multi-release remote OS upgrade without console recovery; migrate to a supported
LTS when physical access is available.

The Vaultwarden deploy validates the staged Caddyfile and Compose/env files
before overwriting live configuration, but it does not depend on Moscow being
online. Audiobookshelf availability and TLS are checked independently by the
`hosts/london/ubuntu/audiobookshelf-monitor/` systemd bundle.

HSTS is intentionally not enabled for `books.nikcode.xyz` until the remaining
mobile-client canary has passed. Public TCP `80` is optional; clients must use
the HTTPS URL directly when the HTTP redirect path is unavailable.

Deploy and inspect the independent monitor as documented in
`hosts/london/ubuntu/audiobookshelf-monitor/README.md`.

Canary checks after deployment:

```sh
curl -fsS https://books.nikcode.xyz/status | jq
curl -fsSI -H 'Range: bytes=0-1023' '<authenticated-audio-url>'
```

Then test web and the actual mobile client over LTE: login, catalog, WebSocket
reconnect, playback, forward/backward seek, progress sync, and an offline download.
Use a non-admin Audiobookshelf account for routine remote access.

Enter the mobile-client server address as exactly
`https://books.nikcode.xyz`, without a port or path. A saved
`http://books.nikcode.xyz` address will fail when public TCP `80` is unavailable;
the application must connect directly over HTTPS on the default port `443`.

Emergency rollback does not require touching Moscow: remove the
`books.nikcode.xyz` DNS record first, restore the previous managed Caddyfile, and
reload/redeploy Caddy. Recheck `vault.nikcode.xyz`, Tailscale Serve, and London
proxy services after rollback.

## Post-Deploy

1. Temporarily set `SIGNUPS_ALLOWED=true` in `/opt/vaultwarden/vaultwarden.env` on `london`.
2. Restart the service with `sudo systemctl restart vaultwarden.service`.
3. Open `https://vault.nikcode.xyz` and create the primary account.
4. Set `SIGNUPS_ALLOWED=false` again and restart `vaultwarden.service`.
5. Enable 2FA on the account.
6. Import the Strongbox export manually through the Web Vault or Bitwarden client.
7. Delete the local Strongbox export.
8. Confirm public signups remain disabled.

## Backup Restore Sketch

Fetch encrypted backup artifacts from a client machine, then decrypt manually with the private age identity from `pass`:

```sh
pass show infra/vaultwarden/backup-age-identity > /tmp/vaultwarden.agekey
age -d -i /tmp/vaultwarden.agekey vaultwarden-london-YYYY-MM-DDTHH-MM-SSZ.tar.zst.age | zstd -d | tar -x
rm /tmp/vaultwarden.agekey
```
