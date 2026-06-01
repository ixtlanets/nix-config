[CmdletBinding()]
param(
  [switch]$SkipInstall
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

. (Join-Path $PSScriptRoot 'windows-lib.ps1')
Assert-Windows

$packages = @(
  @{ Name = 'Brave'; Id = 'Brave.Brave' },
  @{ Name = 'Chrome'; Id = 'Google.Chrome' },
  @{ Name = 'VS Code'; Id = 'Microsoft.VisualStudioCode' },
  @{ Name = '1Password'; Id = 'AgileBits.1Password' },
  @{ Name = 'Telegram Desktop'; Id = 'Telegram.TelegramDesktop' },
  @{ Name = 'Docker Desktop'; Id = 'Docker.DockerDesktop' },
  @{ Name = 'Steam'; Id = 'Valve.Steam' },
  @{ Name = 'Throne'; Id = 'Throneproj.Throne' },
  @{ Name = 'LibreOffice'; Id = 'TheDocumentFoundation.LibreOffice' },
  @{ Name = 'PowerToys'; Id = 'Microsoft.PowerToys' },
  @{ Name = 'Tailscale'; Id = 'Tailscale.Tailscale' },
  @{
    Name = 'yt-dlp-nightly'
    Id = 'yt-dlp.yt-dlp.nightly'
    RemoveBeforeInstallIds = @('yt-dlp.yt-dlp')
  }
)

foreach ($package in $packages) {
  $installArguments = @{
    Name = $package.Name
    Id = $package.Id
    SkipInstall = $SkipInstall
  }

  if ($package.ContainsKey('RemoveBeforeInstallIds')) {
    $installArguments.RemoveBeforeInstallIds = $package.RemoveBeforeInstallIds
  }

  Install-WingetPackageIfMissing @installArguments
}
