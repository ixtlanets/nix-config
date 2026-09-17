# Vault Backup Scheme (since 2026-09-17)

GitHub removed (`snikulin/vault` deleted), `origin` remote removed from `~/vault`,
git-crypt removed from `~/vault` (fresh history). Protection is now whole-archive
GPG encryption pushed to three hosts over tailscale.

## What runs where

- **zenbook**: systemd user timer `vault-backup-push.timer` (~04:00 MSK daily,
  `Persistent=true` catches up after sleep/off). Script:
  `dotfiles/omarchy/bin/vault-backup-push`, installed to `~/.local/bin/` by
  `install.sh` (`install_vault_backup`).
- **um790pro, moscow, london**: passive receivers, nothing runs there.
  They hold encrypted archives only; GPG is not needed to receive.

## Archive

- Content: full `~/vault` including `.git` (fresh local history).
- Stream: `tar --create | zstd -3 -T0 | gpg --encrypt -r 539459F1879941F7`.
- Plaintext never touches disk; the archive is ~6.5 GiB.
- Name: `vault-YYYY-MM-DD.tar.zst.gpg`, written as `.incoming-*` then renamed.

## Destinations and retention

| Host | Path | Retention |
|------|------|-----------|
| `nik@um790pro` | `~/backups/vault/` | 7 days |
| `nik@moscow` | `~/backups/vault/` | 7 days |
| `ubuntu@london` | `~/backups/vault/` | 3 days (small disk) |

Delivery is per-host best-effort: a failing host does not abort the others,
undelivered hosts catch up on the next run. Size is verified after rsync;
a free-space guard drops the oldest archive on a host when the new one would
not fit. Local copy of the newest archive is kept in `~/backups/vault/` on
zenbook for fast restore.

## Cold snapshot of pre-migration history

`vault-history-2026-09-17.tar.zst.gpg` (~3.8 GiB, in `~/backups/vault-history/`
on the same three hosts and on zenbook) contains:

- `vault-history.bundle` — the old git history (331 commits, git-crypt-encrypted
  blobs, 6.5 GiB unpacked)
- `vault-gitcrypt.key` — the old git-crypt key (also at
  `~/.local/share/git-crypt/vault.key`)
- `old-git-dir-2026-09-17/` on zenbook only: the full old `.git` directory.

## Restore

1. Pick the newest `vault-YYYY-MM-DD.tar.zst.gpg` from any host.
2. `gpg -d vault-YYYY-MM-DD.tar.zst.gpg | zstd -d | tar -x -C ~/vault-restored`
   (requires the GPG secret key 539459F1879941F7).
3. Pre-migration state additionally needs the cold snapshot: untar it, then
   `git clone vault-history.bundle` and `git-crypt unlock` with
   `vault-gitcrypt.key`.

## GPG key

Encryption key `539459F1879941F7` (Sergey Nikulin). The secret key lives in the
zenbook keyring; an encrypted copy is committed under `secrets/gpg/private.key`
(git-crypt-protected in this repo). Owner trust export: `secrets/gpg/ownertrust.txt`.

## Changing the scheme

Edit `dotfiles/omarchy/bin/vault-backup-push` (destinations, retention, key) and
re-run `install_vault_backup`-equivalent install (or the relevant part of
`install.sh`). The systemd units live in
`dotfiles/omarchy/system/systemd/user/vault-backup-push.{service,timer}`.
