[CmdletBinding()]
param(
  [switch]$SkipInstall
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

. (Join-Path $PSScriptRoot 'windows-lib.ps1')
Assert-Windows

function Get-WslCommand {
  $commands = @(Get-Command -Name wsl -CommandType Application -All -ErrorAction SilentlyContinue |
      Where-Object { -not [string]::IsNullOrWhiteSpace($_.Source) } |
      Select-Object -First 1)

  if ($commands.Count -eq 0) {
    return $null
  }

  return $commands[0]
}

function Test-WslAvailable {
  $wsl = Get-WslCommand
  if ($null -eq $wsl) {
    return $false
  }

  & $wsl.Source --status *> $null
  if ($LASTEXITCODE -eq 0) {
    return $true
  }

  & $wsl.Source --version *> $null
  return ($LASTEXITCODE -eq 0)
}

function Test-UbuntuDistribution {
  $wsl = Get-WslCommand
  if ($null -eq $wsl) {
    return $false
  }

  $distros = @(& $wsl.Source --list --quiet 2>$null |
      ForEach-Object { $_.Trim() } |
      Where-Object { $_ })

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
