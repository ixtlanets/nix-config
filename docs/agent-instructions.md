# Shared agent instructions

The editable policy is `dotfiles/agents/common.md`. Application additions live in
`codex.md`, `opencode.md`, `hermes.md` and `openclaw.md` in the same directory.
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

Codex and OpenCode are configured on every run. Hermes and OpenClaw are touched
only when their configuration files exist. Standard `CODEX_HOME`,
`OPENCODE_CONFIG_DIR`/`XDG_CONFIG_HOME`, `HERMES_HOME`, and
`OPENCLAW_STATE_DIR`/`OPENCLAW_CONFIG_PATH` overrides are respected.

The updater configures routes; it does not install providers, sign in, broaden
tool permissions or grant additional filesystem access. Verify native discovery:

```sh
opencode debug agents
openclaw config validate --json
openclaw models list --json
python -m unittest discover -s tests -p test_agent_instructions.py -v
```
