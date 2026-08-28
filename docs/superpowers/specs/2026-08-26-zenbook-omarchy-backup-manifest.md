# Zenbook → Omarchy: backup manifest

Date: 2026-08-26

This manifest defines what to copy from the current NixOS installation before
installing Omarchy. It deliberately separates irreplaceable user data from
machine-generated state and from configuration that a fresh Omarchy install
should own.

## Capacity and destination

- Source: the Zenbook user home, about 223 GiB in total. Exact path-by-path
  inventory is intentionally kept outside the public repository.
- Candidate backup after exclusions: about 87.08 GB (81.1 GiB).
- Destination free space after the approved cache cleanup: about 293 GiB on
  `um790pro`.
- Intended destination: a new dated directory under the backup user's home on
  `um790pro`; do not overwrite an existing Zenbook backup.
- A plain LAN `rsync` copy is acceptable. Repository-level encryption is not a
  requirement because the same secrets already live on `um790pro` and both
  machines are on the trusted local network.

The candidate therefore fits with roughly 212 GiB left on the destination.

## A. Required backup: restore deliberately

### Ordinary user data

Copy these top-level directories in full, subject to the common cache
exclusions below:

- `Documents/`
- `Downloads/`
- `Pictures/`
- `Projects/`
- `Videos/`
- `backups/`
- `keepassxc/`
- `nix-config/`
- `org/`
- `pro/`
- `scripts/`
- `work/`

Also copy regular files directly in the home directory, including database
dumps and archives. Shell/Nix symlinks into `/nix/store` are not useful on
Omarchy and must be skipped by using `rsync --safe-links`.

Important details:

- Keep build products such as `dist/`, `build/`, and `.next/`. They are not
  excluded globally because some may be the only copy of an artifact.

### Credentials and identity

Back up these directories with permissions and timestamps preserved:

- `.ssh/`
- `.gnupg/`
- `.password-store/`
- `.pki/`
- `.docker/`
- `.android/`

Also retain `.bash_history`, `.zsh_history`, and `.claude.json` as individual
home files. Restore credentials only after reviewing what Omarchy created and
keep private-key permissions intact.

### Application data worth keeping

- `.local/share/PrismLauncher/` subject to the exclusions below — in
  particular, keep `instances/` with Minecraft instances and worlds, about
  8.8 GiB, plus the small launcher settings.
- `.local/share/opencode/` subject to the exclusions below — in particular,
  keep `storage/`, `skills/`, and `repos/`.
- `.local/state/opencode/`
- `.local/state/gh/`
- `.config/Code/User/`
- `.config/Cursor/User/`
- `.config/Antigravity/User/`
- `.config/gh/`
- `.config/gcloud/`
- `.config/rclone/`
- `.config/keepassxc/`
- `.config/Bitwarden CLI/`
- `.config/configstore/`
- `.config/@opencode-ai/`
- `.config/doom/`
- `.config/mpv/`
- `.config/obs-studio/`
- `.config/transmission/`
- `.config/libreoffice/4/user/`
- `.config/qmd/`
- `.config/ngrok/`

If an entry above is an absolute symlink into `/nix/store`, omit the symlink;
the source configuration remains available in `nix-config/` and the program
can be configured natively after installation.

## B. Safety archive: copy, but do not overlay onto fresh Omarchy

These are useful for recovering a missed login, conversation, browser profile,
or one-off file. Keep them in the backup, but restore individual items only
when needed:

- `tmp/`
- `.codex/`
- `.claude/`
- `.t3/`
- `.grok/`
- `.gemini/`
- `.agents/`
- `.cursor/`
- `.config/Codex/`
- `.config/BraveSoftware/`
- `.config/google-chrome/`
- `.config/chromium/`
- `.mozilla/`
- `.local/share/TelegramDesktop/`

Browser and Electron profiles may contain valuable sessions but also carry
large caches and version-specific state. They are recovery sources, not a
ready-made replacement for the corresponding Omarchy profile.

## C. Exclude: regenerate or reinstall

Exclude these names wherever they occur inside the selected project trees:

- `node_modules/` — about 23.4 GiB
- `.venv/` and `venv/` — about 2.5 GiB combined
- `.devenv/` — about 1.9 GiB
- `.direnv/`
- `__pycache__/`
- `.pytest_cache/`
- `.ruff_cache/`

Exclude these home/application trees:

- `Desktop/`
- `Maildir/`
- `Music/`
- `Public/`
- `Templates/`
- `WebODM/`
- `obsidian-vault/` — already replicated through Syncthing
- `wallpapers/` — already replicated through Syncthing
- `.factorio/` — saves are covered by Steam Cloud
- `.cache/`
- `.local/share/Trash/`
- `.local/share/Steam/`
- `.local/share/voxtype/`
- `.local/share/mise/`
- `.lmstudio/`
- `.antigravity/` except the selected `User/` configuration above
- `.local/share/opencode/bin/`
- `.local/share/opencode/log/`
- `.local/share/opencode/snapshot/`
- `.local/share/opencode/tool-output/`
- `.local/share/PrismLauncher/assets/`
- `.local/share/PrismLauncher/cache/`
- `.local/share/PrismLauncher/libraries/`
- `.local/share/PrismLauncher/logs/`
- `.local/share/PrismLauncher/meta/`
- `.codex/ipc/*.sock`
- `.codex/app-server-control/*.sock`

The three `.sock` entries are live Unix sockets rather than persistent data.

Do not back up for restoration any desktop/session configuration that fresh
Omarchy should generate, notably:

- `.config/hypr/`
- `.config/omarchy/`
- `.config/waybar/`
- `.config/rofi/`
- `.config/alacritty/`
- `.config/ghostty/`
- `.config/kitty/`
- `.config/foot/`
- KDE/Plasma and GTK desktop state
- Home Manager shell files that are merely links into `/nix/store`

## D. Special handling before declaring the backup complete

One project-local `knowledge-blobs/` directory contains eight root-owned mode-0600
files, about 3.5 MiB total. Include them using a narrowly scoped privileged or
containerized read-only copy, preserving their paths and hashes. Exclude this
subtree from the main unprivileged `rsync` pass and copy it immediately
afterward as a separate stream.

Before relying on the exclusions above, verify that Syncthing reports
`obsidian-vault/` and `wallpapers/` as fully synchronized on another machine,
and confirm that the expected Factorio saves are visible in Steam Cloud.

## Verification gate

Before repartitioning or deleting NixOS:

1. Run the final `rsync` once while the system is in normal use.
2. Stop or close applications that mutate important data, then run a short
   final `rsync` pass.
3. Save an inventory containing relative path, size, and preferably SHA-256 for
   the required-data set.
4. Run `rsync --dry-run --itemize-changes` against the destination; there must
   be no unexplained missing required files or permission errors.
5. Restore several samples on `um790pro`: one document, one Git repository, one
   Minecraft world, and one private file with its permissions checked.

Only after these checks should the backup be considered sufficient for the
Omarchy installation and later removal of the NixOS partition.

## Execution result

Backup completed on 2026-08-27 in a dated directory on `um790pro`.

- Initial `rsync`: exit code 0; 87.07 GB transferred in 1:01:27; no deletions.
- Delta pass: exit code 0; eight changed files and two new volatile cache files
  synchronized; no deletions.
- Final full dry-run: exit code 0; zero files remaining to transfer.
- Checksum dry-run over `Documents/`, `nix-config/`, `.ssh/`, and `Pictures/`:
  2,016 regular files / 993,556,813 bytes checked; zero differences.
- Test restore to a temporary directory on `um790pro`: one document, one Git
  metadata file, one Minecraft world file, and one private mode-0600 file copied
  and compared successfully. The private file's mode, UID, GID, and SHA-256
  matched; temporary test data was removed afterward.
- Eight root-owned knowledge blobs copied separately; every source and
  destination SHA-256 matched.
- Partial files remaining: zero.
- Final destination apparent size: about 87.08 GB.
- Free destination space after backup: about 229 GiB.
