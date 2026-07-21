# NixOS Handy Voice Typing Design

## Goal

Replace Voxtype with Handy on the seven active NixOS desktop hosts that currently import the full Linux desktop voice-typing stack:

- `x1carbon`
- `x1extreme`
- `x13`
- `um960pro`
- `zenbook`
- `matebook`
- `desktop`

Handy must use Right Alt as a push-to-talk transcription key and paste with Ctrl+Shift+V. The package must be pinned to the current stable release rather than the older version in the repository's locked nixpkgs.

## Scope

This migration applies only to the seven NixOS desktop hosts. It does not change:

- the current CachyOS installation;
- Darwin or Windows Handy installation behavior;
- `vmmac`, which currently receives the legacy Voxtype service without the Linux desktop configuration;
- model and microphone selection, which remain runtime choices in Handy's UI.

The shared `handyCustomWords` list and the strict assertion relating it to `voxtypeReplacements` remain intact. The old replacement data is retained because it is also consumed and validated by non-Linux paths.

## Package Source

Add Handy as a pinned upstream flake input:

```nix
handy.url = "github:cjpais/Handy/v0.9.4";
```

Do not make the upstream Handy nixpkgs input follow this repository's nixpkgs initially. The upstream package and dependency set are tested together by Handy's release CI. Future stable releases are adopted by changing the release tag and updating only the `handy` lock entry.

The application package is selected as:

```nix
inputs.handy.packages.${pkgs.stdenv.hostPlatform.system}.handy
```

The upstream NixOS and Home Manager modules are not imported. Their package options have no actual defaults, and the local integration needs additional service `PATH`, startup arguments, and settings preparation. The upstream flake remains the package source only.

## NixOS Integration

All seven target hosts import `modules/nixos/hyprland.nix`, while `vmmac` does not. Add the system-level Handy requirements there:

- load the `uinput` kernel module;
- give the existing `input` group read/write access to `/dev/uinput` through a udev rule.

The shared NixOS user definition already puts `nik` in the `input` group, which provides access to `/dev/input/event*`. No additional user-group change is needed.

This placement limits the new system permissions to the selected desktop class without repeating imports in seven host files.

## Home Manager Integration

Extend `modules/home-manager/handy.nix` so it supports both its existing Darwin custom-word synchronization and the new Linux service.

`modules/home-manager/linux-desktop.nix` will import this module and enable Linux Handy voice typing. The Linux configuration will:

- install the pinned Handy package;
- retain `wl-clipboard`, `dotool`, `wtype`, and add `which` to the service runtime path;
- start Handy as a graphical-session systemd user service;
- use `handy --start-hidden` and the tray icon for normal startup;
- restart on failure;
- disable the legacy Voxtype service on these hosts.

The service must use an explicit `PATH` containing Handy, `dotool`, `wl-copy`, `wtype`, `which`, and basic core utilities. Handy v0.9.4 discovers external typing tools through `which`. On KDE Wayland, `dotool` provides reliable Ctrl+Shift+V injection; `wl-copy` writes the clipboard.

## Settings Management

Handy stores mutable Linux settings at:

```text
~/.local/share/com.pais.handy/settings_store.json
```

Do not manage this file with `home.file` or a Nix-store symlink. Handy rewrites the store as users select models, microphones, and UI preferences.

Create an idempotent settings helper and run it as the Handy service's `ExecStartPre`, while the managed Handy process is stopped. The helper must:

- create a minimal settings document when the file is absent;
- reject invalid existing JSON without replacing it;
- preserve every unmanaged setting;
- update only the managed fields;
- write through a same-directory temporary file and atomic rename;
- avoid rewriting an already-current file;
- set permissions to `0600` because the file can contain API keys.

Managed Linux fields:

```json
{
  "keyboard_implementation": "handy_keys",
  "push_to_talk": true,
  "paste_method": "ctrl_shift_v",
  "autostart_enabled": false,
  "update_checks_enabled": false,
  "bindings.transcribe.current_binding": "alt_right",
  "custom_words": "shared handyCustomWords"
}
```

When the transcription binding object is absent, seed its required metadata before setting `current_binding`. Do not manage the selected model, microphone, onboarding state, overlay style, audio feedback, or paste delays.

Internal Handy autostart is disabled because systemd owns startup. Internal update checks are disabled because the immutable package is updated through the pinned flake input.

## Voxtype Migration

Add an explicit enable option around the Voxtype service currently defined in `modules/home-manager/services.nix`. Preserve its current Linux default so `vmmac` remains unchanged, then disable it from `linux-desktop.nix` when Handy is enabled.

Remove from the seven desktop configurations:

- the `voxtype-onnx` package;
- the generated `~/.config/voxtype/config.toml`;
- the Voxtype Waybar custom module;
- Voxtype-specific Waybar CSS.

Keep the local Voxtype package, patch, and overlay definitions because the out-of-scope `vmmac` service still references them. Removing those definitions is a separate cleanup after `vmmac` is migrated or retired.

Handy's tray icon replaces the Waybar indicator. No reduced running/stopped replacement is added.

## First Run

The service starts hidden but leaves the Handy tray icon available. On each machine, the user opens Handy from the tray once to complete onboarding, choose/download a model, select the microphone if necessary, and verify the language behavior. These runtime selections are preserved by the surgical settings merge.

## Verification

Before any host switch:

1. Format and lint the changed Nix files.
2. Evaluate the pinned Handy package version as `0.9.4` for both `x86_64-linux` and `aarch64-linux`.
3. Build the upstream Handy x86_64 package target.
4. Evaluate all seven target NixOS configurations.
5. Verify `vmmac` still evaluates with Voxtype enabled and without the Handy desktop service.
6. Verify Darwin Home Manager configurations still evaluate with their existing Handy custom-word activation.
7. Confirm the generated Linux service contains the expected package, `PATH`, `ExecStartPre`, and `--start-hidden` command.
8. Confirm Voxtype and its Waybar module are absent from the seven target configurations.

The user performs NixOS dry builds or switches; the agent must not run `sudo nixos-rebuild` for any host.

After deployment on one target host, verify:

- `/dev/uinput` is available to the `input` group;
- `systemctl --user status handy` is healthy;
- the journal contains successful HandyKeys initialization and no panic or registration error;
- pressing and holding Right Alt records, releasing it transcribes, and Ctrl+Shift+V pastes into a native Wayland application;
- Voxtype is not running;
- model and microphone choices survive service restarts and later Home Manager activations.

## Rollback

Rollback consists of disabling the Handy integration and re-enabling the Voxtype service/configuration in `linux-desktop.nix`. The retained Voxtype derivation and patch make this possible without reconstructing removed package code. Handy's mutable settings and downloaded models are not deleted during rollback.
