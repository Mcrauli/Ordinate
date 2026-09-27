"""Matterport-aula: onko histogrammi- vai contour-detektori siellä oikea?

Aulassa EI ole ground truthia, joten ainoa käytettävissä oleva tuomari on
pilvi itse: piirretään mallin seinät vyötärökaistan pisteiden PÄÄLLE ja
katsotaan kumpi osuu. Ajaa saman tiedoston kahdesti — kerran nykyisellä
auto-reitityksellä, kerran `_looks_like_retail` patchattuna pois — ja
kirjoittaa molemmista kuvan sekä mitatut tuki/jatkuvuus-luvut.

Ajo: .venv/Scripts/python.exe data/_lobby_ab.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import ordinate.core.pipeline as PL  # noqa: E402
from ordinate.core.pipeline import Pipeline, PipelineConfig  # noqa: E402
from _paths import DOWNLOADS, OUTPUT  # noqa: E402

E57 = Path(str(DOWNLOADS / "matterport_lobby.e57"))


def run(tag: str, force_contour: bool):
    keep = (PL._looks_like_retail, PL._occupancy_area_m2)
    if force_contour:
        PL._looks_like_retail = lambda cloud: False
        PL._occupancy_area_m2 = lambda cloud: 0.0
    try:
        cfg = PipelineConfig(detector="contour", auto_voxel=True, export_ifc=False,
                             export_dxf=False, export_qa=False,
                             semantic_filter_mode="pointnet")
        out = Path(str(OUTPUT / f"_lobbyab_{tag}"))
        models = Pipeline(cfg).run_floors([E57], out)
    finally:
        PL._looks_like_retail, PL._occupancy_area_m2 = keep
    return models, out


_BAND_CACHE = Path("data/_lobby_band.npy")


def band_points(m):
    """Vyötärökaista pilvestä — sama kaista jolla tuki ja jatkuvuus mitataan."""
    if _BAND_CACHE.exists():
        return np.load(_BAND_CACHE)
    z0 = min(w["z_min"] for w in m["walls"])
    h = max(w["height"] for w in m["walls"])
    from ordinate.core.geometry.loader import read_e57_xyz_band
    pts = read_e57_xyz_band(E57, z0 + 0.30 * h, z0 + 0.70 * h, max_points=3_000_000)
    if pts is not None and len(pts):
        np.save(_BAND_CACHE, pts)
    return pts


def _extent(m, pad=2000.0):
    xy = np.array([p for w in m["walls"] for p in w["axis"]], float)
    return (xy[:, 0].min() - pad, xy[:, 0].max() + pad,
            xy[:, 1].min() - pad, xy[:, 1].max() + pad)


def draw(ax, m, pts, title, box):
    x0, x1, y0, y1 = box
    if pts is not None and len(pts):
        k = ((pts[:, 0] > x0) & (pts[:, 0] < x1) & (pts[:, 1] > y0) & (pts[:, 1] < y1))
        ax.scatter(pts[k, 0], pts[k, 1], s=0.35, c="0.62", linewidths=0, rasterized=True)
    ax.set_xlim(x0, x1)
    ax.set_ylim(y0, y1)
    for w in m["walls"]:
        (x0, y0), (x1, y1) = w["axis"]
        cont = w.get("continuity")
        col = "tab:red" if (cont is not None and cont < 0.30) else "tab:blue"
        ax.plot([x0, x1], [y0, y1], color=col, lw=2.0, solid_capstyle="round")
    ax.set_aspect("equal")
    ax.set_title(title, fontsize=9)
    ax.set_xticks([])
    ax.set_yticks([])


def summarise(name, m):
    print(f"\n== {name}: {len(m['walls'])} seinää")
    print(f"{'id':16s} {'pit':>7s} {'tuki':>5s} {'jatk':>5s} {'menet':10s}")
    for w in sorted(m["walls"], key=lambda x: -float(np.linalg.norm(
            np.array(x["axis"][1], float) - np.array(x["axis"][0], float)))):
        L = float(np.linalg.norm(np.array(w["axis"][1], float) - np.array(w["axis"][0], float)))
        s, c = w.get("support"), w.get("continuity")
        print(f"{w['id']:16s} {L/1000:6.1f}m "
              f"{'-' if s is None else f'{s:5.2f}'} "
              f"{'-' if c is None else f'{c:5.2f}'} {w['source']['method']:10s}")
    sup = [w["support"] for w in m["walls"] if w.get("support") is not None]
    con = [w["continuity"] for w in m["walls"] if w.get("continuity") is not None]
    if sup:
        print(f"   tuki mediaani {np.median(sup):.2f}   jatkuvuus mediaani {np.median(con):.2f}")


def main() -> None:
    if not E57.exists():
        print(f"PUUTTUU {E57}")
        return
    plot_only = "--plot-only" in sys.argv
    res = {}
    for tag, force in (("auto", False), ("contour", True)):
        out = Path(str(OUTPUT / f"_lobbyab_{tag}"))
        if not plot_only:
            _, out = run(tag, force)
        m = json.loads((out / "floor_00" / "model.json").read_text(encoding="utf-8"))
        res[tag] = (m, out)
        summarise("AUTO (nykyinen reititys)" if not force else "CONTOUR (pakotettu)", m)

    ex = [_extent(m) for m, _ in res.values()]
    box = (min(e[0] for e in ex), max(e[1] for e in ex),
           min(e[2] for e in ex), max(e[3] for e in ex))

    fig, axes = plt.subplots(1, 2, figsize=(16, 9))
    for ax, tag in zip(axes, ("auto", "contour")):
        m, _ = res[tag]
        draw(ax, m, band_points(res["auto"][0]),
             f"{tag}  —  {len(m['walls'])} seinää", box)
    fig.suptitle("Matterport-aula: auto-reititys vs pakotettu contour "
                 "(punainen = jatkuvuus < 0.30)", fontsize=10)
    fig.tight_layout()
    png = Path("data/_lobby_ab.png")
    fig.savefig(png, dpi=170)
    print(f"\nkuva: {png}")


if __name__ == "__main__":
    main()
