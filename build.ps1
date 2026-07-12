# build.ps1 — scan2bim PyInstaller build
# Aja: .\build.ps1
# Tulos: dist\scan2bim.exe (onefile)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$venv = Join-Path $PSScriptRoot ".venv\Scripts"

Write-Host "=== scan2bim build ===" -ForegroundColor Cyan

# Varmista asennukset
Write-Host "Tarkistetaan riippuvuudet..." -ForegroundColor Yellow
& "$venv\pip" install -e ".[gui]" --quiet
& "$venv\pip" install pyinstaller --quiet

# Aja PyInstaller — build/scan2bim.spec on kanoninen (onefile + MOLEMMAT mallit;
# juuren scan2bim.spec on vanhentunut onedir eikä bundlaa retail-mallia).
Write-Host "Rakennetaan .exe..." -ForegroundColor Yellow
& "$venv\pyinstaller" build\scan2bim.spec --noconfirm --clean --distpath dist --workpath build

if ($LASTEXITCODE -eq 0) {
    $exe = Join-Path $PSScriptRoot "dist\scan2bim.exe"
    $size = [math]::Round((Get-Item $exe).Length / 1MB, 1)
    Write-Host "✓ Build valmis: $exe ($size MB)" -ForegroundColor Green
} else {
    Write-Host "✗ Build epäonnistui" -ForegroundColor Red
    exit 1
}
