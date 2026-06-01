[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

. (Join-Path $PSScriptRoot 'windows-lib.ps1')
Assert-Windows

$ytDlp = @(Get-Command -Name 'yt-dlp.exe' -CommandType Application -All -ErrorAction SilentlyContinue |
    Where-Object { -not [string]::IsNullOrWhiteSpace($_.Source) } |
    Select-Object -First 1)

if ($ytDlp.Count -eq 0) {
  Write-Error "yt: native yt-dlp.exe is not installed or not in PATH. Run scripts/windows-setup.ps1 or install winget package yt-dlp.yt-dlp.nightly."
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
  Add-Type -AssemblyName System.Windows.Forms
  [System.Windows.Forms.Clipboard]::Clear()
} catch {
  Write-Warning "yt: failed to clear Windows clipboard: $($_.Exception.Message)"
}

& $ytDlp[0].Source --config-locations $configPath --output $outputTemplate $url
exit $LASTEXITCODE
