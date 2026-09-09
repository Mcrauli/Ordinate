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
    # build/scan2bim.spec on ONE-DIR (LGPL vaatii erilliset kirjastot), joten
    # exe on dist\scan2bim\scan2bim.exe eika dist\scan2bim.exe. Vanha polku
    # sai skriptin ilmoittamaan epaonnistumisesta vaikka build meni lapi.
    $exe = Join-Path $PSScriptRoot "dist\scan2bim\scan2bim.exe"
    if (-not (Test-Path $exe)) { $exe = Join-Path $PSScriptRoot "dist\scan2bim.exe" }
    $size = [math]::Round((Get-Item $exe).Length / 1MB, 1)
    Write-Host "✓ Build valmis: $exe ($size MB)" -ForegroundColor Green

    # SAVUTESTI on osa buildia, ei erillinen muistettava vaihe. Nelja vikaa
    # loytyi 9.9.2026 pelkastaan silla etta pakattua tuotetta ajettiin
    # ensimmaista kertaa repon ULKOPUOLELTA; testit ja matriisi eivat aja
    # rakennettua exea lainkaan, joten ne eivat voi nahda taman luokan vikoja.
    Write-Host "Savutesti (pakattu tuote repon ulkopuolella)..." -ForegroundColor Yellow
    & "$venv\python" (Join-Path $PSScriptRoot "scripts\smoke_exe.py")
    if ($LASTEXITCODE -ne 0) {
        Write-Host "✗ Savutesti epäonnistui — pakattu tuote ei toimi" -ForegroundColor Red
        exit 1
    }
} else {
    Write-Host "✗ Build epäonnistui" -ForegroundColor Red
    exit 1
}
