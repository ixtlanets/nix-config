# Windows Base Setup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend the Windows-native setup entrypoint so it can idempotently bootstrap WSL, install core applications, install user fonts, activate Bibata cursors, and keep the existing Handy sync working.

**Architecture:** Add focused PowerShell scripts under `scripts/` and keep `windows-setup.ps1` as a thin orchestrator. Put shared Windows helpers in `scripts/windows-lib.ps1` to avoid duplicating elevation, parser-safe path handling, `winget` detection, and idempotent download helpers. Use user-level font and cursor installs where possible; reserve elevation through Windows `sudo` for WSL and package installers that require admin.

**Tech Stack:** PowerShell 5+/7, Windows `sudo`, `winget`, WSL CLI, Windows registry HKCU, GitHub release/download APIs, existing repo data and scripts.

---

## File Structure

- Create `scripts/windows-lib.ps1`: shared helpers for Windows checks, admin detection, sudo relaunch, winget detection/install, downloads, archive extraction, and parser-safe array handling.
- Create `scripts/windows-wsl.ps1`: WSL and Ubuntu bootstrap through `wsl --install -d Ubuntu --no-launch`.
- Create `scripts/windows-apps.ps1`: idempotent app install through `winget`.
- Create `scripts/windows-fonts.ps1`: user-level font installation into `%LOCALAPPDATA%\Microsoft\Windows\Fonts` and HKCU font registry.
- Create `scripts/windows-cursors.ps1`: user-level Bibata cursor install and HKCU cursor scheme activation.
- Modify `scripts/windows-setup.ps1`: add `-Only` dispatch and call the new focused scripts plus existing voice typing.
- Modify `README.md`: add Windows setup and Sudo for Windows instructions.

## Task 1: Shared Windows Setup Helpers

**Files:**
- Create: `scripts/windows-lib.ps1`

- [ ] **Step 1: Verify helper file is new**

Run:

```powershell
Test-Path .\scripts\windows-lib.ps1
```

Expected: `False`.

- [ ] **Step 2: Create `scripts/windows-lib.ps1`**

Write a helper-only script with these functions:

```powershell
Set-StrictMode -Version Latest

function Assert-Windows {
  if ([System.Environment]::OSVersion.Platform -ne [System.PlatformID]::Win32NT) {
    throw 'This script must be run on Windows.'
  }
}

function Test-Administrator {
  $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
  $principal = [Security.Principal.WindowsPrincipal]::new($identity)
  return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Get-RepositoryRootFromScript {
  param([Parameter(Mandatory = $true)][string]$ScriptRoot)
  return (Resolve-Path -LiteralPath (Split-Path -Parent $ScriptRoot)).ProviderPath
}

function Get-RequiredCommand {
  param([Parameter(Mandatory = $true)][string]$Name)
  $command = Get-Command $Name -ErrorAction SilentlyContinue
  if ($null -eq $command) {
    throw "$Name is required but was not found in PATH."
  }
  return $command
}

function Invoke-WithSudoIfNeeded {
  param(
    [Parameter(Mandatory = $true)][string]$ScriptPath,
    [string[]]$ArgumentList = @(),
    [switch]$RequiresAdmin
  )

  Assert-Windows
  if (-not $RequiresAdmin -or (Test-Administrator)) {
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $ScriptPath @ArgumentList
    if ($LASTEXITCODE -ne 0) {
      throw "$ScriptPath failed with exit code $LASTEXITCODE."
    }
    return
  }

  $sudo = Get-Command sudo -ErrorAction SilentlyContinue
  if ($null -eq $sudo) {
    throw 'This setup step requires administrator rights. Enable Sudo for Windows as described in README.md, then rerun setup.'
  }

  & $sudo.Source powershell.exe -NoProfile -ExecutionPolicy Bypass -File $ScriptPath @ArgumentList
  if ($LASTEXITCODE -ne 0) {
    throw "$ScriptPath failed through sudo with exit code $LASTEXITCODE."
  }
}

function Test-WingetPackageInstalled {
  param([Parameter(Mandatory = $true)][string]$Id)
  $winget = Get-Command winget -ErrorAction SilentlyContinue
  if ($null -eq $winget) {
    return $false
  }
  & $winget.Source list --id $Id --exact | Out-Null
  return ($LASTEXITCODE -eq 0)
}

function Install-WingetPackageIfMissing {
  param(
    [Parameter(Mandatory = $true)][string]$Id,
    [Parameter(Mandatory = $true)][string]$Name,
    [switch]$SkipInstall
  )

  if (Test-WingetPackageInstalled -Id $Id) {
    Write-Host "$Name is already installed. Skipping install."
    return
  }

  if ($SkipInstall) {
    Write-Host "$Name is missing. Skipping install because -SkipInstall was passed."
    return
  }

  $winget = Get-RequiredCommand -Name winget
  Write-Host "Installing $Name via winget package $Id."
  & $winget.Source install --id $Id --exact --source winget --accept-package-agreements --accept-source-agreements
  if ($LASTEXITCODE -ne 0) {
    throw "winget install for $Name ($Id) failed with exit code $LASTEXITCODE."
  }
}

function Get-WindowsSetupCacheDirectory {
  $localAppData = [Environment]::GetEnvironmentVariable('LOCALAPPDATA')
  if ([string]::IsNullOrWhiteSpace($localAppData)) {
    throw 'LOCALAPPDATA is not set.'
  }
  $cache = Join-Path $localAppData 'nix-config\downloads'
  New-Item -ItemType Directory -Path $cache -Force | Out-Null
  return $cache
}
```

- [ ] **Step 3: Run parser validation**

Run:

```powershell
$tokens = $null
$errors = $null
$content = Get-Content -Raw .\scripts\windows-lib.ps1
[System.Management.Automation.Language.Parser]::ParseInput($content, [ref]$tokens, [ref]$errors) | Out-Null
$errors
if ($errors.Count -ne 0) { exit 1 }
```

Expected: no parser errors.

- [ ] **Step 4: Commit helper**

Run:

```bash
git add scripts/windows-lib.ps1
git commit -m "scripts: add shared windows setup helpers"
```

Expected: commit succeeds.

## Task 2: WSL Bootstrap Script

**Files:**
- Create: `scripts/windows-wsl.ps1`
- May modify: `scripts/windows-lib.ps1` if a helper bug is found.

- [ ] **Step 1: Create `scripts/windows-wsl.ps1`**

Write a script that dot-sources `windows-lib.ps1`, accepts `[switch]$SkipInstall`, checks WSL/Ubuntu state, and only runs install when missing:

```powershell
[CmdletBinding()]
param([switch]$SkipInstall)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

. (Join-Path $PSScriptRoot 'windows-lib.ps1')
Assert-Windows

function Test-WslAvailable {
  $wsl = Get-Command wsl -ErrorAction SilentlyContinue
  if ($null -eq $wsl) { return $false }
  & $wsl.Source --status *> $null
  if ($LASTEXITCODE -eq 0) { return $true }
  & $wsl.Source --version *> $null
  return ($LASTEXITCODE -eq 0)
}

function Test-UbuntuDistribution {
  $wsl = Get-Command wsl -ErrorAction SilentlyContinue
  if ($null -eq $wsl) { return $false }
  $distros = @(& $wsl.Source --list --quiet 2>$null | ForEach-Object { $_.Trim() } | Where-Object { $_ })
  return ($distros -contains 'Ubuntu')
}

if ((Test-WslAvailable) -and (Test-UbuntuDistribution)) {
  Write-Host 'WSL and Ubuntu are already installed. Skipping install.'
  return
}

if ($SkipInstall) {
  Write-Host 'WSL or Ubuntu is missing. Skipping install because -SkipInstall was passed.'
  return
}

if (-not (Test-Administrator)) {
  throw 'WSL bootstrap requires administrator rights. Rerun through windows-setup.ps1 so it can elevate with sudo.'
}

$wsl = Get-RequiredCommand -Name wsl
Write-Host 'Installing WSL with Ubuntu. A reboot may be required after this completes.'
& $wsl.Source --install -d Ubuntu --no-launch
if ($LASTEXITCODE -ne 0) {
  throw "wsl --install -d Ubuntu --no-launch failed with exit code $LASTEXITCODE."
}
Write-Host 'WSL install command completed. Reboot if Windows reports that one is required.'
```

- [ ] **Step 2: Validate parser and current-host detection**

Run:

```powershell
foreach ($script in '.\scripts\windows-lib.ps1', '.\scripts\windows-wsl.ps1') {
  $tokens = $null
  $errors = $null
  [System.Management.Automation.Language.Parser]::ParseInput((Get-Content -Raw $script), [ref]$tokens, [ref]$errors) | Out-Null
  if ($errors.Count -ne 0) { $errors; exit 1 }
}
.\scripts\windows-wsl.ps1 -SkipInstall
```

Expected: parser passes. On the current host, WSL/Ubuntu should report already installed or missing-but-skipped; it must not run `wsl --install`.

- [ ] **Step 3: Commit WSL script**

Run:

```bash
git add scripts/windows-wsl.ps1 scripts/windows-lib.ps1
git commit -m "scripts: add windows WSL bootstrap"
```

Expected: commit succeeds.

## Task 3: Winget Apps Script

**Files:**
- Create: `scripts/windows-apps.ps1`
- May modify: `scripts/windows-lib.ps1` if package detection needs hardening.

- [ ] **Step 1: Create `scripts/windows-apps.ps1`**

Write a script that dot-sources `windows-lib.ps1`, accepts `[switch]$SkipInstall`, and installs this list through `Install-WingetPackageIfMissing`:

```powershell
[CmdletBinding()]
param([switch]$SkipInstall)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

. (Join-Path $PSScriptRoot 'windows-lib.ps1')
Assert-Windows

$packages = @(
  @{ Name = 'Brave'; Id = 'Brave.Brave' },
  @{ Name = 'Chrome'; Id = 'Google.Chrome' },
  @{ Name = 'VS Code'; Id = 'Microsoft.VisualStudioCode' },
  @{ Name = '1Password'; Id = 'AgileBits.1Password' },
  @{ Name = 'Telegram Desktop'; Id = 'Telegram.TelegramDesktop' },
  @{ Name = 'Docker Desktop'; Id = 'Docker.DockerDesktop' },
  @{ Name = 'Steam'; Id = 'Valve.Steam' },
  @{ Name = 'Throne'; Id = 'Throneproj.Throne' },
  @{ Name = 'LibreOffice'; Id = 'TheDocumentFoundation.LibreOffice' },
  @{ Name = 'PowerToys'; Id = 'Microsoft.PowerToys' },
  @{ Name = 'Tailscale'; Id = 'Tailscale.Tailscale' },
  @{ Name = 'yt-dlp'; Id = 'yt-dlp.yt-dlp' }
)

foreach ($package in $packages) {
  Install-WingetPackageIfMissing -Name $package.Name -Id $package.Id -SkipInstall:$SkipInstall
}
```

- [ ] **Step 2: Validate app reporting without installing**

Run:

```powershell
foreach ($script in '.\scripts\windows-lib.ps1', '.\scripts\windows-apps.ps1') {
  $tokens = $null
  $errors = $null
  [System.Management.Automation.Language.Parser]::ParseInput((Get-Content -Raw $script), [ref]$tokens, [ref]$errors) | Out-Null
  if ($errors.Count -ne 0) { $errors; exit 1 }
}
.\scripts\windows-apps.ps1 -SkipInstall
```

Expected: installed apps report already installed; missing apps report missing-but-skipped. It must not install anything with `-SkipInstall`.

- [ ] **Step 3: Commit apps script**

Run:

```bash
git add scripts/windows-apps.ps1 scripts/windows-lib.ps1
git commit -m "scripts: add windows app installer"
```

Expected: commit succeeds.

## Task 4: User Font Installer

**Files:**
- Create: `scripts/windows-fonts.ps1`
- May modify: `scripts/windows-lib.ps1` for download/archive helpers.

- [ ] **Step 1: Add download helpers if missing**

If Task 1 did not add download helpers, extend `scripts/windows-lib.ps1` with:

```powershell
function Save-UrlIfMissing {
  param(
    [Parameter(Mandatory = $true)][string]$Uri,
    [Parameter(Mandatory = $true)][string]$Destination
  )
  if (Test-Path -LiteralPath $Destination -PathType Leaf) {
    Write-Host "Using cached download $Destination"
    return
  }
  New-Item -ItemType Directory -Path (Split-Path -Parent $Destination) -Force | Out-Null
  Write-Host "Downloading $Uri"
  Invoke-WebRequest -Uri $Uri -OutFile $Destination
}

function Expand-ZipToDirectory {
  param(
    [Parameter(Mandatory = $true)][string]$ZipPath,
    [Parameter(Mandatory = $true)][string]$Destination
  )
  New-Item -ItemType Directory -Path $Destination -Force | Out-Null
  Expand-Archive -LiteralPath $ZipPath -DestinationPath $Destination -Force
}
```

- [ ] **Step 2: Create `scripts/windows-fonts.ps1`**

Implement user-level font install with parameters `[switch]$SkipInstall`, `[string]$FontRoot`, and `[string]$CacheRoot`. Use `%LOCALAPPDATA%\Microsoft\Windows\Fonts` and HKCU by default. Use versionless latest release URLs where practical:

```powershell
[CmdletBinding()]
param(
  [switch]$SkipInstall,
  [string]$FontRoot,
  [string]$CacheRoot
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

. (Join-Path $PSScriptRoot 'windows-lib.ps1')
Assert-Windows

if ($SkipInstall) {
  Write-Host 'Skipping font installation because -SkipInstall was passed.'
  return
}

if ([string]::IsNullOrWhiteSpace($FontRoot)) {
  $localAppData = [Environment]::GetEnvironmentVariable('LOCALAPPDATA')
  if ([string]::IsNullOrWhiteSpace($localAppData)) { throw 'LOCALAPPDATA is not set.' }
  $FontRoot = Join-Path $localAppData 'Microsoft\Windows\Fonts'
}
if ([string]::IsNullOrWhiteSpace($CacheRoot)) {
  $CacheRoot = Get-WindowsSetupCacheDirectory
}

New-Item -ItemType Directory -Path $FontRoot -Force | Out-Null
$fontRegistry = 'HKCU:\Software\Microsoft\Windows NT\CurrentVersion\Fonts'

function Install-FontFile {
  param(
    [Parameter(Mandatory = $true)][string]$SourcePath,
    [Parameter(Mandatory = $true)][string]$RegistryName
  )
  $target = Join-Path $FontRoot (Split-Path -Leaf $SourcePath)
  if (-not (Test-Path -LiteralPath $target -PathType Leaf)) {
    Copy-Item -LiteralPath $SourcePath -Destination $target
    Write-Host "Installed font file $target"
  }
  $current = (Get-ItemProperty -Path $fontRegistry -Name $RegistryName -ErrorAction SilentlyContinue).$RegistryName
  if ($current -ne $target) {
    New-ItemProperty -Path $fontRegistry -Name $RegistryName -Value $target -PropertyType String -Force | Out-Null
    Write-Host "Registered font $RegistryName"
  }
}
```

Then add concrete font source groups:

- Nerd Fonts latest release assets from `https://github.com/ryanoasis/nerd-fonts/releases/latest/download/`: `Hack.zip`, `Ubuntu.zip`, `UbuntuMono.zip`, `UbuntuSans.zip`, `SauceCodePro.zip`, `JetBrainsMono.zip`.
- Monaspace latest release from `https://github.com/githubnext/monaspace/releases/latest`.
- Font Awesome latest release from `https://github.com/FortAwesome/Font-Awesome/releases/latest`.
- Google Fonts raw TTFs for Roboto, Source Sans 3, Source Serif 4, Source Code Pro, and Fira Code. Use raw URLs under `https://github.com/google/fonts/raw/main/ofl/...` and keep the source paths in a manifest inside the script.
- Microsoft Cascadia Code latest release from `https://github.com/microsoft/cascadia-code/releases/latest`; select the TTF zip asset from the latest release metadata.

For Task 4, the complete implementation should install and register Hack Nerd Font, Ubuntu Nerd Font, Ubuntu Mono Nerd Font, Ubuntu Sans Nerd Font, SauceCodePro Nerd Font, JetBrainsMono Nerd Font, Monaspace, Font Awesome, Roboto, Source Sans 3, Source Serif 4, Source Code Pro, Fira Code, and Cascadia Code.

- [ ] **Step 3: Validate fonts in a temp font root**

Run:

```powershell
$tempFonts = Join-Path $env:TEMP "windows-fonts-test-$PID"
$tempCache = Join-Path $env:TEMP "windows-fonts-cache-$PID"
.\scripts\windows-fonts.ps1 -FontRoot $tempFonts -CacheRoot $tempCache
if (-not (Get-ChildItem -LiteralPath $tempFonts -Recurse -Include *.ttf,*.otf | Select-Object -First 1)) { exit 1 }
$beforeCount = @(Get-ChildItem -LiteralPath $tempFonts -Recurse -Include *.ttf,*.otf).Count
.\scripts\windows-fonts.ps1 -FontRoot $tempFonts -CacheRoot $tempCache
$afterCount = @(Get-ChildItem -LiteralPath $tempFonts -Recurse -Include *.ttf,*.otf).Count
if ($afterCount -ne $beforeCount) { exit 1 }
```

Expected: first run installs fonts into temp root; second run does not duplicate files.

- [ ] **Step 4: Commit fonts script**

Run:

```bash
git add scripts/windows-fonts.ps1 scripts/windows-lib.ps1
git commit -m "scripts: add windows font installer"
```

Expected: commit succeeds.

## Task 5: Bibata Cursor Installer

**Files:**
- Create: `scripts/windows-cursors.ps1`
- May modify: `scripts/windows-lib.ps1`.

- [ ] **Step 1: Create `scripts/windows-cursors.ps1`**

Implement user-level Bibata install with `[switch]$SkipInstall`, `[string]$CursorRoot`, and `[string]$CacheRoot`. Use a user-owned default root under `%LOCALAPPDATA%\Microsoft\Windows\Cursors\Bibata-Original-Ice`. Download Bibata from the upstream GitHub release source `ful1e5/Bibata_Cursor`.

Core behavior:

```powershell
[CmdletBinding()]
param(
  [switch]$SkipInstall,
  [string]$CursorRoot,
  [string]$CacheRoot
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

. (Join-Path $PSScriptRoot 'windows-lib.ps1')
Assert-Windows

if ($SkipInstall) {
  Write-Host 'Skipping cursor installation because -SkipInstall was passed.'
  return
}

if ([string]::IsNullOrWhiteSpace($CacheRoot)) { $CacheRoot = Get-WindowsSetupCacheDirectory }
if ([string]::IsNullOrWhiteSpace($CursorRoot)) {
  $localAppData = [Environment]::GetEnvironmentVariable('LOCALAPPDATA')
  if ([string]::IsNullOrWhiteSpace($localAppData)) { throw 'LOCALAPPDATA is not set.' }
  $CursorRoot = Join-Path $localAppData 'Microsoft\Windows\Cursors\Bibata-Original-Ice'
}

New-Item -ItemType Directory -Path $CursorRoot -Force | Out-Null
```

The implementation should locate a Windows-compatible Bibata archive from the latest GitHub release assets, extract it into the cursor root, then update `HKCU:\Control Panel\Cursors` only if values differ.

Cursor registry names to set:

```powershell
$cursorMap = @{
  Arrow       = 'arrow.cur'
  Help        = 'help.cur'
  AppStarting = 'working.ani'
  Wait        = 'busy.ani'
  Crosshair   = 'cross.cur'
  IBeam       = 'beam.cur'
  NWPen       = 'pen.cur'
  No          = 'unavailable.cur'
  SizeNS      = 'size_ns.cur'
  SizeWE      = 'size_we.cur'
  SizeNWSE    = 'size_nwse.cur'
  SizeNESW    = 'size_nesw.cur'
  SizeAll     = 'move.cur'
  UpArrow     = 'up.cur'
  Hand        = 'link.cur'
}
```

If the upstream filenames differ, add a normalization map in the script and document it in comments near the map. Refresh the cursor scheme only when at least one registry value changed.

- [ ] **Step 2: Validate cursor install in temp root without registry write**

Add a `-NoActivate` switch if needed for tests. Then run:

```powershell
$tempCursors = Join-Path $env:TEMP "windows-cursors-test-$PID"
$tempCache = Join-Path $env:TEMP "windows-cursors-cache-$PID"
.\scripts\windows-cursors.ps1 -CursorRoot $tempCursors -CacheRoot $tempCache -NoActivate
if (-not (Get-ChildItem -LiteralPath $tempCursors -Recurse -Include *.cur,*.ani | Select-Object -First 1)) { exit 1 }
$beforeCount = @(Get-ChildItem -LiteralPath $tempCursors -Recurse -Include *.cur,*.ani).Count
.\scripts\windows-cursors.ps1 -CursorRoot $tempCursors -CacheRoot $tempCache -NoActivate
$afterCount = @(Get-ChildItem -LiteralPath $tempCursors -Recurse -Include *.cur,*.ani).Count
if ($afterCount -ne $beforeCount) { exit 1 }
```

Expected: cursor files exist after first run; second run does not duplicate files.

- [ ] **Step 3: Commit cursor script**

Run:

```bash
git add scripts/windows-cursors.ps1 scripts/windows-lib.ps1
git commit -m "scripts: add windows cursor installer"
```

Expected: commit succeeds.

## Task 6: Orchestrator and README

**Files:**
- Modify: `scripts/windows-setup.ps1`
- Modify: `README.md`

- [ ] **Step 1: Update `scripts/windows-setup.ps1`**

Add parameter validation for `-Only` and call focused scripts in order:

```powershell
[CmdletBinding()]
param(
  [ValidateSet('All', 'Wsl', 'Apps', 'Fonts', 'Cursors', 'VoiceTyping')]
  [string[]]$Only = @('All'),
  [switch]$SkipInstall,
  [switch]$Force
)
```

Dot-source `windows-lib.ps1`, resolve `$repositoryRoot`, and dispatch:

```powershell
$runAll = $Only -contains 'All'

function Test-Selected {
  param([string]$Name)
  return $runAll -or ($Only -contains $Name)
}

if (Test-Selected -Name 'Wsl') {
  $args = @()
  if ($SkipInstall) { $args += '-SkipInstall' }
  Invoke-WithSudoIfNeeded -ScriptPath (Join-Path $PSScriptRoot 'windows-wsl.ps1') -ArgumentList $args -RequiresAdmin
}

if (Test-Selected -Name 'Apps') {
  $args = @()
  if ($SkipInstall) { $args += '-SkipInstall' }
  Invoke-WithSudoIfNeeded -ScriptPath (Join-Path $PSScriptRoot 'windows-apps.ps1') -ArgumentList $args
}

if (Test-Selected -Name 'Fonts') {
  $args = @()
  if ($SkipInstall) { $args += '-SkipInstall' }
  Invoke-WithSudoIfNeeded -ScriptPath (Join-Path $PSScriptRoot 'windows-fonts.ps1') -ArgumentList $args
}

if (Test-Selected -Name 'Cursors') {
  $args = @()
  if ($SkipInstall) { $args += '-SkipInstall' }
  Invoke-WithSudoIfNeeded -ScriptPath (Join-Path $PSScriptRoot 'windows-cursors.ps1') -ArgumentList $args
}

if (Test-Selected -Name 'VoiceTyping') {
  $args = @('-RepositoryRoot', $repositoryRoot)
  if ($SkipInstall) { $args += '-SkipInstall' }
  if ($Force) { $args += '-Force' }
  Invoke-WithSudoIfNeeded -ScriptPath (Join-Path $PSScriptRoot 'windows-voice-typing.ps1') -ArgumentList $args
}
```

Keep start and completion messages.

- [ ] **Step 2: Update README Windows section**

Add a Windows section that includes:

```markdown
### Windows Setup

Run from Windows PowerShell:

```powershell
cd \\wsl.localhost\Ubuntu\home\nik\nix-config
powershell.exe -ExecutionPolicy Bypass -File .\scripts\windows-setup.ps1
```

The setup scripts are idempotent and safe to rerun. Use `-Only Apps`, `-Only Fonts`, `-Only Cursors`, `-Only Wsl`, or `-Only VoiceTyping` to run one area.

Some steps need administrator rights. On Windows 11 24H2+, enable Sudo for Windows in Settings, then use the default `forceNewWindow` mode:

```powershell
sudo config --enable forceNewWindow
```

WSL setup uses:

```powershell
wsl --install -d Ubuntu --no-launch
```

It may require a reboot. The script reports this but does not reboot automatically.
```

- [ ] **Step 3: Validate dispatch without installs**

Run:

```powershell
foreach ($script in Get-ChildItem .\scripts\windows-*.ps1) {
  $tokens = $null
  $errors = $null
  [System.Management.Automation.Language.Parser]::ParseInput((Get-Content -Raw $script), [ref]$tokens, [ref]$errors) | Out-Null
  if ($errors.Count -ne 0) { $script.FullName; $errors; exit 1 }
}
.\scripts\windows-setup.ps1 -Only VoiceTyping -SkipInstall -Force
.\scripts\windows-setup.ps1 -Only Apps -SkipInstall
.\scripts\windows-setup.ps1 -Only Wsl -SkipInstall
```

Expected: parser passes; commands do not install packages; existing Handy behavior remains intact.

- [ ] **Step 4: Commit orchestrator and README**

Run:

```bash
git add scripts/windows-setup.ps1 README.md
git commit -m "scripts: orchestrate windows base setup"
```

Expected: commit succeeds.

## Task 7: Final Verification

**Files:**
- No new files unless a validation fix is required.

- [ ] **Step 1: Run parser validation for all Windows scripts**

Run:

```powershell
foreach ($script in Get-ChildItem .\scripts\windows-*.ps1) {
  $tokens = $null
  $errors = $null
  [System.Management.Automation.Language.Parser]::ParseInput((Get-Content -Raw $script), [ref]$tokens, [ref]$errors) | Out-Null
  if ($errors.Count -ne 0) { $script.FullName; $errors; exit 1 }
}
```

Expected: no parser errors.

- [ ] **Step 2: Run non-mutating checks**

Run:

```powershell
.\scripts\windows-apps.ps1 -SkipInstall
.\scripts\windows-wsl.ps1 -SkipInstall
.\scripts\windows-setup.ps1 -Only VoiceTyping -SkipInstall -Force
```

Expected: app and WSL scripts report current state without installing; voice typing remains idempotent.

- [ ] **Step 3: Run temp font and cursor checks**

Run the temp-root checks from Task 4 and Task 5 again.

Expected: files appear on first temp run and are not duplicated on second temp run.

- [ ] **Step 4: Check git state**

Run:

```bash
git diff --check HEAD~6..HEAD
git status --short
```

Expected: no whitespace errors and clean working tree.

- [ ] **Step 5: Record validation in final response**

Report:

- Parser validation result.
- Apps skip-install result.
- WSL skip-install result.
- Font temp install/idempotency result.
- Cursor temp install/idempotency result.
- VoiceTyping real idempotency result.
- Commit hashes created during implementation.
