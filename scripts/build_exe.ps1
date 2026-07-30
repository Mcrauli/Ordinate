# Local Windows PyInstaller build for scan2bim.
# Usage:  .\scripts\build_exe.ps1
# Output: dist/scan2bim/ (one-dir) + dist/scan2bim-<version>.zip (+ .sha256)
#
# ONE-DIR eika one-file: LGPL (IfcOpenShell, Qt) vaatii etta kayttaja voi
# vaihtaa kirjaston. Itsepaivitys lataa zipin ja vaihtaa hakemiston
# tiedosto kerrallaan (updater.replace_app_dir) - yha hiljainen, ei UAC:ia.
#
# Uses the project .venv (python -m PyInstaller). Run from the repo root.

$ErrorActionPreference = "Stop"

$root = (Resolve-Path "$PSScriptRoot\..").Path
$py = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path $py)) { throw "venv missing: $py - create with: py -3.12 -m venv .venv" }

if (-not $env:SCAN2BIM_VERSION) {
    $env:SCAN2BIM_VERSION = (Select-String -Path "$root\src\scan2bim\_version.py" -Pattern '__version__\s*=\s*"([^"]+)"').Matches[0].Groups[1].Value
}
Write-Host "Building scan2bim.exe version $($env:SCAN2BIM_VERSION)..."

$appDir = Join-Path $root "dist\scan2bim"
$source = Join-Path $appDir "scan2bim.exe"
$target = Join-Path $root "dist\scan2bim-$($env:SCAN2BIM_VERSION).zip"
$preBuildMtime = if (Test-Path $source) { (Get-Item $source).LastWriteTime } else { [datetime]::MinValue }

& $py -m pip install -e "$root[gui,build]" --quiet
if ($LASTEXITCODE -ne 0) { throw "pip install failed (exit $LASTEXITCODE)" }

& $py -m PyInstaller "$root\build\scan2bim.spec" --clean --noconfirm --distpath "$root\dist" --workpath "$root\build"
if ($LASTEXITCODE -ne 0) { throw "pyinstaller failed (exit $LASTEXITCODE)" }

if (-not (Test-Path $source)) { throw "PyInstaller did not produce $source" }
if ((Get-Item $source).LastWriteTime -le $preBuildMtime) {
    throw "PyInstaller output not refreshed - build did not actually run."
}

# Zip koko hakemisto: itsepaivityksen payload.
if (Test-Path $target) { Remove-Item $target -Force }
Compress-Archive -Path (Join-Path $appDir "*") -DestinationPath $target -CompressionLevel Optimal
$hash = Get-FileHash -Algorithm SHA256 -Path $target
Write-Host "Built  : $target"
Write-Host "SHA256 : $($hash.Hash)"
Set-Content -Path "$target.sha256" -Value "$($hash.Hash)  $(Split-Path -Leaf $target)"
