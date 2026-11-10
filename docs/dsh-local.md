# DSH on a local Omarchy workstation

Run the upstream DSH Web UI as the desktop user, with exact mise DSH/Node versions and a user systemd service. The local endpoint is **http://127.0.0.1:3080/**. No Docker, Tailscale configuration, public ingress, credential transfer, or VM deployment is involved.

The local launcher reuses the [VM lifecycle engine](../hosts/omarchy-vm/dsh/dsh-vm), including consistent snapshots, authenticated readiness, and update recovery. Local assets are in [dotfiles/dsh/local](../dotfiles/dsh/local/); the VM's public URL and trusted-host arguments are not used.

## Install tooling without interrupting a running DSH

Prerequisites: Linux/Omarchy, Python 3.12+, `/usr/bin/mise`, `curl`, and a working systemd user manager. Run as the intended user, **never root**.

```bash
cd ~/nix-config
bash install.sh --dsh-local
```

This opt-in branch runs only the local DSH installer, not the workstation-wide setup. It installs the lifecycle helper, launcher, user unit, and initial exact pins; enables autostart; and reloads the user manager. **It does not start, stop, or restart DSH.** Existing runtime pins and the existing DSH profile, credentials, and conversations are preserved. No VM model profile is copied onto the workstation.

Initial pins: DSH `0.2.2-rc.1`, Node `26.13.0`. The service selects these exact mise versions, not Omarchy's moving `latest` defaults or auto-updating DSH shim. Active pins live in `~/.config/dsh-local/runtime.env`; do not edit them while the service is running.

For startup before login and persistence after logout, check:

```bash
loginctl show-user "$USER" -p Linger
```

`Linger=yes` is already configured on `zenbook`. This does not prevent laptop suspend: DSH is unavailable while the host is asleep or powered off.

## First service cutover — perform in a separate terminal

Finish agent tasks and wait for the agent's final instructions. Stop the existing foreground `dsh web` command with **Ctrl-C in its original terminal**. Stop other DSH processes using the same `~/.dsh` too. Do not issue the cutover from inside a DSH tool call: stopping its server also interrupts that call.

Then run in the terminal:

```bash
~/.local/bin/dsh-local start
~/.local/bin/dsh-local status
~/.local/bin/dsh-local check
~/.local/bin/dsh-local url
```

`start` waits for authenticated local API readiness. The explicit `url` command prints the current launch URL containing a login token: open it locally, but do not paste it into chat, Git, or issues. Ordinary `status` and `check` do not print tokens. Refresh the existing browser tab after the cutover and send a small message to verify actual provider access; API readiness alone does not prove inference works.

The service uses the existing `~/.dsh` and Web profile. It does not grant root access or force `DSH_PERMISSION_MODE=danger-full-access`; it uses the configured DSH permissions. A terminal-only environment override is not automatically part of a systemd service. API keys stored only in a terminal environment, SSH agents, graphical-session variables, and proxy variables may need explicit user-manager configuration; avoid putting secrets in repository files or command arguments.

If startup fails, do not launch another copy alongside the service. Stop the unit first, inspect the helper's error locally, then decide whether to return to the original foreground command:

```bash
systemctl --user stop dsh-local.service
```

Raw journal/status output may contain the launch token. Do not share it unredacted.

## Manual version updates

Wait for all agent work to finish and stop all other writers of `~/.dsh`. Run from an independent terminal, substituting an explicit released version:

```bash
~/.local/bin/dsh-local update VERSION
# Optionally change Node too:
~/.local/bin/dsh-local update VERSION NODE_VERSION
```

Moving aliases such as `latest` are deliberately rejected. The candidate runtime is installed and checked before stopping the current service. The helper then stops the unit, saves a consistent service snapshot, changes the pin, restarts, and checks authenticated API readiness tied to the new systemd invocation. If startup/readiness fails, it attempts to restore both the previous runtime pin and the matching state. Displaced state is preserved, not deleted.

Snapshots live in `~/.local/state/dsh-local/snapshots/`. A lifecycle lock serializes helper operations; it cannot stop arbitrary unrelated programs from writing the same DSH home. The account owner must ensure the service is the only writer. Do not run automatic background updates or prune old mise installations while retained snapshots depend on them.

### Legacy npx package links

The existing `zenbook` state includes absolute package links under `profiles/node_modules` into an older npm npx cache. These are not discarded or dereferenced one package at a time: nested versions and unlinked native dependencies are part of the original dependency graph. Local snapshots embed the complete recognized npx `node_modules` tree under a private state subtree outside `profiles` and rewrite only the archived links to relative, contained paths. The live state and npm cache are unchanged. A restored snapshot no longer depends on that old npx cache remaining present.

Only recognized package-root projections into the same user's canonical `.npm/_npx/<id>/node_modules` tree are supported. Other external links, escaping cache links, special files, and reserved-path collisions are refused rather than creating a misleading rollback snapshot. Do not install into or prune that npm cache concurrently with an update. The current state plus legacy cache produced an approximately 280 MiB uncompressed archive in the structural check (about 230 MiB file payload before tar overhead); check free disk space and retention.

After an update, run `check`, open the browser, and verify a provider response. No reboot or provider inference check is implied by a successful local API check.

## Rollback and backups

Use the exact snapshot name/path printed by the helper:

```bash
~/.local/bin/dsh-local rollback SNAPSHOT --yes
```

**Rollback restores all DSH state**, including settings, sessions, conversation history, credentials, and browser-signing state. Newer changes disappear from the active state but remain in the safety snapshot/preserved directory. OAuth refresh tokens or revoked API keys may no longer be valid after restoration; reauthorize if necessary. Keep the old DSH and Node installations for any snapshot that may be restored.

Snapshots and preserved directories contain secrets. Their permissions are private. They are local rollback artifacts, **not encrypted off-host disaster-recovery backups**. No automatic retention or deletion is configured: monitor disk use and create encrypted external backups separately. Never delete `~/.dsh` as an update procedure.

## Routine commands

```bash
~/.local/bin/dsh-local status
~/.local/bin/dsh-local check
~/.local/bin/dsh-local url
systemctl --user stop dsh-local.service
# After refreshing launcher/unit files, finish agent work before restarting:
systemctl --user restart dsh-local.service
~/.local/bin/dsh-local check
```

The user unit is `dsh-local.service`, wanted by `default.target`, with restart on failure. Tooling reinstall does not silently restart a running instance. Use the helper's `start` command for the initial handover rather than bypassing its preflight.

## Isolated verification

```bash
python3 hosts/omarchy-vm/dsh/tests/test_lifecycle.py
python3 tests/test_dsh_local.py
python3 tests/test_dsh_local_port_guard.py
python3 tests/test_dsh_local_snapshot.py
bash tests/dsh-local-install.sh
bash -n install.sh scripts/install-dsh-local.sh dotfiles/dsh/local/dsh-local-runtime
```

These tests use temporary homes, mocked services, and real ephemeral TCP sockets (including a server-side `TIME_WAIT` regression). They must not touch the running workstation DSH.
