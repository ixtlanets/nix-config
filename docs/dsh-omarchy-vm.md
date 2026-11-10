# DSH on omarchy-vm

## Agreed deployment plan (2026-11-08)

- Run upstream `@deepseek-ai/dsh` directly on the Arch/Omarchy VM as user `nik`, not in Docker.
- Install exact DSH and Node versions with mise. The systemd service selects its own pinned versions, independently of Omarchy's moving `latest` tool defaults.
- Run a persistent user systemd service with linger already enabled. Listen on `127.0.0.1:3080` only.
- Publish a private access path through Tailscale Serve at `https://personal-openclaw.tailf108.ts.net:8443/`. Preserve the existing Serve endpoint on port 443. No Funnel/public ingress.
- Keep DSH's own launch-token/cookie authentication. Treat authenticated access as access to the `nik` account's projects and command execution.
- Copy the current local Harness model routes, catalog overrides, main model (`openai-codex/gpt-6.1-sol`, high), and subagent allowlist. Transfer only required API-key references over SSH; never put secrets in Git. Authorize Codex separately on the VM, without cloning rotating OAuth credentials.
- Manual updates only: install a selected version before stopping the service; create a consistent service snapshot with writers stopped; start the new pinned version and check readiness. Retain the old version and matching state for explicit rollback.
- Keep lifecycle scripts and this runbook in this repository. Keep runtime state, credentials, backups, and browser cookies outside Git.

## Access and security

- Private URL: **https://personal-openclaw.tailf108.ts.net:8443/**.
- The client computer must be connected to the same tailnet and permitted by its ACLs. MagicDNS should resolve the hostname; the VM itself has `accept-dns=false`, which does not prevent other clients from resolving it.
- The first browser visit needs a DSH launch URL containing `?token=...`. DSH exchanges it for an authority-bound cookie and removes the token from the address bar. Treat this URL as a password; do not paste it into issues, logs, or Git.
- A bare URL is not enough in a new browser without an authentication cookie. The lifecycle helper's explicit `url` command retrieves the current instance's launch URL.
- Access is not a read-only dashboard: an authenticated DSH user can instruct an agent to read files and run commands as `nik` on the VM. Do not share access with untrusted tailnet members.
- Do not enable Tailscale Funnel, wildcard listener addresses, or a public firewall rule for port 3080.

Tailscale Serve is managed independently from the user service. Add only port 8443 (requires administrator privileges):

```bash
ssh -t omarchy-vm 'sudo tailscale serve --bg --yes --https=8443 http://127.0.0.1:3080'
```

Inspect with `ssh omarchy-vm 'tailscale serve status'`. The existing port 443 must still proxy to `127.0.0.1:4179`. To remove **only** DSH's private endpoint:

```bash
ssh -t omarchy-vm 'sudo tailscale serve --https=8443 off'
```

Never use `tailscale serve reset`: it would remove unrelated services too.

## Model configuration and credentials

The reproducible, nonsecret Web profile is in [`dotfiles/dsh/web`](../dotfiles/dsh/web/). It includes the same experimental Agent Teams bundle and model configuration as the source Harness on 2026-11-08:

- Main model: `openai-codex/gpt-6.1-sol`, reasoning `high`.
- Codex catalog overrides: `gpt-5.6-luna`, `gpt-5.6-sol`, `gpt-5.6-terra`, `gpt-6-astra`, `gpt-6.1-sol`, `gpt-6.1-terra`.
- Kimi Coding via credential reference `KIMI_CODING_API_KEY`.
- PlusVibe gateway `https://gw.plusvibeapi.ru/v1`, model `deepseek-v4.1-flash`, via `PLUSVIBE_API_KEY`.
- Subagent allowlist: Kimi `k3.1-pro`, PlusVibe `deepseek-v4.1-flash`, Codex `gpt-6.1-sol` and `gpt-6.1-terra`.

The VM's API keys are stored in `~/.dsh/.credentials.yaml` (0600; parent directory 0700). Only the two required `refs` were transferred over SSH; no OAuth records, browser-session signing key, source sessions, or project paths were copied. Never print this file in a diagnostic command or check it into Git.

DSH `0.2.2-rc.1` does **not** expose Codex OAuth in the Models editor; selecting ChatGPT there only edits its route. Use the compatibility entrypoint supplied by this bundle:

```bash
ssh -t omarchy-vm '~/.local/bin/dsh-vm login'
```

Open the displayed `https://auth.openai.com/codex/device` page on your client computer, enter the displayed one-time code, and approve **your VM sign-in**. Keep the terminal open until it reports `Codex authorized on VM`. Do not paste the code, credentials, or callback URLs into chat. Ctrl-C cancels the attempt. If OpenAI requires device-code login to be enabled, enable it in your ChatGPT security settings and retry.

This is our small compatibility command, **not** an upstream `dsh auth` command: [`dsh-vm-login.mjs`](../hosts/omarchy-vm/dsh/dsh-vm-login.mjs) mounts the installed DSH authorization service and pi-ai adapter, selects their native device-code method, and lets that adapter commit `llm-pi-ai/openai-codex` through the normal locked credential service. Existing API keys and browser-signing records are preserved; the Web service stays running and watches the store. No CLI/browser tokens from another instance are imported. No callback port or SSH forward is needed. The lifecycle lock prevents an update/rollback during this command.

Check redacted record metadata with `ssh omarchy-vm '~/.local/bin/dsh-vm login-status'`, then send a small message in the VM Web UI using **GPT‑6.1 Sol / high**. A saved record alone does not prove upstream inference. Do not work around login failures by cloning rotating OAuth refresh tokens from another running instance.

Runtime state and backup archives contain secrets and conversation history. They remain outside Git and must be protected like credentials. Local rollback snapshots are not off-host disaster-recovery backups.

## Install or refresh lifecycle tooling

Prerequisites: Arch/Omarchy, `/usr/bin/mise`, Python 3.12+, `curl`, a working systemd user manager, SSH access, and a joined tailnet. Run as `nik`, **not root**. `loginctl show-user nik -p Linger` must report `Linger=yes`; otherwise have an administrator enable linger. The service never follows Omarchy's global `latest` DSH/Node defaults.

From this repository on the source computer:

```bash
tar -cf - install.sh scripts/install-dsh-vm.sh \
  hosts/omarchy-vm/dsh/dsh-vm \
  hosts/omarchy-vm/dsh/dsh-vm-runtime \
  hosts/omarchy-vm/dsh/dsh-vm-login.mjs \
  hosts/omarchy-vm/dsh/dsh-vm.service \
  dotfiles/dsh/web/package.json dotfiles/dsh/web/cordis.patch.yml |
ssh omarchy-vm 'umask 077; mkdir -p ~/.local/share/dsh-vm-source && tar -xf - -C ~/.local/share/dsh-vm-source && bash ~/.local/share/dsh-vm-source/install.sh --dsh-vm'
```

The `--dsh-vm` branch in [`install.sh`](../install.sh) runs only [`scripts/install-dsh-vm.sh`](../scripts/install-dsh-vm.sh), **not** the workstation-wide installer. Missing model-profile files are seeded; existing files and credentials are preserved. The lifecycle bundle installs/enables the unit but does not start or restart it automatically. On initial installation:

```bash
ssh omarchy-vm '~/.local/bin/dsh-vm start'
ssh omarchy-vm '~/.local/bin/dsh-vm status'
ssh omarchy-vm '~/.local/bin/dsh-vm check'
ssh omarchy-vm '~/.local/bin/dsh-vm url'
```

After deliberately refreshing the launcher/unit files, restart the service and run `check`; wait for in-flight agent work to finish first. Installing tooling does not change an existing runtime version pin. Keep the source bundle on the VM to refresh the tooling from the repository; reinstalling the already installed helper only reapplies its current assets.

## Manual updates and rollback

Implementation: [`hosts/omarchy-vm/dsh`](../hosts/omarchy-vm/dsh/). Active exact versions live in `~/.config/dsh-vm/runtime.env`; initial pins are DSH `0.2.2-rc.1`, Node `26.13.0`. Do not edit these pins while the service is running, and do not use `latest` in lifecycle commands.

1. Finish active agent work. **This instance must be the only writer of `~/.dsh`**: stop any separately started DSH CLI/server using that home before continuing.
2. Select an explicit released DSH version; optionally select an exact Node version. Review upstream release notes.
3. Run the helper, substituting real versions:

   ```bash
   ssh omarchy-vm '~/.local/bin/dsh-vm update VERSION'
   # Optional Node change:
   ssh omarchy-vm '~/.local/bin/dsh-vm update VERSION NODE_VERSION'
   ```

4. The candidate runtime is installed and checked **before** stopping the service. With the service stopped, a consistent snapshot of the complete `~/.dsh` plus the previous runtime pin is saved under `~/.local/state/dsh-vm/snapshots/`. An exclusive lock serializes helper operations. The helper then switches the pin, starts DSH, and checks authenticated API readiness using the current systemd invocation's launch token. A TCP-only check is not considered success.
5. Startup/readiness failure triggers restoration of both the old pin and the matching complete state. Failed/displaced state is preserved in a private `~/.dsh-vm-preserved-*` directory, not deleted. If automatic recovery itself fails, the helper reports the snapshot path for manual investigation.
6. Verify `status`, `check`, and the browser after the cutover. `check` validates local authentication/API availability, **not** Tailscale reachability or a model-provider response. Check HTTPS separately from a tailnet client.

To explicitly restore a prior snapshot, use the exact snapshot name/path printed during an update:

```bash
ssh omarchy-vm '~/.local/bin/dsh-vm rollback SNAPSHOT --yes'
```

**Rollback rewinds all settings, sessions, history, credentials, and browser-signing state**, not just the package. The helper creates another safety snapshot first and preserves displaced data. Restored OAuth refresh tokens or revoked API keys may no longer be valid: reauthorize the provider if necessary. Recent conversations remain in the safety snapshot/displaced directory but disappear from the restored active state. Do not roll back casually after substantial new work.

Keep old mise runtime versions while any retained snapshot references them. Snapshots are private directories (0700), with archive/config/metadata files 0600 and a checksum/completion marker. Absolute/external symlinks and special files in active state are refused before cutover so an unusable safety snapshot cannot be accepted; unsafe archive members are also refused on restore. There is no automatic retention/deletion policy; inspect disk use and retain encrypted off-host backups as needed. Never delete `~/.dsh` to perform an update or rollback.

## Diagnostics and tests

```bash
ssh omarchy-vm '~/.local/bin/dsh-vm status'  # no launch token in ordinary status
ssh omarchy-vm '~/.local/bin/dsh-vm check'   # authenticated API, current invocation
ssh omarchy-vm 'ss -ltnp "sport = :3080"'
ssh omarchy-vm 'tailscale serve status'
```

Raw `systemctl --user status` and journal output may contain a launch token; do not share them unredacted. The unit is `dsh-vm.service`; normal stop/restart operations use `systemctl --user` without sudo. Stopping DSH leaves the unrelated Tailscale 443 endpoint intact.

Isolated tests (temporary HOME, mocked mise/systemctl/curl/journal; no live service changes):

```bash
python3 hosts/omarchy-vm/dsh/tests/test_lifecycle.py
# Uses the actual pinned libraries, temporary stores, and no upstream OAuth:
/usr/bin/mise exec node@26.13.0 npm:@deepseek-ai/dsh@0.2.2-rc.1 -- \
  node --test hosts/omarchy-vm/dsh/tests/test_login.mjs
bash -n install.sh scripts/install-dsh-vm.sh hosts/omarchy-vm/dsh/dsh-vm-runtime
```

## Deployment verification

Verified on **2026-11-08**:

- DSH `0.2.2-rc.1` on Node `26.13.0`; installed lifecycle launcher/unit active, enabled, and `Linger=yes`. No reboot was performed; persistence was checked through systemd configuration.
- The only DSH listener is `127.0.0.1:3080`; runtime home 0700, credential store and pin file 0600. No source-machine OAuth or browser-signing credentials were transferred.
- Administrator added Tailscale Serve 8443 → 3080. Existing 443 → 4179 remains unchanged. From a separate tailnet client, the exact advertised HTTPS URL passes certificate verification, rejects an unauthenticated page request with 401, exchanges the launch token with 303, delivers the injected Web application and its JavaScript entries, serves the authenticated model-catalog API, and accepts an authenticated WSS upgrade at `/api/remote.mux` (101).
- Authenticated catalog has no reported failures, routes `kimi-coding`, `openai-codex`, and `plusvibe`, and keeps `openai-codex/gpt-6.1-sol` with reasoning `high` as the exact default. Catalog presence alone does **not** demonstrate upstream model authorization/inference.
- Completed a **same-version** live update/restart rehearsal and full-state rollback; the model profile remained identical and authenticated readiness passed after both. This exercises lifecycle/state restoration, not compatibility with a future DSH migration. Snapshot IDs: `20261108T145735Z-update-db68ce2ac34a` and `20261108T145737Z-rollback-bd504e1d1ab9`.
- All **16 isolated lifecycle tests + 3 actual-library OAuth seam tests** passed, plus Bash syntax, opt-in installer routing/profile-preservation checks, and `git diff --check`. The 3 OAuth tests pass both locally and on the VM using its installed runtime: they reach the real native method selector without network, verify cancellation writes nothing, and verify synthetic grant commits preserve unrelated refs/records with mode 0600. VM production credential bytes remained unchanged after the tests. Unsupported snapshot links/special files are rejected before cutover.
- Deployed the OAuth compatibility helper without restarting the Web service or changing credential bytes. The account owner then completed separate VM authorization using `dsh-vm login`; redacted status now reports `configured:true, kind:grant, writable:true`. No source-machine OAuth credentials were imported.
- **Live inference acceptance passed through the exact Tailscale HTTPS endpoint and the running Web service**, without a restart: catalog default and accepted Session selection were both `openai-codex/gpt-6.1-sol`, reasoning `high`. The test prompt requested no tools or file changes. The actual upstream assistant record reports provider `openai-codex`, model `gpt-6.1-sol`, API `openai-codex-responses`, normal `stop`, and the exact response `DSH_VM_CODEX_OK_20261108`; Session settled idle with no pending input. The retained conversation is titled `DSH VM acceptance — GPT-6.1 Sol/high`, Session `session-7176b6c4-4184-45af-ab1d-146faecf3814`.

**Acceptance complete.** The rc.1 Models UI still has no OAuth button; use `dsh-vm login` for future reauthorization. Do not run the pre-authorization rehearsal rollback after signing in: it would rewind the credential state. Future normal updates create a fresh snapshot of the now-authorized state first.
