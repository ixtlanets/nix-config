---
description: Bump opencode package to latest release
agent: build
subtask: false
---

Update `pkgs/opencode.nix` using the repo helper script.

Steps:
1. Run:
   - `./.opencode/scripts/bump-opencode.sh $ARGUMENTS`
2. Show what changed in `pkgs/opencode.nix`.
3. Report old/new version and whether `nix build .#opencode` passed.

Rules:
- Do not run `nix flake update`.
- Do not modify files other than `pkgs/opencode.nix` unless fixing this bump workflow.
- Do not commit unless explicitly asked.
