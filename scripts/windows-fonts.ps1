[CmdletBinding()]
param(
  [switch]$SkipInstall,
  [string]$FontRoot,
  [string]$CacheRoot,
  [switch]$NoRegister
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

. (Join-Path $PSScriptRoot 'windows-lib.ps1')
Assert-Windows

if ($SkipInstall) {
  Write-Host 'Skipping font installation because -SkipInstall was passed.'
  return
}

if ([string]::IsNullOrWhiteSpace($FontRoot)) {
  $localAppData = [Environment]::GetEnvironmentVariable('LOCALAPPDATA')
  if ([string]::IsNullOrWhiteSpace($localAppData)) {
    throw 'LOCALAPPDATA is not set.'
  }

  $FontRoot = Join-Path $localAppData 'Microsoft\Windows\Fonts'
}

if ([string]::IsNullOrWhiteSpace($CacheRoot)) {
  $CacheRoot = Get-WindowsSetupCacheDirectory
}

$script:FontRoot = $FontRoot
$script:NoRegister = $NoRegister.IsPresent
$script:FontRegistry = 'HKCU:\Software\Microsoft\Windows NT\CurrentVersion\Fonts'
$script:FontRegistryChanged = $false

New-Item -ItemType Directory -Path $script:FontRoot -Force | Out-Null
if (-not $script:NoRegister) {
  New-Item -Path $script:FontRegistry -Force | Out-Null
}

$fontCache = Join-Path $CacheRoot 'fonts'
$archiveCache = Join-Path $fontCache 'archives'
$extractRoot = Join-Path $fontCache 'expanded'
$directFileCache = Join-Path $fontCache 'files'

$nerdFontsVersion = 'v3.4.0'
$monaspaceVersion = 'v1.101'
$fontAwesomeVersion = '6.7.2'
$cascadiaCodeVersion = 'v2407.24'
$googleFontsSnapshot = '2026-05-31'

function New-FontSelection {
  param(
    [Parameter(Mandatory = $true)]
    [string]$Path,

    [Parameter(Mandatory = $true)]
    [string]$RegistryName,

    [string]$TargetFileName
  )

  $selection = @{
    Path = $Path
    RegistryName = $RegistryName
  }

  if (-not [string]::IsNullOrWhiteSpace($TargetFileName)) {
    $selection.TargetFileName = $TargetFileName
  }

  return $selection
}

function New-StyleSet {
  param(
    [Parameter(Mandatory = $true)]
    [string]$Prefix,

    [Parameter(Mandatory = $true)]
    [string]$Family,

    [string]$Extension = 'ttf',

    [string]$Directory = ''
  )

  $styles = @(
    @{ Suffix = 'Regular'; Label = 'Regular' },
    @{ Suffix = 'Bold'; Label = 'Bold' },
    @{ Suffix = 'Italic'; Label = 'Italic' },
    @{ Suffix = 'BoldItalic'; Label = 'Bold Italic' }
  )

  return @($styles | ForEach-Object {
      $fileName = "$Prefix-$($_.Suffix).$Extension"
      $path = if ([string]::IsNullOrWhiteSpace($Directory)) { $fileName } else { "$Directory/$fileName" }
      New-FontSelection -Path $path -RegistryName "$Family $($_.Label) ($(if ($Extension -eq 'otf') { 'OpenType' } else { 'TrueType' }))"
    })
}

$archiveFontSources = @(
  @{
    Name = 'Hack Nerd Font'
    Uri = "https://github.com/ryanoasis/nerd-fonts/releases/download/$nerdFontsVersion/Hack.zip"
    FileName = "nerd-fonts-$nerdFontsVersion-Hack.zip"
    SelectedFiles = @(
      (New-StyleSet -Prefix 'HackNerdFont' -Family 'Hack Nerd Font')
      (New-StyleSet -Prefix 'HackNerdFontMono' -Family 'Hack Nerd Font Mono')
    )
  },
  @{
    Name = 'Ubuntu Nerd Font'
    Uri = "https://github.com/ryanoasis/nerd-fonts/releases/download/$nerdFontsVersion/Ubuntu.zip"
    FileName = "nerd-fonts-$nerdFontsVersion-Ubuntu.zip"
    SelectedFiles = @(New-StyleSet -Prefix 'UbuntuNerdFont' -Family 'Ubuntu Nerd Font')
  },
  @{
    Name = 'Ubuntu Mono Nerd Font'
    Uri = "https://github.com/ryanoasis/nerd-fonts/releases/download/$nerdFontsVersion/UbuntuMono.zip"
    FileName = "nerd-fonts-$nerdFontsVersion-UbuntuMono.zip"
    SelectedFiles = @(New-StyleSet -Prefix 'UbuntuMonoNerdFont' -Family 'Ubuntu Mono Nerd Font')
  },
  @{
    Name = 'Ubuntu Sans Nerd Font'
    Uri = "https://github.com/ryanoasis/nerd-fonts/releases/download/$nerdFontsVersion/UbuntuSans.zip"
    FileName = "nerd-fonts-$nerdFontsVersion-UbuntuSans.zip"
    SelectedFiles = @(New-StyleSet -Prefix 'UbuntuSansNerdFont' -Family 'Ubuntu Sans Nerd Font')
  },
  @{
    Name = 'SauceCodePro Nerd Font'
    Uri = "https://github.com/ryanoasis/nerd-fonts/releases/download/$nerdFontsVersion/SourceCodePro.zip"
    FileName = "nerd-fonts-$nerdFontsVersion-SourceCodePro.zip"
    SelectedFiles = @(
      (New-StyleSet -Prefix 'SauceCodeProNerdFont' -Family 'SauceCodePro Nerd Font')
      (New-StyleSet -Prefix 'SauceCodeProNerdFontMono' -Family 'SauceCodePro Nerd Font Mono')
    )
  },
  @{
    Name = 'JetBrainsMono Nerd Font'
    Uri = "https://github.com/ryanoasis/nerd-fonts/releases/download/$nerdFontsVersion/JetBrainsMono.zip"
    FileName = "nerd-fonts-$nerdFontsVersion-JetBrainsMono.zip"
    SelectedFiles = @(
      (New-StyleSet -Prefix 'JetBrainsMonoNerdFont' -Family 'JetBrainsMono Nerd Font')
      (New-StyleSet -Prefix 'JetBrainsMonoNerdFontMono' -Family 'JetBrainsMono Nerd Font Mono')
    )
  },
  @{
    Name = 'Monaspace'
    Uri = "https://github.com/githubnext/monaspace/releases/download/$monaspaceVersion/monaspace-$monaspaceVersion.zip"
    FileName = "monaspace-$monaspaceVersion.zip"
    SelectedFiles = @(
      (New-StyleSet -Prefix 'MonaspaceNeon' -Family 'Monaspace Neon' -Extension 'otf' -Directory "monaspace-$monaspaceVersion/fonts/otf")
      (New-StyleSet -Prefix 'MonaspaceKrypton' -Family 'Monaspace Krypton' -Extension 'otf' -Directory "monaspace-$monaspaceVersion/fonts/otf")
    )
  },
  @{
    Name = 'Cascadia Code'
    Uri = "https://github.com/microsoft/cascadia-code/releases/download/$cascadiaCodeVersion/CascadiaCode-2407.24.zip"
    FileName = "CascadiaCode-$cascadiaCodeVersion.zip"
    SelectedFiles = @(
      (New-StyleSet -Prefix 'CascadiaCode' -Family 'Cascadia Code' -Extension 'otf' -Directory 'otf/static')
      (New-StyleSet -Prefix 'CascadiaMono' -Family 'Cascadia Mono' -Extension 'otf' -Directory 'otf/static')
    )
  }
)

$directFontSources = @(
  @{
    Name = 'Font Awesome 6 Brands'
    Uri = "https://raw.githubusercontent.com/FortAwesome/Font-Awesome/$fontAwesomeVersion/otfs/Font%20Awesome%206%20Brands-Regular-400.otf"
    FileName = "FontAwesome-$fontAwesomeVersion-Brands-Regular-400.otf"
    TargetFileName = 'FontAwesome6Brands-Regular-400.otf'
    RegistryName = 'Font Awesome 6 Brands Regular (OpenType)'
  },
  @{
    Name = 'Font Awesome 6 Free Regular'
    Uri = "https://raw.githubusercontent.com/FortAwesome/Font-Awesome/$fontAwesomeVersion/otfs/Font%20Awesome%206%20Free-Regular-400.otf"
    FileName = "FontAwesome-$fontAwesomeVersion-Free-Regular-400.otf"
    TargetFileName = 'FontAwesome6Free-Regular-400.otf'
    RegistryName = 'Font Awesome 6 Free Regular (OpenType)'
  },
  @{
    Name = 'Font Awesome 6 Free Solid'
    Uri = "https://raw.githubusercontent.com/FortAwesome/Font-Awesome/$fontAwesomeVersion/otfs/Font%20Awesome%206%20Free-Solid-900.otf"
    FileName = "FontAwesome-$fontAwesomeVersion-Free-Solid-900.otf"
    TargetFileName = 'FontAwesome6Free-Solid-900.otf'
    RegistryName = 'Font Awesome 6 Free Solid (OpenType)'
  },
  @{
    Name = 'Roboto'
    Uri = 'https://raw.githubusercontent.com/google/fonts/main/ofl/roboto/Roboto%5Bwdth,wght%5D.ttf'
    FileName = "google-fonts-$googleFontsSnapshot-Roboto.ttf"
    TargetFileName = 'Roboto.ttf'
    RegistryName = 'Roboto (TrueType)'
  },
  @{
    Name = 'Source Sans 3'
    Uri = 'https://raw.githubusercontent.com/google/fonts/main/ofl/sourcesans3/SourceSans3%5Bwght%5D.ttf'
    FileName = "google-fonts-$googleFontsSnapshot-SourceSans3.ttf"
    TargetFileName = 'SourceSans3.ttf'
    RegistryName = 'Source Sans 3 (TrueType)'
  },
  @{
    Name = 'Source Serif 4'
    Uri = 'https://raw.githubusercontent.com/google/fonts/main/ofl/sourceserif4/SourceSerif4%5Bopsz,wght%5D.ttf'
    FileName = "google-fonts-$googleFontsSnapshot-SourceSerif4.ttf"
    TargetFileName = 'SourceSerif4.ttf'
    RegistryName = 'Source Serif 4 (TrueType)'
  },
  @{
    Name = 'Source Code Pro'
    Uri = 'https://raw.githubusercontent.com/google/fonts/main/ofl/sourcecodepro/SourceCodePro%5Bwght%5D.ttf'
    FileName = "google-fonts-$googleFontsSnapshot-SourceCodePro.ttf"
    TargetFileName = 'SourceCodePro.ttf'
    RegistryName = 'Source Code Pro (TrueType)'
  },
  @{
    Name = 'Fira Code'
    Uri = 'https://raw.githubusercontent.com/google/fonts/main/ofl/firacode/FiraCode%5Bwght%5D.ttf'
    FileName = "google-fonts-$googleFontsSnapshot-FiraCode.ttf"
    TargetFileName = 'FiraCode.ttf'
    RegistryName = 'Fira Code (TrueType)'
  }
)

function Get-FontRegistryName {
  param(
    [Parameter(Mandatory = $true)]
    [string]$Path
  )

  $extension = [IO.Path]::GetExtension($Path).ToLowerInvariant()
  $fontType = if ($extension -eq '.otf') { 'OpenType' } else { 'TrueType' }
  return "$([IO.Path]::GetFileNameWithoutExtension($Path)) ($fontType)"
}

function Get-SelectedFontPath {
  param(
    [Parameter(Mandatory = $true)]
    [string]$ExtractPath,

    [Parameter(Mandatory = $true)]
    [hashtable]$Selection
  )

  return Join-Path -Path $ExtractPath -ChildPath $Selection.Path
}

function Get-ExtractionMarkerPath {
  param(
    [Parameter(Mandatory = $true)]
    [string]$ExtractPath
  )

  return Join-Path $ExtractPath '.extraction-complete'
}

function Test-ArchiveExtractionComplete {
  param(
    [Parameter(Mandatory = $true)]
    [string]$ExtractPath,

    [Parameter(Mandatory = $true)]
    [hashtable[]]$SelectedFiles
  )

  $markerPath = Get-ExtractionMarkerPath -ExtractPath $ExtractPath
  if (-not (Test-Path -LiteralPath $markerPath -PathType Leaf)) {
    return $false
  }

  foreach ($selection in $SelectedFiles) {
    $fontPath = Get-SelectedFontPath -ExtractPath $ExtractPath -Selection $selection
    if (-not (Test-Path -LiteralPath $fontPath -PathType Leaf)) {
      return $false
    }

    if ((Get-Item -LiteralPath $fontPath).Length -le 0) {
      return $false
    }
  }

  return $true
}

function Expand-FontArchiveIfNeeded {
  param(
    [Parameter(Mandatory = $true)]
    [hashtable]$Source,

    [Parameter(Mandatory = $true)]
    [string]$ZipPath,

    [Parameter(Mandatory = $true)]
    [string]$ExtractPath
  )

  $selectedFiles = @($Source.SelectedFiles)
  if (Test-ArchiveExtractionComplete -ExtractPath $ExtractPath -SelectedFiles $selectedFiles) {
    Write-Host "Using extracted fonts $ExtractPath"
    return
  }

  if (Test-Path -LiteralPath $ExtractPath -PathType Container) {
    Write-Host "Clearing incomplete extracted fonts $ExtractPath"
    Remove-Item -LiteralPath $ExtractPath -Recurse -Force
  }

  Write-Host "Expanding $($Source.Name)"
  Expand-ZipToDirectory -ZipPath $ZipPath -Destination $ExtractPath

  $markerPath = Get-ExtractionMarkerPath -ExtractPath $ExtractPath
  New-Item -ItemType File -Path $markerPath -Force | Out-Null

  if (-not (Test-ArchiveExtractionComplete -ExtractPath $ExtractPath -SelectedFiles $selectedFiles)) {
    throw "Archive $($Source.Name) did not extract all selected font files."
  }
}

function Test-SameFileContent {
  param(
    [Parameter(Mandatory = $true)]
    [string]$SourcePath,

    [Parameter(Mandatory = $true)]
    [string]$TargetPath
  )

  if (-not (Test-Path -LiteralPath $TargetPath -PathType Leaf)) {
    return $false
  }

  $source = Get-Item -LiteralPath $SourcePath
  $target = Get-Item -LiteralPath $TargetPath
  if ($source.Length -ne $target.Length) {
    return $false
  }

  $sourceHash = (Get-FileHash -LiteralPath $SourcePath -Algorithm SHA256).Hash
  $targetHash = (Get-FileHash -LiteralPath $TargetPath -Algorithm SHA256).Hash
  return ($sourceHash -eq $targetHash)
}

function Install-FontFile {
  param(
    [Parameter(Mandatory = $true)]
    [string]$SourcePath,

    [string]$RegistryName,

    [string]$TargetFileName
  )

  if ([string]::IsNullOrWhiteSpace($RegistryName)) {
    $RegistryName = Get-FontRegistryName -Path $SourcePath
  }

  if ([string]::IsNullOrWhiteSpace($TargetFileName)) {
    $TargetFileName = Split-Path -Leaf $SourcePath
  }

  $target = Join-Path $script:FontRoot $TargetFileName
  if (Test-SameFileContent -SourcePath $SourcePath -TargetPath $target) {
    Write-Host "Font file $target is current."
  } else {
    Copy-Item -LiteralPath $SourcePath -Destination $target -Force
    Write-Host "Installed font file $target"
  }

  if ($script:NoRegister) {
    return
  }

  $property = Get-ItemProperty -Path $script:FontRegistry -Name $RegistryName -ErrorAction SilentlyContinue
  $current = $null
  if ($null -ne $property -and $null -ne $property.PSObject.Properties[$RegistryName]) {
    $current = $property.PSObject.Properties[$RegistryName].Value
  }

  if ($current -ne $target) {
    New-ItemProperty -Path $script:FontRegistry -Name $RegistryName -Value $target -PropertyType String -Force | Out-Null
    $script:FontRegistryChanged = $true
    Write-Host "Registered font $RegistryName"
  }
}

function Install-FontArchive {
  param(
    [Parameter(Mandatory = $true)]
    [hashtable]$Source
  )

  $zipPath = Join-Path $archiveCache $Source.FileName
  $extractPath = Join-Path $extractRoot $Source.Name

  Save-UrlIfMissing -Uri $Source.Uri -Destination $zipPath
  Expand-FontArchiveIfNeeded -Source $Source -ZipPath $zipPath -ExtractPath $extractPath

  foreach ($selection in @($Source.SelectedFiles)) {
    $fontPath = Get-SelectedFontPath -ExtractPath $extractPath -Selection $selection
    $targetFileName = if ($selection.ContainsKey('TargetFileName')) { $selection.TargetFileName } else { Split-Path -Leaf $fontPath }
    Install-FontFile -SourcePath $fontPath -RegistryName $selection.RegistryName -TargetFileName $targetFileName
  }
}

function Install-DirectFont {
  param(
    [Parameter(Mandatory = $true)]
    [hashtable]$Source
  )

  $fontPath = Join-Path $directFileCache $Source.FileName
  Save-UrlIfMissing -Uri $Source.Uri -Destination $fontPath
  $targetFileName = if ($Source.ContainsKey('TargetFileName')) { $Source.TargetFileName } else { Split-Path -Leaf $fontPath }
  Install-FontFile -SourcePath $fontPath -RegistryName $Source.RegistryName -TargetFileName $targetFileName
}

function Send-FontChangeNotification {
  if ($script:NoRegister) {
    return
  }

  if (-not $script:FontRegistryChanged) {
    return
  }

  if (-not ('NativeMethods.FontBroadcast' -as [type])) {
    Add-Type -TypeDefinition @'
namespace NativeMethods {
  using System;
  using System.Runtime.InteropServices;

  public static class FontBroadcast {
    [DllImport("user32.dll", SetLastError = true, CharSet = CharSet.Auto)]
    public static extern IntPtr SendMessageTimeout(
      IntPtr hWnd,
      uint Msg,
      UIntPtr wParam,
      IntPtr lParam,
      uint fuFlags,
      uint uTimeout,
      out UIntPtr lpdwResult);
  }
}
'@
  }

  $result = [UIntPtr]::Zero
  $null = [NativeMethods.FontBroadcast]::SendMessageTimeout(
    [IntPtr]0xffff,
    0x001d,
    [UIntPtr]::Zero,
    [IntPtr]::Zero,
    0x0002,
    5000,
    [ref]$result)
  Write-Host 'Broadcasted WM_FONTCHANGE.'
}

foreach ($source in $archiveFontSources) {
  Install-FontArchive -Source $source
}

foreach ($source in $directFontSources) {
  Install-DirectFont -Source $source
}

Send-FontChangeNotification
