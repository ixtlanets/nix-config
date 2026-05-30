---
name: codex-bump
description: Use when the user asks to bump codex, run the codex bump workflow, update the codex package in overlays/default.nix to the latest release or a specified version, or invokes $codex-bump.
---

# Codex Bump

Update the `codex` package in `overlays/default.nix` using the repo helper script.

## Workflow

1. Run `./.opencode/scripts/bump-codex.sh`.
   - If the user supplied a version or flags such as `--dry-run`, pass those arguments through to the script.
   - With no supplied arguments, run the script with no arguments so it fetches the latest release.
2. Show what changed in `overlays/default.nix`.
3. Report the old version, new version, and whether the codex overlay package build passed.

## Rules

- Do not run `nix flake update`.
- Do not modify files other than `overlays/default.nix` unless fixing this bump workflow.
- Do not commit unless explicitly asked.
