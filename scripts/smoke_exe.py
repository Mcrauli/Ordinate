"""Savutesti PAKATULLE tuotteelle: aja se repon ULKOPUOLELTA.

Nelja vikaa loytyi 9.9.2026 pelkastaan silla etta pakattua exea ajettiin
ensimmaista kertaa automaattisesti: malli olisi voinut jaada bundlaamatta
hiljaa, komentorivia ei ollut paketissa lainkaan, `cli.py`:sta puuttui
`__main__`-vartija (toimi vain `pip install -e`:n luoman kaynnistimen kautta)
ja Click kaatui `UnicodeEncodeError`iin cp1252-konsolissa. Yksikaan niista ei
nay testeissa eika matriisissa, koska kumpikaan ei aja rakennettua tuotetta.

Tarkistaa myos ettei semanttinen suodatin ole pudonnut geometriseen
fallbackiin — se on hiljainen laadun heikennys eika virhe.

Aja buildin jalkeen:  .venv/Scripts/python scripts/smoke_exe.py
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    dist = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "dist" / "scan2bim"
    cloud = Path(sys.argv[2]) if len(sys.argv) > 2 else ROOT / "data" / "raw" / "test_room.ply"
    if not (dist / "scan2bim-cli.exe").exists():
        print(f"EI LOYDY: {dist / 'scan2bim-cli.exe'} — aja build ensin")
        return 2
    if not cloud.exists():
        print(f"EI LOYDY: {cloud}")
        return 2

    # Paketin on sisallettava MOLEMMAT exet ja malli. GUI on se mita asiakas
    # kayttaa; CLI on se mita voi testata automaattisesti. Jos toinen puuttuu,
    # paketti on vajaa vaikka konversio onnistuisi.
    missing = [str(f) for f in (dist / "scan2bim.exe",
                                dist / "_internal" / "models" / "s3dis_pointnet.onnx")
               if not f.exists()]
    if missing:
        print("PUUTTUU PAKETISTA: " + ", ".join(missing))
        return 1

    tmp = Path(tempfile.mkdtemp(prefix="s2b_smoke_"))
    try:
        shutil.copytree(dist, tmp / "app")
        shutil.copy(cloud, tmp / "scan.ply")
        exe = tmp / "app" / "scan2bim-cli.exe"

        r = subprocess.run([str(exe), "--help"], cwd=tmp, capture_output=True,
                           text=True, encoding="utf-8", errors="replace")
        if r.returncode != 0 or "convert" not in r.stdout:
            print("KAATUI: --help"); print(r.stdout[-2000:], r.stderr[-2000:])
            return 1
        print("  --help ok")

        # PAKOTA semanttinen suodatin: `auto` ohittaa sen pienessa tilassa,
        # jolloin mallin latautumista ei testata lainkaan ja fallback-tarkistus
        # alla on tyhja. Tama on koko testin tarkein rivi.
        r = subprocess.run([str(exe), "convert", "scan.ply", "out",
                            "--semantic-filter", "pointnet"], cwd=tmp,
                           capture_output=True, text=True, encoding="utf-8",
                           errors="replace")
        if r.returncode != 0:
            print("KAATUI: convert"); print(r.stdout[-3000:], r.stderr[-3000:])
            return 1
        for f in ("model.json", "model.ifc", "model.dxf"):
            if not (tmp / "out" / f).exists():
                print(f"PUUTTUU: out/{f}")
                return 1
        print("  convert ok — model.json, model.ifc, model.dxf")

        log = r.stdout
        if "PointNet-fallback" in log:
            print("VAROITUS: semanttinen suodatin putosi geometriseen "
                  "fallbackiin — malli ei ole paketissa tai se ei latatunut")
            return 1
        if "Semanttinen suodatin" not in log:
            print("KAATUI: semanttista suodatinta ei ajettu vaikka se pakotettiin")
            return 1
        print("  semanttinen suodatin latasi mallin paketista")
        print("SAVUTESTI OK — pakattu tuote toimii repon ulkopuolella")
        return 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
