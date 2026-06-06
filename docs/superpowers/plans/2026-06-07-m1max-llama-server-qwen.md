# M1max Llama Server Qwen Rollback Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restore `m1max` `llama-server` launchd config to previous Qwen model and arguments.

**Architecture:** Single Darwin host config change in `hosts/m1max/nixos/configuration.nix`. Launchd continues to run `/opt/homebrew/bin/llama-server` with same host, port, flash attention, logging, and working directory settings.

**Tech Stack:** Nix Darwin config, Homebrew `llama.cpp`, launchd user agent.

---

### Task 1: Restore Qwen launch args

**Files:**
- Modify: `hosts/m1max/nixos/configuration.nix:156-174`

- [ ] **Step 1: Replace Gemma model and sampling args**

Set `ProgramArguments` model and options to:

```nix
      ProgramArguments = [
        "/opt/homebrew/bin/llama-server"
        "-hf"
        "unsloth/Qwen3.6-35B-A3B-MTP-GGUF"
        "--host"
        "0.0.0.0"
        "--port"
        "8080"
        "--flash-attn"
        "on"
        "--spec-type"
        "draft-mtp"
        "--spec-draft-n-max"
        "3"
        "--reasoning"
        "off"
        "--chat-template-kwargs"
        ''{"enable_thinking": false}''
      ];
```

- [ ] **Step 2: Verify diff only touches intended config**

Run: `git diff -- hosts/m1max/nixos/configuration.nix`

Expected: Gemma model and sampling args removed; Qwen model and MTP/chat-template args restored.

- [ ] **Step 3: Evaluate m1max Darwin config**

Run: `nix eval .#darwinConfigurations.m1max.config.system.build.toplevel.drvPath`

Expected: command exits 0 and prints a `/nix/store/...-darwin-system-...drv` path.
