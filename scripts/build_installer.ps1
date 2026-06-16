# Build scan2bim Inno Setup installer.
#   1. scripts/build_exe.ps1 -> dist/scan2bim.exe (+ dist/scan2bim-<v>.exe)
#   2. Ensure dist/LICENSES.md exists (fallback if missing).
#   3. Locate ISCC.exe (Inno Setup 6).
#   4. Compile build/installer.iss -> dist/scan2bim-Setup-<v>.exe (+ .sha256)
#
# Usage:  .\scripts\build_installer.ps1

$ErrorActionPreference = "Stop"

& "$PSScriptRoot\build_exe.ps1"

$version = $env:SCAN2BIM_VERSION
if (-not $version) { throw "SCAN2BIM_VERSION not set after build_exe.ps1" }

$root = (Resolve-Path "$PSScriptRoot\..").Path
$dist = Join-Path $root "dist"
$sourceExe = Join-Path $dist "scan2bim.exe"
$licensesFile = Join-Path $dist "LICENSES.md"

if (-not (Test-Path $sourceExe)) { throw "PyInstaller did not produce $sourceExe" }

if (-not (Test-Path $licensesFile)) {
    @(
        "# scan2bim - third-party licenses",
        "",
        "open3d (MIT), ifcopenshell (LGPL-3.0), ezdxf (MIT), PySide6 (LGPL-3.0),",
        "scipy/numpy (BSD), opencv-python (Apache-2.0), laspy (BSD), pye57 (MIT).",
        "",
        "Source and full license texts: https://github.com/Mcrauli/scan2bim"
    ) -join "`n" | Set-Content -Encoding UTF8 -Path $licensesFile
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

$iconFile = Join-Path $root "assets\scan2bim.ico"
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
    "/DSourceExe=$sourceExe",
    "/DLicensesFile=$licensesFile",
    "/DOutputDir=$dist"
)
if ($hasIcon) { $isccArgs += "/DIconFile=$iconFile" }
$isccArgs += $issPath

Write-Host "Compiling installer with ISCC: $iscc"
& $iscc @isccArgs
if ($LASTEXITCODE -ne 0) { throw "ISCC failed (exit $LASTEXITCODE)" }

$installer = Join-Path $dist "scan2bim-Setup-$version.exe"
if (-not (Test-Path $installer)) { throw "Installer missing after ISCC: $installer" }

$hash = Get-FileHash -Algorithm SHA256 -Path $installer
Write-Host "Built  : $installer"
Write-Host "SHA256 : $($hash.Hash)"
Set-Content -Path "$installer.sha256" -Value "$($hash.Hash)  $(Split-Path -Leaf $installer)"
