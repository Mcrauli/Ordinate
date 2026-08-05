"""Projisoi detektoitu malli E57:n kalibroitujen valokuvien PAALLE.

Tama on tarkastustyokalu jolla nahdaan OIKEASTI ollaanko lahella totuutta:
skanneri tallentaa poseineen kalibroidut kuvat (Matterport: 6 skybox-sivua per
asema), joten mallin seinat/aukot/pilarit voi projisoida niiden paalle ja
verrata suoraan siihen mita kamera nayki (Cintoo-tyylinen tarkistus).

Kaytto:
  python data/_photo_overlay.py <e57> <model.json> <out_dir> [img_idx|all]

Kirjoittaa <out_dir>/overlay_<idx>.png. Seinat syaani, aukot punainen, pilarit
keltainen. Ilman idx: piirtaa kaikki kuvat joissa nakyy mallia.
"""
import sys
import json
from pathlib import Path

import numpy as np
import pye57
from PIL import Image, ImageDraw


def _quat_to_R(w, x, y, z):
    return np.array([
        [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
        [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
        [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
    ])


class Camera:
    """E57 pinhole-kamera: maailma (mm) -> kuvapikselit."""
    def __init__(self, image_node):
        ph = image_node["pinholeRepresentation"]
        self.w = ph["imageWidth"].value()
        self.h = ph["imageHeight"].value()
        self.fl = ph["focalLength"].value()
        self.pw = ph["pixelWidth"].value()
        self.ph_ = ph["pixelHeight"].value()
        self.ppx = ph["principalPointX"].value()
        self.ppy = ph["principalPointY"].value()
        pose = image_node["pose"]
        rot, tr = pose["rotation"], pose["translation"]
        q = [rot[k].value() for k in ("w", "x", "y", "z")]
        self.R = _quat_to_R(*q)
        self.T = np.array([tr[k].value() for k in ("x", "y", "z")]) * 1000.0
        self.name = image_node["name"].value()
        blob = ph["jpegImage"]
        n = blob.byteCount()
        buf = bytearray(n)
        blob.read(buf, 0, n)
        self._jpeg = bytes(buf)

    def image(self):
        import io
        return Image.open(io.BytesIO(self._jpeg)).convert("RGB")

    def to_cam(self, P):
        return (np.asarray(P, float) - self.T) @ self.R      # R^T (Pw - T)

    def project(self, P):
        """Nx3 maailma -> (Nx2 pikselit, Nx bool front)."""
        Pc = self.to_cam(P)
        zc = Pc[:, 2]
        front = zc > 1.0
        u = self.ppx + self.fl * Pc[:, 0] / (zc * self.pw)
        v = self.ppy + self.fl * Pc[:, 1] / (zc * self.ph_)
        return np.column_stack([u, v]), front

    def depth_of(self, P):
        """Nx3 maailma -> Nx kameran z-syvyys (mm), inf jos takana."""
        zc = self.to_cam(np.atleast_2d(P))[:, 2]
        zc[zc <= 1.0] = np.inf
        return zc

    def build_depth_buffer(self, cloud_pts, cell=8):
        """Karkea depth-buffer pilvesta: min-z per (cell x cell) pikseliruutu."""
        uv, front = self.project(cloud_pts)
        Pc = self.to_cam(cloud_pts)
        zc = Pc[:, 2]
        u, v = uv[:, 0], uv[:, 1]
        ok = front & (u >= 0) & (u < self.w) & (v >= 0) & (v < self.h)
        gw = int(np.ceil(self.w / cell)); gh = int(np.ceil(self.h / cell))
        buf = np.full((gh, gw), np.inf)
        gi = (v[ok] / cell).astype(int); gj = (u[ok] / cell).astype(int)
        z = zc[ok]
        np.minimum.at(buf, (gi, gj), z)
        self._depth = buf; self._cell = cell
        return buf

    def occluded(self, world_pt, margin=250.0):
        """True jos world_pt on lahemman pilvipinnan takana (piilossa)."""
        if getattr(self, "_depth", None) is None:
            return False
        Pc = self.to_cam(np.atleast_2d(world_pt))[0]
        if Pc[2] <= 1.0:
            return True
        u = self.ppx + self.fl * Pc[0] / (Pc[2] * self.pw)
        v = self.ppy + self.fl * Pc[1] / (Pc[2] * self.ph_)
        gi = int(v / self._cell); gj = int(u / self._cell)
        if gi < 0 or gj < 0 or gi >= self._depth.shape[0] or gj >= self._depth.shape[1]:
            return False
        d = self._depth[gi, gj]
        return np.isfinite(d) and Pc[2] > d + margin

    def clip_project_segment(self, a, b):
        """Yksi jana a->b (mm) near-plane-leikattuna -> [(u,v),(u,v)] tai None."""
        a = np.asarray(a, float); b = np.asarray(b, float)
        za = self.to_cam(a[None])[0, 2]
        zb = self.to_cam(b[None])[0, 2]
        eps = 50.0
        if za < eps and zb < eps:
            return None
        if za < eps:
            t = (eps - za) / (zb - za); a = a + t * (b - a)
        elif zb < eps:
            t = (eps - zb) / (za - zb); b = b + t * (a - b)
        uv, _ = self.project(np.vstack([a, b]))
        return uv


def load_cameras(e57_path):
    f = pye57.E57(str(e57_path))
    return [Camera(f.root["images2D"][i]) for i in range(len(f.root["images2D"]))]


def _wall_edges(wall):
    (x0, y0), (x1, y1) = wall["axis"][0], wall["axis"][1]
    z0 = wall.get("z_min", 0.0); z1 = z0 + wall["height"]
    a = np.array([x0, y0, z0]); b = np.array([x1, y1, z0])
    c = np.array([x1, y1, z1]); d = np.array([x0, y0, z1])
    return [(a, b), (b, c), (c, d), (d, a)]


def _opening_edges(op, wall_by_id):
    w = wall_by_id.get(op["wall_id"])
    if w is None:
        return []
    (x0, y0), (x1, y1) = w["axis"][0], w["axis"][1]
    d = np.array([x1 - x0, y1 - y0]); L = np.linalg.norm(d)
    if L < 1:
        return []
    u = d / L
    a0 = op["position_along"]; a1 = a0 + op["width"]
    zf = w.get("z_min", 0.0)
    z0 = zf + op["sill_height"]; z1 = z0 + op["opening_height"]
    p_a0 = np.array([x0, y0]) + u * a0
    p_a1 = np.array([x0, y0]) + u * a1
    A = np.array([p_a0[0], p_a0[1], z0]); B = np.array([p_a1[0], p_a1[1], z0])
    C = np.array([p_a1[0], p_a1[1], z1]); D = np.array([p_a0[0], p_a0[1], z1])
    return [(A, B), (B, C), (C, D), (D, A)]


def _column_edges(col):
    x, y = col["location"]; z0 = col["base_z"]; z1 = z0 + col["height"]
    pr = col["profile"]; wx = pr["width"] / 2; wy = pr["depth"] / 2
    corners = [(-wx, -wy), (wx, -wy), (wx, wy), (-wx, wy)]
    edges = []
    for i in range(4):
        cx, cy = corners[i]; nx, ny = corners[(i + 1) % 4]
        bot0 = np.array([x + cx, y + cy, z0]); bot1 = np.array([x + nx, y + ny, z0])
        top0 = np.array([x + cx, y + cy, z1]); top1 = np.array([x + nx, y + ny, z1])
        edges += [(bot0, bot1), (top0, top1), (bot0, top0)]
    return edges


def draw_overlay(cam, model, wall_by_id, cloud_pts=None):
    img = cam.image()
    dr = ImageDraw.Draw(img)
    W, H = cam.w, cam.h
    occ = cloud_pts is not None
    if occ:
        cam.build_depth_buffer(cloud_pts)

    def draw_edges(edges, color, width):
        drew = 0
        for a, b in edges:
            a = np.asarray(a, float); b = np.asarray(b, float)
            # jaa jana osiin -> syvyystesti pilvipintaa vasten (piilota peitetyt)
            nseg = 24
            prev = None
            for t in np.linspace(0.0, 1.0, nseg + 1):
                p = a + t * (b - a)
                vis = not (occ and cam.occluded(p))
                uv = cam.clip_project_segment(p, p + 1e-3) if vis else None
                cur = None
                if vis and uv is not None:
                    u0, v0 = uv[0]
                    if -W < u0 < 2 * W and -H < v0 < 2 * H:
                        cur = (u0, v0)
                if prev is not None and cur is not None:
                    dr.line([prev, cur], fill=color, width=width); drew += 1
                prev = cur
        return drew

    n = 0
    for w in model["walls"]:
        n += draw_edges(_wall_edges(w), (0, 200, 255), 3)
    for op in model.get("openings", []):
        draw_edges(_opening_edges(op, wall_by_id), (255, 40, 40), 6)
    for col in model.get("columns", []):
        draw_edges(_column_edges(col), (255, 220, 0), 3)
    return img, n


def main():
    e57 = Path(sys.argv[1]); model_path = Path(sys.argv[2]); out_dir = Path(sys.argv[3])
    which = sys.argv[4] if len(sys.argv) > 4 else "all"
    out_dir.mkdir(parents=True, exist_ok=True)
    model = json.load(open(model_path))
    wall_by_id = {w["id"]: w for w in model["walls"]}
    cams = load_cameras(e57)
    # pilvi syvyyskulkua varten (piilota mallireunat lahemman pinnan takaa)
    from scan2bim.core.geometry.loader import load_point_cloud
    cloud = np.asarray(load_point_cloud(e57).points)
    if len(cloud) > 12_000_000:
        cloud = cloud[:: len(cloud) // 12_000_000]
    print(f"depth-pilvi: {len(cloud)} pistetta")
    idxs = range(len(cams)) if which == "all" else [int(which)]
    for i in idxs:
        img, n = draw_overlay(cams[i], model, wall_by_id, cloud_pts=cloud)
        if which == "all" and n == 0:
            continue
        out = out_dir / f"overlay_{i:02d}.png"
        img.save(out)
        print(f"[{i:02d}] {cams[i].name:14s} malliviivoja={n} -> {out}")


if __name__ == "__main__":
    main()
