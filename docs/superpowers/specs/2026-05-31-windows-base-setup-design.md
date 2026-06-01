# Windows Base Setup Design

## Goal

Extend the Windows-native setup path so a fresh or semi-fresh Windows host can be brought closer to the NixOS desktop baseline. The setup must remain idempotent: every script should detect current state first and only install or write when needed.

This design builds on the existing `scripts/windows-setup.ps1` and `scripts/windows-voice-typing.ps1`.

## Entry Points

`scripts/windows-setup.ps1` remains the main entrypoint. It should orchestrate focused scripts:

- `scripts/windows-wsl.ps1`: WSL system component and Ubuntu bootstrap.
- `scripts/windows-apps.ps1`: application installation through `winget`.
- `scripts/windows-fonts.ps1`: user-level font installation.
- `scripts/windows-cursors.ps1`: user-level cursor theme installation and activation.
- `scripts/windows-voice-typing.ps1`: existing Handy custom words sync.

The orchestrator should support running everything or one area at a time:

```powershell
.\scripts\windows-setup.ps1
.\scripts\windows-setup.ps1 -Only Wsl
.\scripts\windows-setup.ps1 -Only Apps
.\scripts\windows-setup.ps1 -Only Fonts
.\scripts\windows-setup.ps1 -Only Cursors
.\scripts\windows-setup.ps1 -Only VoiceTyping
.\scripts\windows-setup.ps1 -SkipInstall
.\scripts\windows-setup.ps1 -Force
```

`-SkipInstall` should skip application/package installation work while still allowing state synchronization steps such as Handy custom words. `-Force` should keep its existing meaning for scripts that need to override a running-app guard.

## Elevation

Some Windows setup actions require administrator rights. The setup should use Windows `sudo` when elevation is needed and the current process is not elevated.

Admin-required areas:

- WSL install/bootstrap when WSL or Ubuntu is missing.
- Any `winget` package that requires elevation.
- Any future system-level font or cursor install path.

The script should:

1. Detect whether the current process is elevated.
2. Detect whether a step requires elevation.
3. If elevation is needed and the process is not elevated, relaunch the specialized script with:

   ```powershell
   sudo powershell.exe -NoProfile -ExecutionPolicy Bypass -File <script> <args>
   ```

4. If `sudo` is unavailable or disabled, fail with a clear message pointing to the Windows README section.

The README should document that Sudo for Windows is available on Windows 11 24H2+ and can be enabled from Windows Settings. The recommended setup mode should be `forceNewWindow` unless the user intentionally chooses another mode.

## WSL

WSL is not a normal winget application in this setup. It should have a dedicated script because the primary bootstrap command enables Windows system components in addition to installing the WSL package and distribution.

`scripts/windows-wsl.ps1` should:

- Check WSL state with `wsl --status` or `wsl --version`.
- Check installed distributions with `wsl --list --quiet`.
- Treat Ubuntu as the desired distribution.
- If WSL and Ubuntu are already present, do nothing.
- If WSL exists but Ubuntu is missing, run:

  ```powershell
  wsl --install -d Ubuntu --no-launch
  ```

- If WSL is missing, run the same elevated command:

  ```powershell
  wsl --install -d Ubuntu --no-launch
  ```

- Avoid `wsl --update` by default. A future explicit `-Upgrade` flag can add update behavior.
- Consider `--web-download` only as a fallback or future option if Store-backed install fails.

The script should report when a reboot is likely required, but should not reboot automatically.

## Apps

`scripts/windows-apps.ps1` should install requested applications through `winget` only when missing.

Package list:

| App | winget id |
| --- | --- |
| Brave | `Brave.Brave` |
| Chrome | `Google.Chrome` |
| VS Code | `Microsoft.VisualStudioCode` |
| 1Password | `AgileBits.1Password` |
| Telegram Desktop | `Telegram.TelegramDesktop` |
| Docker Desktop | `Docker.DockerDesktop` |
| Steam | `Valve.Steam` |
| Throne | `Throneproj.Throne` |
| LibreOffice | `TheDocumentFoundation.LibreOffice` |
| PowerToys | `Microsoft.PowerToys` |
| Tailscale | `Tailscale.Tailscale` |
| yt-dlp | `yt-dlp.yt-dlp` |

The script should use:

```powershell
winget list --id <id> --exact
winget install --id <id> --exact --source winget --accept-package-agreements --accept-source-agreements
```

If a package is already installed, the default run should not reinstall or upgrade it. A future explicit `-Upgrade` flag can add update behavior.

`Microsoft.WSL` should not live in this app list; WSL is handled by `windows-wsl.ps1`.

## Fonts

`scripts/windows-fonts.ps1` should install fonts at user scope:

```text
%LOCALAPPDATA%\Microsoft\Windows\Fonts
HKCU:\Software\Microsoft\Windows NT\CurrentVersion\Fonts
```

This avoids requiring admin rights for normal font setup.

Desired font families should track the NixOS/Home Manager baseline pragmatically:

- Hack Nerd Font
- Ubuntu Nerd Font
- Ubuntu Mono Nerd Font
- Ubuntu Sans Nerd Font
- SauceCodePro Nerd Font
- JetBrainsMono Nerd Font
- Monaspace
- Font Awesome
- Roboto
- Source Sans / Source Serif / Source Code
- Fira Code / Fira Mono
- Cascadia Code

Downloads should be cached under:

```text
%LOCALAPPDATA%\nix-config\downloads
```

The script should install only missing font files and missing registry entries. If a font file and registry entry already exist, it should leave them untouched.

## Cursors

`scripts/windows-cursors.ps1` should install and activate Bibata at user scope.

Desired cursor theme:

```text
Bibata-Original-Ice
```

The script should download Bibata from its upstream release source because `winget` does not expose a Bibata package. It should cache downloads under `%LOCALAPPDATA%\nix-config\downloads`, install cursor files under a user-owned directory, update `HKCU:\Control Panel\Cursors`, and refresh the active cursor scheme.

The script should not require admin rights if the cursor files are installed under the user profile and only HKCU is modified.

Idempotency requirements:

- Do not re-download if the archive is already cached and valid.
- Do not reinstall cursor files if the desired files already exist.
- Do not rewrite cursor registry values if they already point to the desired files.
- Do not refresh the cursor scheme if no cursor setting changed.

## README

Add a Windows section to `README.md` covering:

- Running the setup from Windows PowerShell.
- Using `powershell.exe -ExecutionPolicy Bypass -File .\scripts\windows-setup.ps1`.
- Enabling Sudo for Windows before admin-required setup steps.
- Recommended Sudo for Windows mode: `forceNewWindow`.
- WSL behavior: `wsl --install -d Ubuntu --no-launch`, possible reboot, and no automatic reboot.
- Idempotency: scripts are safe to run repeatedly.

## Validation

Implementation should be validated with:

- PowerShell parser validation for every new or modified `.ps1` file.
- `windows-apps.ps1 -SkipInstall` or dry-run behavior that reports package state without installing.
- WSL detection on the current host without reinstalling WSL.
- Font install against a temporary test font directory and registry abstraction where practical.
- Cursor install against a temporary directory and dry-run registry comparison where practical.
- A real `windows-setup.ps1 -SkipInstall -Force` run to ensure existing Handy behavior still works.

No `sudo nixos-rebuild` command is needed for this work.
