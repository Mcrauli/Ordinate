"""One-dir-itsepaivitys: hakemiston vaihto tiedosto kerrallaan.

LGPL vaatii vaihdettavat kirjastot -> one-dir (ks. build/ordinate.spec).
Paivityksen on silti toimittava hiljaisena, joten vaihto kaytaa samaa
Windows-kikkaa kuin ennenkin: kaytossa olevaa tiedostoa ei voi poistaa
mutta sen voi nimeta uudelleen.
"""
import zipfile

import pytest

from ordinate.core.updater import (
    _select_asset,
    apply_downloaded_update,
    asset_is_zip,
    cleanup_old_exe,
    extract_zip,
    replace_app_dir,
)
import ordinate.core.updater as _updater


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
        {"name": "ordinate.exe", "browser_download_url": "u/ordinate.exe", "size": 1},
        {"name": "ordinate-0.9.0.zip", "browser_download_url": "u/a.zip", "size": 2},
        {"name": "ordinate-Setup.exe", "browser_download_url": "u/s.exe", "size": 3},
        {"name": "ordinate.exe.sha256", "browser_download_url": "u/x.sha256", "size": 4},
    ]}
    url, size = _select_asset(rel)
    assert url == "u/a.zip" and size == 2
    assert asset_is_zip(url)


def test_raw_exe_still_works_for_old_releases():
    """Vanhat one-file-julkaisut on yha paivitettava (ei zip-assettia)."""
    rel = {"assets": [
        {"name": "ordinate-Setup.exe", "browser_download_url": "u/s.exe", "size": 3},
        {"name": "ordinate.exe", "browser_download_url": "u/ordinate.exe", "size": 1},
    ]}
    url, _ = _select_asset(rel)
    assert url == "u/ordinate.exe"
    assert not asset_is_zip(url)


def test_setup_exe_never_selected_as_update_payload():
    """KRIITTINEN: Setup.exe on ASENNUSOHJELMA. Jos se valittaisiin, replace_exe
    korvaisi appin asentajalla → appi muuttuisi installeriksi (kavi kentalla).
    Pelkka Setup.exe -julkaisusta EI saa paivittaa."""
    rel = {"assets": [
        {"name": "ordinate-Setup-0.9.7.exe", "browser_download_url": "u/s1.exe", "size": 3},
        {"name": "ordinate-Setup.exe", "browser_download_url": "u/s2.exe", "size": 4},
        {"name": "ordinate-Setup.exe.sha256", "browser_download_url": "u/s.sha256", "size": 1},
    ]}
    assert _select_asset(rel) is None


def test_apply_zip_uses_helper_not_replace_exe(tmp_path, monkeypatch):
    """KRIITTINEN regressio: one-dir-ZIP-paivitys puretaan ja vaihdetaan APUPROSESSILLA
    (base_library.zip lukossa ajon aikana → ei in-place). EI koskaan kirjoiteta zippia
    ordinate.exe:ksi (replace_exe). Palauttaa True (kutsujan suljettava app)."""
    calls = []
    monkeypatch.setattr(_updater, "extract_zip", lambda p, d: tmp_path / "app")
    monkeypatch.setattr(_updater, "swap_app_dir_via_helper", lambda d: calls.append(("helper", d)))
    monkeypatch.setattr(_updater, "replace_exe", lambda p: calls.append(("exe", p)))
    result = apply_downloaded_update(tmp_path / "ordinate-0.9.8.zip",
                                    "https://x/releases/download/v0.9.8/ordinate-0.9.8.zip")
    assert calls == [("helper", tmp_path / "app")], f"zip meni vaaraan polkuun: {calls}"
    assert result is True


def test_apply_raw_exe_uses_replace_exe(tmp_path, monkeypatch):
    """Vanha one-file-.exe kirjoitetaan sellaisenaan (replace_exe); palauttaa False."""
    calls = []
    monkeypatch.setattr(_updater, "swap_app_dir_via_helper", lambda d: calls.append(("helper", d)))
    monkeypatch.setattr(_updater, "replace_exe", lambda p: calls.append(("exe", p)))
    result = apply_downloaded_update(tmp_path / "ordinate.exe",
                                    "https://x/releases/download/v0.8.0/ordinate.exe")
    assert calls == [("exe", tmp_path / "ordinate.exe")], f"exe meni vaaraan polkuun: {calls}"
    assert result is False


def test_update_helper_script_waits_copies_relaunches(tmp_path):
    """Apuskripti: odota PID:n sulkeutumista → robocopy staging→install → kaynnista."""
    from ordinate.core.updater import _build_update_helper_script
    s = _build_update_helper_script(12345, tmp_path / "staging", tmp_path / "install")
    assert 'PID eq 12345' in s              # odottaa oikeaa prosessia
    assert ':wait' in s and 'goto wait' in s  # odotussilmukka
    assert 'robocopy' in s and str(tmp_path / "staging") in s and str(tmp_path / "install") in s
    assert 'start ""' in s and 'Ordinate.exe' in s  # kaynnistaa uudelleen
    assert 'del "%~f0"' in s                 # siivoaa itsensa


def test_replace_app_dir_swaps_every_file_and_keeps_old(tmp_path):
    cur = _mkapp(tmp_path / "app", {
        "ordinate.exe": "vanha-exe",
        "Qt6Core.dll": "vanha-qt",
        "models/s3dis_pointnet.onnx": "vanha-malli",
    })
    new = _mkapp(tmp_path / "new", {
        "ordinate.exe": "uusi-exe",
        "Qt6Core.dll": "uusi-qt",
        "models/s3dis_pointnet.onnx": "uusi-malli",
        "uusi_tiedosto.txt": "lisatty",
    })

    replace_app_dir(new, current_dir=cur)

    assert (cur / "ordinate.exe").read_text(encoding="utf-8") == "uusi-exe"
    assert (cur / "Qt6Core.dll").read_text(encoding="utf-8") == "uusi-qt"
    assert (cur / "models/s3dis_pointnet.onnx").read_text(encoding="utf-8") == "uusi-malli"
    assert (cur / "uusi_tiedosto.txt").read_text(encoding="utf-8") == "lisatty"
    # vanhat sailyvat .old-nimisina kunnes seuraava kaynnistys siivoaa
    assert (cur / "ordinate.exe.old").read_text(encoding="utf-8") == "vanha-exe"
    assert (cur / "Qt6Core.dll.old").read_text(encoding="utf-8") == "vanha-qt"


def test_cleanup_removes_old_files_recursively(tmp_path):
    cur = _mkapp(tmp_path / "app", {
        "ordinate.exe": "exe",
        "ordinate.exe.old": "roska",
        "Qt6Core.dll.old": "roska",
        "models/malli.onnx.old": "roska",
    })
    cleanup_old_exe(cur / "ordinate.exe")
    assert not list(cur.rglob("*.old")), "jaannokset jaivat siivoamatta"
    assert (cur / "ordinate.exe").exists(), "kayttokelpoinen exe ei saa kadota"


def test_extract_zip_finds_app_dir_with_or_without_root(tmp_path):
    for name, arc in (("juuressa", "ordinate.exe"), ("alihakemistossa", "ordinate/ordinate.exe")):
        z = tmp_path / f"{name}.zip"
        with zipfile.ZipFile(z, "w") as zf:
            zf.writestr(arc, "exe")
            zf.writestr(arc.replace("ordinate.exe", "Qt6Core.dll"), "qt")
        out = extract_zip(z, tmp_path / f"out_{name}")
        assert (out / "ordinate.exe").exists(), f"{name}: sovellushakemistoa ei loytynyt"


def test_replace_app_dir_refuses_missing_source(tmp_path):
    cur = _mkapp(tmp_path / "app", {"ordinate.exe": "exe"})
    with pytest.raises(FileNotFoundError):
        replace_app_dir(tmp_path / "puuttuu", current_dir=cur)


def test_extract_zip_finds_legacy_exe_name(tmp_path):
    """Siltajulkaisu: zipissa voi olla vain scan2bim.exe (vanha nimi)."""
    import zipfile
    z = tmp_path / "u.zip"
    with zipfile.ZipFile(z, "w") as zf:
        zf.writestr("app/scan2bim.exe", "exe")
    assert (extract_zip(z, tmp_path / "out") / "scan2bim.exe").exists()


def test_helper_waits_for_running_exe_but_launches_new_one(tmp_path):
    """Vanhasta scan2bim.exe:sta ajettu paivitys odottaa SITA prosessia ja
    kaynnistaa uuden Ordinate.exe:n."""
    from ordinate.core.updater import _build_update_helper_script
    s = _build_update_helper_script(1, tmp_path / "s", tmp_path / "i",
                                    "Ordinate.exe", "scan2bim.exe")
    assert '/I "scan2bim.exe"' in s
    assert 'Ordinate.exe"' in s.split("start")[1]
