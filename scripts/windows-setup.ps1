[CmdletBinding()]
param(
  [ValidateSet('All', 'Wsl', 'Apps', 'Apps,Yt', 'Yt', 'Fonts', 'Cursors', 'VoiceTyping')]
  [string[]]$Only = @('All'),
  [switch]$SkipInstall,
  [switch]$Force
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

. (Join-Path $PSScriptRoot 'windows-lib.ps1')
Assert-Windows

$repositoryRoot = Get-RepositoryRootFromScript -ScriptRoot $PSScriptRoot
$Only = @(
  foreach ($selection in $Only) {
    foreach ($name in ($selection -split ',')) {
      $trimmedName = $name.Trim()
      if (-not [string]::IsNullOrWhiteSpace($trimmedName)) {
        $trimmedName
      }
    }
  }
)
$runAll = $Only -contains 'All'

function Test-Selected {
  param(
    [Parameter(Mandatory = $true)]
    [string]$Name
  )

  return $runAll -or ($Only -contains $Name)
}

function Invoke-WindowsSetupStep {
  param(
    [Parameter(Mandatory = $true)]
    [string]$Name,

    [Parameter(Mandatory = $true)]
    [string]$ScriptName,

    [string[]]$ArgumentList = @(),

    [switch]$RequiresAdmin
  )

  $scriptPath = Join-Path $PSScriptRoot $ScriptName
  if (-not (Test-Path -LiteralPath $scriptPath -PathType Leaf)) {
    throw "Windows $Name setup script not found: $scriptPath"
  }

  Write-Host "Running Windows $Name setup."
  Invoke-WithSudoIfNeeded -ScriptPath $scriptPath -ArgumentList $ArgumentList -RequiresAdmin:$RequiresAdmin
}

Write-Host 'Running Windows setup.'

if (Test-Selected -Name 'Wsl') {
  $arguments = @()
  if ($SkipInstall) {
    $arguments += '-SkipInstall'
  }

  Invoke-WindowsSetupStep -Name 'WSL' -ScriptName 'windows-wsl.ps1' -ArgumentList $arguments
}

if (Test-Selected -Name 'Apps') {
  $arguments = @()
  if ($SkipInstall) {
    $arguments += '-SkipInstall'
  }

  Invoke-WindowsSetupStep -Name 'apps' -ScriptName 'windows-apps.ps1' -ArgumentList $arguments
}

if (Test-Selected -Name 'Yt') {
  Invoke-WindowsSetupStep -Name 'yt' -ScriptName 'windows-yt-setup.ps1'
}

if (Test-Selected -Name 'Fonts') {
  $arguments = @()
  if ($SkipInstall) {
    $arguments += '-SkipInstall'
  }

  Invoke-WindowsSetupStep -Name 'fonts' -ScriptName 'windows-fonts.ps1' -ArgumentList $arguments
}

if (Test-Selected -Name 'Cursors') {
  $arguments = @()
  if ($SkipInstall) {
    $arguments += '-SkipInstall'
  }

  Invoke-WindowsSetupStep -Name 'cursors' -ScriptName 'windows-cursors.ps1' -ArgumentList $arguments
}

if (Test-Selected -Name 'VoiceTyping') {
  $arguments = @('-RepositoryRoot', $repositoryRoot)
  if ($SkipInstall) {
    $arguments += '-SkipInstall'
  }

  if ($Force) {
    $arguments += '-Force'
  }

  Invoke-WindowsSetupStep -Name 'voice typing' -ScriptName 'windows-voice-typing.ps1' -ArgumentList $arguments
}

Write-Host 'Windows setup complete.'
