import json
from pathlib import Path
import numpy as np
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Polygon

P = np.load(r"C:\Users\lauri\scan2bim\data\_work_cloud.npy")
m = json.loads(Path(r"C:\Users\lauri\scan2bim\data\output\_v088_ifc\floor_00\model.json").read_text(encoding="utf-8"))
zf, zc = -25902.0, -23216.0
z = P[:, 2]
mid = P[(z > zf + 900) & (z < zf + 1900)]
flo = P[(z > zf - 150) & (z < zf + 250)]
cei = P[(z > zc - 250) & (z < zc + 150)]


def draw(ax, xlim=None, ylim=None, show_floor=True):
    if show_floor:
        ax.scatter(cei[::7, 0], cei[::7, 1], s=0.3, c="#ffd27f", linewidths=0, label="katto")
        ax.scatter(flo[::7, 0], flo[::7, 1], s=0.3, c="#7fdca0", linewidths=0, label="lattia")
    ax.scatter(mid[::3, 0], mid[::3, 1], s=0.4, c="0.35", linewidths=0, label="keskikaista")
    for w in m["walls"]:
        a = np.array(w["axis"][0], float); b = np.array(w["axis"][1], float)
        d = b - a; L = np.linalg.norm(d)
        if L < 1:
            continue
        u = d / L; n = np.array([-u[1], u[0]]); h = w["thickness"] / 2
        fp = w["source"]["method"] == "floorplan"
        ax.add_patch(Polygon([a+n*h, b+n*h, b-n*h, a-n*h], closed=True,
                             facecolor="#f22" if fp else "#26f", alpha=0.45,
                             edgecolor="#a00" if fp else "#04c", lw=1.4))
        ax.text(*(a+b)/2, w["id"].replace("wall_", ""), fontsize=7,
                color="#600" if fp else "#004", ha="center")
    ax.set_aspect("equal")
    if xlim: ax.set_xlim(*xlim)
    if ylim: ax.set_ylim(*ylim)


fig, axs = plt.subplots(1, 2, figsize=(22, 12))
draw(axs[0], show_floor=False)
axs[0].set_title("koko asunto (keskikaista) — punainen = floorplan/perimetri")
draw(axs[1], xlim=(-6300, -3300), ylim=(-7600, 2000))
axs[1].legend(markerscale=14, loc="upper right", fontsize=8)
axs[1].set_title("vasen reuna: lattia (vihrea) / katto (kelt) / keskikaista (musta)")
out = Path(r"C:\Users\lauri\scan2bim\data\_left_view.png")
plt.savefig(out, dpi=100, bbox_inches="tight")
print("saved", out)
