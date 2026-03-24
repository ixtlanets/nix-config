---
name: git-commit-helper
description: Split a git working tree into logically coherent commits, craft short meaningful commit messages following repo rules (fallback: Conventional Commits), and create commits only after presenting a commit plan and getting explicit confirmation.
---

# Git Commit Helper

## Workflow

1. Discover repo rules + current state

- Prefer repo-specific rules if they exist (in roughly this order): `AGENTS.md`, `CONTRIBUTING*`, `README*`, `.github/*`, commitlint config (`commitlint.config.*`, `.commitlintrc*`).
- Infer commit message style from history: `git log -20 --oneline`.
- Capture change set:
  - `git status --porcelain=v1`
  - `git diff` (unstaged)
  - `git diff --staged` (already staged)

2. Propose a commit plan (do not commit yet)

- Split changes into the smallest number of commits where each commit has one purpose and a clean message.
- Prefer to split when any of these apply:
  - behavior change + formatting/refactor mixed
  - unrelated features/fixes mixed
  - generated/lockfile changes mixed with source changes (only split if safe)
  - mechanical renames/moves mixed with logic changes
- Ensure each commit is logically consistent and plausibly reviewable on its own.
- Always present the plan first and use the `question` tool to ask for approval:
  - Use header: "Commit plan"
  - Use multiple: false (single choice)
  - Provide three options:
    - **Confirm** (description: "Proceed with executing all commits as planned")
    - **Edit** (description: "I want to adjust messages or commit splits")
    - **Abort** (description: "Cancel — do not commit anything")
  - Only proceed with commits if user selects "Confirm"
  - If "Edit" is selected, ask the user what changes they want to make
  - If "Abort" is selected, stop and do not commit

Commit plan output format (example)

```
Commit 1
  message: fix(parser): handle empty headline
  includes:
    - src/parser.ts (hunks: 2)
    - tests/parser.test.ts (all)

Commit 2
  message: refactor(parser): extract headline normalization
  includes:
    - src/parser.ts (hunks: 3)
```

3. Stage changes for commit N (non-interactive)

- Prefer whole-file staging when a file is "pure" for the commit:
  - `git add path/to/file1 path/to/file2`
- If a file has mixed changes and interactive staging is unavailable:
  - Create a patch that contains only the hunks for this commit.
  - Stage via: `git apply --cached /path/to/commit-N.patch`
  - Verify: `git diff --cached`
- If patching is impractical (binary files, large rewrites), fall back to whole-file staging and adjust the plan.

4. Create the commit

- Commits are executed after plan approval in step 2.
- Create exactly one commit per planned unit.
- Never create empty commits.
- After each commit, re-check what remains and update the next patch/plan if needed:
  - `git status --porcelain=v1`
  - `git diff`

## Commit message rules

1. Use repo rules if present

- If the repo defines a format (e.g., Conventional Commits + scopes), follow it.

2. Default (Conventional Commits)

- Format: `type(scope): subject` or `type: subject`
- Subject: imperative, no trailing period, aim <= 72 chars.
- Use a scope only when it clearly helps and matches repo patterns.
- Prefer a body only when the "why" is not obvious from the diff.

Recommended types

- `feat`, `fix`, `refactor`, `docs`, `test`, `chore`, `perf`

## Safety and hygiene

- Do not commit likely secrets (e.g. `.env*`, `*credentials*`, `*.pem`, `id_rsa`, `*.p12`, `*.key`). If found, stop and warn.
- Do not rewrite history (no `--amend`, no rebases, no force pushes) unless explicitly requested.
- Do not change git config.
- Do not push unless explicitly requested.
