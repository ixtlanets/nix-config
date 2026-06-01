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
$script:FontFilesChanged = $false

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
$googleFontsCommit = 'fafaa09e4abf799c185f85e9b6eacb7db31ca5ed'
$googleFontsCacheKey = $googleFontsCommit.Substring(0, 12)

function New-FontSelection {
  param(
    [Parameter(Mandatory = $true)]
    [string]$Path,

    [Parameter(Mandatory = $true)]
    [string]$RegistryName,

    [string]$TargetFileName,

    [string]$ManagedPrefix
  )

  $selection = @{
    Path = $Path
    RegistryName = $RegistryName
  }

  if (-not [string]::IsNullOrWhiteSpace($TargetFileName)) {
    $selection.TargetFileName = $TargetFileName
  }

  if (-not [string]::IsNullOrWhiteSpace($ManagedPrefix)) {
    $selection.ManagedPrefix = $ManagedPrefix
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
      New-FontSelection -Path $path -RegistryName "$Family $($_.Label) ($(if ($Extension -eq 'otf') { 'OpenType' } else { 'TrueType' }))" -ManagedPrefix $Prefix
    })
}

$archiveFontSources = @(
  @{
    Name = 'Hack Nerd Font'
    Uri = "https://github.com/ryanoasis/nerd-fonts/releases/download/$nerdFontsVersion/Hack.zip"
    FileName = "nerd-fonts-$nerdFontsVersion-Hack.zip"
    CleanupPrefixes = @('HackNerdFontPropo')
    SelectedFiles = @(
      (New-StyleSet -Prefix 'HackNerdFont' -Family 'Hack Nerd Font')
      (New-StyleSet -Prefix 'HackNerdFontMono' -Family 'Hack Nerd Font Mono')
    )
  },
  @{
    Name = 'Ubuntu Nerd Font'
    Uri = "https://github.com/ryanoasis/nerd-fonts/releases/download/$nerdFontsVersion/Ubuntu.zip"
    FileName = "nerd-fonts-$nerdFontsVersion-Ubuntu.zip"
    CleanupPrefixes = @('UbuntuNerdFontPropo')
    SelectedFiles = @(New-StyleSet -Prefix 'UbuntuNerdFont' -Family 'Ubuntu Nerd Font')
  },
  @{
    Name = 'Ubuntu Mono Nerd Font'
    Uri = "https://github.com/ryanoasis/nerd-fonts/releases/download/$nerdFontsVersion/UbuntuMono.zip"
    FileName = "nerd-fonts-$nerdFontsVersion-UbuntuMono.zip"
    CleanupPrefixes = @('UbuntuMonoNerdFontPropo')
    SelectedFiles = @(New-StyleSet -Prefix 'UbuntuMonoNerdFont' -Family 'Ubuntu Mono Nerd Font')
  },
  @{
    Name = 'Ubuntu Sans Nerd Font'
    Uri = "https://github.com/ryanoasis/nerd-fonts/releases/download/$nerdFontsVersion/UbuntuSans.zip"
    FileName = "nerd-fonts-$nerdFontsVersion-UbuntuSans.zip"
    CleanupPrefixes = @('UbuntuSansNerdFontPropo')
    SelectedFiles = @(New-StyleSet -Prefix 'UbuntuSansNerdFont' -Family 'Ubuntu Sans Nerd Font')
  },
  @{
    Name = 'SauceCodePro Nerd Font'
    Uri = "https://github.com/ryanoasis/nerd-fonts/releases/download/$nerdFontsVersion/SourceCodePro.zip"
    FileName = "nerd-fonts-$nerdFontsVersion-SourceCodePro.zip"
    CleanupPrefixes = @('SauceCodeProNerdFontPropo')
    SelectedFiles = @(
      (New-StyleSet -Prefix 'SauceCodeProNerdFont' -Family 'SauceCodePro Nerd Font')
      (New-StyleSet -Prefix 'SauceCodeProNerdFontMono' -Family 'SauceCodePro Nerd Font Mono')
    )
  },
  @{
    Name = 'JetBrainsMono Nerd Font'
    Uri = "https://github.com/ryanoasis/nerd-fonts/releases/download/$nerdFontsVersion/JetBrainsMono.zip"
    FileName = "nerd-fonts-$nerdFontsVersion-JetBrainsMono.zip"
    CleanupPrefixes = @('JetBrainsMonoNerdFontPropo')
    SelectedFiles = @(
      (New-StyleSet -Prefix 'JetBrainsMonoNerdFont' -Family 'JetBrainsMono Nerd Font')
      (New-StyleSet -Prefix 'JetBrainsMonoNerdFontMono' -Family 'JetBrainsMono Nerd Font Mono')
    )
  },
  @{
    Name = 'Monaspace'
    Uri = "https://github.com/githubnext/monaspace/releases/download/$monaspaceVersion/monaspace-$monaspaceVersion.zip"
    FileName = "monaspace-$monaspaceVersion.zip"
    CleanupPrefixes = @('MonaspaceArgon', 'MonaspaceRadon', 'MonaspaceXenon')
    SelectedFiles = @(
      (New-StyleSet -Prefix 'MonaspaceNeon' -Family 'Monaspace Neon' -Extension 'otf' -Directory "monaspace-$monaspaceVersion/fonts/otf")
      (New-StyleSet -Prefix 'MonaspaceKrypton' -Family 'Monaspace Krypton' -Extension 'otf' -Directory "monaspace-$monaspaceVersion/fonts/otf")
    )
  },
  @{
    Name = 'Cascadia Code'
    Uri = "https://github.com/microsoft/cascadia-code/releases/download/$cascadiaCodeVersion/CascadiaCode-2407.24.zip"
    FileName = "CascadiaCode-$cascadiaCodeVersion.zip"
    CleanupPrefixes = @('CascadiaCodePL', 'CascadiaMonoPL')
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
    ManagedPrefix = 'FontAwesome6Brands'
    RegistryName = 'Font Awesome 6 Brands Regular (OpenType)'
  },
  @{
    Name = 'Font Awesome 6 Free Regular'
    Uri = "https://raw.githubusercontent.com/FortAwesome/Font-Awesome/$fontAwesomeVersion/otfs/Font%20Awesome%206%20Free-Regular-400.otf"
    FileName = "FontAwesome-$fontAwesomeVersion-Free-Regular-400.otf"
    TargetFileName = 'FontAwesome6Free-Regular-400.otf'
    ManagedPrefix = 'FontAwesome6Free'
    RegistryName = 'Font Awesome 6 Free Regular (OpenType)'
  },
  @{
    Name = 'Font Awesome 6 Free Solid'
    Uri = "https://raw.githubusercontent.com/FortAwesome/Font-Awesome/$fontAwesomeVersion/otfs/Font%20Awesome%206%20Free-Solid-900.otf"
    FileName = "FontAwesome-$fontAwesomeVersion-Free-Solid-900.otf"
    TargetFileName = 'FontAwesome6Free-Solid-900.otf'
    ManagedPrefix = 'FontAwesome6Free'
    RegistryName = 'Font Awesome 6 Free Solid (OpenType)'
  },
  @{
    Name = 'Roboto'
    Uri = "https://raw.githubusercontent.com/google/fonts/$googleFontsCommit/ofl/roboto/Roboto%5Bwdth,wght%5D.ttf"
    FileName = "google-fonts-$googleFontsCacheKey-Roboto.ttf"
    TargetFileName = 'Roboto.ttf'
    ManagedPrefix = 'Roboto'
    RegistryName = 'Roboto (TrueType)'
  },
  @{
    Name = 'Source Sans 3'
    Uri = "https://raw.githubusercontent.com/google/fonts/$googleFontsCommit/ofl/sourcesans3/SourceSans3%5Bwght%5D.ttf"
    FileName = "google-fonts-$googleFontsCacheKey-SourceSans3.ttf"
    TargetFileName = 'SourceSans3.ttf'
    ManagedPrefix = 'SourceSans3'
    RegistryName = 'Source Sans 3 (TrueType)'
  },
  @{
    Name = 'Source Serif 4'
    Uri = "https://raw.githubusercontent.com/google/fonts/$googleFontsCommit/ofl/sourceserif4/SourceSerif4%5Bopsz,wght%5D.ttf"
    FileName = "google-fonts-$googleFontsCacheKey-SourceSerif4.ttf"
    TargetFileName = 'SourceSerif4.ttf'
    ManagedPrefix = 'SourceSerif4'
    RegistryName = 'Source Serif 4 (TrueType)'
  },
  @{
    Name = 'Source Code Pro'
    Uri = "https://raw.githubusercontent.com/google/fonts/$googleFontsCommit/ofl/sourcecodepro/SourceCodePro%5Bwght%5D.ttf"
    FileName = "google-fonts-$googleFontsCacheKey-SourceCodePro.ttf"
    TargetFileName = 'SourceCodePro.ttf'
    ManagedPrefix = 'SourceCodePro'
    RegistryName = 'Source Code Pro (TrueType)'
  },
  @{
    Name = 'Fira Code'
    Uri = "https://raw.githubusercontent.com/google/fonts/$googleFontsCommit/ofl/firacode/FiraCode%5Bwght%5D.ttf"
    FileName = "google-fonts-$googleFontsCacheKey-FiraCode.ttf"
    TargetFileName = 'FiraCode.ttf'
    ManagedPrefix = 'FiraCode'
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

function Get-ArchiveSelectionTargetFileName {
  param(
    [Parameter(Mandatory = $true)]
    [hashtable]$Selection
  )

  if ($Selection.ContainsKey('TargetFileName')) {
    return $Selection.TargetFileName
  }

  return [IO.Path]::GetFileName($Selection.Path)
}

function Get-DirectFontTargetFileName {
  param(
    [Parameter(Mandatory = $true)]
    [hashtable]$Source
  )

  if ($Source.ContainsKey('TargetFileName')) {
    return $Source.TargetFileName
  }

  return $Source.FileName
}

function Add-CaseInsensitiveSetValue {
  param(
    [Parameter(Mandatory = $true)]
    [hashtable]$Set,

    [Parameter(Mandatory = $true)]
    [string]$Value
  )

  if (-not [string]::IsNullOrWhiteSpace($Value)) {
    $Set[$Value.ToLowerInvariant()] = $true
  }
}

function Test-CaseInsensitiveSetContains {
  param(
    [Parameter(Mandatory = $true)]
    [hashtable]$Set,

    [Parameter(Mandatory = $true)]
    [string]$Value
  )

  return $Set.ContainsKey($Value.ToLowerInvariant())
}

function Get-DesiredFontTargetFileNameSet {
  $targets = @{}

  foreach ($source in $archiveFontSources) {
    foreach ($selection in @($source.SelectedFiles)) {
      Add-CaseInsensitiveSetValue -Set $targets -Value (Get-ArchiveSelectionTargetFileName -Selection $selection)
    }
  }

  foreach ($source in $directFontSources) {
    Add-CaseInsensitiveSetValue -Set $targets -Value (Get-DirectFontTargetFileName -Source $source)
  }

  return $targets
}

function Get-ManagedFontPrefixSet {
  $prefixes = @{}

  foreach ($source in $archiveFontSources) {
    if ($source.ContainsKey('CleanupPrefixes')) {
      foreach ($prefix in @($source.CleanupPrefixes)) {
        Add-CaseInsensitiveSetValue -Set $prefixes -Value $prefix
      }
    }

    foreach ($selection in @($source.SelectedFiles)) {
      if ($selection.ContainsKey('ManagedPrefix')) {
        Add-CaseInsensitiveSetValue -Set $prefixes -Value $selection.ManagedPrefix
      }
    }
  }

  foreach ($source in $directFontSources) {
    if ($source.ContainsKey('ManagedPrefix')) {
      Add-CaseInsensitiveSetValue -Set $prefixes -Value $source.ManagedPrefix
    }
  }

  return $prefixes
}

function Test-ManagedFontFileName {
  param(
    [Parameter(Mandatory = $true)]
    [string]$FileName,

    [Parameter(Mandatory = $true)]
    [hashtable]$ManagedPrefixes
  )

  $extension = [IO.Path]::GetExtension($FileName).ToLowerInvariant()
  if ($extension -ne '.ttf' -and $extension -ne '.otf') {
    return $false
  }

  $stem = [IO.Path]::GetFileNameWithoutExtension($FileName).ToLowerInvariant()
  foreach ($prefix in $ManagedPrefixes.Keys) {
    if ($stem -eq $prefix -or $stem.StartsWith("$prefix-") -or $stem.StartsWith("$prefix[")) {
      return $true
    }
  }

  return $false
}

function Test-PathUnderRoot {
  param(
    [Parameter(Mandatory = $true)]
    [string]$Path,

    [Parameter(Mandatory = $true)]
    [string]$Root
  )

  try {
    $rootPath = [IO.Path]::GetFullPath($Root).TrimEnd([IO.Path]::DirectorySeparatorChar, [IO.Path]::AltDirectorySeparatorChar)
    $candidatePath = [IO.Path]::GetFullPath($Path)
    return $candidatePath.StartsWith("$rootPath$([IO.Path]::DirectorySeparatorChar)", [StringComparison]::OrdinalIgnoreCase)
  } catch {
    return $false
  }
}

function Remove-StaleManagedFonts {
  param(
    [Parameter(Mandatory = $true)]
    [hashtable]$DesiredTargetFileNames,

    [Parameter(Mandatory = $true)]
    [hashtable]$ManagedPrefixes
  )

  foreach ($fontFile in @(Get-ChildItem -LiteralPath $script:FontRoot -File -ErrorAction SilentlyContinue)) {
    if (Test-CaseInsensitiveSetContains -Set $DesiredTargetFileNames -Value $fontFile.Name) {
      continue
    }

    if (-not (Test-ManagedFontFileName -FileName $fontFile.Name -ManagedPrefixes $ManagedPrefixes)) {
      continue
    }

    try {
      Remove-Item -LiteralPath $fontFile.FullName -Force -ErrorAction Stop
      $script:FontFilesChanged = $true
      Write-Host "Removed stale managed font file $($fontFile.FullName)"
    } catch {
      Write-Warning "Could not remove stale managed font file $($fontFile.FullName): $($_.Exception.Message). It may be in use; leaving it for a later run."
    }
  }

  if ($script:NoRegister) {
    return
  }

  $properties = Get-ItemProperty -Path $script:FontRegistry -ErrorAction SilentlyContinue
  if ($null -eq $properties) {
    return
  }

  foreach ($property in @($properties.PSObject.Properties)) {
    if ($property.Name.StartsWith('PS')) {
      continue
    }

    $registeredPath = [string]$property.Value
    if ([string]::IsNullOrWhiteSpace($registeredPath)) {
      continue
    }

    if (-not (Test-PathUnderRoot -Path $registeredPath -Root $script:FontRoot)) {
      continue
    }

    $registeredFileName = [IO.Path]::GetFileName($registeredPath)
    if (Test-CaseInsensitiveSetContains -Set $DesiredTargetFileNames -Value $registeredFileName) {
      continue
    }

    if (-not (Test-ManagedFontFileName -FileName $registeredFileName -ManagedPrefixes $ManagedPrefixes)) {
      continue
    }

    Remove-ItemProperty -Path $script:FontRegistry -Name $property.Name -Force
    $script:FontRegistryChanged = $true
    Write-Host "Removed stale managed font registration $($property.Name)"
  }
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

function Clear-FontArchiveCache {
  param(
    [Parameter(Mandatory = $true)]
    [string]$ZipPath,

    [Parameter(Mandatory = $true)]
    [string]$ExtractPath
  )

  Remove-Item -LiteralPath $ZipPath -Force -ErrorAction SilentlyContinue
  Remove-Item -LiteralPath (Get-ExtractionMarkerPath -ExtractPath $ExtractPath) -Force -ErrorAction SilentlyContinue

  if (Test-Path -LiteralPath $ExtractPath -PathType Container) {
    Remove-Item -LiteralPath $ExtractPath -Recurse -Force
  }
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

  for ($attempt = 1; $attempt -le 2; $attempt++) {
    if (Test-Path -LiteralPath $ExtractPath -PathType Container) {
      Write-Host "Clearing incomplete extracted fonts $ExtractPath"
      Remove-Item -LiteralPath $ExtractPath -Recurse -Force
    }

    Save-UrlIfMissing -Uri $Source.Uri -Destination $ZipPath

    Write-Host "Expanding $($Source.Name)"
    try {
      Expand-ZipToDirectory -ZipPath $ZipPath -Destination $ExtractPath

      $markerPath = Get-ExtractionMarkerPath -ExtractPath $ExtractPath
      New-Item -ItemType File -Path $markerPath -Force | Out-Null

      if (Test-ArchiveExtractionComplete -ExtractPath $ExtractPath -SelectedFiles $selectedFiles) {
        return
      }

      throw "Archive $($Source.Name) did not extract all selected font files."
    } catch {
      $message = $_.Exception.Message
      Clear-FontArchiveCache -ZipPath $ZipPath -ExtractPath $ExtractPath

      if ($attempt -lt 2) {
        Write-Host "Cached archive for $($Source.Name) is invalid. Downloading again."
        continue
      }

      throw "Archive $($Source.Name) failed after retry: $message"
    }
  }
}

function Test-FontFilePlausible {
  param(
    [Parameter(Mandatory = $true)]
    [string]$Path
  )

  if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
    return $false
  }

  $extension = [IO.Path]::GetExtension($Path).ToLowerInvariant()
  if ($extension -ne '.ttf' -and $extension -ne '.otf') {
    return $false
  }

  $fontFile = Get-Item -LiteralPath $Path
  if ($fontFile.Length -lt 12) {
    return $false
  }

  $stream = $null
  try {
    $stream = [IO.File]::Open($Path, [IO.FileMode]::Open, [IO.FileAccess]::Read, [IO.FileShare]::Read)
    $header = New-Object byte[] 4
    if ($stream.Read($header, 0, $header.Length) -ne $header.Length) {
      return $false
    }
  } catch {
    return $false
  } finally {
    if ($null -ne $stream) {
      $stream.Dispose()
    }
  }

  $signature = [Text.Encoding]::ASCII.GetString($header)
  if ($signature -eq 'true' -or $signature -eq 'ttcf' -or $signature -eq 'OTTO') {
    return $true
  }

  return ($header[0] -eq 0x00 -and $header[1] -eq 0x01 -and $header[2] -eq 0x00 -and $header[3] -eq 0x00)
}

function Resolve-DirectFontCache {
  param(
    [Parameter(Mandatory = $true)]
    [hashtable]$Source
  )

  $fontPath = Join-Path $directFileCache $Source.FileName

  for ($attempt = 1; $attempt -le 2; $attempt++) {
    Save-UrlIfMissing -Uri $Source.Uri -Destination $fontPath

    if (Test-FontFilePlausible -Path $fontPath) {
      return $fontPath
    }

    Remove-Item -LiteralPath $fontPath -Force -ErrorAction SilentlyContinue

    if ($attempt -lt 2) {
      Write-Host "Cached direct font $fontPath is invalid. Downloading again."
      continue
    }

    throw "Downloaded direct font $($Source.Name) is not a plausible font file."
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
    $targetExists = Test-Path -LiteralPath $target -PathType Leaf
    try {
      Copy-Item -LiteralPath $SourcePath -Destination $target -Force -ErrorAction Stop
      $script:FontFilesChanged = $true
      Write-Host "Installed font file $target"
    } catch {
      if (-not $targetExists) {
        throw
      }

      Write-Warning "Could not update font file ${target}: $($_.Exception.Message). It may be in use; leaving the existing file for a later run."
    }
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

  Expand-FontArchiveIfNeeded -Source $Source -ZipPath $zipPath -ExtractPath $extractPath

  foreach ($selection in @($Source.SelectedFiles)) {
    $fontPath = Get-SelectedFontPath -ExtractPath $extractPath -Selection $selection
    $targetFileName = Get-ArchiveSelectionTargetFileName -Selection $selection
    Install-FontFile -SourcePath $fontPath -RegistryName $selection.RegistryName -TargetFileName $targetFileName
  }
}

function Install-DirectFont {
  param(
    [Parameter(Mandatory = $true)]
    [hashtable]$Source
  )

  $fontPath = Resolve-DirectFontCache -Source $Source
  $targetFileName = Get-DirectFontTargetFileName -Source $Source
  Install-FontFile -SourcePath $fontPath -RegistryName $Source.RegistryName -TargetFileName $targetFileName
}

function Send-FontChangeNotification {
  if ($script:NoRegister) {
    return
  }

  if (-not $script:FontRegistryChanged -and -not $script:FontFilesChanged) {
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
  $sendMessageResult = [NativeMethods.FontBroadcast]::SendMessageTimeout(
    [IntPtr]0xffff,
    0x001d,
    [UIntPtr]::Zero,
    [IntPtr]::Zero,
    0x0002,
    5000,
    [ref]$result)

  if ($sendMessageResult -eq [IntPtr]::Zero) {
    $lastWin32Error = [Runtime.InteropServices.Marshal]::GetLastWin32Error()
    if ($lastWin32Error -ne 0) {
      $win32Message = ([ComponentModel.Win32Exception]::new($lastWin32Error)).Message
      throw "Failed to broadcast WM_FONTCHANGE with SendMessageTimeout: Win32 error $lastWin32Error ($win32Message)."
    }

    throw 'Failed to broadcast WM_FONTCHANGE with SendMessageTimeout.'
  }

  Write-Host 'Broadcasted WM_FONTCHANGE.'
}

$desiredFontTargetFileNames = Get-DesiredFontTargetFileNameSet
$managedFontPrefixes = Get-ManagedFontPrefixSet
Remove-StaleManagedFonts -DesiredTargetFileNames $desiredFontTargetFileNames -ManagedPrefixes $managedFontPrefixes

foreach ($source in $archiveFontSources) {
  Install-FontArchive -Source $source
}

foreach ($source in $directFontSources) {
  Install-DirectFont -Source $source
}

Send-FontChangeNotification
