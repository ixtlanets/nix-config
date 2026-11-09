# DSH user instructions on Zenbook and omarchy-vm

## Agreed scope

Apply the user's communication preferences to the main DSH agent by default,
without changing its name or requiring a separate persona preset. The style is
Russian, direct, warm, concise when possible, detailed when useful, with candid
opinions and situational irony rather than ceremonial introductions.

Keep this style and user context DSH-only. Do not change Codex, OpenCode, Hermes
or OpenClaw configuration during this rollout. Do not move the `.tt` project back
to Zenbook, modify its preset or delete its old local copy. Preserve the VM's
recent switch from `minimal` to `standard`, credentials, permissions, model
configuration, browser integration and running sessions.

## Design

- Keep shared outcome/delegation policy in `dotfiles/agents/common.md`.
- Add `dotfiles/agents/dsh-user.md` for the approved communication style and the
  nonsecret user-context rules already present on the VM. Do not import personal
  memories or the OpenClaw agent's name, fictional biography or continuity claims.
- Add `dotfiles/agents/dsh.md` for DSH-specific delegation and project routing.
  Render default fast/deep provider/model/effort guidance from `routes.json`;
  project constraints and actual session model availability still govern use.
- Extend the existing synchronizer with an optional DSH adapter and a selective
  `--app dsh` mode. Generate only `$DSH_HOME/AGENTS.md` (default `~/.dsh/AGENTS.md`)
  when that DSH home exists. Preserve unmanaged text using the existing markers
  and backup/atomic replacement mechanism. Do not write `~/.agents/AGENTS.md`.
- Use native instruction loading, not a replacement system prompt or a fork of
  shipped presets. The main-agent style applies to user-facing conversation;
  children return the bounded technical result contract.

## Rollout and maintenance

1. Add isolated tests for DSH selection, preservation, environment overrides,
   style isolation, source updates and generated routes.
2. On Zenbook, use the repository synchronizer in DSH-only mode. Refresh the
   installed command's script so future maintenance supports that mode.
3. On the VM, back up the reviewed legacy instructions before replacing their
   now-imported content with the managed block. Do not keep duplicate legacy
   delegation rules below it. Copy only required policy/script sources, retaining
   unrelated VM-local content and profile settings.
4. Verify repeat synchronization reports no drift on both hosts, unrelated
   application/profile files are unchanged, and native DSH instruction discovery
   includes the generated content. Use a fresh session for behavioral acceptance;
   do not promise retroactive refresh of active conversations.
5. Commit only this change set after confirming the commit plan, then push the
   normal branch without rewriting history.

Future edits go to the sources in `nix-config`, followed by DSH-only drift check
and explicit application. Runtime credentials, histories, backups and private
memories remain outside Git. The VM currently has a copied source tree rather
than a Git checkout; deploy the reviewed source subset explicitly, not by
bidirectional runtime-directory synchronization.
