[CmdletBinding()]
param(
  [switch]$SkipInstall,
  [switch]$Force
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

if ([System.Environment]::OSVersion.Platform -ne [System.PlatformID]::Win32NT) {
  throw 'This script must be run on Windows.'
}

$repositoryRoot = (Resolve-Path -LiteralPath (Split-Path -Parent $PSScriptRoot)).ProviderPath
$voiceTypingSetup = Join-Path $PSScriptRoot 'windows-voice-typing.ps1'

if (-not (Test-Path -LiteralPath $voiceTypingSetup -PathType Leaf)) {
  throw "Windows voice typing setup script not found: $voiceTypingSetup"
}

Write-Host 'Running Windows voice typing setup.'
& $voiceTypingSetup -RepositoryRoot $repositoryRoot -SkipInstall:$SkipInstall -Force:$Force
Write-Host 'Windows setup complete.'
