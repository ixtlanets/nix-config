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

  $commands = @(Get-Command -Name $Name -CommandType Application -All -ErrorAction SilentlyContinue |
      Where-Object { -not [string]::IsNullOrWhiteSpace($_.Source) } |
      Select-Object -First 1)

  if ($commands.Count -eq 0) {
    throw "$Name is required but no application executable was found in PATH."
  }

  return $commands[0]
}

function Invoke-WithSudoIfNeeded {
  param(
    [Parameter(Mandatory = $true)]
    [string]$ScriptPath,

    [string[]]$ArgumentList = @(),

    [switch]$RequiresAdmin
  )

  Assert-Windows

  $powershell = Get-RequiredCommand -Name powershell.exe

  if ((-not $RequiresAdmin) -or (Test-Administrator)) {
    & $powershell.Source -NoProfile -ExecutionPolicy Bypass -File $ScriptPath @ArgumentList
    if ($LASTEXITCODE -ne 0) {
      throw "$ScriptPath failed with exit code $LASTEXITCODE."
    }

    return
  }

  $sudoCommands = @(Get-Command -Name sudo -CommandType Application -All -ErrorAction SilentlyContinue |
      Where-Object { -not [string]::IsNullOrWhiteSpace($_.Source) } |
      Select-Object -First 1)

  if ($sudoCommands.Count -eq 0) {
    throw 'This setup step requires administrator rights. Enable Sudo for Windows as described in README.md, then rerun setup.'
  }

  & $sudoCommands[0].Source $powershell.Source -NoProfile -ExecutionPolicy Bypass -File $ScriptPath @ArgumentList
  if ($LASTEXITCODE -ne 0) {
    throw "$ScriptPath failed through sudo with exit code $LASTEXITCODE."
  }
}

function Test-WingetPackageInstalled {
  param(
    [Parameter(Mandatory = $true)]
    [string]$Id
  )

  # This only detects packages registered with winget under the exact package id.
  $wingetCommands = @(Get-Command -Name winget -CommandType Application -All -ErrorAction SilentlyContinue |
      Where-Object { -not [string]::IsNullOrWhiteSpace($_.Source) } |
      Select-Object -First 1)

  if ($wingetCommands.Count -eq 0) {
    return $false
  }

  & $wingetCommands[0].Source list --id $Id --exact | Out-Null
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
