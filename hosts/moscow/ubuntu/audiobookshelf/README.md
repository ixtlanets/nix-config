# Moscow Audiobookshelf

Воспроизводимый Ubuntu/Docker bundle для Audiobookshelf на `moscow`. Хост пока не управляется NixOS; репозиторий владеет только этим service unit. Portainer разрешён для просмотра, но не для edit, recreate или update контейнера.

Первый переход — `2.6.0` → `2.36.0`. Он намеренно сохраняет существующую схему `/config` и `/metadata` на одном host directory; их разделение выполняется отдельным будущим update unit.

## Safety model

- `preflight.sh` — read-only и сравнивает текущий container fingerprint с инвентаризацией.
- Production state никогда не используется для upgrade rehearsal напрямую.
- Каждый snapshot создаётся при остановленном writer; trap пытается немедленно вернуть старый production при ошибке копирования.
- Compose использует локальный deployment tag только после проверки Linux/ARM64 image ID.
- `cutover.sh`, `rollback.sh` и `cleanup.sh` требуют `--execute` и точный ID.
- Rollback восстанавливает одновременно старый container/image и соответствующий pre-cutover snapshot.
- Cleanup не удаляет verified snapshot и старый image.
- Scripts не выполняют `sudo`, package/OS update, reboot, Docker prune или Portainer API calls.

## Identity

| Объект | Значение |
| --- | --- |
| Current version | `2.6.0` |
| Current image ID | `sha256:b83b66d7c1f3fec8bdea64f7ef670a9b7b61d8ab227d279b3d65551a877851ad` |
| Target version | `2.36.0` |
| Target OCI index | `sha256:180acad33d69c99ed208676465d8edcb268fa46967735579a7810859885b1a8e` |
| Target ARM64 manifest | `sha256:14a6492c743f2acfa00bcd96ec2a5c0c95e311f567718d29cb3c7f3772dc773f` |
| Target ARM64 image ID | `sha256:28b665b047a1e02474fad2bc703bd2a7489e4e72295f67e431c17f07c63320b3` |
| Production URL | `http://100.81.67.47:13378` through Tailscale |
| Public URL | `https://books.nikcode.xyz` through London Caddy and Tailscale |
| Rehearsal URL | `http://100.81.67.47:13379` through Tailscale |

## Layout

- `docker-compose.yml` preserves the current production mounts, port and restart policy.
- `docker-compose.rehearsal.yml` binds only to Tailscale, uses cloned state and mounts media read-only.
- `scripts/lib.sh` contains the recorded fingerprints and path defaults.
- `scripts/preflight.sh` validates the unchanged source container and host prerequisites.
- `scripts/prepare-image.sh` prepares a verified single-platform target image.
- `scripts/snapshot.sh` creates a consistent rehearsal or cutover snapshot.
- `scripts/rehearse.sh` starts the isolated upgraded copy.
- `scripts/cutover.sh` performs the production state migration and retains the old container.
- `scripts/rollback.sh` restores a cutover snapshot and the old container.
- `scripts/cleanup.sh` removes only the stopped rollback container and rehearsal workdir after seven days.
- `tests/run.sh` exercises CLI guardrails, Compose topology, image-transfer fallback and snapshot recovery behavior.

Remote defaults:

- deployed bundle: `/home/nik/.local/share/nix-config-services/audiobookshelf`;
- snapshots: `/home/nik/.local/state/audiobookshelf/snapshots`;
- rehearsals: `/home/nik/.local/state/audiobookshelf/rehearsals`;
- production state: `/media/disk1/media/meta`;
- media: `/media/disk1/media/Audiobooks`.

State directories are created with mode `0700`. They contain the Audiobookshelf database, including password hashes and auth state, and must never be copied into the repository.

The public endpoint does not require a home-router port forward. Cloudflare is
authoritative for `nikcode.xyz`, but the `books.nikcode.xyz` record is deliberately
DNS-only. TLS terminates at the managed Caddy instance on `london`, which reaches
this production endpoint through Tailscale. The reproducible ingress and its
rollback procedure live in `hosts/london/ubuntu/vaultwarden/README.md`.

For user provisioning in Absorb, prefer its per-user setup link/QR flow. It
passes `https://books.nikcode.xyz` and a dedicated revocable API key without
requiring the recipient to type a server address, username or password. The
operator and recipient instructions, stable-version fallback, and credential
handling rules are documented in `docs/absorb-onboarding.md`.

## Prerequisites

Local:

- `ssh`, `scp` and Docker with `buildx imagetools`;
- SSH alias `moscow`;
- access to the Docker daemon if the ARM64 transfer fallback is required.

Remote:

- current Docker `20.10.12` and `docker-compose` v1 `1.27.4`;
- user `nik` retains Docker socket access;
- `python3`, `curl`, `tar`, `sha256sum`, `findmnt`, `ss` and `ip`;
- Tailscale address `100.81.67.47`;
- production container still matches the recorded fingerprint.

## Tests

From the repository root:

```sh
hosts/moscow/ubuntu/audiobookshelf/tests/run.sh
```

Static checks:

```sh
scripts=hosts/moscow/ubuntu/audiobookshelf/scripts
find "$scripts" -maxdepth 1 -type f -name '*.sh' ! -name lib.sh -print0 \
  | xargs -0 shellcheck -x -P "$scripts"
find hosts/moscow/ubuntu/audiobookshelf/tests -type f -perm -0100 -print0 \
  | xargs -0 shellcheck

docker compose \
  -f hosts/moscow/ubuntu/audiobookshelf/docker-compose.yml \
  config

REHEARSAL_STATE_DIR=/tmp/audiobookshelf-rehearsal \
  docker compose \
  -f hosts/moscow/ubuntu/audiobookshelf/docker-compose.rehearsal.yml \
  config
```

## Operator flow

Run commands from the repository root. Never proceed to the next phase merely because the prior command exited zero; observe the stated manual gate.

### 1. Read-only preflight

```sh
hosts/moscow/ubuntu/audiobookshelf/scripts/preflight.sh
```

Stop if any fingerprint differs. Re-inventory rather than editing constants to bypass the check.

### 2. Prepare target image

```sh
hosts/moscow/ubuntu/audiobookshelf/scripts/prepare-image.sh
```

This first tries native pull on `moscow`. If Docker 20.10 cannot read the OCI index, it pulls only `linux/arm64` locally and streams a Docker archive through SSH. Both routes must produce the expected image ID before assigning the local deployment tag.

### 3. Consistent rehearsal snapshot

```sh
hosts/moscow/ubuntu/audiobookshelf/scripts/snapshot.sh rehearsal
```

Record the printed `snapshot_id`. Audiobookshelf is expected to be unavailable for less than two minutes; SSH, Tailscale and other services are unaffected. Do not continue unless the command reports that the old production is healthy again.

### 4. Upgrade rehearsal

```sh
hosts/moscow/ubuntu/audiobookshelf/scripts/rehearse.sh <snapshot-id>
```

In Absorb, add `http://100.81.67.47:13379`, sign in again with the ordinary user and verify the service baseline:

1. Expected catalog and covers are visible.
2. A book starts playing.
3. Seeking works.
4. Progress remains after closing and reopening the app.
5. Rehearsal progress does not alter production on `13378`.
6. Root and ordinary-user web login work.

Do not proceed if any check fails. The rehearsal uses its own writable state and read-only media, so it can be stopped and investigated without touching production.

### 5. Production cutover

Running this command explicitly confirms that the manual rehearsal baseline passed:

```sh
hosts/moscow/ubuntu/audiobookshelf/scripts/cutover.sh \
  --execute <rehearsal-snapshot-id>
```

Cutover stops the rehearsal, stops `2.6.0`, takes a fresh snapshot of the latest production state, renames and retains the old container, then starts `2.36.0` against the original production state. It never promotes the stale rehearsal copy.

Record the printed cutover `snapshot_id`. Re-authentication is expected because the target crosses the auth migration introduced in `2.26.0`. Repeat the complete service baseline on the normal `13378` endpoint.

### 6. Rollback if needed

Rollback loses progress written after the selected cutover snapshot:

```sh
hosts/moscow/ubuntu/audiobookshelf/scripts/rollback.sh \
  --execute <cutover-snapshot-id>
```

The script first prepares and verifies restored state alongside production. Only then does it atomically preserve migrated state, replace it with the snapshot and start the old container. Failed migrated state and logs are retained for diagnosis.

The quick rollback decision window is 24 hours. After that, prefer a forward fix unless restoring the snapshot is clearly worth the data loss.

### 7. Cleanup after seven days

After at least seven days of healthy `2.36.0` operation and another manual baseline:

```sh
hosts/moscow/ubuntu/audiobookshelf/scripts/cleanup.sh \
  --execute <cutover-snapshot-id>
```

Cleanup refuses to run earlier. It removes the stopped rollback container and rehearsal workdir, then marks the cutover stable. The verified cutover snapshot and old image remain available until a separate long-term backup policy exists.

## Overrides

For controlled testing, the local scripts accept environment overrides:

- `REMOTE` and `SSH_BIN`;
- `DOCKER_BIN` and `SCP_BIN`;
- `REMOTE_BUNDLE_DIR` and `REMOTE_STATE_DIR`;
- `SOURCE_STATE_DIR`, `MEDIA_DIR` and `TAILSCALE_IP`.

Production-changing remote scripts still restrict destructive paths to the known `/home/nik` state root and `/media/disk1/media/meta` production path. Do not use overrides to bypass a failed fingerprint.

## Deferred work

- separate `/config` and `/metadata` host directories;
- regular encrypted off-host backup and restore drill;
- storage alerts and external-disk remediation;
- production exposure tightening;
- Docker/Compose and Ubuntu updates;
- ZeroTier repair;
- adoption of the remaining Docker services.
