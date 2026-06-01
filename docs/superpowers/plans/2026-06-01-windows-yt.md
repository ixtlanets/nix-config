# Windows yt Helper Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a Windows-native `yt` command that reads a video URL from the clipboard and downloads it with nightly `yt-dlp`.

**Architecture:** Keep `scripts/windows-yt.ps1` as the repo-owned command implementation. Add `scripts/windows-yt-setup.ps1` to write the Windows yt-dlp config and a user-level `yt.cmd` shim in the winget links directory. Wire that setup script into `scripts/windows-setup.ps1` while keeping package installation in `scripts/windows-apps.ps1`.

**Tech Stack:** PowerShell 5+/7, Windows clipboard cmdlets, winget, yt-dlp nightly, existing `scripts/windows-lib.ps1` helpers.

---

## File Structure

- Modify `scripts/windows-apps.ps1`: install `yt-dlp.yt-dlp.nightly` instead of stable `yt-dlp.yt-dlp`.
- Create `scripts/windows-yt.ps1`: command invoked by the shim or directly from the repo.
- Create `scripts/windows-yt-setup.ps1`: idempotently writes `%APPDATA%\yt-dlp\config` and `%LOCALAPPDATA%\Microsoft\WinGet\Links\yt.cmd`.
- Modify `scripts/windows-setup.ps1`: add `Yt` to `-Only` and run `windows-yt-setup.ps1` during `All`.
- Modify `README.md`: document `-Only Yt`, the `yt` command, and the nightly yt-dlp package.

## Task 1: Switch Windows yt-dlp Package To Nightly

**Files:**
- Modify: `scripts/windows-apps.ps1`

- [ ] **Step 1: Write the package-id change**

In `scripts/windows-apps.ps1`, replace:

```powershell
@{ Name = 'yt-dlp'; Id = 'yt-dlp.yt-dlp' }
```

with:

```powershell
@{ Name = 'yt-dlp-nightly'; Id = 'yt-dlp.yt-dlp.nightly' }
```

- [ ] **Step 2: Verify parser and skip-install output**

Run:

```powershell
$tokens = $null
$errors = $null
$null = [System.Management.Automation.Language.Parser]::ParseFile((Resolve-Path .\scripts\windows-apps.ps1).ProviderPath, [ref]$tokens, [ref]$errors)
if ($errors -and $errors.Count -gt 0) { throw ($errors | Out-String) }
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\windows-apps.ps1 -SkipInstall
```

Expected:

- parser produces no errors;
- output includes either `yt-dlp-nightly is already installed. Skipping install.` or `yt-dlp-nightly is missing. Skipping install because -SkipInstall was passed.`

- [ ] **Step 3: Commit**

Run:

```bash
git add scripts/windows-apps.ps1
git commit -m "scripts: install nightly yt-dlp on Windows"
```

## Task 2: Add Windows yt Command Script

**Files:**
- Create: `scripts/windows-yt.ps1`

- [ ] **Step 1: Create `scripts/windows-yt.ps1`**

Add this script:

```powershell
[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

. (Join-Path $PSScriptRoot 'windows-lib.ps1')
Assert-Windows

$ytDlp = @(Get-Command -Name 'yt-dlp' -CommandType Application -All -ErrorAction SilentlyContinue |
    Where-Object { -not [string]::IsNullOrWhiteSpace($_.Source) } |
    Select-Object -First 1)

if ($ytDlp.Count -eq 0) {
  Write-Error "yt: yt-dlp is not installed or not in PATH. Run scripts/windows-setup.ps1 or install winget package yt-dlp.yt-dlp.nightly."
  exit 1
}

try {
  $clipboard = Get-Clipboard -Raw
} catch {
  Write-Error "yt: failed to read Windows clipboard: $($_.Exception.Message)"
  exit 1
}

$url = ([string]$clipboard).Trim()
if (-not ($url -match '^https?://')) {
  Write-Error "yt: clipboard does not contain a valid URL: $url"
  exit 1
}

$userProfile = [Environment]::GetEnvironmentVariable('USERPROFILE')
if ([string]::IsNullOrWhiteSpace($userProfile)) {
  Write-Error 'yt: USERPROFILE is not set.'
  exit 1
}

$appData = [Environment]::GetEnvironmentVariable('APPDATA')
if ([string]::IsNullOrWhiteSpace($appData)) {
  Write-Error 'yt: APPDATA is not set.'
  exit 1
}

$videosDirectory = Join-Path $userProfile 'Videos'
$configPath = Join-Path $appData 'yt-dlp\config'
$outputTemplate = Join-Path $videosDirectory '%(title)s.%(ext)s'

New-Item -ItemType Directory -Path $videosDirectory -Force | Out-Null

try {
  Set-Clipboard ''
} catch {
  Write-Warning "yt: failed to clear Windows clipboard: $($_.Exception.Message)"
}

& $ytDlp[0].Source --config-locations $configPath --output $outputTemplate $url
exit $LASTEXITCODE
```

- [ ] **Step 2: Run parser check**

Run:

```powershell
$tokens = $null
$errors = $null
$null = [System.Management.Automation.Language.Parser]::ParseFile((Resolve-Path .\scripts\windows-yt.ps1).ProviderPath, [ref]$tokens, [ref]$errors)
if ($errors -and $errors.Count -gt 0) { throw ($errors | Out-String) }
```

Expected: no parser errors.

- [ ] **Step 3: Verify invalid clipboard handling**

Run:

```powershell
Set-Clipboard 'not a url'
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\windows-yt.ps1
if ($LASTEXITCODE -eq 0) { throw 'windows-yt.ps1 unexpectedly succeeded with invalid clipboard content.' }
```

Expected:

- command exits non-zero;
- output includes `yt: clipboard does not contain a valid URL: not a url`.

- [ ] **Step 4: Verify command construction without downloading**

Run:

```powershell
$fakeBin = Join-Path $env:TEMP "windows-yt-fake-bin-$PID"
New-Item -ItemType Directory -Path $fakeBin -Force | Out-Null
$fakeYtDlp = Join-Path $fakeBin 'yt-dlp.cmd'
@'
@echo off
echo %*
exit /b 0
'@ | Set-Content -LiteralPath $fakeYtDlp -Encoding ASCII

$oldPath = $env:PATH
try {
  $env:PATH = "$fakeBin;$oldPath"
  Set-Clipboard 'https://example.com/video'
  powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\windows-yt.ps1
  if ($LASTEXITCODE -ne 0) { throw "windows-yt.ps1 failed with exit code $LASTEXITCODE" }
} finally {
  $env:PATH = $oldPath
  Remove-Item -LiteralPath $fakeBin -Recurse -Force -ErrorAction SilentlyContinue
}
```

Expected output includes:

```text
--config-locations
yt-dlp\config
--output
Videos\%(title)s.%(ext)s
https://example.com/video
```

- [ ] **Step 5: Commit**

Run:

```bash
git add scripts/windows-yt.ps1
git commit -m "scripts: add windows yt command"
```

## Task 3: Add Windows yt Setup Script

**Files:**
- Create: `scripts/windows-yt-setup.ps1`

- [ ] **Step 1: Create `scripts/windows-yt-setup.ps1`**

Add this script:

```powershell
[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

. (Join-Path $PSScriptRoot 'windows-lib.ps1')
Assert-Windows

$appData = [Environment]::GetEnvironmentVariable('APPDATA')
if ([string]::IsNullOrWhiteSpace($appData)) {
  throw 'APPDATA is not set.'
}

$localAppData = [Environment]::GetEnvironmentVariable('LOCALAPPDATA')
if ([string]::IsNullOrWhiteSpace($localAppData)) {
  throw 'LOCALAPPDATA is not set.'
}

$configDirectory = Join-Path $appData 'yt-dlp'
$configPath = Join-Path $configDirectory 'config'
$wingetLinksDirectory = Join-Path $localAppData 'Microsoft\WinGet\Links'
$shimPath = Join-Path $wingetLinksDirectory 'yt.cmd'
$ytScriptPath = Join-Path $PSScriptRoot 'windows-yt.ps1'

function Set-ContentIfChanged {
  param(
    [Parameter(Mandatory = $true)]
    [string]$Path,

    [Parameter(Mandatory = $true)]
    [string]$Content,

    [Parameter(Mandatory = $true)]
    [string]$Description
  )

  $parent = Split-Path -Parent $Path
  if (-not [string]::IsNullOrWhiteSpace($parent)) {
    New-Item -ItemType Directory -Path $parent -Force | Out-Null
  }

  if (Test-Path -LiteralPath $Path -PathType Leaf) {
    $existing = Get-Content -LiteralPath $Path -Raw
    if ($existing -eq $Content) {
      Write-Host "$Description is already current."
      return
    }
  }

  Set-Content -LiteralPath $Path -Value $Content -Encoding ASCII -NoNewline
  Write-Host "Wrote $Description to $Path"
}

if (-not (Test-Path -LiteralPath $ytScriptPath -PathType Leaf)) {
  throw "Windows yt script not found: $ytScriptPath"
}

$ytDlpConfigLines = @(
  '--cookies-from-browser brave'
  '--format bv*[height<=1080]+ba/b[height<=1080]/b'
)
$ytDlpConfig = ($ytDlpConfigLines -join "`r`n") + "`r`n"

$shimLines = @(
  '@echo off'
  "powershell.exe -NoProfile -ExecutionPolicy Bypass -File ""$ytScriptPath"" %*"
  'exit /b %ERRORLEVEL%'
)
$shimContent = ($shimLines -join "`r`n") + "`r`n"

Set-ContentIfChanged -Path $configPath -Content $ytDlpConfig -Description 'yt-dlp config'
Set-ContentIfChanged -Path $shimPath -Content $shimContent -Description 'yt command shim'

$pathEntries = @([Environment]::GetEnvironmentVariable('PATH', 'User') -split ';') +
  @([Environment]::GetEnvironmentVariable('PATH', 'Machine') -split ';') +
  @($env:PATH -split ';')

$linksInPath = $false
foreach ($entry in $pathEntries) {
  if ([string]::IsNullOrWhiteSpace($entry)) {
    continue
  }

  try {
    $normalizedEntry = [IO.Path]::GetFullPath($entry).TrimEnd([IO.Path]::DirectorySeparatorChar, [IO.Path]::AltDirectorySeparatorChar)
    $normalizedLinks = [IO.Path]::GetFullPath($wingetLinksDirectory).TrimEnd([IO.Path]::DirectorySeparatorChar, [IO.Path]::AltDirectorySeparatorChar)
    if ($normalizedEntry.Equals($normalizedLinks, [StringComparison]::OrdinalIgnoreCase)) {
      $linksInPath = $true
      break
    }
  } catch {
    continue
  }
}

if (-not $linksInPath) {
  Write-Warning "$wingetLinksDirectory is not currently in PATH. The yt shim was written, but a new terminal or PATH repair may be needed before 'yt' resolves."
}
```

- [ ] **Step 2: Run setup script parser check**

Run:

```powershell
$tokens = $null
$errors = $null
$null = [System.Management.Automation.Language.Parser]::ParseFile((Resolve-Path .\scripts\windows-yt-setup.ps1).ProviderPath, [ref]$tokens, [ref]$errors)
if ($errors -and $errors.Count -gt 0) { throw ($errors | Out-String) }
```

Expected: no parser errors.

- [ ] **Step 3: Verify setup writes config and shim**

Run:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\windows-yt-setup.ps1
$config = Join-Path $env:APPDATA 'yt-dlp\config'
$shim = Join-Path $env:LOCALAPPDATA 'Microsoft\WinGet\Links\yt.cmd'
if (-not (Test-Path -LiteralPath $config -PathType Leaf)) { throw "Missing $config" }
if (-not (Test-Path -LiteralPath $shim -PathType Leaf)) { throw "Missing $shim" }
Get-Content -LiteralPath $config
Get-Content -LiteralPath $shim
```

Expected:

- config contains `--cookies-from-browser brave`;
- config contains `--format bv*[height<=1080]+ba/b[height<=1080]/b`;
- shim calls `powershell.exe -NoProfile -ExecutionPolicy Bypass -File`.

- [ ] **Step 4: Verify idempotency**

Run:

```powershell
$config = Join-Path $env:APPDATA 'yt-dlp\config'
$shim = Join-Path $env:LOCALAPPDATA 'Microsoft\WinGet\Links\yt.cmd'
$before = @{
  Config = (Get-Item -LiteralPath $config).LastWriteTimeUtc
  Shim = (Get-Item -LiteralPath $shim).LastWriteTimeUtc
}
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\windows-yt-setup.ps1
$after = @{
  Config = (Get-Item -LiteralPath $config).LastWriteTimeUtc
  Shim = (Get-Item -LiteralPath $shim).LastWriteTimeUtc
}
if ($before.Config -ne $after.Config) { throw 'yt-dlp config was rewritten on idempotent run.' }
if ($before.Shim -ne $after.Shim) { throw 'yt shim was rewritten on idempotent run.' }
```

Expected: no exception.

- [ ] **Step 5: Commit**

Run:

```bash
git add scripts/windows-yt-setup.ps1
git commit -m "scripts: add windows yt setup"
```

## Task 4: Wire yt Into Windows Setup And Documentation

**Files:**
- Modify: `scripts/windows-setup.ps1`
- Modify: `README.md`

- [ ] **Step 1: Add `Yt` to setup selection**

In `scripts/windows-setup.ps1`, update:

```powershell
[ValidateSet('All', 'Wsl', 'Apps', 'Fonts', 'Cursors', 'VoiceTyping')]
```

to:

```powershell
[ValidateSet('All', 'Wsl', 'Apps', 'Yt', 'Fonts', 'Cursors', 'VoiceTyping')]
```

- [ ] **Step 2: Add setup invocation after apps**

After the existing `Apps` block, add:

```powershell
if (Test-Selected -Name 'Yt') {
  Invoke-WindowsSetupStep -Name 'yt' -ScriptName 'windows-yt-setup.ps1'
}
```

Do not pass `-SkipInstall` to this setup step. It writes configuration and shim files and does not install packages.

- [ ] **Step 3: Update README Windows setup section**

In `README.md`, replace:

```text
The setup scripts are idempotent and safe to rerun. Use `-Only Apps`, `-Only Fonts`, `-Only Cursors`, `-Only Wsl`, or `-Only VoiceTyping` to run one area. Use `-SkipInstall` to report missing install targets without acquiring or installing packages, fonts, or cursors; configuration sync steps such as Handy custom words may still run.
```

with:

```text
The setup scripts are idempotent and safe to rerun. Use `-Only Apps`, `-Only Yt`, `-Only Fonts`, `-Only Cursors`, `-Only Wsl`, or `-Only VoiceTyping` to run one area. Use `-SkipInstall` to report missing install targets without acquiring or installing packages, fonts, or cursors; configuration sync steps such as the `yt` shim/config and Handy custom words may still run.
```

Then add this paragraph immediately after it:

```markdown
The Windows `yt` helper is installed as `%LOCALAPPDATA%\Microsoft\WinGet\Links\yt.cmd`. It reads a URL from the Windows clipboard, clears the clipboard, and downloads with `yt-dlp` into `%USERPROFILE%\Videos`. Windows setup installs `yt-dlp.yt-dlp.nightly` through winget.
```

- [ ] **Step 4: Run parser checks for all Windows scripts**

Run:

```powershell
$files = Get-ChildItem -LiteralPath .\scripts -Filter 'windows-*.ps1'
foreach ($file in $files) {
  $tokens = $null
  $errors = $null
  $null = [System.Management.Automation.Language.Parser]::ParseFile($file.FullName, [ref]$tokens, [ref]$errors)
  if ($errors -and $errors.Count -gt 0) {
    throw "Parser errors in $($file.Name): $($errors | Out-String)"
  }
}
```

Expected: no parser errors.

- [ ] **Step 5: Verify setup `-Only Yt` idempotency**

Run:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\windows-setup.ps1 -Only Yt
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\windows-setup.ps1 -Only Yt
```

Expected:

- first run writes missing config or shim if needed;
- second run reports both are already current;
- both runs exit 0.

- [ ] **Step 6: Verify complete setup skip-install path**

Run:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\windows-setup.ps1 -Only Apps,Yt -SkipInstall
```

Expected:

- apps step reports `yt-dlp-nightly` under the nightly package id;
- yt step writes or confirms the config and shim;
- command exits 0.

- [ ] **Step 7: Run whitespace diff check**

Run:

```bash
git diff --check
```

Expected: no output.

- [ ] **Step 8: Commit**

Run:

```bash
git add scripts/windows-setup.ps1 README.md
git commit -m "scripts: wire windows yt setup"
```

## Final Verification

Run these commands after all tasks are complete:

```powershell
$files = Get-ChildItem -LiteralPath .\scripts -Filter 'windows-*.ps1'
foreach ($file in $files) {
  $tokens = $null
  $errors = $null
  $null = [System.Management.Automation.Language.Parser]::ParseFile($file.FullName, [ref]$tokens, [ref]$errors)
  if ($errors -and $errors.Count -gt 0) {
    throw "Parser errors in $($file.Name): $($errors | Out-String)"
  }
}
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\windows-setup.ps1 -Only Apps,Yt -SkipInstall
Set-Clipboard 'not a url'
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\windows-yt.ps1
if ($LASTEXITCODE -eq 0) { throw 'windows-yt.ps1 unexpectedly succeeded with invalid clipboard content.' }
```

```bash
git diff --check
git status --short
```

Expected:

- parser checks pass;
- `Apps,Yt -SkipInstall` exits 0 and mentions `yt-dlp-nightly`;
- invalid clipboard test exits non-zero with the `yt:` validation message;
- `git diff --check` exits 0;
- `git status --short` is clean after commits.
