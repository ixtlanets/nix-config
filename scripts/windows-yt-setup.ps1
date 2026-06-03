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
