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

New-Item -ItemType Directory -Path $script:FontRoot -Force | Out-Null
if (-not $script:NoRegister) {
  New-Item -Path $script:FontRegistry -Force | Out-Null
}

$fontCache = Join-Path $CacheRoot 'fonts'
$archiveCache = Join-Path $fontCache 'archives'
$extractRoot = Join-Path $fontCache 'expanded'
$directFileCache = Join-Path $fontCache 'files'

$archiveFontSources = @(
  @{
    Name = 'Hack Nerd Font'
    Uri = 'https://github.com/ryanoasis/nerd-fonts/releases/latest/download/Hack.zip'
    FileName = 'Hack.zip'
  },
  @{
    Name = 'Ubuntu Nerd Font'
    Uri = 'https://github.com/ryanoasis/nerd-fonts/releases/latest/download/Ubuntu.zip'
    FileName = 'Ubuntu.zip'
  },
  @{
    Name = 'Ubuntu Mono Nerd Font'
    Uri = 'https://github.com/ryanoasis/nerd-fonts/releases/latest/download/UbuntuMono.zip'
    FileName = 'UbuntuMono.zip'
  },
  @{
    Name = 'Ubuntu Sans Nerd Font'
    Uri = 'https://github.com/ryanoasis/nerd-fonts/releases/latest/download/UbuntuSans.zip'
    FileName = 'UbuntuSans.zip'
  },
  @{
    Name = 'SauceCodePro Nerd Font'
    Uri = 'https://github.com/ryanoasis/nerd-fonts/releases/latest/download/SourceCodePro.zip'
    FileName = 'SourceCodePro.zip'
  },
  @{
    Name = 'JetBrainsMono Nerd Font'
    Uri = 'https://github.com/ryanoasis/nerd-fonts/releases/latest/download/JetBrainsMono.zip'
    FileName = 'JetBrainsMono.zip'
  },
  @{
    Name = 'Monaspace'
    Uri = 'https://github.com/githubnext/monaspace/releases/download/v1.101/monaspace-v1.101.zip'
    FileName = 'monaspace-v1.101.zip'
  },
  @{
    Name = 'Cascadia Code'
    Uri = 'https://github.com/microsoft/cascadia-code/releases/download/v2407.24/CascadiaCode-2407.24.zip'
    FileName = 'CascadiaCode-2407.24.zip'
  }
)

$directFontSources = @(
  @{
    Name = 'Font Awesome 6 Brands'
    Uri = 'https://raw.githubusercontent.com/FortAwesome/Font-Awesome/6.x/otfs/Font%20Awesome%206%20Brands-Regular-400.otf'
    FileName = 'FontAwesome6Brands-Regular-400.otf'
    RegistryName = 'Font Awesome 6 Brands Regular (OpenType)'
  },
  @{
    Name = 'Font Awesome 6 Free Regular'
    Uri = 'https://raw.githubusercontent.com/FortAwesome/Font-Awesome/6.x/otfs/Font%20Awesome%206%20Free-Regular-400.otf'
    FileName = 'FontAwesome6Free-Regular-400.otf'
    RegistryName = 'Font Awesome 6 Free Regular (OpenType)'
  },
  @{
    Name = 'Font Awesome 6 Free Solid'
    Uri = 'https://raw.githubusercontent.com/FortAwesome/Font-Awesome/6.x/otfs/Font%20Awesome%206%20Free-Solid-900.otf'
    FileName = 'FontAwesome6Free-Solid-900.otf'
    RegistryName = 'Font Awesome 6 Free Solid (OpenType)'
  },
  @{
    Name = 'Roboto'
    Uri = 'https://raw.githubusercontent.com/google/fonts/main/ofl/roboto/Roboto%5Bwdth,wght%5D.ttf'
    FileName = 'Roboto.ttf'
    RegistryName = 'Roboto (TrueType)'
  },
  @{
    Name = 'Source Sans 3'
    Uri = 'https://raw.githubusercontent.com/google/fonts/main/ofl/sourcesans3/SourceSans3%5Bwght%5D.ttf'
    FileName = 'SourceSans3.ttf'
    RegistryName = 'Source Sans 3 (TrueType)'
  },
  @{
    Name = 'Source Serif 4'
    Uri = 'https://raw.githubusercontent.com/google/fonts/main/ofl/sourceserif4/SourceSerif4%5Bopsz,wght%5D.ttf'
    FileName = 'SourceSerif4.ttf'
    RegistryName = 'Source Serif 4 (TrueType)'
  },
  @{
    Name = 'Source Code Pro'
    Uri = 'https://raw.githubusercontent.com/google/fonts/main/ofl/sourcecodepro/SourceCodePro%5Bwght%5D.ttf'
    FileName = 'SourceCodePro.ttf'
    RegistryName = 'Source Code Pro (TrueType)'
  },
  @{
    Name = 'Fira Code'
    Uri = 'https://raw.githubusercontent.com/google/fonts/main/ofl/firacode/FiraCode%5Bwght%5D.ttf'
    FileName = 'FiraCode.ttf'
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

function Get-FontFiles {
  param(
    [Parameter(Mandatory = $true)]
    [string]$Directory
  )

  if (-not (Test-Path -LiteralPath $Directory -PathType Container)) {
    return @()
  }

  return @(Get-ChildItem -LiteralPath $Directory -Recurse -File |
      Where-Object { $_.Extension -in @('.ttf', '.otf') } |
      Sort-Object -Property FullName)
}

function Install-FontFile {
  param(
    [Parameter(Mandatory = $true)]
    [string]$SourcePath,

    [string]$RegistryName
  )

  if ([string]::IsNullOrWhiteSpace($RegistryName)) {
    $RegistryName = Get-FontRegistryName -Path $SourcePath
  }

  $target = Join-Path $script:FontRoot (Split-Path -Leaf $SourcePath)
  if (-not (Test-Path -LiteralPath $target -PathType Leaf)) {
    Copy-Item -LiteralPath $SourcePath -Destination $target
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
    Write-Host "Registered font $RegistryName"
  }
}

function Install-FontFilesFromDirectory {
  param(
    [Parameter(Mandatory = $true)]
    [string]$Directory,

    [Parameter(Mandatory = $true)]
    [string]$Name
  )

  $fontFiles = @(Get-FontFiles -Directory $Directory)
  if ($fontFiles.Count -eq 0) {
    throw "No .ttf or .otf files found for $Name in $Directory."
  }

  foreach ($fontFile in $fontFiles) {
    Install-FontFile -SourcePath $fontFile.FullName
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

  $extractedFonts = @(Get-FontFiles -Directory $extractPath)
  if ($extractedFonts.Count -eq 0) {
    Write-Host "Expanding $($Source.Name)"
    Expand-ZipToDirectory -ZipPath $zipPath -Destination $extractPath
  } else {
    Write-Host "Using extracted fonts $extractPath"
  }

  Install-FontFilesFromDirectory -Directory $extractPath -Name $Source.Name
}

function Install-DirectFont {
  param(
    [Parameter(Mandatory = $true)]
    [hashtable]$Source
  )

  $fontPath = Join-Path $directFileCache $Source.FileName
  Save-UrlIfMissing -Uri $Source.Uri -Destination $fontPath
  Install-FontFile -SourcePath $fontPath -RegistryName $Source.RegistryName
}

foreach ($source in $archiveFontSources) {
  Install-FontArchive -Source $source
}

foreach ($source in $directFontSources) {
  Install-DirectFont -Source $source
}
