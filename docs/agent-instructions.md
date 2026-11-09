# Shared agent instructions

The editable shared policy is `dotfiles/agents/common.md`. Application additions
live in `codex.md`, `opencode.md`, `hermes.md`, `openclaw.md` and `dsh.md` in the
same directory. `dsh-user.md` holds DSH-only communication preferences and
nonsecret user context; it is never included in another application's output.
`routes.json` owns the models, reasoning efforts and short route descriptions:
`fast` is GPT-6.1 Terra/high; `deep` is GPT-6.1 Sol/high.

`scripts/sync-agent-instructions.py` renders these sources into native application
files. Generated blocks are delimited by `nix-config:agent-instructions` comments;
all text outside those blocks is preserved. Edit the sources, then synchronize:

```sh
agent-instructions-sync --check
agent-instructions-sync
```

On Arch/CachyOS, `install.sh` installs the command with Python dependencies and
points it at this checkout's policy directory. Keep the checkout in place. Home
Manager packages the same sources and runs synchronization during activation;
after editing the checkout, activate the new generation or synchronize directly:

```sh
python scripts/sync-agent-instructions.py --check
python scripts/sync-agent-instructions.py
```

Use `--app dsh` to check or apply only DSH, without parsing or changing other
applications' configuration. Repeat `--app` to select several applications;
omitting it retains the all-applications behavior.

```sh
python scripts/sync-agent-instructions.py --app dsh --check
python scripts/sync-agent-instructions.py --app dsh
```

Direct execution requires Python 3, PyYAML and tomlkit. `--check` writes nothing
and exits nonzero on drift or an optional application prerequisite warning.
Every changed existing file gets a mode-0600 backup under
`~/.local/state/agent-instructions/backups/<UTC timestamp>/`, retaining its full
absolute path below that directory. Backups may contain credentials; they stay
local. To undo a change, restore the corresponding backup file. Newly created
files have no prior backup.

## Application scope

- **Codex:** adds a block to the effective global `AGENTS.md` or an existing
  nonempty `AGENTS.override.md`, enables native agents and merges
  `agents/{fast,deep}.toml`. Existing parent model, provider, hooks and other roles
  remain unchanged. Start a fresh session to load new roles.
- **OpenCode V2:** adds a block to the global `AGENTS.md` and merges
  `agents/{fast,deep}.md` using OpenAI models with the `high` variant. Existing
  providers and authentication remain unchanged. `opencode-defaults.md` is only a
  first-install seed, moved verbatim from the previous Home Manager configuration;
  subsequent edits to that seed deliberately leave existing local guidance alone.
  Use a new session or reload configuration to refresh the agent catalog.
- **Hermes:** updates `SOUL.md` and named model-map routes in the current
  `HERMES_HOME` (default `~/.hermes`). Other profiles are not implicitly modified.
  The profile needs installed and enabled `advanced-delegation`; otherwise it is
  skipped with a warning while other applications are synchronized. Old endpoint,
  credential, fallback and speed overrides are removed only from `fast`/`deep`;
  unrelated routes and settings are retained. Unrepresentable YAML structures
  fail validation before any files are written. Start a new Hermes conversation
  to load the revised schema.
- **OpenClaw:** adds a block to the default and configured agents' workspace
  `AGENTS.md` files. Model aliases point to OpenAI Terra/Sol, with Terra/high as
  the default child model. Primary models, workspace-specific instructions and
  tool restrictions remain unchanged. Use new sessions for fresh bootstrap
  context. The Gateway normally hot-reloads model configuration; synchronization
  does not restart it or interrupt existing work.

- **DSH:** when its home directory exists, adds one managed block to
  `$DSH_HOME/AGENTS.md` (default `~/.dsh/AGENTS.md`), in this order: DSH user
  preferences, shared policy, DSH-specific delegation. Default provider/model/
  effort guidance is rendered from `routes.json`, not copied from the VM's live
  profile. This does not rename the main agent or require a new persona preset.
  The conversational style is for the main agent; children retain the technical
  result contract. No profile, model allowlist, permissions, credentials,
  `~/.agents/AGENTS.md` or project preset is modified.

Unless filtered with `--app`, Codex and OpenCode are configured on every run.
Hermes and OpenClaw are touched only when their configuration files exist; DSH is
optional and requires an existing home directory. Standard `CODEX_HOME`,
`OPENCODE_CONFIG_DIR`/`XDG_CONFIG_HOME`, `HERMES_HOME`,
`OPENCLAW_STATE_DIR`/`OPENCLAW_CONFIG_PATH`, and `DSH_HOME` overrides are respected.

## DSH rollout and maintenance

The approved design and exclusions are recorded in
[`2026-11-10-dsh-user-instructions.md`](superpowers/specs/2026-11-10-dsh-user-instructions.md).
Zenbook and omarchy-vm use the same sources. `.tt` remains VM-only; its old
Zenbook copy is not removed by this change.

Edit source files, review the DSH-only drift check, then apply explicitly. Do not
edit the generated block on a host and synchronize it back into Git. Preserve
host-local additions outside the markers; review them for conflicting rules.
Private memories, credentials, runtime state and backups stay outside Git.

The VM currently has a copied `~/nix-config` subset, not a Git checkout. Deploy
only `scripts/sync-agent-instructions.py` and these policy sources to their
matching paths: `common.md`, `routes.json`, `dsh.md`, `dsh-user.md`. This is enough
for `--app dsh`; do not copy the entire runtime profile or overwrite unrelated
VM-local policy sources. From the checkout, deploy and check with:

```sh
scp scripts/sync-agent-instructions.py omarchy-vm:nix-config/scripts/
scp dotfiles/agents/{common.md,routes.json,dsh.md,dsh-user.md} omarchy-vm:nix-config/dotfiles/agents/
ssh omarchy-vm 'install -Dm755 ~/nix-config/scripts/sync-agent-instructions.py ~/.local/libexec/sync-agent-instructions.py'
ssh omarchy-vm '~/.local/bin/agent-instructions-sync --app dsh --check'
```

A drift check exits 1 when application is needed. Review it, then apply:

```sh
ssh omarchy-vm '~/.local/bin/agent-instructions-sync --app dsh'
```

Use the VM's existing launcher: it supplies its private Python dependency path
for PyYAML/tomlkit. Do not replace that launcher with the simpler Zenbook one.

On Arch, after changing the synchronizer itself, refresh its installed copy on
each host (the existing launcher already forwards arguments):

```sh
install -Dm755 scripts/sync-agent-instructions.py ~/.local/libexec/sync-agent-instructions.py
agent-instructions-sync --app dsh --check
```

The first VM adoption replaces its reviewed legacy global instructions with the
managed block after taking a local mode-0600 backup. That one-time replacement
must not become the normal update procedure: later updates preserve all text
outside the managed block.

**Instruction loading depends on the preset.** `standard` and the VM's `.tt`
preset include native `agent-instructions`; shipped `minimal` does not. Keep a
preset with that loader. Do not replace the system persona, edit installed DSH
packages or set `complete: true` to inject these preferences. Existing nonempty
sessions can retain their preset revision; use fresh sessions for acceptance.
DSH has no continuous instructions-file watcher, so do not assume that external
writes immediately update a running conversation.

Acceptance: check no drift after application; verify a fresh native DSH agent
loads the user style, shared rules and project route restrictions; inspect an
ordinary bounded child's instruction loading and model selection. Test source
and route updates, preservation and isolation with the unittest command below.
Instruction loading tests prove delivery, not perfect behavioral compliance.

Initial rollout verification: 20 synchronizer tests passed; both hosts' generated
instructions and source subset have matching SHA-256 hashes and no DSH drift.
Unrelated application/profile fingerprints were unchanged, and the VM service
remained active. The native rc.1 baseline resolver loaded all three policy layers
without truncation on both hosts, including alongside `.tt` project instructions
on the VM. A fresh Terra/high child on Zenbook received the complete policy in
its initial context without opening a file; this does not establish behavioral
compliance or verify a newly spawned child on the VM.

The updater configures routes (DSH: guidance only); it does not install providers,
sign in, broaden tool permissions or grant additional filesystem access. Verify
native discovery:

```sh
opencode debug agents
openclaw config validate --json
openclaw models list --json
python -m unittest discover -s tests -p test_agent_instructions.py -v
```
