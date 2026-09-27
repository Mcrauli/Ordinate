"""Self-update for the bundled Windows exe.

Polls GitHub Releases for newer versions of ordinate and exposes a
helper to download + swap the exe. The swap relies on a Windows quirk:
a running ``.exe`` cannot be deleted but it CAN be renamed, so:

    1. Download new exe to a temp path
    2. Rename current exe → ``….exe.old``
    3. Move the temp exe into the freed slot
    4. Quit; the OS releases the ``.old`` handle and
       ``cleanup_old_exe()`` deletes it on the next startup.

When running from source (``python -m ordinate``) the mechanism is
no-op — :func:`is_running_bundled` returns ``False``.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from packaging.version import InvalidVersion, Version

from ordinate._version import __version__

DEFAULT_REPO: str = "Mcrauli/scan2bim-web"
GITHUB_API_URL: str = "https://api.github.com/repos/{repo}/releases"
USER_AGENT: str = f"ordinate-updater/{__version__}"
APP_EXE: str = "Ordinate.exe"
LEGACY_EXE: str = "scan2bim.exe"


@dataclass(frozen=True)
class UpdateInfo:
    """Metadata for a release that is newer than the current version."""

    version: str
    tag: str
    release_url: str
    download_url: str
    download_size: int
    notes: str


def is_running_bundled() -> bool:
    """True only when running inside the PyInstaller bundle."""
    return bool(getattr(sys, "frozen", False))


def _normalise_version(raw: str) -> Version | None:
    cleaned = raw.lstrip("vV").strip()
    cleaned = (
        cleaned.replace("-alpha", "a0")
        .replace("-beta", "b0")
        .replace("-rc", "rc0")
    )
    try:
        return Version(cleaned)
    except InvalidVersion:
        return None


def _select_asset(release: dict) -> tuple[str, int] | None:
    """Pick the update payload, skipping .sha256 sidecars.

    Order: **zip** (one-dir paketti) → raaka exe → Setup.

    Zip on ensisijainen koska sovellus on one-dir (LGPL vaatii vaihdettavat
    kirjastot, ks. build/ordinate.spec). Raaka exe säilyy tuettuna, jotta
    yhdellä siirtymäjulkaisulla voi olla molemmat assetit eivätkä vanhat
    one-file-asennukset jää päivityksettä.
    """
    zips: list[tuple[str, int]] = []
    exes: list[tuple[str, int]] = []
    for asset in release.get("assets", []):
        name = (asset.get("name") or "").lower()
        if name.endswith(".sha256"):
            continue
        url = asset.get("browser_download_url")
        size = int(asset.get("size", 0))
        if name.endswith(".zip"):
            zips.append((url, size))
        elif name.endswith(".exe") and "setup" not in name:
            # KRIITTINEN: Setup.exe on ASENNUSOHJELMA, EI päivityspayload. Jos se
            # valittaisiin, replace_exe korvaisi appin (ordinate.exe) asentajalla →
            # käyttäjän "appi" muuttuisi installeriksi (mitattu: näin kävi kentällä).
            # Vain zip (one-dir) tai raaka onefile-exe kelpaa itsepäivitykseen;
            # "setup"-niminen exe ohitetaan aina. Tunnistus assetNIMESTÄ (URL voi
            # olla nimetön).
            exes.append((url, size))
    if zips:
        return zips[0]
    if exes:
        return exes[0]
    return None


def asset_is_zip(url_or_name: str) -> bool:
    """True jos asset on one-dir-zip (→ :func:`replace_app_dir`)."""
    return str(url_or_name).lower().endswith(".zip")


def app_dir() -> Path:
    """Asennushakemisto (one-dir): exen hakemisto."""
    return Path(sys.executable).parent


def _open_releases(repo: str, *, timeout: float) -> list[dict]:
    url = GITHUB_API_URL.format(repo=repo) + "?per_page=10"
    request = urllib.request.Request(
        url, headers={"User-Agent": USER_AGENT, "Accept": "application/vnd.github+json"}
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        payload = response.read()
    data = json.loads(payload)
    if not isinstance(data, list):
        return []
    return data


def check_for_update(
    *,
    current_version: str = __version__,
    repo: str = DEFAULT_REPO,
    include_prereleases: bool = True,
    timeout: float = 5.0,
) -> UpdateInfo | None:
    """Return :class:`UpdateInfo` if a newer release has an exe asset.

    Returns ``None`` for any of: no newer release, network failure,
    rate-limit, malformed payload — silent so a transient failure never
    blocks app startup.
    """
    current = _normalise_version(current_version)
    if current is None:
        return None
    try:
        releases = _open_releases(repo, timeout=timeout)
    except (urllib.error.URLError, TimeoutError, OSError):
        return None
    except json.JSONDecodeError:
        return None

    newest: tuple[Version, dict] | None = None
    for release in releases:
        if release.get("draft"):
            continue
        if release.get("prerelease") and not include_prereleases:
            continue
        tag = release.get("tag_name", "")
        version = _normalise_version(tag)
        if version is None or version <= current:
            continue
        if newest is None or version > newest[0]:
            newest = (version, release)

    if newest is None:
        return None

    version, release = newest
    asset = _select_asset(release)
    if asset is None:
        return None
    download_url, download_size = asset
    return UpdateInfo(
        version=str(version),
        tag=release.get("tag_name", ""),
        release_url=release.get("html_url", ""),
        download_url=download_url,
        download_size=download_size,
        notes=release.get("body", "") or "",
    )


def fetch_expected_sha256(asset_url: str, *, timeout: float = 5.0) -> str | None:
    """Fetch the ``.sha256`` sidecar for an asset (sha256sum format).

    Returns the lowercase hex digest, or ``None`` if unreachable or
    malformed (download then degrades to size-only verification).
    """
    sidecar_url = asset_url + ".sha256"
    request = urllib.request.Request(sidecar_url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = response.read().decode("ascii", errors="replace").strip()
    except (urllib.error.URLError, TimeoutError, OSError):
        return None
    parts = payload.split()
    if not parts or len(parts[0]) != 64:
        return None
    try:
        bytes.fromhex(parts[0])
    except ValueError:
        return None
    return parts[0].lower()


def download_asset(
    url: str,
    target_path: Path,
    *,
    progress_cb: Callable[[int, int], None] | None = None,
    chunk_size: int = 256 * 1024,
    timeout: float = 30.0,
    expected_sha256: str | None = None,
) -> None:
    """Stream an asset to ``target_path``, calling ``progress_cb(done, total)``.

    Writes to a ``.part`` file and renames on success. When
    ``expected_sha256`` is given, the digest is verified before the
    rename — mismatch raises :class:`ValueError`.
    """
    target_path.parent.mkdir(parents=True, exist_ok=True)
    part_path = target_path.with_suffix(target_path.suffix + ".part")
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    hasher = hashlib.sha256() if expected_sha256 else None
    with urllib.request.urlopen(request, timeout=timeout) as response:
        total = int(response.headers.get("Content-Length", 0))
        downloaded = 0
        with open(part_path, "wb") as out:
            while True:
                chunk = response.read(chunk_size)
                if not chunk:
                    break
                out.write(chunk)
                if hasher is not None:
                    hasher.update(chunk)
                downloaded += len(chunk)
                if progress_cb is not None:
                    try:
                        progress_cb(downloaded, total)
                    except Exception:
                        pass
    if hasher is not None:
        actual = hasher.hexdigest()
        if actual.lower() != expected_sha256.lower():
            try:
                part_path.unlink()
            except OSError:
                pass
            raise ValueError(
                f"SHA-256 mismatch on {target_path.name}: "
                f"expected {expected_sha256.lower()}, got {actual}"
            )
    if target_path.exists():
        target_path.unlink()
    part_path.rename(target_path)


def asset_is_installer(url_or_name: str) -> bool:
    """True jos asset on Inno Setup -installeri (``*Setup*.exe``)."""
    return "setup" in url_or_name.lower()


def launch_installer(installer_path: Path) -> None:
    """Käynnistä ladattu Inno Setup -installeri ja palaa heti.

    Installeri hoitaa oman elevaationsa (UAC), joten se voi kirjoittaa
    Program Filesiin vaikka sovellus itse ei ole elevoitu. Kutsujan on
    suljettava sovellus heti tämän jälkeen, jotta installeri voi korvata
    käynnissä olevan exen. ``/CLOSEAPPLICATIONS /RESTARTAPPLICATIONS``:
    Restart Manager sulkee ja avaa ordinatein asennuksen ympäriltä.
    """
    import subprocess

    if not installer_path.exists():
        raise FileNotFoundError(f"installer not found: {installer_path}")
    subprocess.Popen(
        [str(installer_path), "/CLOSEAPPLICATIONS", "/RESTARTAPPLICATIONS"],
        close_fds=True,
    )


def _old_path_for(exe_path: Path) -> Path:
    return exe_path.with_suffix(exe_path.suffix + ".old")


def cleanup_old_exe(exe_path: Path | None = None) -> None:
    """Poista edellisen päivityksen ``.old``-jäämät.

    One-dirissä niitä on useita (jokainen käytössä ollut .dll/.pyd), joten
    koko asennushakemisto käydään läpi. Epäonnistuva poisto ohitetaan:
    tiedosto voi olla yhä lukittu, ja seuraava käynnistys yrittää uudelleen."""
    if exe_path is None:
        if not is_running_bundled():
            return
        exe_path = Path(sys.executable)
    old_path = _old_path_for(exe_path)
    if old_path.exists():
        try:
            old_path.unlink()
        except OSError:
            pass
    root = exe_path.parent
    if not root.is_dir():
        return
    for stale in root.rglob("*.old"):
        try:
            stale.unlink()
        except OSError:
            pass


def replace_app_dir(new_dir: Path, *, current_dir: Path | None = None) -> None:
    """Vaihda one-dir-asennus paikallaan. Ei uudelleenkäynnistystä.

    Käyttää samaa Windows-kikkaa kuin :func:`replace_exe`, mutta TIEDOSTO
    KERRALLAAN: käytössä olevaa tiedostoa ei voi poistaa, mutta sen voi nimetä
    uudelleen — tämä pätee myös ladattuihin DLL:iin, ei vain exeen. Siksi
    hakemiston voi päivittää ilman että sovellus suljetaan ensin, ja ilman
    UAC:ia kun asennus on per-user.

    Vanhat tiedostot jäävät ``.old``-nimisiksi ja :func:`cleanup_old_exe`
    siivoaa ne seuraavalla käynnistyksellä.
    """
    if current_dir is None:
        if not is_running_bundled():
            raise RuntimeError(
                "replace_app_dir requires a frozen exe; running from source "
                "has nothing meaningful to swap."
            )
        current_dir = app_dir()
    if not new_dir.is_dir():
        raise FileNotFoundError(f"new app dir not found: {new_dir}")
    if not current_dir.is_dir():
        raise FileNotFoundError(f"current app dir not found: {current_dir}")

    for src in sorted(new_dir.rglob("*")):
        if src.is_dir():
            continue
        rel = src.relative_to(new_dir)
        dst = current_dir / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        if dst.exists():
            old = dst.with_name(dst.name + ".old")
            if old.exists():
                try:
                    old.unlink()
                except OSError:
                    pass
            dst.rename(old)
        shutil.move(str(src), str(dst))


def extract_zip(zip_path: Path, dest: Path) -> Path:
    """Pura päivityszip ja palauta sovellushakemisto sen sisältä.

    Zipissä voi olla juurihakemisto (``ordinate/``) tai tiedostot suoraan
    juuressa; molemmat kelpaavat."""
    import zipfile

    dest.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path) as zf:
        zf.extractall(dest)
    names = (APP_EXE, LEGACY_EXE)
    if any((dest / n).exists() for n in names):
        return dest
    for child in sorted(dest.iterdir()):
        if child.is_dir() and any((child / n).exists() for n in names):
            return child
    return dest


def replace_exe(
    new_exe: Path,
    *,
    current_exe: Path | None = None,
) -> None:
    """Swap ``current_exe`` for ``new_exe``. No restart.

    Caller quits the Qt event loop right after this returns so the OS
    releases the ``.old`` handle; the user reopens the app manually.
    That delay lets Defender finish scanning the freshly-written exe,
    side-stepping the "Failed to load Python DLL" race that auto-restart
    triggers on unsigned onefile PyInstaller builds.

    Raises :class:`RuntimeError` if not running inside a bundled exe.
    """
    if current_exe is None:
        if not is_running_bundled():
            raise RuntimeError(
                "replace_exe requires a frozen exe; running from source "
                "has nothing meaningful to swap."
            )
        current_exe = Path(sys.executable)

    if not new_exe.exists():
        raise FileNotFoundError(f"new exe not found: {new_exe}")
    if not current_exe.exists():
        raise FileNotFoundError(f"current exe not found: {current_exe}")

    old_path = _old_path_for(current_exe)
    if old_path.exists():
        try:
            old_path.unlink()
        except OSError:
            pass

    current_exe.rename(old_path)
    shutil.move(str(new_exe), str(current_exe))


def _build_update_helper_script(pid: int, staging_dir: Path, install_dir: Path,
                                exe_name: str = APP_EXE, wait_name: str | None = None) -> str:
    """Batch-skripti joka odottaa PID:n sulkeutumista, kopioi staging→install ja
    käynnistää appin uudelleen. Erillinen (puhdas) funktio → testattava."""
    exe = install_dir / exe_name
    wait_name = wait_name or exe_name
    # TÄYDET POLUT system-työkaluihin: apuri ei saa nojata PATH:iin (voi olla
    # saastunut esim. Git Bashin find.exe:llä) eikä käyttää `timeout`:ia (vaatii
    # konsolin, mutta apuri on DETACHED → ei konsolia → `ping` viiveeksi).
    sys32 = r"%SystemRoot%\System32"
    return (
        "@echo off\r\n"
        ":wait\r\n"
        f'{sys32}\\tasklist.exe /FI "PID eq {pid}" /NH 2>NUL | '
        f'{sys32}\\find.exe /I "{wait_name}" >NUL\r\n'
        "if not errorlevel 1 (\r\n"
        f"  {sys32}\\ping.exe -n 2 127.0.0.1 >NUL\r\n"
        "  goto wait\r\n"
        ")\r\n"
        f'{sys32}\\robocopy.exe "{staging_dir}" "{install_dir}" /E /IS /IT /R:5 /W:2 >NUL\r\n'
        f'start "" "{exe}"\r\n'
        'del "%~f0" >NUL 2>&1\r\n'
    )


def swap_app_dir_via_helper(new_app_dir: Path, install_dir: Path | None = None) -> None:
    """Vaihda one-dir-asennus APUPROSESSILLA joka odottaa appin sulkeutumista.

    In-place-vaihto (:func:`replace_app_dir`) EPÄONNISTUU käynnissä olevalle
    one-dir-appille: ``_internal/base_library.zip`` (PyInstallerin ajonaikainen
    tiedosto) on lukossa eikä sitä voi nimetä uudelleen → WinError 32 (kenttäbugi
    5.8.2026). Ratkaisu: kirjoita irrallinen batch-apuri joka ODOTTAA tämän prosessin
    sulkeutumista (silloin lukot vapautuvat), kopioi uusi versio paikalleen ja
    käynnistää appin uudelleen. Kutsuja sulkee appin heti tämän jälkeen."""
    inst = install_dir or app_dir()
    helper = Path(tempfile.gettempdir()) / f"ordinate_update_{os.getpid()}.cmd"
    launch = APP_EXE if (new_app_dir / APP_EXE).exists() else Path(sys.executable).name
    helper.write_text(_build_update_helper_script(os.getpid(), new_app_dir, inst, launch,
                                                  Path(sys.executable).name),
                      encoding="ascii")
    # CREATE_NO_WINDOW (piilokonsoli), EI DETACHED_PROCESS: apuri käyttää konsoli-
    # työkaluja (tasklist/find/robocopy), jotka JUMITTAVAT ilman konsolia. Piilo-
    # konsoli antaa niille konsolin näyttämättä ikkunaa. NEW_PROCESS_GROUP + apuri
    # jää eloon kun app sulkeutuu. (Todennettu hiekkalaatikossa 5.8.2026.)
    _CREATE_NO_WINDOW = 0x08000000
    _CREATE_NEW_PROCESS_GROUP = 0x00000200
    subprocess.Popen(
        ["cmd", "/c", str(helper)],
        creationflags=_CREATE_NO_WINDOW | _CREATE_NEW_PROCESS_GROUP,
        close_fds=True, cwd=tempfile.gettempdir(),
    )


def apply_downloaded_update(downloaded_path: Path, download_url: str) -> bool:
    """Ota ladattu päivitys käyttöön: valitse OIKEA vaihtotapa payloadin mukaan.
    Palauttaa True jos vaihto tapahtuu VASTA appin sulkeutuessa (one-dir, apuprosessi)
    → kutsujan on suljettava app; False jos vaihto on jo tehty (legacy one-file).

    KRIITTINEN historia: (1) GUI kutsui ennen aina replace_exe:ä → zip kirjoittui
    exe:ksi → "ei toimi tietokoneessasi". (2) Korjaus replace_app_dir:iin kaatui
    WinError 32:een koska base_library.zip on lukossa ajon aikana. → one-dir vaihto
    tehdään nyt apuprosessilla appin sulkeuduttua. replace_exe on VAIN legacy one-file."""
    if asset_is_zip(download_url):
        extract_dir = Path(tempfile.mkdtemp(prefix="ordinate_upd_"))
        app_root = extract_zip(downloaded_path, extract_dir)
        swap_app_dir_via_helper(app_root)
        return True
    replace_exe(downloaded_path)
    return False
