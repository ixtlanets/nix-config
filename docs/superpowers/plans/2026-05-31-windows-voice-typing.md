# Windows Voice Typing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an idempotent Windows-native PowerShell setup entrypoint that installs Handy when needed and syncs Handy custom words from `dotfiles/voice-typing/words.json`.

**Architecture:** `scripts/windows-setup.ps1` is a thin orchestrator. `scripts/windows-voice-typing.ps1` owns Handy-specific installation detection, `winget` install, shared word validation, JSON settings update, backups, and idempotency. Tests use PowerShell parser checks plus temp-file integration runs so behavior can be verified before touching real Handy settings.

**Tech Stack:** PowerShell 5+/7, Windows `winget`, JSON via `ConvertFrom-Json`/`ConvertTo-Json`, repository data from `dotfiles/voice-typing/words.json`.

---

## File Structure

- Create `scripts/windows-voice-typing.ps1`: Handy setup and custom words synchronization.
- Create `scripts/windows-setup.ps1`: Windows host setup entrypoint that calls specialized setup scripts.
- No changes to `dotfiles/voice-typing/words.json`; it remains the shared source of truth.
- No changes to Nix modules; this path is Windows-native.

## Task 1: Add Handy Voice Typing Script

**Files:**
- Create: `scripts/windows-voice-typing.ps1`

- [ ] **Step 1: Verify the script does not exist yet**

Run:

```powershell
Test-Path .\scripts\windows-voice-typing.ps1
```

Expected: `False`

- [ ] **Step 2: Create `scripts/windows-voice-typing.ps1`**

Write this file:

```powershell
[CmdletBinding()]
param(
    [switch]$SkipInstall,
    [switch]$Force,
    [string]$RepositoryRoot,
    [string]$SettingsStorePath
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Assert-Windows {
    if ([System.Environment]::OSVersion.Platform -ne [System.PlatformID]::Win32NT) {
        throw 'This script must be run on Windows.'
    }
}

function Get-RepositoryRoot {
    param([string]$ExplicitRoot)

    if ($ExplicitRoot) {
        return (Resolve-Path -LiteralPath $ExplicitRoot).Path
    }

    return (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
}

function Test-HandyInstalled {
    $winget = Get-Command winget -ErrorAction SilentlyContinue
    if ($winget) {
        $listOutput = & winget list --id cjpais.Handy --exact 2>$null
        if ($LASTEXITCODE -eq 0 -and ($listOutput -match 'cjpais\.Handy')) {
            return $true
        }
    }

    $localHandy = Join-Path $env:LOCALAPPDATA 'Handy\handy.exe'
    return Test-Path -LiteralPath $localHandy
}

function Install-HandyIfNeeded {
    param([bool]$Skip)

    if (Test-HandyInstalled) {
        Write-Host 'Handy is already installed.'
        return
    }

    if ($Skip) {
        Write-Host 'Handy is not installed; skipping install because -SkipInstall was provided.'
        return
    }

    if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
        throw 'winget is required to install Handy, but winget was not found.'
    }

    Write-Host 'Installing Handy via winget package cjpais.Handy.'
    & winget install --id cjpais.Handy --exact --source winget --accept-package-agreements --accept-source-agreements
    if ($LASTEXITCODE -ne 0) {
        throw "winget failed to install Handy with exit code $LASTEXITCODE."
    }
}

function Get-HandySettingsPath {
    param([string]$ExplicitPath)

    if ($ExplicitPath) {
        return $ExplicitPath
    }

    if (-not $env:APPDATA) {
        throw 'APPDATA is not set.'
    }

    return (Join-Path $env:APPDATA 'com.pais.handy\settings_store.json')
}

function Read-VoiceTypingWords {
    param([string]$Root)

    $wordsPath = Join-Path $Root 'dotfiles\voice-typing\words.json'
    if (-not (Test-Path -LiteralPath $wordsPath)) {
        throw "Voice typing words file not found: $wordsPath"
    }

    try {
        $words = Get-Content -Raw -LiteralPath $wordsPath | ConvertFrom-Json
    } catch {
        throw "Voice typing words file is not valid JSON: $wordsPath"
    }

    if (-not $words.handyCustomWords) {
        throw 'words.json is missing handyCustomWords.'
    }
    if (-not $words.voxtypeReplacements) {
        throw 'words.json is missing voxtypeReplacements.'
    }

    $customWords = @($words.handyCustomWords)
    $replacementValues = @($words.voxtypeReplacements.PSObject.Properties | ForEach-Object { [string]$_.Value } | Select-Object -Unique)
    $missing = @($replacementValues | Where-Object { $customWords -notcontains $_ })
    if ($missing.Count -gt 0) {
        throw "handyCustomWords is missing values from voxtypeReplacements: $($missing -join ', ')"
    }

    return $customWords
}

function Read-HandySettings {
    param([string]$Path)

    if (-not (Test-Path -LiteralPath $Path)) {
        return [pscustomobject]@{ settings = [pscustomobject]@{} }
    }

    try {
        $settings = Get-Content -Raw -LiteralPath $Path | ConvertFrom-Json
    } catch {
        throw "Handy settings file is not valid JSON: $Path"
    }

    if (-not ($settings.PSObject.Properties.Name -contains 'settings') -or $null -eq $settings.settings) {
        Add-Member -InputObject $settings -MemberType NoteProperty -Name settings -Value ([pscustomobject]@{})
    }

    return $settings
}

function Test-StringArrayEqual {
    param(
        [object[]]$Actual,
        [object[]]$Expected
    )

    $actualStrings = @($Actual | ForEach-Object { [string]$_ })
    $expectedStrings = @($Expected | ForEach-Object { [string]$_ })
    if ($actualStrings.Count -ne $expectedStrings.Count) {
        return $false
    }

    for ($i = 0; $i -lt $expectedStrings.Count; $i++) {
        if ($actualStrings[$i] -ne $expectedStrings[$i]) {
            return $false
        }
    }

    return $true
}

function Set-HandyCustomWords {
    param(
        [string]$Path,
        [string[]]$CustomWords,
        [bool]$AllowRunning
    )

    $currentProcess = Get-Process handy -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($currentProcess -and -not $AllowRunning) {
        Write-Host 'Handy is running. Close Handy and rerun, or use -Force.'
        return
    }

    $settings = Read-HandySettings -Path $Path
    $currentWords = @()
    if ($settings.settings.PSObject.Properties.Name -contains 'custom_words') {
        $currentWords = @($settings.settings.custom_words)
    }

    if (Test-StringArrayEqual -Actual $currentWords -Expected $CustomWords) {
        Write-Host "Handy custom words already up to date in $Path"
        return
    }

    $settingsDir = Split-Path -Parent $Path
    if (-not (Test-Path -LiteralPath $settingsDir)) {
        New-Item -ItemType Directory -Path $settingsDir | Out-Null
    }

    if (Test-Path -LiteralPath $Path) {
        $timestamp = Get-Date -Format 'yyyyMMdd-HHmmss'
        $backupPath = "$Path.backup-$timestamp"
        Copy-Item -LiteralPath $Path -Destination $backupPath
        Write-Host "Backup written to $backupPath"
    }

    if ($settings.settings.PSObject.Properties.Name -contains 'custom_words') {
        $settings.settings.custom_words = $CustomWords
    } else {
        Add-Member -InputObject $settings.settings -MemberType NoteProperty -Name custom_words -Value $CustomWords
    }

    $json = $settings | ConvertTo-Json -Depth 100
    Set-Content -LiteralPath $Path -Value $json -Encoding UTF8
    Write-Host "Updated Handy custom words in $Path"
}

Assert-Windows
$root = Get-RepositoryRoot -ExplicitRoot $RepositoryRoot
Install-HandyIfNeeded -Skip $SkipInstall.IsPresent
$targetSettingsPath = Get-HandySettingsPath -ExplicitPath $SettingsStorePath
$desiredWords = Read-VoiceTypingWords -Root $root
Set-HandyCustomWords -Path $targetSettingsPath -CustomWords $desiredWords -AllowRunning $Force.IsPresent
```

- [ ] **Step 3: Run parser validation**

Run:

```powershell
$tokens = $null
$errors = $null
[System.Management.Automation.Language.Parser]::ParseFile(
  (Resolve-Path .\scripts\windows-voice-typing.ps1),
  [ref]$tokens,
  [ref]$errors
) | Out-Null
$errors
if ($errors.Count -ne 0) { exit 1 }
```

Expected: no output and exit code `0`.

- [ ] **Step 4: Run temp settings integration check**

Run:

```powershell
$tempRoot = Join-Path $env:TEMP "handy-settings-test-$PID"
New-Item -ItemType Directory -Path $tempRoot | Out-Null
$settingsPath = Join-Path $tempRoot 'settings_store.json'
'{"settings":{"custom_words":["old"],"paste_delay_ms":60}}' | Set-Content -LiteralPath $settingsPath -Encoding UTF8
.\scripts\windows-voice-typing.ps1 -SkipInstall -Force -SettingsStorePath $settingsPath
$settings = Get-Content -Raw -LiteralPath $settingsPath | ConvertFrom-Json
$words = Get-Content -Raw .\dotfiles\voice-typing\words.json | ConvertFrom-Json
if (($settings.settings.custom_words | ConvertTo-Json -Compress) -ne ($words.handyCustomWords | ConvertTo-Json -Compress)) { exit 1 }
if ($settings.settings.paste_delay_ms -ne 60) { exit 1 }
if (-not (Get-ChildItem -LiteralPath $tempRoot -Filter 'settings_store.json.backup-*')) { exit 1 }
```

Expected: script reports backup and update, exit code `0`.

- [ ] **Step 5: Run idempotency check**

Run:

```powershell
$before = (Get-Item -LiteralPath $settingsPath).LastWriteTimeUtc
$backupCountBefore = @(Get-ChildItem -LiteralPath $tempRoot -Filter 'settings_store.json.backup-*').Count
Start-Sleep -Milliseconds 1200
.\scripts\windows-voice-typing.ps1 -SkipInstall -Force -SettingsStorePath $settingsPath
$after = (Get-Item -LiteralPath $settingsPath).LastWriteTimeUtc
$backupCountAfter = @(Get-ChildItem -LiteralPath $tempRoot -Filter 'settings_store.json.backup-*').Count
if ($after -ne $before) { exit 1 }
if ($backupCountAfter -ne $backupCountBefore) { exit 1 }
```

Expected: script reports words already up to date, no new backup, exit code `0`.

- [ ] **Step 6: Commit Handy script**

Run:

```bash
git add scripts/windows-voice-typing.ps1
git commit -m "scripts: add windows Handy voice typing setup"
```

Expected: commit succeeds.

## Task 2: Add Windows Setup Orchestrator

**Files:**
- Create: `scripts/windows-setup.ps1`
- Modify: `scripts/windows-voice-typing.ps1` only if Task 1 exposed a parameter mismatch.

- [ ] **Step 1: Verify the orchestrator does not exist yet**

Run:

```powershell
Test-Path .\scripts\windows-setup.ps1
```

Expected: `False`

- [ ] **Step 2: Create `scripts/windows-setup.ps1`**

Write this file:

```powershell
[CmdletBinding()]
param(
    [switch]$SkipInstall,
    [switch]$Force
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Assert-Windows {
    if ([System.Environment]::OSVersion.Platform -ne [System.PlatformID]::Win32NT) {
        throw 'This script must be run on Windows.'
    }
}

Assert-Windows

$repositoryRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$voiceTypingScript = Join-Path $PSScriptRoot 'windows-voice-typing.ps1'

if (-not (Test-Path -LiteralPath $voiceTypingScript)) {
    throw "Windows voice typing setup script not found: $voiceTypingScript"
}

Write-Host 'Running Windows voice typing setup.'
& $voiceTypingScript -RepositoryRoot $repositoryRoot -SkipInstall:$SkipInstall -Force:$Force

Write-Host 'Windows setup complete.'
```

- [ ] **Step 3: Run parser validation**

Run:

```powershell
foreach ($script in '.\scripts\windows-setup.ps1', '.\scripts\windows-voice-typing.ps1') {
  $tokens = $null
  $errors = $null
  [System.Management.Automation.Language.Parser]::ParseFile(
    (Resolve-Path $script),
    [ref]$tokens,
    [ref]$errors
  ) | Out-Null
  if ($errors.Count -ne 0) {
    $errors
    exit 1
  }
}
```

Expected: no output and exit code `0`.

- [ ] **Step 4: Run orchestrator through temp settings path manually**

Because `windows-setup.ps1` intentionally exposes only the public flags, run the Handy script directly for temp-file behavior and use the orchestrator for real path behavior in Task 3.

Run:

```powershell
.\scripts\windows-voice-typing.ps1 -SkipInstall -Force -SettingsStorePath $settingsPath
```

Expected: words already up to date, no new backup.

- [ ] **Step 5: Commit orchestrator**

Run:

```bash
git add scripts/windows-setup.ps1
git commit -m "scripts: add windows setup entrypoint"
```

Expected: commit succeeds.

## Task 3: Validate Against Real Windows Handy State

**Files:**
- No new files.
- May modify: `scripts/windows-voice-typing.ps1` or `scripts/windows-setup.ps1` only if validation exposes a bug.

- [ ] **Step 1: Check Handy process state**

Run:

```powershell
Get-Process handy -ErrorAction SilentlyContinue | Select-Object ProcessName,Id,Path
```

Expected: either no output, or a Handy process that should be closed before the non-Force real run.

- [ ] **Step 2: Run setup with installation skipped first**

Run:

```powershell
.\scripts\windows-setup.ps1 -SkipInstall
```

Expected:

- If Handy is closed and current custom words differ: backup is created and settings are updated.
- If Handy is closed and custom words already match: reports already up to date and creates no backup.
- If Handy is running: reports that Handy is running and skips the settings write.

- [ ] **Step 3: Verify real settings content**

Run:

```powershell
$settingsPath = Join-Path $env:APPDATA 'com.pais.handy\settings_store.json'
$settings = Get-Content -Raw -LiteralPath $settingsPath | ConvertFrom-Json
$words = Get-Content -Raw .\dotfiles\voice-typing\words.json | ConvertFrom-Json
if (($settings.settings.custom_words | ConvertTo-Json -Compress) -ne ($words.handyCustomWords | ConvertTo-Json -Compress)) { exit 1 }
```

Expected: exit code `0` when Handy was closed or when `-Force` was used.

- [ ] **Step 4: Verify real idempotency**

Run:

```powershell
$settingsPath = Join-Path $env:APPDATA 'com.pais.handy\settings_store.json'
$before = (Get-Item -LiteralPath $settingsPath).LastWriteTimeUtc
$backupCountBefore = @(Get-ChildItem -LiteralPath (Split-Path -Parent $settingsPath) -Filter 'settings_store.json.backup-*').Count
Start-Sleep -Milliseconds 1200
.\scripts\windows-setup.ps1 -SkipInstall -Force
$after = (Get-Item -LiteralPath $settingsPath).LastWriteTimeUtc
$backupCountAfter = @(Get-ChildItem -LiteralPath (Split-Path -Parent $settingsPath) -Filter 'settings_store.json.backup-*').Count
if ($after -ne $before) { exit 1 }
if ($backupCountAfter -ne $backupCountBefore) { exit 1 }
```

Expected: exit code `0`; no extra backup.

- [ ] **Step 5: Run default setup path**

Run:

```powershell
.\scripts\windows-setup.ps1 -Force
```

Expected: Handy is detected as already installed, no reinstall or upgrade happens, and settings remain up to date.

- [ ] **Step 6: Commit validation fixes if any**

If any script changes were needed during real validation, run:

```bash
git add scripts/windows-setup.ps1 scripts/windows-voice-typing.ps1
git commit -m "scripts: harden windows voice typing setup"
```

Expected: commit succeeds only if files changed. If no files changed, skip this step.

## Task 4: Final Verification

**Files:**
- No new files.

- [ ] **Step 1: Run parser validation one final time**

Run:

```powershell
foreach ($script in '.\scripts\windows-setup.ps1', '.\scripts\windows-voice-typing.ps1') {
  $tokens = $null
  $errors = $null
  [System.Management.Automation.Language.Parser]::ParseFile(
    (Resolve-Path $script),
    [ref]$tokens,
    [ref]$errors
  ) | Out-Null
  if ($errors.Count -ne 0) {
    $errors
    exit 1
  }
}
```

Expected: no output and exit code `0`.

- [ ] **Step 2: Inspect git history and working tree**

Run:

```bash
git log --oneline -5
git status --short
```

Expected: recent commits include the Windows setup script commits, and `git status --short` is empty.

- [ ] **Step 3: Record validation in the final response**

Report:

- Parser validation result.
- Temp settings integration result.
- Real Handy settings result.
- Whether Handy was running during real validation.
- Commit hashes created during implementation.
