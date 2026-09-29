"""Kaikki ladatut Rohbau3D-scenet putken lapi + GT-mittaus (instanssi + tarkkuus).

Kaytto: _rohbau_wide.py <tag> [MODUULI:NIMI=arvo ...]
Tulos: data/output/_wide/<tag>.csv (jatkaa siita mihin jai). Asetukset
korvaavat moduulivakion ajon ajaksi, esim. ordinate.core.pipeline:_UNION_NORMALS=False.
"""
import csv
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
PY = sys.executable


def scenes():
    return sorted(p for p in (HERE / "_rohbau").glob("site_*/scene_*") if (p / "cloud.ply").exists())


def main(tag, *sets):
    out_root = ROOT / "data" / "output" / "_wide" / tag
    out_root.mkdir(parents=True, exist_ok=True)
    csv_path = out_root.parent / f"{tag}.csv"
    done = set()
    if csv_path.exists():
        done = {r["scene"] for r in csv.DictReader(open(csv_path, encoding="utf-8"))}
    new = not csv_path.exists()
    with open(csv_path, "a", newline="", encoding="utf-8") as fh:
        wr = csv.writer(fh)
        if new:
            wr.writerow(["scene", "walls", "gt_pre", "inst_found", "inst_total", "inst", "inside", "secs"])
        for sc in scenes():
            if sc.name in done:
                continue
            od = out_root / sc.name
            r = subprocess.run([PY, str(HERE / "_run_one_cfg.py"), str(sc / "cloud.ply"), str(od), *sets],
                               capture_output=True, text=True, encoding="utf-8", errors="replace")
            mj = od / "floor_00" / "model.json"
            secs = re.search(r"aika ([\d.]+)", r.stdout)
            if not mj.exists():
                wr.writerow([sc.name, "FAIL", "", "", "", "", "", ""]); fh.flush()
                print(sc.name, "FAIL", r.stderr[-300:], flush=True)
                continue
            q = subprocess.run([PY, str(HERE / "_rohbau_qa.py"), str(mj), str(sc / "coord.npy"), str(sc / "class.npy")],
                               capture_output=True, text=True, encoding="utf-8", errors="replace").stdout
            qi = subprocess.run([PY, str(HERE / "_wall_inst_qa.py"), str(mj), str(sc / "coord.npy"), str(sc / "class.npy")],
                                capture_output=True, text=True, encoding="utf-8", errors="replace").stdout
            pre = re.search(r"TARKKUUS.*?([\d.]+)", q)
            ins = re.search(r"INSTANSSIKATTAVUUS\s+(\d+)/(\d+)\s*=\s*([\d.]+)", qi)
            walls = re.search(r"mallin seinia (\d+)", qi)
            inside = re.search(r"JALANJALJEN SISALLA\s+(\d+/\d+)", qi)
            row = [sc.name, walls.group(1) if walls else "", pre.group(1) if pre else "",
                   *(ins.groups() if ins else ("", "", "")), inside.group(1) if inside else "",
                   secs.group(1) if secs else ""]
            wr.writerow(row); fh.flush()
            print(*row, flush=True)


if __name__ == "__main__":
    main(*sys.argv[1:])
