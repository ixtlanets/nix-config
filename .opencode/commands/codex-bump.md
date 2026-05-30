---
description: Bump codex package to latest release
agent: build
subtask: false
---

Update `overlays/default.nix` using the repo helper script.

Steps:
1. Run:
   - `./.opencode/scripts/bump-codex.sh $ARGUMENTS`
2. Show what changed in `overlays/default.nix`.
3. Report old/new version and whether the codex overlay package build passed.

Rules:
- Do not run `nix flake update`.
- Do not modify files other than `overlays/default.nix` unless fixing this bump workflow.
- Do not commit unless explicitly asked.
