"""One-dir-itsepaivitys: hakemiston vaihto tiedosto kerrallaan.

LGPL vaatii vaihdettavat kirjastot -> one-dir (ks. build/scan2bim.spec).
Paivityksen on silti toimittava hiljaisena, joten vaihto kaytaa samaa
Windows-kikkaa kuin ennenkin: kaytossa olevaa tiedostoa ei voi poistaa
mutta sen voi nimeta uudelleen.
"""
import zipfile

import pytest

from scan2bim.core.updater import (
    _select_asset,
    asset_is_zip,
    cleanup_old_exe,
    extract_zip,
    replace_app_dir,
)


def _mkapp(root, files):
    root.mkdir(parents=True, exist_ok=True)
    for rel, text in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
    return root


def test_zip_asset_preferred_over_raw_exe():
    """Siirtymajulkaisussa on MOLEMMAT assetit; zip voittaa."""
    rel = {"assets": [
        {"name": "scan2bim.exe", "browser_download_url": "u/scan2bim.exe", "size": 1},
        {"name": "scan2bim-0.9.0.zip", "browser_download_url": "u/a.zip", "size": 2},
        {"name": "scan2bim-Setup.exe", "browser_download_url": "u/s.exe", "size": 3},
        {"name": "scan2bim.exe.sha256", "browser_download_url": "u/x.sha256", "size": 4},
    ]}
    url, size = _select_asset(rel)
    assert url == "u/a.zip" and size == 2
    assert asset_is_zip(url)


def test_raw_exe_still_works_for_old_releases():
    """Vanhat one-file-julkaisut on yha paivitettava (ei zip-assettia)."""
    rel = {"assets": [
        {"name": "scan2bim-Setup.exe", "browser_download_url": "u/s.exe", "size": 3},
        {"name": "scan2bim.exe", "browser_download_url": "u/scan2bim.exe", "size": 1},
    ]}
    url, _ = _select_asset(rel)
    assert url == "u/scan2bim.exe"
    assert not asset_is_zip(url)


def test_setup_exe_never_selected_as_update_payload():
    """KRIITTINEN: Setup.exe on ASENNUSOHJELMA. Jos se valittaisiin, replace_exe
    korvaisi appin asentajalla → appi muuttuisi installeriksi (kavi kentalla).
    Pelkka Setup.exe -julkaisusta EI saa paivittaa."""
    rel = {"assets": [
        {"name": "scan2bim-Setup-0.9.7.exe", "browser_download_url": "u/s1.exe", "size": 3},
        {"name": "scan2bim-Setup.exe", "browser_download_url": "u/s2.exe", "size": 4},
        {"name": "scan2bim-Setup.exe.sha256", "browser_download_url": "u/s.sha256", "size": 1},
    ]}
    assert _select_asset(rel) is None


def test_replace_app_dir_swaps_every_file_and_keeps_old(tmp_path):
    cur = _mkapp(tmp_path / "app", {
        "scan2bim.exe": "vanha-exe",
        "Qt6Core.dll": "vanha-qt",
        "models/s3dis_pointnet.onnx": "vanha-malli",
    })
    new = _mkapp(tmp_path / "new", {
        "scan2bim.exe": "uusi-exe",
        "Qt6Core.dll": "uusi-qt",
        "models/s3dis_pointnet.onnx": "uusi-malli",
        "uusi_tiedosto.txt": "lisatty",
    })

    replace_app_dir(new, current_dir=cur)

    assert (cur / "scan2bim.exe").read_text(encoding="utf-8") == "uusi-exe"
    assert (cur / "Qt6Core.dll").read_text(encoding="utf-8") == "uusi-qt"
    assert (cur / "models/s3dis_pointnet.onnx").read_text(encoding="utf-8") == "uusi-malli"
    assert (cur / "uusi_tiedosto.txt").read_text(encoding="utf-8") == "lisatty"
    # vanhat sailyvat .old-nimisina kunnes seuraava kaynnistys siivoaa
    assert (cur / "scan2bim.exe.old").read_text(encoding="utf-8") == "vanha-exe"
    assert (cur / "Qt6Core.dll.old").read_text(encoding="utf-8") == "vanha-qt"


def test_cleanup_removes_old_files_recursively(tmp_path):
    cur = _mkapp(tmp_path / "app", {
        "scan2bim.exe": "exe",
        "scan2bim.exe.old": "roska",
        "Qt6Core.dll.old": "roska",
        "models/malli.onnx.old": "roska",
    })
    cleanup_old_exe(cur / "scan2bim.exe")
    assert not list(cur.rglob("*.old")), "jaannokset jaivat siivoamatta"
    assert (cur / "scan2bim.exe").exists(), "kayttokelpoinen exe ei saa kadota"


def test_extract_zip_finds_app_dir_with_or_without_root(tmp_path):
    for name, arc in (("juuressa", "scan2bim.exe"), ("alihakemistossa", "scan2bim/scan2bim.exe")):
        z = tmp_path / f"{name}.zip"
        with zipfile.ZipFile(z, "w") as zf:
            zf.writestr(arc, "exe")
            zf.writestr(arc.replace("scan2bim.exe", "Qt6Core.dll"), "qt")
        out = extract_zip(z, tmp_path / f"out_{name}")
        assert (out / "scan2bim.exe").exists(), f"{name}: sovellushakemistoa ei loytynyt"


def test_replace_app_dir_refuses_missing_source(tmp_path):
    cur = _mkapp(tmp_path / "app", {"scan2bim.exe": "exe"})
    with pytest.raises(FileNotFoundError):
        replace_app_dir(tmp_path / "puuttuu", current_dir=cur)
