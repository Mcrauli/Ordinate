"""Regressiomatriisi: KAIKKI aineistot, sama mittari, yksi taulukko.

Jokainen tamankin projektin korjaus on tahan asti arvioitu yhta aineistoa
vasten kerrallaan, ja siksi jokainen niista on kaatunut toisella. `_rohbau_all`
kattaa vain Rohbaun, jolla on GT; asiakaskohteilla GT:ta ei ole eika tule.

`_wall_coverage_nogt` mittaa kattavuuden pilven omista pystypinnoista, joten
sama luku saadaan mista tahansa skannista. Tama ajaa putken jokaiselle
aineistolle ja tulostaa rivit rinnakkain — ja tallentaa tuloksen JSONiin,
jotta seuraava ajo voi verrata siihen ja nayttaa MIKA muuttui.

  _matrix.py                      aja kaikki, tallenna data/_matrix_last.json
  _matrix.py --baseline t.json    aja kaikki ja vertaa tiedostoon
  _matrix.py --only kellari,apt   aja vain nimetyt

Rohbau-scenet mitataan LISAKSI GT:lla, koska se on ainoa paikka jossa
GT-vapaan mittarin voi tarkistaa.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
PY = str(Path(sys.executable))
OUT = ROOT / "data" / "output" / "_matrix"

# nimi -> (pilvi, gt-hakemisto tai None)
DATASETS: dict[str, tuple[str, str | None]] = {
    "rohbau_07000": ("data/_rohbau/site_07/scene_07000/cloud.ply", "data/_rohbau/site_07/scene_07000"),
    "rohbau_07001": ("data/_rohbau/site_07/scene_07001/cloud.ply", "data/_rohbau/site_07/scene_07001"),
    "rohbau_07002": ("data/_rohbau/site_07/scene_07002/cloud.ply", "data/_rohbau/site_07/scene_07002"),
    "rohbau_07003": ("data/_rohbau/site_07/scene_07003/cloud.ply", "data/_rohbau/site_07/scene_07003"),
    "rohbau_07004": ("data/_rohbau/site_07/scene_07004/cloud.ply", "data/_rohbau/site_07/scene_07004"),
    "kellari":      ("data/kellari_20mm.ply", None),
    "apt":          ("data/_cache_apt.ply", None),
    "retail_s":     ("data/_retail_s.ply", None),
    "retail_l":     ("data/_retail_l.ply", None),
    "3dses":        ("data/_3dses/_3dses_cloud.ply", None),
    "test_room":    ("data/raw/test_room.ply", None),
    "synth":        ("data/_synth.ply", None),
}


def _run_pipeline(name: str, cloud: Path, out_dir: Path) -> Path | None:
    r = subprocess.run(
        [PY, str(HERE / "_run_one.py"), str(cloud), str(out_dir)],
        capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        print(f"    ajo kaatui: {r.stderr.strip().splitlines()[-1] if r.stderr.strip() else '?'}")
        return None
    model = out_dir / "floor_00" / "model.json"
    return model if model.exists() else None


def _render(name: str, model: Path, cloud: Path) -> None:
    """Piirra malli JOKA ajosta — luku ei kerro onko seina oikeassa paikassa.

    Kellarin kattavuus 0.310 nayttI voitolta kunnes zoom-kuva paljasti etta
    seinat oli vedetty pilven sirpaleiden YLI: 116 seinaa 30x30 metrissa,
    ristiin toistensa lapi. Sita ei nakynyt yhdessakaan mittarissa.
    """
    out = OUT / name
    for script, args, tag in (
        ("_model_view.py", [], "yleis"),
        ("_zoom_view.py", [], "zoom"),
    ):
        try:
            subprocess.run([PY, str(HERE / script), str(model), str(cloud),
                            str(out / f"_{tag}.png")] + args,
                           capture_output=True, text=True, timeout=900)
        except Exception:  # noqa: BLE001 — kuva ei saa kaataa mittausta
            pass


def _nogt(model: Path, cloud: Path) -> dict:
    r = subprocess.run([PY, str(HERE / "_wall_coverage_nogt.py"), str(model), str(cloud)],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    cov = re.search(r"KATTAVUUS.*?([\d.]+)", r.stdout)
    pre = re.search(r"TARKKUUS.*?([\d.]+)", r.stdout)
    pts = re.search(r"seinamaisia pystypintapisteita ([\d\s,]+)", r.stdout)
    return {"cov": float(cov.group(1)) if cov else None,
            "pre": float(pre.group(1)) if pre else None,
            "wallish": int(pts.group(1).replace(",", "").replace(" ", "")) if pts else None}


def _gt(model: Path, gt_dir: Path) -> dict:
    """GT-luvut kahdella nimittajalla — PISTEILLA ja INSTANSSEILLA.

    Pistekattavuus yksin valehtelee, ja se on mitattu: perimetriseinat omistavat
    valtaosan pisteista, joten valiseinat voivat puuttua ilman etta luku liikkuu.
    3.9.2026 pistekattavuus oli 0.76-0.92 samaan aikaan kun instanssikattavuus
    oli 0.41-0.67 — putki loysi noin puolet seinista ja mittari sanoi 86 %.

    GT-vapaa mittari ei voi nayttaa tata eroa lainkaan (`_metric_blindness.py`:
    kaikkien lyhyiden seinien lisaaminen taydelliseen malliin nostaa sen
    kattavuutta 0.02 ja LASKEE sen F1:ta), joten instanssiluku on se sarake joka
    kertoo auttoiko muutos. GT-vapaa sarake kertoo vain huononiko jokin.
    """
    r = subprocess.run([PY, str(HERE / "_rohbau_qa.py"), str(model),
                        str(gt_dir / "coord.npy"), str(gt_dir / "class.npy")],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    cov = re.search(r"KATTAVUUS.*?([\d.]+)", r.stdout)
    pre = re.search(r"TARKKUUS.*?([\d.]+)", r.stdout)
    out = {"gt_cov": float(cov.group(1)) if cov else None,
           "gt_pre": float(pre.group(1)) if pre else None}
    ri = subprocess.run([PY, str(HERE / "_wall_inst_qa.py"), str(model),
                         str(gt_dir / "coord.npy"), str(gt_dir / "class.npy"),
                         str(gt_dir / "instance.npy")],
                        capture_output=True, text=True, encoding="utf-8", errors="replace")
    inst = re.search(r"INSTANSSIKATTAVUUS\s+\d+/\d+\s*=\s*([\d.]+)", ri.stdout)
    out["gt_inst"] = float(inst.group(1)) if inst else None
    return out


def main() -> None:
    args = sys.argv[1:]
    baseline = None
    only = None
    if "--baseline" in args:
        baseline = json.loads(Path(args[args.index("--baseline") + 1]).read_text(encoding="utf-8"))
    if "--only" in args:
        only = set(args[args.index("--only") + 1].split(","))

    OUT.mkdir(parents=True, exist_ok=True)
    results: dict[str, dict] = {}
    for name, (rel, gt) in DATASETS.items():
        if only and name not in only:
            continue
        cloud = ROOT / rel
        if not cloud.exists():
            print(f"{name:14s} ei tiedostoa: {rel}")
            continue
        t0 = time.time()
        print(f"{name:14s} ajetaan...", flush=True)
        model = _run_pipeline(name, cloud, OUT / name)
        if model is None:
            results[name] = {"error": "ei mallia"}
            continue
        row = _nogt(model, cloud)
        if gt is not None:
            row.update(_gt(model, ROOT / gt))
        _render(name, model, cloud)
        m = json.loads(model.read_text(encoding="utf-8"))
        row["walls"] = len(m["walls"])
        row["openings"] = len(m["openings"])
        row["secs"] = round(time.time() - t0)
        results[name] = row
        print(f"    kattavuus {row['cov']}  tarkkuus {row['pre']}  seinia {row['walls']}"
              f"  {row['secs']} s", flush=True)

    print(f"\n{'aineisto':14s} {'kattav':>7s} {'tarkk':>6s} {'seinia':>7s} {'aukot':>6s}"
          f" {'GTkatt':>7s} {'GTtark':>7s} {'GTinst':>7s}   muutos")
    for name, r in results.items():
        if "error" in r:
            print(f"{name:14s}  {r['error']}")
            continue
        delta = ""
        if baseline and name in baseline and "cov" in baseline[name]:
            b = baseline[name].get("cov")
            if b is not None and r["cov"] is not None:
                d = r["cov"] - b
                delta = f"{d:+.3f}" + ("  HUONOMPI" if d < -0.005 else
                                       ("  parempi" if d > 0.005 else ""))
            bi = baseline[name].get("gt_inst")
            if bi is not None and r.get("gt_inst") is not None:
                di = r["gt_inst"] - bi
                delta += f"   inst {di:+.3f}" + (
                    "  HUONOMPI" if di < -0.005 else
                    ("  PAREMPI" if di > 0.005 else ""))
        print(f"{name:14s} {r['cov'] if r['cov'] is not None else '-':>7} "
              f"{r['pre'] if r['pre'] is not None else '-':>6} {r['walls']:>7d} "
              f"{r['openings']:>6d} {r.get('gt_cov', '-'):>7} {r.get('gt_pre', '-'):>7} "
              f"{r.get('gt_inst', '-'):>7}   {delta}")

    path = ROOT / "data" / "_matrix_last.json"
    path.write_text(json.dumps(results, indent=1), encoding="utf-8")
    print(f"\ntallennettu {path}")


if __name__ == "__main__":
    main()
