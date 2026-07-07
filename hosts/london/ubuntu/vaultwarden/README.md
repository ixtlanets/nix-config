# London Vaultwarden

Reproducible Ubuntu-managed Vaultwarden deployment for `london`.

This host is not NixOS. The repo owns the service bundle in this directory, while host state lives under `/opt/vaultwarden` and encrypted backup artifacts under `/var/backups/vaultwarden`.

## Layout

- `docker-compose.yml` runs Vaultwarden and Caddy.
- `Caddyfile` exposes `https://vault.nikcode.xyz`.
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
- Oracle Cloud ingress allows TCP `443` to the instance. TCP `80` is recommended for plain-HTTP redirects and HTTP-01 ACME validation, but Caddy can still issue certificates via TLS-ALPN-01 on `443`.
- `ubuntu@london` has sudo access.
- Docker and Docker Compose are installed on `london`.
- `secrets/vaultwarden/london/vaultwarden.env` and `backup.env` exist locally.

Update DNS if needed:

```sh
hosts/london/ubuntu/vaultwarden/scripts/cloudflare-dns-upsert.sh <london-public-ip>
```

Deploy:

```sh
hosts/london/ubuntu/vaultwarden/scripts/deploy.sh
```

On the first managed deploy, an existing `/opt/vaultwarden/vw-data` directory is renamed to a timestamped archive and a new clean data directory is created. Archived directories are never deleted by the deploy script.

Observed deployment note: public HTTPS works via `443`; if public `http://vault.nikcode.xyz` returns an empty reply or times out, open TCP `80` in Oracle Cloud to enable the HTTP redirect path.

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
