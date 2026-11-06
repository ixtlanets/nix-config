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

- Content: full `~/vault` including `.git`, external `~/.history-base` state
  archived under `./.history-base`, verified history SQLite snapshots, archived
  sources and workflow configuration in `history-backup/`.
- History snapshots use a private temporary workspace; a lock prevents concurrent
  runs. Live vault files retain the existing tolerance for changes during tar.
  The history stream validator and post-stream bundle verification remain fatal.
- Stream: `tar --create | history validate-stream | zstd -3 -T0 | gpg --encrypt`.
  Encryption recipient: `539459F1879941F7`. No plaintext tar is written to disk.
- The current encrypted artifact is about 22 GiB; allow room for growth.
- Name: `vault-YYYY-MM-DD.tar.zst.gpg`, assembled as `.assembling-*`, then atomically
  finalized immediately after successful encryption and history verification.
- A finalized daily artifact is immutable: a same-day retry reuses it rather than
  rebuilding it. Interrupted new-protocol `.assembling-*` files have no
  completion proof and are removed on the next normal run, never automatically promoted. Legacy
  `.incoming-*` files may contain fully assembled archives: they are preserved
  with a warning for manual classification.

## Destinations and retention

| Host | Path | Retention |
|------|------|-----------|
| `nik@um790pro` | `~/backups/vault/` | 3 verified archives |
| `nik@moscow` | `~/backups/vault/` | 3 verified archives |
| `ubuntu@london` | `~/backups/vault/` | 3 verified archives, subject to capacity |
| zenbook local | `~/backups/vault/` | 3 finalized archives |

Local finalization and count-based rotation happen before any network operation.
An interrupted assembly may temporarily add one hidden file; normal runs clear
stale new-protocol assembly files before writing another. This bound excludes
legacy `.incoming-*` files awaiting manual classification. Local rotation sorts ISO dates.
Delivery failures return a nonzero status and trigger a critical desktop
notification through `vault-backup-alert.service`; inspect details with
`journalctl --user -u vault-backup-push.service`.

Receivers run in parallel, each with a 6-hour wall-clock timeout (including SSH,
transfer and checksum verification). SSH keepalives detect broken connections;
rsync also has a 30-minute inactivity timeout. The systemd whole-job limit is
8 hours, so a slow receiver cannot starve the other two. London measured about
1.13 MiB/s during interrupted transfers: a 21.8 GiB archive needs roughly 5.5 hours
before verification. The audit observed a relay route, but did not establish the
route used during those transfers. Moscow deliveries have also exceeded three hours.
The 6-hour receiver limit accommodates those observed transfer times; the
8-hour whole-job limit leaves time for assembly and stays below the daily
schedule. The local copy remains finalized even if the overall job is killed.

Each receiver has at most one hidden `.upload-vault-*.tar.zst.gpg` resumable
upload. Rsync writes that file in place; a retry uses the same immutable local
archive and rsync checksums. The receiver checks full SHA256 against the local
encrypted artifact before atomically publishing the final filename and its
`.sha256` verification marker. An existing matching final file is verified and
adopted without a transfer, even if free space is low. A same-sized corrupt or
partial file is insufficient to pass this check.

The capacity check reserves the remaining upload size plus 1 GiB. It never
removes a completed archive to make a transfer fit. Rotation runs only after a
new artifact is verified and only counts artifacts with checksum markers from
this protocol. Legacy unmarked final names may be interrupted uploads from the
old script; preserve and classify them manually rather than counting them as
verified backups or automatically deleting them.

London's 44 GiB filesystem cannot support the current 3-copy retention policy.
With a 21.8 GiB artifact and roughly 13.6 GiB of other usage, even safely replacing
one existing copy requires about 58.2 GiB total capacity. Three copies plus
staging need roughly 102 GiB; plan at least 128 GiB with growth headroom. Until
capacity is changed, London may fail with an explicit space error while existing
copies remain intact. Archive content must not be reduced silently to fit.

A separate London-only option is an encrypted incremental repository using
[restic over SFTP](https://restic.readthedocs.io/en/stable/030_preparing_a_new_repo.html#sftp).
Deduplication needs the verified raw tar before GPG, not freshly encrypted daily
archives. Preserve producer failure propagation with
[`--stdin-from-command`](https://restic.readthedocs.io/en/stable/040_backup.html#reading-data-from-a-command)
and `pipefail`. This is not deployed: it needs an independently recoverable
repository password, two measured snapshots and a restore check before assuming
that the existing disk is sufficient. The other two receivers can retain GPG.

To retry only delivery of the newest finalized local artifact, without creating
an archive, deleting assembly files or rotating local copies:

```sh
~/.local/bin/vault-backup-push --retry-delivery
```

## Regression verification

```sh
python3 tests/test_vault_backup_push.py
bash -n dotfiles/omarchy/bin/vault-backup-push install.sh
```

The tests run the actual shell script and delivery functions against tiny
fixtures, fake crypto and local simulated SSH/rsync. They check stalled receiver
isolation, bounded local copies, same-day reuse, delivery-only retries,
insufficient space, hidden interrupted uploads, checksum rejection, verified
publication and legacy adoption. They do not create production archives or
contact receivers. Real encryption/history roundtrip coverage remains available
through `vault-backup-push --history-local-check NEW_PRIVATE_DIRECTORY`.

## Incident: 2026-11-05

The November 2-5 jobs hit the former four-hour limit before the serial deliveries
finished. Local finalization and rotation came after delivery, leaving completed
archives under `.incoming-*` and bypassing local retention. The successful
November 1 run had already taken 236 minutes, leaving almost no time margin.

The former remote space-reclamation step deleted older archives before receiving
a replacement. Combined with `rsync --partial` writing final names, this removed
London's last full daily copy and left two partial files that looked like backups.
The November 5 audit found complete-sized copies on um790pro and Moscow; London
had no complete daily archive. Its separate pre-migration history was unaffected.
The fixes above prevent this failure pattern; restoring sustainable London
coverage still requires a capacity or storage-format decision.

Three current-size local archives need about 65 GiB, with another 22 GiB during
assembly, plus the separate private history workspace. These are expected
working-space requirements, distinct from unbounded abandoned uploads.

## Cold snapshot of pre-migration history

`vault-history-2026-09-17.tar.zst.gpg` (~3.8 GiB, in `~/backups/vault-history/`
on the same three hosts and on zenbook) contains:

- `vault-history.bundle` — the old git history (331 commits, git-crypt-encrypted
  blobs, 6.5 GiB unpacked)
- `vault-gitcrypt.key` — the old git-crypt key (also at
  `~/.local/share/git-crypt/vault.key`)
- `old-git-dir-2026-09-17/` on zenbook only: the full old `.git` directory.

## Restore

1. Pick the newest verified `vault-YYYY-MM-DD.tar.zst.gpg` from any host.
   New deliveries include a `.sha256` marker; classify legacy unmarked files
   before relying on them.
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
`dotfiles/omarchy/system/systemd/user/vault-backup-push.{service,timer}` and
`vault-backup-alert.service` in the same directory. `install.sh` copies these
exact sources; Home Manager has no separate vault-backup-push implementation.
For a focused deployment, install the helper with mode 755 and all three units
with mode 644 to the existing paths, run `systemctl --user daemon-reload`, and
ensure the timer remains enabled. Do not run a full system rebuild for this
script-only change. Deployment itself does not require a new 22 GiB archive.
Use `--retry-delivery` for acceptance against an already verified local artifact.
The first normal run will rotate local daily archives; move any explicitly
retained recovery copy outside the daily rotation before invoking it.
