"""Allekirjoita julkaisun päivityspaketit ja tarkista allekirjoitukset.

Aja buildin ja installerin jälkeen, ennen `gh release create`:
  .venv/Scripts/python scripts/sign_release.py 0.9.37
Kirjoittaa dist/<paketti>.sig.json jokaiselle versioidulle paketille ja
tarkistaa ne heti ohjelman omalla tarkistuskoodilla ja upotetuilla avaimilla:
jos avain ei vastaa ohjelmaan upotettua, skripti kaatuu eikä julkaisua tehdä.
Avain: ORDINATE_SIGNING_KEY tai %USERPROFILE%/.ordinate/release_ed25519.pem.
"""
import hashlib
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
from ordinate.core.release_signing import sign, verify  # noqa: E402


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main(version: str) -> int:
    key_path = Path(os.environ.get("ORDINATE_SIGNING_KEY", Path.home() / ".ordinate" / "release_ed25519.pem"))
    if not key_path.exists():
        print(f"Allekirjoitusavainta ei löydy: {key_path}")
        return 2
    pem = key_path.read_bytes()
    dist = ROOT / "dist"
    targets = [dist / f"Ordinate-{version}.zip", dist / f"Ordinate-Setup-{version}.exe",
               dist / "Ordinate-Setup.exe", dist / "scan2bim-Setup.exe"]
    missing = [str(t) for t in targets if not t.exists()]
    if missing:
        print("Puuttuu: " + ", ".join(missing))
        return 2
    for path in targets:
        manifest = {"file": path.name, "version": version, "sha256": sha256(path),
                    "size": path.stat().st_size}
        doc = sign(manifest, pem)
        if verify(doc) != manifest:
            print(f"Tarkistus epäonnistui: {path.name}")
            return 1
        out = path.with_name(path.name + ".sig.json")
        out.write_text(json.dumps(doc, indent=1), encoding="utf-8")
        print(f"  {out.name}  sha256 {manifest['sha256'][:16]}…  {manifest['size']:,} tavua")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
