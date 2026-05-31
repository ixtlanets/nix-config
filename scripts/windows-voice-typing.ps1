[CmdletBinding()]
param(
  [switch]$SkipInstall,
  [switch]$Force,
  [string]$RepositoryRoot,
  [string]$SettingsStorePath
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Test-HandyInstalled {
  $wingetCommand = Get-Command winget -ErrorAction SilentlyContinue
  if ($null -ne $wingetCommand) {
    & $wingetCommand.Source list --id cjpais.Handy --exact | Out-Null
    if ($LASTEXITCODE -eq 0) {
      return $true
    }
  }

  $localAppData = [System.Environment]::GetEnvironmentVariable('LOCALAPPDATA')
  if ([string]::IsNullOrWhiteSpace($localAppData)) {
    return $false
  }

  $handyExe = Join-Path $localAppData 'Handy\handy.exe'
  return (Test-Path -LiteralPath $handyExe -PathType Leaf)
}

function Assert-JsonProperty {
  param(
    [Parameter(Mandatory = $true)]$InputObject,
    [Parameter(Mandatory = $true)][string]$Name,
    [Parameter(Mandatory = $true)][string]$SourcePath
  )

  if ($null -eq $InputObject.PSObject.Properties[$Name]) {
    throw "$SourcePath must contain a '$Name' property."
  }
}

function ConvertTo-StringArray {
  param(
    [AllowNull()]$Value
  )

  if ($null -eq $Value) {
    return @()
  }

  if ($Value -is [System.Array]) {
    return @($Value | ForEach-Object { [string]$_ })
  }

  return @([string]$Value)
}

function Set-JsonProperty {
  param(
    [Parameter(Mandatory = $true)]$InputObject,
    [Parameter(Mandatory = $true)][string]$Name,
    [AllowNull()]$Value
  )

  if ($null -eq $InputObject.PSObject.Properties[$Name]) {
    Add-Member -InputObject $InputObject -MemberType NoteProperty -Name $Name -Value $Value
  } else {
    $InputObject.$Name = $Value
  }
}

if ([System.Environment]::OSVersion.Platform -ne [System.PlatformID]::Win32NT) {
  throw 'This script must be run on Windows.'
}

if ([string]::IsNullOrWhiteSpace($RepositoryRoot)) {
  $resolvedRepositoryRoot = Split-Path -Parent $PSScriptRoot
} else {
  $resolvedRepositoryRoot = $RepositoryRoot
}

$resolvedRepositoryRoot = (Resolve-Path -LiteralPath $resolvedRepositoryRoot).ProviderPath

if (Test-HandyInstalled) {
  Write-Host 'Handy is already installed. Skipping install.'
} elseif ($SkipInstall) {
  Write-Host 'Handy is not installed. Skipping install because -SkipInstall was passed.'
} else {
  $wingetCommand = Get-Command winget -ErrorAction SilentlyContinue
  if ($null -eq $wingetCommand) {
    throw 'winget is required to install Handy, but it was not found.'
  }

  & $wingetCommand.Source install --id cjpais.Handy --exact --source winget --accept-package-agreements --accept-source-agreements
  if ($LASTEXITCODE -ne 0) {
    throw "winget install for Handy failed with exit code $LASTEXITCODE."
  }
}

$wordsPath = Join-Path $resolvedRepositoryRoot 'dotfiles\voice-typing\words.json'
if (-not (Test-Path -LiteralPath $wordsPath -PathType Leaf)) {
  throw "Voice typing words file not found: $wordsPath"
}

try {
  $wordsConfig = Get-Content -LiteralPath $wordsPath -Raw -Encoding UTF8 | ConvertFrom-Json
} catch {
  throw "Invalid JSON in $wordsPath. $($_.Exception.Message)"
}

Assert-JsonProperty -InputObject $wordsConfig -Name 'handyCustomWords' -SourcePath $wordsPath
Assert-JsonProperty -InputObject $wordsConfig -Name 'voxtypeReplacements' -SourcePath $wordsPath

$desiredCustomWords = @(ConvertTo-StringArray -Value $wordsConfig.handyCustomWords)
$desiredWordSet = [System.Collections.Generic.HashSet[string]]::new([System.StringComparer]::Ordinal)
foreach ($word in $desiredCustomWords) {
  [void]$desiredWordSet.Add($word)
}

$seenReplacementValues = [System.Collections.Generic.HashSet[string]]::new([System.StringComparer]::Ordinal)
$missingReplacementValues = [System.Collections.Generic.List[string]]::new()
foreach ($property in $wordsConfig.voxtypeReplacements.PSObject.Properties) {
  $replacementValue = [string]$property.Value
  if ($seenReplacementValues.Add($replacementValue) -and -not $desiredWordSet.Contains($replacementValue)) {
    [void]$missingReplacementValues.Add($replacementValue)
  }
}

if ($missingReplacementValues.Count -gt 0) {
  throw "Every voxtypeReplacements value must be present in handyCustomWords. Missing: $($missingReplacementValues -join ', ')"
}

if ([string]::IsNullOrWhiteSpace($SettingsStorePath)) {
  $appData = [System.Environment]::GetEnvironmentVariable('APPDATA')
  if ([string]::IsNullOrWhiteSpace($appData)) {
    throw 'APPDATA is not set; pass -SettingsStorePath explicitly.'
  }

  $resolvedSettingsStorePath = Join-Path $appData 'com.pais.handy\settings_store.json'
} else {
  $resolvedSettingsStorePath = $SettingsStorePath
}

$settingsExists = Test-Path -LiteralPath $resolvedSettingsStorePath -PathType Leaf

$handyProcess = Get-Process -Name Handy -ErrorAction SilentlyContinue
if ($null -ne $handyProcess -and -not $Force) {
  Write-Host 'Handy is running. Close Handy and rerun, or use -Force.'
  return
}

if ($settingsExists) {
  try {
    $settingsDocument = Get-Content -LiteralPath $resolvedSettingsStorePath -Raw -Encoding UTF8 | ConvertFrom-Json
  } catch {
    throw "Invalid JSON in Handy settings file $resolvedSettingsStorePath. $($_.Exception.Message)"
  }
} else {
  $settingsDocument = [pscustomobject]@{
    settings = [pscustomobject]@{}
  }
}

if ($null -eq $settingsDocument.PSObject.Properties['settings'] -or $null -eq $settingsDocument.settings) {
  Set-JsonProperty -InputObject $settingsDocument -Name 'settings' -Value ([pscustomobject]@{})
}

$currentCustomWords = @()
if ($null -ne $settingsDocument.settings.PSObject.Properties['custom_words']) {
  $currentCustomWords = @(ConvertTo-StringArray -Value $settingsDocument.settings.custom_words)
}

$isUpToDate = $currentCustomWords.Count -eq $desiredCustomWords.Count
if ($isUpToDate) {
  for ($index = 0; $index -lt $desiredCustomWords.Count; $index++) {
    if ($currentCustomWords[$index] -cne $desiredCustomWords[$index]) {
      $isUpToDate = $false
      break
    }
  }
}

if ($isUpToDate) {
  Write-Host 'Handy custom words are already up to date.'
  return
}

$settingsDirectory = Split-Path -Parent $resolvedSettingsStorePath
if (-not [string]::IsNullOrWhiteSpace($settingsDirectory)) {
  New-Item -ItemType Directory -Path $settingsDirectory -Force | Out-Null
}

if ($settingsExists) {
  $timestamp = Get-Date -Format 'yyyyMMdd-HHmmss'
  $settingsLeaf = Split-Path -Leaf $resolvedSettingsStorePath
  if ([string]::IsNullOrWhiteSpace($settingsLeaf)) {
    throw "Settings store path must include a file name: $resolvedSettingsStorePath"
  }

  $backupDirectory = $settingsDirectory
  if ([string]::IsNullOrWhiteSpace($backupDirectory)) {
    $backupDirectory = '.'
  }

  $backupPath = Join-Path $backupDirectory "$settingsLeaf.backup-$timestamp"
  Copy-Item -LiteralPath $resolvedSettingsStorePath -Destination $backupPath
}

Set-JsonProperty -InputObject $settingsDocument.settings -Name 'custom_words' -Value $desiredCustomWords
$settingsDocument | ConvertTo-Json -Depth 100 | Set-Content -LiteralPath $resolvedSettingsStorePath -Encoding UTF8
Write-Host "Updated Handy custom words in $resolvedSettingsStorePath."
