# Build ordinate Inno Setup installer.
#   1. scripts/build_exe.ps1 -> dist/ordinate.exe (+ dist/ordinate-<v>.exe)
#   2. Ensure dist/LICENSES.md exists (fallback if missing).
#   3. Locate ISCC.exe (Inno Setup 6).
#   4. Compile build/installer.iss -> dist/ordinate-Setup-<v>.exe (+ .sha256)
#
# Usage:  .\scripts\build_installer.ps1

$ErrorActionPreference = "Stop"

& "$PSScriptRoot\build_exe.ps1"

$version = $env:ORDINATE_VERSION
if (-not $version) { throw "ORDINATE_VERSION not set after build_exe.ps1" }

$root = (Resolve-Path "$PSScriptRoot\..").Path
$dist = Join-Path $root "dist"
$sourceDir = Join-Path $dist "ordinate"
$licensesFile = Join-Path $dist "LICENSES.md"

if (-not (Test-Path $sourceDir)) { throw "PyInstaller did not produce $sourceDir" }

# Lisenssit tulevat repon THIRD-PARTY-NOTICES.md:sta. Aiemmin tama generoi
# tyngan joka (a) ei maininnut Cloud2BIM:ia vaikka wall_contour.py on portattu
# siita (MIT vaatii copyright-ilmoituksen) ja (b) ohjasi "full license texts"
# YKSITYISEEN repoon johon asiakas ei paase. Kumpikin oli lisenssirikkomus.
$noticesSrc = Join-Path $root "THIRD-PARTY-NOTICES.md"
if (Test-Path $noticesSrc) {
    Copy-Item -Path $noticesSrc -Destination $licensesFile -Force
} elseif (-not (Test-Path $licensesFile)) {
    throw "THIRD-PARTY-NOTICES.md puuttuu — lisenssitiedostoa ei voi toimittaa."
}

$iscc = $env:ISCC
if (-not $iscc -or -not (Test-Path $iscc)) {
    $candidates = @(
        "${Env:ProgramFiles}\Inno Setup 6\ISCC.exe",
        "${Env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
        "${Env:LOCALAPPDATA}\Programs\Inno Setup 6\ISCC.exe"
    )
    $iscc = $candidates | Where-Object { Test-Path $_ } | Select-Object -First 1
}
if (-not $iscc) {
    throw "ISCC.exe not found. Install Inno Setup 6 (https://jrsoftware.org/isinfo.php) or set `$env:ISCC."
}

$iconFile = Join-Path $root "assets\ordinate.ico"
$hasIcon = Test-Path $iconFile

$numericVersion = $version -replace '[A-Za-z].*$', ''
$parts = @($numericVersion -split '\.' | Where-Object { $_ -ne '' })
while ($parts.Count -lt 4) { $parts += '0' }
$numericVersion = ($parts[0..3] -join '.')

$issPath = Join-Path $root "build\installer.iss"
$isccArgs = @(
    "/Qp",
    "/DAppVersion=$version",
    "/DAppNumericVersion=$numericVersion",
    "/DSourceDir=$sourceDir",
    "/DLicensesFile=$licensesFile",
    "/DOutputDir=$dist"
)
if ($hasIcon) { $isccArgs += "/DIconFile=$iconFile" }
$isccArgs += $issPath

Write-Host "Compiling installer with ISCC: $iscc"
& $iscc @isccArgs
if ($LASTEXITCODE -ne 0) { throw "ISCC failed (exit $LASTEXITCODE)" }

$installer = Join-Path $dist "Ordinate-Setup-$version.exe"
if (-not (Test-Path $installer)) { throw "Installer missing after ISCC: $installer" }

$hash = Get-FileHash -Algorithm SHA256 -Path $installer
Write-Host "Built  : $installer"
Write-Host "SHA256 : $($hash.Hash)"
Set-Content -Path "$installer.sha256" -Value "$($hash.Hash)  $(Split-Path -Leaf $installer)"

# VERSIOIMATON KOPIO: nettisivun latausnappi osoittaa kiinteaan nimeen
# releases/latest/download/scan2bim-Setup.exe (sivu) ja Ordinate-Setup.exe. Se puuttui v0.9.17:sta ja
# v0.9.18:sta -> sivun lataus oli 404. Julkaise TAMA jokaisessa releasessa.
foreach ($name in @("Ordinate-Setup.exe", "scan2bim-Setup.exe")) {
    $plain = Join-Path $dist $name
    Copy-Item -Path $installer -Destination $plain -Force
    Set-Content -Path "$plain.sha256" -Value "$($hash.Hash)  $name"
}
Write-Host "Built  : Ordinate-Setup.exe + scan2bim-Setup.exe (nettisivun linkki)"
