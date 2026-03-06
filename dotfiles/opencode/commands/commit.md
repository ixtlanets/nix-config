---
description: Split and create clean git commits
agent: build
subtask: false
---

Use the `git-commit-helper` skill for this task.

Turn the current git working tree into the smallest set of logically coherent commits.

Requirements:
- Discover repo commit-message conventions and inspect both staged and unstaged changes.
- Propose a commit plan first.
- Ask for explicit confirmation before any `git commit`.
- Split into multiple commits when changes are mixed or unrelated.
- After each commit, re-check remaining changes and continue until done.
- Never amend/rebase/force-push/change git config.
- Do not push unless explicitly asked.

Additional instructions from the user: $ARGUMENTS
