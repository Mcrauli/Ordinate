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

        # GUI EI AJA PUTKEA ITSE — se kaynnistaa taman komennon aliprosessina
        # (jaatymisen juurisyy oli in-process QThread). Jos `run` puuttuu tai
        # --config ei deserialisoidu, sovellus on rikki vaikka `convert` toimii.
        import dataclasses as _dc
        import json as _json
        from scan2bim.core.pipeline import PipelineConfig as _PC
        raw = {k: (str(v) if isinstance(v, Path) else v)
               for k, v in _dc.asdict(_PC()).items()}
        (tmp / "cfg.json").write_text(_json.dumps(raw), encoding="utf-8")
        r = subprocess.run([str(exe), "run", "--out", "out2",
                            "--config", "cfg.json", "scan.ply"], cwd=tmp,
                           capture_output=True, text=True, encoding="utf-8",
                           errors="replace")
        if r.returncode != 0:
            print("KAATUI: run (GUI:n ajopolku)")
            print(r.stdout[-3000:], r.stderr[-3000:])
            return 1
        floors = sorted((tmp / "out2").glob("floor_*/model.json"))
        if not floors:
            print("PUUTTUU: out2/floor_00/model.json — GUI ei saisi tulosta")
            return 1
        print(f"  run ok — {len(floors)} kerros(ta), GUI:n ajopolku toimii")

        # Tarkistuksen oppiminen lukee `Wall.evidence`n mallista. Mittaus on
        # try/except-suojattu putkessa, joten jos se kaatuu paketissa, ajo
        # onnistuu ja oppiminen kuolee hiljaa — GUI vain ei koskaan järjestä.
        import json as _json2
        walls = _json2.loads(floors[0].read_text(encoding="utf-8"))["walls"]
        with_ev = sum(1 for w in walls if w.get("evidence"))
        if walls and not with_ev:
            print(f"KAATUI: yhdelläkään {len(walls)} seinästä ei ole evidence-kenttää "
                  "— Tarkistus ei voi oppia korjauksista")
            return 1
        print(f"  evidence ok — {with_ev}/{len(walls)} seinää")

        # Ja loytaako GUI sen komennon TASTA paketista: `cli_command()`:n
        # frozen-haara ei aja kehityksessa koskaan.
        r = subprocess.run([str(exe), "selftest-paths"], cwd=tmp,
                           capture_output=True, text=True, encoding="utf-8",
                           errors="replace")
        if r.returncode != 0 or "POLUT OK" not in r.stdout:
            print("KAATUI: GUI ei loytaisi komentorivia paketista")
            print(r.stdout[-2000:], r.stderr[-2000:])
            return 1
        print("  " + r.stdout.strip().splitlines()[0])

        print("SAVUTESTI OK — pakattu tuote toimii repon ulkopuolella")
        return 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
