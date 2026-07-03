"""Toleranssilampokartta: piste->mallipinta -poikkeama seinittain + virhelahteiden erottelu.

    python data/_tol_heatmap.py <model.json> <skannaus.ply> <ulos.png>

Jokaiselle seinalle: pinnan pisteet (kaista akselin ymparilla), etaisyys lahimpaan
mallipintaan (akseli +- paksuus/2). Erottelu:
  A) snapatty toimituspaksuus vs mitattu paksuus (konventio, ei mittausvirhe)
  B) per-pinta plane-fit RMS = pilven oma kohinapohja (fysikaalinen raja)
  C) pinnan offset-virhe = mallipinnan etaisyys pistepinnan mediaanista (aito sijaintivirhe)
"""
import json, math, sys
import numpy as np, open3d as o3d
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

model_json = Path(sys.argv[1])
ply = Path(sys.argv[2])
out_png = Path(sys.argv[3])

m = json.loads(model_json.read_text(encoding="utf-8"))
pc = o3d.io.read_point_cloud(str(ply))
pts = np.asarray(pc.points)
if np.ptp(pts[:, 0]) < 100:
    pts = pts * 1000.0

floor_z = min((s["elevation"] for s in m["slabs"] if s["slab_type"] == "floor"), default=0.0)
ceil_z = max((s["elevation"] for s in m["slabs"] if s["slab_type"] == "ceiling"), default=2700.0)
zm = (pts[:, 2] > floor_z + 150) & (pts[:, 2] < ceil_z - 150)
P = pts[zm]
xy = P[:, :2]

fig = plt.figure(figsize=(20, 14))
gs = fig.add_gridspec(2, 2, height_ratios=[3, 1])
ax = fig.add_subplot(gs[0, :])

GRID = 40.0
x0, y0 = xy[:, 0].min(), xy[:, 1].min()
nx = int((xy[:, 0].max() - x0) / GRID) + 1
ny = int((xy[:, 1].max() - y0) / GRID) + 1
H, _, _ = np.histogram2d(xy[:, 0], xy[:, 1], bins=[nx, ny],
                         range=[[x0, x0 + nx * GRID], [y0, y0 + ny * GRID]])
ax.imshow(np.log1p(H.T), origin="lower", extent=[x0, x0 + nx * GRID, y0, y0 + ny * GRID],
          cmap="Greys", aspect="equal", alpha=.6)

cmap = plt.get_cmap("RdYlGn_r")
all_abs = []
rows = []
BIN = 200.0
for w in m["walls"]:
    a = np.array(w["axis"][0], float); b = np.array(w["axis"][1], float)
    ab = b - a; L = float(np.linalg.norm(ab))
    if L < 1:
        continue
    u = ab / L; n = np.array([-u[1], u[0]])
    th = float(w["thickness"])
    mth = float(w.get("measured_thickness") or th)
    rel = xy - a; t = rel @ u; perp = rel @ n
    band = (np.abs(perp) < max(th, 150) / 2 + 80) & (t > 0) & (t < L)
    if band.sum() < 200:
        ax.plot([a[0], b[0]], [a[1], b[1]], "-", lw=2, color="#999")
        continue
    s_perp = perp[band]; s_t = t[band]
    # etaisyys lahimpaan SNAPATTUUN pintaan
    d_snap = np.minimum(np.abs(s_perp - th / 2), np.abs(s_perp + th / 2))
    # etaisyys lahimpaan MITATTUUN pintaan
    d_meas = np.minimum(np.abs(s_perp - mth / 2), np.abs(s_perp + mth / 2))
    # pintakohtainen analyysi: dominoiva pinta = se puoli jolla enemman pisteita
    side = s_perp > 0
    dom = side if side.sum() >= (~side).sum() else ~side
    surf_perp = s_perp[dom]
    med_off = float(np.median(surf_perp))
    # kohinapohja: pisteiden hajonta oman mediaanitasonsa ympärillä (60mm ikkuna)
    core = surf_perp[np.abs(surf_perp - med_off) < 60]
    noise_rms = float(np.sqrt(np.mean((core - np.median(core)) ** 2))) if len(core) > 50 else float("nan")
    # aito pintasijaintivirhe: mallipinta vs pistepinnan mediaani
    model_face = th / 2 if med_off > 0 else -th / 2
    model_face_m = mth / 2 if med_off > 0 else -mth / 2
    face_err_snap = abs(med_off - model_face)
    face_err_meas = abs(med_off - model_face_m)
    rows.append((w["id"], L, th, mth, float(np.median(d_snap)), float(np.median(d_meas)),
                 face_err_snap, face_err_meas, noise_rms))
    all_abs.append(d_snap)
    # lampokartta: binita akselia pitkin, vari = median d_snap
    nb = max(int(L / BIN), 1)
    for k in range(nb):
        mm_ = (s_t >= k * L / nb) & (s_t < (k + 1) * L / nb)
        if mm_.sum() < 20:
            continue
        v = float(np.median(d_snap[mm_]))
        c = cmap(min(v / 20.0, 1.0))
        p0 = a + u * (k * L / nb); p1 = a + u * ((k + 1) * L / nb)
        ax.plot([p0[0], p1[0]], [p0[1], p1[1]], "-", lw=5, color=c, solid_capstyle="butt")

sm = plt.cm.ScalarMappable(cmap=cmap, norm=plt.Normalize(0, 20))
plt.colorbar(sm, ax=ax, label="median |piste - mallipinta| mm (per 200mm segmentti)", shrink=.6)
ax.set_title(f"{model_json.parent.name}: pinta-poikkeamalampokartta (vihrea=0mm, punainen>=20mm)")
ax.set_aspect("equal")

ax2 = fig.add_subplot(gs[1, 0])
if all_abs:
    allv = np.concatenate(all_abs)
    ax2.hist(allv, bins=np.arange(0, 50, 1), color="#468")
    for q, c in ((50, "k"), (95, "r")):
        v = np.percentile(allv, q)
        ax2.axvline(v, color=c, ls="--", label=f"p{q}={v:.1f}mm")
    ax2.legend(); ax2.set_xlabel("mm"); ax2.set_title("|piste - mallipinta| jakauma (kaikki seinat)")

ax3 = fig.add_subplot(gs[1, 1]); ax3.axis("off")
hdr = f"{'seina':12s} {'L':>5s} {'th':>4s} {'mth':>6s} {'d.snap':>7s} {'d.mit':>6s} {'pinta.snap':>10s} {'pinta.mit':>9s} {'kohina':>6s}"
lines = [hdr]
for r in rows:
    lines.append(f"{r[0]:12s} {r[1]:5.0f} {r[2]:4.0f} {r[3]:6.1f} {r[4]:7.1f} {r[5]:6.1f} {r[6]:10.1f} {r[7]:9.1f} {r[8]:6.1f}")
ax3.text(0, 1, "\n".join(lines), family="monospace", fontsize=9, va="top")

plt.tight_layout()
plt.savefig(str(out_png), dpi=85, bbox_inches="tight")
print(f"saved {out_png}")
print("\n" + "\n".join(lines))
print("\nSarakkeet: d.snap = median-etaisyys snapattuun pintaan; d.mit = mitattuun pintaan;")
print("pinta.snap/mit = mallipinnan virhe pistepinnan mediaanista; kohina = pilven RMS pinnan ymparilla.")
