# Audiobook Ops production runbook

This runbook separates read-only verification from owner-gated production
changes. Do not run a privileged command, stop a production service, install a
credential, edit the Moscow authorized key, or change Hermes without explicit
owner approval.

## Production paths

| Purpose | Exact path |
|---|---|
| Reviewed bundle | `/usr/local/lib/audiobook-ops` |
| Operator config | `/etc/audiobook-ops/config` |
| Runtime secrets | `/etc/audiobook-ops/secrets` |
| Control state | `/home/nik/services/audiobook-ops` |
| Retained Prowlarr/Transmission/download state | `/home/nik/services/readmeabook` |
| Backups | `/var/backups/audiobook-ops` |
| Host logs | `/var/log/audiobook-ops` |
| Units | `/etc/systemd/system/audiobook-ops-*` |

The retained service root keeps its physical name to avoid copying live
Prowlarr, Transmission, FlareSolverr, and download state. It is not a
ReadMeABook application dependency.

## Read-only repository verification

Run on `um790pro` from the checkout:

```bash
cd /home/nik/nix-config/hosts/um790pro/docker/audiobook-ops
./tests/run.sh
docker build --platform linux/amd64 \
  --tag localhost/audiobook-ops:0.2.0-ticket9 .
docker image inspect localhost/audiobook-ops:0.2.0-ticket9 \
  --format '{{.Id}} {{.Architecture}}'
```

Expected result: all tests pass, Compose renders without starting containers,
and image inspection prints one `sha256:` ID followed by `amd64`. Record that
exact ID; do not push it.

## Owner gate: privileged file installation

These commands are intentionally not executed by repository automation. From
the bundle directory on `um790pro`, the owner installs only the reviewed tree:

```bash
sudo install -d -o root -g root -m 0755 /usr/local/lib/audiobook-ops
sudo rsync --archive --delete \
  --exclude '__pycache__/' --exclude '.pytest_cache/' \
  --chown=root:root ./ /usr/local/lib/audiobook-ops/
sudo install -d -o root -g nik -m 0750 /etc/audiobook-ops/config
sudo install -d -o root -g root -m 0700 /etc/audiobook-ops/secrets
sudo install -d -o nik -g nik -m 0750 /home/nik/services/audiobook-ops
sudo install -d -o nik -g nik -m 0750 /home/nik/services/audiobook-ops/staging
sudo install -d -o nik -g nik -m 0750 /home/nik/services/audiobook-ops/migration
sudo install -d -o root -g root -m 0700 /var/backups/audiobook-ops
```

Expected result: executable bits are preserved; the installed bundle and
operator config remain root-owned and are not writable by `nik`; the config
directory is group-readable by the `nik` service group; control/staging are
writable by UID 1000; backups and secrets are root-only. Create the six config
files from the reviewed examples, replace only environment-specific values, and
set the exact reviewed image ID in `compose.env`:

```text
/etc/audiobook-ops/config/audiobook-ops.json
/etc/audiobook-ops/config/backup.json
/etc/audiobook-ops/config/compose.env
/etc/audiobook-ops/config/health.json
/etc/audiobook-ops/config/policy.json
/etc/audiobook-ops/config/publisher.json
```

Install every operator config file as `root:nik` mode `0640`: host services run
as `nik` and require read access, while only root may modify the files. Keep the
config directory itself `root:nik` mode `0750`.

Do not put credentials in those files. The five separate root-owned mode `0600`
files are `abs-api-token`, `mcp-bearer`, `prowlarr-api-key`,
`publisher-ssh-key`, and `transmission-password`. Their creation or installation
is a separate owner gate.

Install but do not enable or start host assets:

```bash
sudo install -o root -g root -m 0644 systemd/audiobook-ops-* \
  /etc/systemd/system/
sudo install -o root -g root -m 0644 tmpfiles/audiobook-ops.conf \
  /etc/tmpfiles.d/audiobook-ops.conf
sudo install -o root -g root -m 0644 logrotate/audiobook-ops \
  /etc/logrotate.d/audiobook-ops
sudo systemd-tmpfiles --create /etc/tmpfiles.d/audiobook-ops.conf
sudo systemctl daemon-reload
```

Expected result: logs and the shared lock exist, units load without parse
errors, and no production container or timer has changed state.

## Preflight and resolved Compose

After credentials and configs exist, run:

```bash
sudo /usr/local/lib/audiobook-ops/scripts/preflight.sh --host um790pro
sudo /usr/bin/docker compose \
  --env-file /etc/audiobook-ops/config/compose.env \
  -f /usr/local/lib/audiobook-ops/docker-compose.yml config --quiet
```

Expected result: every line is `PASS`, the final line is `Preflight passed`, and
Compose exits zero without creating or starting a container.

The Moscow gate installs the reviewed forced-command wrapper and verifies that
`capacity` returns one JSON integer while a shell command is denied. The exact
commands are in the README publisher installation and recovery section and must
be approved before use.

## Owner gate: production startup

After preflight passes, enable the production service and timers:

```bash
sudo systemctl enable --now audiobook-ops-compose.service
sudo systemctl enable --now audiobook-ops-policy.timer \
  audiobook-ops-worker.timer audiobook-ops-publisher.timer \
  audiobook-ops-cleanup.timer audiobook-ops-backup.timer \
  audiobook-ops-healthcheck.timer
```

Expected result: exactly five audiobook-ops containers are running, and the
service plus six timers are active. Run:

```bash
sudo /usr/local/lib/audiobook-ops/scripts/verify-startup.sh
sudo systemctl start audiobook-ops-policy.service
sudo systemctl start audiobook-ops-healthcheck.service
sudo tail -n 1 /var/log/audiobook-ops/health.jsonl
```

The checklist must pass; health JSON must be `ok` or only
`external-search=degraded`. If a critical check fails, stop and diagnose the
new stack from its logs and durable state; do not resurrect the removed request
manager or operate a mixed deployment.

## ReadMeABook retirement record

Production acceptance in issue #11 retired the ReadMeABook request manager.
The retained root above contains only generalized infrastructure state. The
final consistent legacy snapshot is retained for 30 days under
`/var/backups/readmeabook/20260913T145146Z`; deleting that exact snapshot is a
separate owner-gated operation after 2026-10-13.

## Backup and disposable restore

Create a production backup only inside an approved acceptance window:

```bash
sudo systemctl start audiobook-ops-backup.service
sudo systemctl show audiobook-ops-backup.service -p Result --value
sudo find /var/backups/audiobook-ops -mindepth 1 -maxdepth 1 \
  -type d -printf '%f\n' | sort | tail -n 1
```

Expected result: the oneshot is inactive/success, one timestamped directory has
`backup.json` and `SHA256SUMS`, and all containers are unpaused. Use the printed
timestamp literally in the rehearsal; do not use a wildcard or `latest` link:

```bash
sudo env PYTHONPATH=/usr/local/lib/audiobook-ops/src \
  /usr/bin/python3 /usr/local/lib/audiobook-ops/scripts/restore-rehearsal.py \
  --backup /var/backups/audiobook-ops/YYYYMMDDTHHMMSSZ \
  --destination /var/tmp/audiobook-ops-restore-YYYYMMDDTHHMMSSZ \
  --production-path /home/nik/services/audiobook-ops \
  --production-path /home/nik/services/readmeabook \
  --production-path /etc/audiobook-ops \
  --execute
```

Expected result: exact checksums and SQLite integrity pass, the disposable root
is created once, restored secrets are mode `0600`, and replay to the same path
fails. Removal of that exact disposable root requires separate approval.

## Restart acceptance

Before a host reboot, record the active task IDs and timer state. After the
owner performs the reboot, run:

```bash
sudo /usr/local/lib/audiobook-ops/scripts/verify-startup.sh
sudo systemctl start audiobook-ops-healthcheck.service
sudo tail -n 1 /var/log/audiobook-ops/health.jsonl
```

Expected result: the same durable tasks reconcile without duplicate publication,
the five containers and all required timers are active, and critical health is
green. Audiobookshelf and Absorb on `moscow` are not restarted by this runbook.
