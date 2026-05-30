---
name: opencode-bump
description: Use when the user asks to bump opencode, run the opencode bump workflow, update pkgs/opencode.nix to the latest release or a specified version, or invokes $opencode-bump.
---

# OpenCode Bump

Update `pkgs/opencode.nix` using the repo helper script.

## Workflow

1. Run `./.opencode/scripts/bump-opencode.sh`.
   - If the user supplied a version or flags such as `--dry-run`, pass those arguments through to the script.
   - With no supplied arguments, run the script with no arguments so it fetches the latest release.
2. Show what changed in `pkgs/opencode.nix`.
3. Report the old version, new version, and whether `nix build .#opencode` passed.

## Rules

- Do not run `nix flake update`.
- Do not modify files other than `pkgs/opencode.nix` unless fixing this bump workflow.
- Do not commit unless explicitly asked.
