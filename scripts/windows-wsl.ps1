[CmdletBinding()]
param(
  [switch]$SkipInstall
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

. (Join-Path $PSScriptRoot 'windows-lib.ps1')
Assert-Windows

function Get-WslCommandPath {
  $windowsRoots = @(
    [Environment]::GetEnvironmentVariable('WINDIR'),
    [Environment]::GetEnvironmentVariable('SystemRoot')
  ) |
    Where-Object { -not [string]::IsNullOrWhiteSpace($_) } |
    Select-Object -Unique

  foreach ($windowsRoot in $windowsRoots) {
    foreach ($systemDirectory in @('System32', 'Sysnative')) {
      $candidatePath = Join-Path -Path $windowsRoot -ChildPath "$systemDirectory\wsl.exe"
      if (Test-Path -LiteralPath $candidatePath -PathType Leaf) {
        return (Resolve-Path -LiteralPath $candidatePath).ProviderPath
      }
    }
  }

  return $null
}

function Test-WslAvailable {
  $wslPath = Get-WslCommandPath
  if ($null -eq $wslPath) {
    return $false
  }

  & $wslPath --status *> $null
  if ($LASTEXITCODE -eq 0) {
    return $true
  }

  & $wslPath --version *> $null
  return ($LASTEXITCODE -eq 0)
}

function Test-UbuntuDistribution {
  $wslPath = Get-WslCommandPath
  if ($null -eq $wslPath) {
    return $false
  }

  $listOutput = @(& $wslPath --list --quiet)
  if ($LASTEXITCODE -ne 0) {
    throw "wsl --list --quiet failed with exit code $LASTEXITCODE. WSL is available, but distro enumeration failed; not installing Ubuntu automatically."
  }

  $distros = @($listOutput |
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
  throw 'WSL bootstrap requires administrator rights. Rerun from an elevated PowerShell, or run through windows-setup.ps1 after orchestration is enabled.'
}

$wslPath = Get-WslCommandPath
if ($null -eq $wslPath) {
  throw 'System WSL executable was not found under %WINDIR%\System32 or %WINDIR%\Sysnative.'
}

Write-Host 'Installing WSL with Ubuntu. A reboot may be required after this completes.'
& $wslPath --install -d Ubuntu --no-launch
if ($LASTEXITCODE -ne 0) {
  throw "wsl --install -d Ubuntu --no-launch failed with exit code $LASTEXITCODE."
}

Write-Host 'WSL install command completed. Reboot if Windows reports that one is required.'
