# NixOS Handy Voice Typing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace Voxtype with pinned Handy v0.9.4 on the seven active NixOS desktop hosts while preserving mutable user settings and the out-of-scope `vmmac` Voxtype service.

**Architecture:** Use Handy's pinned upstream flake only as the application package source. Add `uinput` permissions to the shared Hyprland NixOS module, implement the Handy service and surgical settings merge locally in Home Manager, and gate the legacy Voxtype service so only the seven Linux desktop homes switch backends.

**Tech Stack:** Nix flakes, NixOS modules, Home Manager, systemd user services, udev, jq, Bash, Handy v0.9.4, HandyKeys v0.3.1.

---

## File Map

- Modify `flake.nix`: add the pinned upstream Handy input.
- Modify `flake.lock`: lock Handy v0.9.4 and its upstream dependency graph.
- Modify `modules/nixos/hyprland.nix`: load `uinput` and grant the existing `input` group access.
- Create `modules/home-manager/handy-settings.jq`: perform the exact surgical settings merge.
- Create `tests/handy-settings.sh`: verify managed fields, preserved state, and missing-binding initialization.
- Modify `modules/home-manager/handy.nix`: retain Darwin behavior and add the Linux package, settings updater, and systemd service.
- Modify `modules/home-manager/services.nix`: add an explicit legacy Voxtype service option while preserving its Linux default.
- Modify `modules/home-manager/linux-desktop.nix`: enable Handy, disable Voxtype, and remove Voxtype package/configuration.
- Modify `modules/home-manager/waybar.nix`: remove the incompatible Voxtype status module.
- Modify `dotfiles/waybar/style.css`: remove Voxtype-only styling.

### Task 1: Pin Handy v0.9.4

**Files:**
- Modify: `flake.nix:10-50`
- Modify: `flake.lock`

- [ ] **Step 1: Confirm the locked nixpkgs package is too old**

Run:

```bash
nix eval --raw --impure --expr 'let f = builtins.getFlake (toString ./.); pkgs = import f.inputs.nixpkgs { system = "x86_64-linux"; }; in pkgs.handy.version'
```

Expected: a version older than `0.9.4` for the currently locked/referenced nixpkgs package.

- [ ] **Step 2: Add the pinned upstream input**

Add beside the other application inputs in `flake.nix`:

```nix
handy.url = "github:cjpais/Handy/v0.9.4";
```

Do not add `handy.inputs.nixpkgs.follows = "nixpkgs"`; keep the dependency set tested by upstream release CI.

- [ ] **Step 3: Update only the Handy lock input**

Run:

```bash
nix flake lock --update-input handy
```

Expected: `flake.lock` gains the Handy input at tag commit `17d6c763413e3e29ec5cee76aa19ad01eccb73b2` and its transitive inputs.

- [ ] **Step 4: Verify both target architectures expose v0.9.4**

Run:

```bash
nix eval --raw --impure --expr 'let f = builtins.getFlake (toString ./.); in f.inputs.handy.packages.x86_64-linux.handy.version'
nix eval --raw --impure --expr 'let f = builtins.getFlake (toString ./.); in f.inputs.handy.packages.aarch64-linux.handy.version'
```

Expected: both commands print `0.9.4`.

- [ ] **Step 5: Review the lock diff**

Run:

```bash
git diff -- flake.nix flake.lock
```

Expected: only the pinned input declaration and its generated lock graph are present.

### Task 2: Add NixOS input-device support

**Files:**
- Modify: `modules/nixos/hyprland.nix:1-33`

- [ ] **Step 1: Record the failing pre-change assertions**

Run:

```bash
nix eval --json .#nixosConfigurations.x1carbon.config.boot.kernelModules
nix eval --raw .#nixosConfigurations.x1carbon.config.services.udev.extraRules | rg 'uinput.*GROUP="input"'
```

Expected before implementation: `uinput` is absent and the `rg` command finds no Handy rule.

- [ ] **Step 2: Declare the kernel module and udev rule**

Add to `modules/nixos/hyprland.nix`:

```nix
boot.kernelModules = [ "uinput" ];

services.udev.extraRules = ''
  KERNEL=="uinput", GROUP="input", MODE="0660"
'';
```

Do not change `modules/nixos/common.nix`; `nik` is already in the `input` group there.

- [ ] **Step 3: Verify a target host receives both settings**

Run:

```bash
nix eval --json .#nixosConfigurations.x1carbon.config.boot.kernelModules | jq -e 'index("uinput") != null'
nix eval --raw .#nixosConfigurations.x1carbon.config.services.udev.extraRules | rg 'KERNEL=="uinput", GROUP="input", MODE="0660"'
```

Expected: jq exits zero and the exact udev rule is printed.

- [ ] **Step 4: Verify the scope boundary statically**

Run:

```bash
rg -l 'modules/nixos/hyprland\.nix' hosts/{x1carbon,x1extreme,x13,um960pro,zenbook,matebook,desktop}/nixos/configuration.nix
rg 'modules/nixos/hyprland\.nix' hosts/vmmac/nixos/configuration.nix
```

Expected: all seven target files are listed by the first command; the second command has no match.

### Task 3: Test and implement the Handy settings filter

**Files:**
- Create: `tests/handy-settings.sh`
- Create: `modules/home-manager/handy-settings.jq`

- [ ] **Step 1: Write the settings regression test**

Create `tests/handy-settings.sh`:

```bash
#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
filter="$repo_root/modules/home-manager/handy-settings.jq"
tmp_dir="$(mktemp -d)"
trap 'rm -rf "$tmp_dir"' EXIT

cat > "$tmp_dir/custom-words.json" <<'JSON'
["NixOS", "Handy"]
JSON

cat > "$tmp_dir/existing.json" <<'JSON'
{
  "settings": {
    "selected_model": "keep-this-model",
    "selected_microphone": "keep-this-microphone",
    "overlay_style": "live",
    "bindings": {
      "transcribe": {
        "id": "transcribe",
        "name": "Existing name",
        "description": "Existing description",
        "default_binding": "ctrl+space",
        "current_binding": "f6"
      }
    }
  }
}
JSON

jq --slurpfile customWords "$tmp_dir/custom-words.json" -f "$filter" \
  "$tmp_dir/existing.json" > "$tmp_dir/existing.out.json"

jq -e '
  .settings.selected_model == "keep-this-model" and
  .settings.selected_microphone == "keep-this-microphone" and
  .settings.overlay_style == "live" and
  .settings.keyboard_implementation == "handy_keys" and
  .settings.push_to_talk == true and
  .settings.paste_method == "ctrl_shift_v" and
  .settings.autostart_enabled == false and
  .settings.update_checks_enabled == false and
  .settings.bindings.transcribe.current_binding == "alt_right" and
  .settings.bindings.transcribe.name == "Existing name" and
  .settings.custom_words == ["NixOS", "Handy"]
' "$tmp_dir/existing.out.json" > /dev/null

printf '%s\n' '{"settings":{}}' > "$tmp_dir/minimal.json"
jq --slurpfile customWords "$tmp_dir/custom-words.json" -f "$filter" \
  "$tmp_dir/minimal.json" > "$tmp_dir/minimal.out.json"

jq -e '
  .settings.bindings.transcribe == {
    "id": "transcribe",
    "name": "Transcribe",
    "description": "Converts your speech into text.",
    "default_binding": "ctrl+space",
    "current_binding": "alt_right"
  }
' "$tmp_dir/minimal.out.json" > /dev/null
```

- [ ] **Step 2: Run the test to verify it fails**

Run:

```bash
nix shell nixpkgs#jq --command bash tests/handy-settings.sh
```

Expected: FAIL because `modules/home-manager/handy-settings.jq` does not exist.

- [ ] **Step 3: Implement the minimal jq filter**

Create `modules/home-manager/handy-settings.jq`:

```jq
.settings = (.settings // {})
| .settings.bindings = (.settings.bindings // {})
| .settings.bindings.transcribe = (
    {
      "id": "transcribe",
      "name": "Transcribe",
      "description": "Converts your speech into text.",
      "default_binding": "ctrl+space",
      "current_binding": "ctrl+space"
    }
    + (.settings.bindings.transcribe // {})
    + { "current_binding": "alt_right" }
  )
| .settings.keyboard_implementation = "handy_keys"
| .settings.push_to_talk = true
| .settings.paste_method = "ctrl_shift_v"
| .settings.autostart_enabled = false
| .settings.update_checks_enabled = false
| .settings.custom_words = $customWords[0]
```

- [ ] **Step 4: Run the test to verify it passes**

Run:

```bash
nix shell nixpkgs#jq --command bash tests/handy-settings.sh
```

Expected: exit zero with no output.

### Task 4: Add the Linux Handy Home Manager integration

**Files:**
- Modify: `modules/home-manager/handy.nix:1-40`
- Modify: `modules/home-manager/linux-desktop.nix:1-61`

- [ ] **Step 1: Extend the Handy module interface without changing Darwin defaults**

Change the module arguments to include `config` and `inputs`. Add:

```nix
options.voiceTyping.handy.enable = lib.mkOption {
  type = lib.types.bool;
  default = pkgs.stdenv.isDarwin;
  description = "Whether to configure Handy voice typing.";
};
```

Use `config.voiceTyping.handy.enable` only for the Linux service. Keep the existing Darwin activation under `lib.mkIf pkgs.stdenv.isDarwin` so its behavior remains unchanged.

- [ ] **Step 2: Define the pinned package and settings updater**

In `modules/home-manager/handy.nix`, define the Linux package lazily:

```nix
handyPackage = inputs.handy.packages.${pkgs.stdenv.hostPlatform.system}.handy;
```

Define `updateLinuxHandySettings` with `pkgs.writeShellApplication` and the exact generated paths:

```nix
updateLinuxHandySettings = pkgs.writeShellApplication {
  name = "update-handy-settings";
  runtimeInputs = [
    pkgs.coreutils
    pkgs.jq
  ];
  text = ''
    settings_dir="''${XDG_DATA_HOME:-$HOME/.local/share}/com.pais.handy"
    settings_file="$settings_dir/settings_store.json"
    mkdir -p "$settings_dir"
    umask 077

    input_file="$settings_file"
    cleanup_input=false
    if [[ ! -f "$settings_file" ]]; then
      input_file="$(mktemp "$settings_dir/settings_store.input.XXXXXX")"
      printf '%s\n' '{"settings":{}}' > "$input_file"
      cleanup_input=true
    fi

    tmp_file="$(mktemp "$settings_dir/settings_store.json.XXXXXX")"
    cleanup() {
      rm -f "$tmp_file"
      if [[ "$cleanup_input" == true ]]; then
        rm -f "$input_file"
      fi
    }
    trap cleanup EXIT

    jq --slurpfile customWords ${handyCustomWordsJson} \
      -f ${./handy-settings.jq} "$input_file" > "$tmp_file"
    chmod 0600 "$tmp_file"

    if [[ -f "$settings_file" ]] && cmp -s "$settings_file" "$tmp_file"; then
      chmod 0600 "$settings_file"
    else
      mv "$tmp_file" "$settings_file"
    fi
  '';
};
```

Invalid JSON must cause the helper and `ExecStartPre` to fail without replacing the original file.

- [ ] **Step 3: Add the Linux package and service**

Under `lib.mkIf (pkgs.stdenv.isLinux && config.voiceTyping.handy.enable)`, add:

```nix
home.packages = [
  handyPackage
  pkgs.dotool
  pkgs.which
  pkgs.wl-clipboard
  pkgs.wtype
];

systemd.user.services.handy = {
  Unit = {
    Description = "Handy speech-to-text";
    After = [ "graphical-session.target" ];
    PartOf = [ "graphical-session.target" ];
  };
  Service = {
    ExecStartPre = "${updateLinuxHandySettings}/bin/update-handy-settings";
    ExecStart = "${handyPackage}/bin/handy --start-hidden";
    Environment = "PATH=${lib.makeBinPath [ handyPackage pkgs.coreutils pkgs.dotool pkgs.which pkgs.wl-clipboard pkgs.wtype ]}";
    Restart = "on-failure";
    RestartSec = 5;
  };
  Install.WantedBy = [ "graphical-session.target" ];
};
```

- [ ] **Step 4: Import and enable Handy from the Linux desktop module**

In `modules/home-manager/linux-desktop.nix`:

```nix
imports = [ ./handy.nix ];
voiceTyping.handy.enable = true;
```

Remove `wl-clipboard`, `dotool`, and `wtype` from the general package list because the Handy module now owns those runtime dependencies.

- [ ] **Step 5: Evaluate the generated service**

Run:

```bash
nix eval --json .#nixosConfigurations.x1carbon.config.home-manager.users.nik.systemd.user.services.handy.Service | jq
```

Expected: `ExecStartPre` references `update-handy-settings`, `ExecStart` ends in `handy --start-hidden`, and `Environment` contains `dotool`, `wl-clipboard`, `which`, and `wtype` store paths.

### Task 5: Gate and disable the legacy Voxtype service

**Files:**
- Modify: `modules/home-manager/services.nix:1-50`
- Modify: `modules/home-manager/linux-desktop.nix:1-209`

- [ ] **Step 1: Add the legacy service option with a preserving default**

In `modules/home-manager/services.nix`, add:

```nix
options.voiceTyping.voxtype.enable = lib.mkOption {
  type = lib.types.bool;
  default = pkgs.stdenv.isLinux;
  description = "Whether to run the legacy Voxtype voice typing daemon.";
};
```

Bind a local `voxtypeCfg = config.voiceTyping.voxtype;` and wrap the existing service:

```nix
systemd.user.services.voxtype = lib.mkIf voxtypeCfg.enable {
  # existing unit unchanged
};
```

- [ ] **Step 2: Disable Voxtype on Linux desktop homes**

Add to `modules/home-manager/linux-desktop.nix`:

```nix
voiceTyping.voxtype.enable = false;
```

- [ ] **Step 3: Remove the Voxtype package and generated config**

From `modules/home-manager/linux-desktop.nix`, remove:

- `voxtype-onnx` from `home.packages`;
- the `voiceTyping` and `voxtypeReplacementLines` let bindings;
- the complete `xdg.configFile."voxtype/config.toml"` declaration.

Do not modify `dotfiles/voice-typing/words.json`, `voice-typing-words.nix`, `pkgs/voxtype.nix`, the dotool patch, `pkgs/default.nix`, or the Voxtype overlays.

- [ ] **Step 4: Verify the target service set**

Run:

```bash
nix eval --json .#nixosConfigurations.x1carbon.config.home-manager.users.nik.systemd.user.services | jq -e 'has("handy") and (has("voxtype") | not)'
```

Expected: exit zero.

- [ ] **Step 5: Verify the vmmac source path retains Voxtype**

Run:

```bash
rg 'default = pkgs\.stdenv\.isLinux' modules/home-manager/services.nix
rg 'voiceTyping\.voxtype\.enable = false' hosts/vmmac modules/home-manager/linux-desktop.nix
```

Expected: the preserving default is present; the explicit disable appears only in `linux-desktop.nix`, which `vmmac` does not import.

### Task 6: Remove the Voxtype Waybar integration

**Files:**
- Modify: `modules/home-manager/waybar.nix:80-127`
- Modify: `dotfiles/waybar/style.css:148-191`

- [ ] **Step 1: Remove the Waybar module**

Remove `"custom/voxtype"` from `modules-right` and remove the complete `"custom/voxtype"` settings block. Keep the tray module because Handy exposes its own tray icon.

- [ ] **Step 2: Remove the Voxtype CSS**

Delete these selectors and their declarations from `dotfiles/waybar/style.css`:

```css
#custom-voxtype
#custom-voxtype.idle
#custom-voxtype.recording
#custom-voxtype.transcribing
#custom-voxtype.stopped
```

- [ ] **Step 3: Verify no active desktop reference remains**

Run:

```bash
rg 'custom/voxtype|#custom-voxtype|voxtype status' modules/home-manager/waybar.nix dotfiles/waybar/style.css
```

Expected: no matches.

### Task 7: Format and verify the complete migration

**Files:**
- Verify all files listed in the File Map.

- [ ] **Step 1: Format changed Nix files**

Run:

```bash
nixfmt flake.nix modules/nixos/hyprland.nix modules/home-manager/handy.nix modules/home-manager/services.nix modules/home-manager/linux-desktop.nix modules/home-manager/waybar.nix
```

Expected: exit zero.

- [ ] **Step 2: Re-run the settings regression test**

Run:

```bash
nix shell nixpkgs#jq --command bash tests/handy-settings.sh
```

Expected: exit zero.

- [ ] **Step 3: Evaluate all seven NixOS configurations**

Run:

```bash
for host in x1carbon x1extreme x13 um960pro zenbook matebook desktop; do
  nix eval --raw ".#nixosConfigurations.$host.config.system.build.toplevel.drvPath"
done
```

Expected: seven derivation paths and no evaluation errors.

- [ ] **Step 4: Evaluate Darwin regressions**

Run:

```bash
for host in i9mac m1max m3max; do
  nix eval --raw ".#darwinConfigurations.$host.system.drvPath"
done
```

Expected: three derivation paths and no errors from the generalized Handy module.

- [ ] **Step 5: Build the pinned Handy package**

Run:

```bash
nix build github:cjpais/Handy/v0.9.4#handy
```

Expected: a successful source build of Handy v0.9.4. This may take approximately 25 minutes without a binary cache.

- [ ] **Step 6: Run repository checks relevant to the changes**

Run:

```bash
nix flake check
```

Expected: formatting check passes; advisory statix/deadnix checks do not block the build.

- [ ] **Step 7: Inspect the final diff and worktree**

Run:

```bash
git diff --check
git status --short
git diff --stat
git diff
```

Expected: only the planned Handy migration, generated lock update, test, and accepted plan document are present. Do not commit implementation changes until the user explicitly confirms a commit plan.

- [ ] **Step 8: Hand off host deployment**

Ask the user to run a dry build or switch on one target host. The agent must not run `sudo nixos-rebuild` itself. After deployment, verify the user service, HandyKeys journal, Right Alt push-to-talk, Ctrl+Shift+V paste into a native Wayland client, absence of Voxtype, and persistence of model/microphone choices.
