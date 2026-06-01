# Windows yt Helper Design

## Goal

Add a Windows-native equivalent of the existing Linux/macOS `yt` helper.
The command should download the URL currently stored in the Windows clipboard using `yt-dlp`, while matching the existing repository style for Windows setup scripts.

## Existing Behavior To Mirror

The current `yt` helper is defined in `modules/home-manager/yt-script.nix` and also mirrored in `install.sh`.
It:

- reads a URL from the clipboard;
- requires the clipboard value to start with `http://` or `https://`;
- creates a user video output directory;
- clears the clipboard before starting the download;
- runs `yt-dlp` with the repository yt-dlp config and an explicit output template.

On Windows, the command should preserve that behavior using PowerShell and Windows clipboard APIs.

## Package Requirement

The Windows setup should install the latest nightly `yt-dlp` package from winget:

```text
yt-dlp.yt-dlp.nightly
```

This replaces the current stable winget package id `yt-dlp.yt-dlp` in `scripts/windows-apps.ps1`.

## Architecture

The repo-owned script is the source of truth:

```text
scripts/windows-yt.ps1
```

The setup installs a user-level command shim:

```text
%LOCALAPPDATA%\Microsoft\WinGet\Links\yt.cmd
```

That directory is already expected to be on the user's PATH because winget uses it for command aliases. The shim should call `powershell.exe` with `-NoProfile -ExecutionPolicy Bypass -File` and point at `scripts/windows-yt.ps1`.

This gives both workflows:

- run directly from the repo with `.\scripts\windows-yt.ps1`;
- run from any PowerShell session with `yt` after setup has installed the shim.

## Windows yt-dlp Config

Setup should create a Windows user config at:

```text
%APPDATA%\yt-dlp\config
```

The config should contain:

```text
--cookies-from-browser brave
--format bv*[height<=1080]+ba/b[height<=1080]/b
```

The `yt` helper should still pass an explicit output template for the one-off command, matching the existing Linux helper's behavior.

## Command Behavior

`scripts/windows-yt.ps1` should:

1. Assert it is running on Windows.
2. Locate native `yt-dlp.exe` on PATH and fail clearly if it is missing. Do not invoke `.cmd` or `.bat` shims, because URLs may contain shell metacharacters such as `&`.
3. Read the URL from the Windows clipboard with `Get-Clipboard`.
4. Trim whitespace and validate that the URL starts with `http://` or `https://`.
5. Create `%USERPROFILE%\Videos` if needed.
6. Clear the clipboard with `Set-Clipboard ''`.
7. Run:

```powershell
yt-dlp.exe --config-locations "$env:APPDATA\yt-dlp\config" --output "$env:USERPROFILE\Videos\%(title)s.%(ext)s" "$url"
```

The script should forward the `yt-dlp.exe` exit code.

## Setup Integration

`scripts/windows-setup.ps1` should gain an `-Only Yt` option and include the new step in the default `All` run.

The setup step should be idempotent:

- create directories if missing;
- write the yt-dlp config only when content differs;
- write `yt.cmd` only when content differs;
- avoid duplicate PATH edits by using the existing winget links directory instead of adding a new directory.

If `%LOCALAPPDATA%\Microsoft\WinGet\Links` is not present in the current user `PATH`, setup should still write the shim there but print a warning that a new terminal or PATH repair may be needed before `yt` resolves as a command.

`-SkipInstall` should skip package installation through `windows-apps.ps1`, but it should not prevent writing the yt-dlp config or shim because those are configuration steps.

## Error Handling

Clipboard validation errors should be clear and use the `yt:` prefix, for example:

```text
yt: clipboard does not contain a valid URL: <value>
```

Missing native `yt-dlp.exe` should also be explicit and tell the user to run the setup or install `yt-dlp.yt-dlp.nightly`.

## Verification

Implementation should verify:

- PowerShell parser checks pass for all modified Windows scripts.
- `windows-apps.ps1 -SkipInstall` reports `yt-dlp-nightly` using the nightly package id.
- the setup step writes `%APPDATA%\yt-dlp\config`;
- the setup step writes `%LOCALAPPDATA%\Microsoft\WinGet\Links\yt.cmd`;
- running `windows-yt.ps1` with a non-URL clipboard value fails with the expected validation message;
- a dry command-construction test can run without downloading real video by compiling and injecting a harmless fake native `yt-dlp.exe` earlier in PATH.
