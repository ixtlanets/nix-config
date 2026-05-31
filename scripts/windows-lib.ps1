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
  param(
    [Parameter(Mandatory = $true)]
    [string]$ScriptRoot
  )

  return (Resolve-Path -LiteralPath (Split-Path -Parent $ScriptRoot)).ProviderPath
}

function Get-RequiredCommand {
  param(
    [Parameter(Mandatory = $true)]
    [string]$Name
  )

  $command = Get-Command -Name $Name -ErrorAction SilentlyContinue
  if ($null -eq $command) {
    throw "$Name is required but was not found in PATH."
  }

  return $command
}

function Invoke-WithSudoIfNeeded {
  param(
    [Parameter(Mandatory = $true)]
    [string]$ScriptPath,

    [string[]]$ArgumentList = @(),

    [switch]$RequiresAdmin
  )

  Assert-Windows

  if ((-not $RequiresAdmin) -or (Test-Administrator)) {
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $ScriptPath @ArgumentList
    if ($LASTEXITCODE -ne 0) {
      throw "$ScriptPath failed with exit code $LASTEXITCODE."
    }

    return
  }

  $sudo = Get-Command -Name sudo -ErrorAction SilentlyContinue
  if ($null -eq $sudo) {
    throw 'This setup step requires administrator rights. Enable Sudo for Windows as described in README.md, then rerun setup.'
  }

  & $sudo.Source powershell.exe -NoProfile -ExecutionPolicy Bypass -File $ScriptPath @ArgumentList
  if ($LASTEXITCODE -ne 0) {
    throw "$ScriptPath failed through sudo with exit code $LASTEXITCODE."
  }
}

function Test-WingetPackageInstalled {
  param(
    [Parameter(Mandatory = $true)]
    [string]$Id
  )

  $winget = Get-Command -Name winget -ErrorAction SilentlyContinue
  if ($null -eq $winget) {
    return $false
  }

  & $winget.Source list --id $Id --exact | Out-Null
  return ($LASTEXITCODE -eq 0)
}

function Install-WingetPackageIfMissing {
  param(
    [Parameter(Mandatory = $true)]
    [string]$Id,

    [Parameter(Mandatory = $true)]
    [string]$Name,

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

  $cache = Join-Path -Path $localAppData -ChildPath 'nix-config\downloads'
  New-Item -ItemType Directory -Path $cache -Force | Out-Null
  return $cache
}
