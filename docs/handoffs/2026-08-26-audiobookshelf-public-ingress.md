# Audiobookshelf public ingress deployment handoff

**Date:** 2026-08-26  
**Status:** deployment and Vaultwarden recovery complete; manual Audiobookshelf
client canary remains

## Live path

```text
books.nikcode.xyz
  -> Cloudflare authoritative DNS (DNS-only A record, TTL 300)
  -> Caddy 2.11.4 on london:443
  -> Moscow over Tailscale
  -> Audiobookshelf 2.36.0 on moscow
```

No home-router port was opened. A connection test from `london` to the observed
Moscow public IPv4 on TCP `13378` was closed/filtered.

## Completed verification

- Cloudflare API returns exactly one DNS-only A record for `books.nikcode.xyz`.
- Let’s Encrypt issued a certificate for `books.nikcode.xyz` via TLS-ALPN-01.
- Public `/status` returns Audiobookshelf `2.36.0` over HTTP/2.
- A Socket.IO WebSocket handshake returns `101 Switching Protocols` through
  Caddy.
- `vault.nikcode.xyz/alive` remains publicly healthy.
- `microsocks`, `tailscaled`, and Tailscale Serve were not changed; their
  services/path remained active after the deployment.
- The managed Vaultwarden secrets were restored from an unlocked clean worktree,
  `vaultwarden-backup.timer` is active, and a fresh encrypted backup completed at
  `2026-08-26T18:13:25Z`.

Manual client verification is still required over LTE/5G: login, catalog,
playback, seek, progress sync, reconnect, and an offline download using a
non-admin Audiobookshelf account.

HSTS remains disabled for `books.nikcode.xyz` until that client canary passes.
Public TCP `80` is optional; the supported client path starts directly at HTTPS
on `443`. Runtime checks are deployed separately from Vaultwarden by the
`hosts/london/ubuntu/audiobookshelf-monitor/` systemd bundle.

The mobile application connection was confirmed after changing its saved server
address from `http://books.nikcode.xyz` to `https://books.nikcode.xyz`. No port
is required: HTTPS uses public TCP `443`. Public TCP `80` is not part of the
mobile-client path.

## Vaultwarden recovery record

The first deploy was run from a checkout whose git-crypt secrets were still
encrypted. The previous deploy script copied those encrypted blobs and stopped
the Compose stack before the next start failed. The Vaultwarden database and
`vw-data` were not modified.

Vaultwarden was restored immediately with this temporary non-secret environment:

```text
INVITATIONS_ALLOWED=false
SIGNUPS_ALLOWED=false
```

Recovery then used a separate clean Git worktree for an interactive
`git-crypt unlock`, leaving the main dirty checkout untouched. The managed
environment, including `ADMIN_TOKEN`, was redeployed without printing secret
values. The backup timer is active and the fresh encrypted backup is:

```text
/var/backups/vaultwarden/vaultwarden-london-2026-08-26T18-13-21Z.tar.zst.age
```

The encrypted blobs from the failed deployment remain preserved as incident
artifacts:

```text
/opt/vaultwarden/vaultwarden.env.gitcrypt-2026-08-26T18-01-27Z
/opt/vaultwarden/backup.env.gitcrypt-2026-08-26T18-01-27Z
```

They are no longer needed for service recovery and may be removed during a
separate cleanup after this handoff has been reviewed.

Final recovery verification returned `active` for `vaultwarden.service`,
`vaultwarden-backup.timer`, `microsocks`, and `tailscaled`. Public checks returned
HTTP/2 `200` for Audiobookshelf and a successful Vaultwarden `/alive` response.

Repeatable verification commands:

```sh
ssh ubuntu@london 'systemctl is-active vaultwarden.service vaultwarden-backup.timer'
curl -fsS https://vault.nikcode.xyz/alive
curl -fsS https://books.nikcode.xyz/status | jq
```

The Vaultwarden deploy script now fails before any remote mutation when a secret
retains the git-crypt header. It parses staged Compose/env configuration before
the stop-before-start systemd restart and validates the Caddyfile. It does not
depend on Moscow availability; the independent monitor checks the upstream,
public HTTPS, and TLS lifetime every five minutes.
