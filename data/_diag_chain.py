"""Mista kohdasta ketju katkeaa Rohbaulla: maski -> kontuurit -> segmentit ->
pituussuodatus -> parit -> akselit. Instrumentoi WallDetectorContour sisalta."""
from pathlib import Path
import numpy as np
import cv2

import scan2bim.core.segmentation.wall_contour as WC
from _paths import DATA, OUTPUT  # portable dev-tool paths

_vm = WC.WallDetectorContour._vertical_mask
_c2s = WC.WallDetectorContour._contours_to_segments
_mc = WC._merge_collinear
_gs = WC._group_segments
_ro = WC._regularize_orthogonal


def vm(self, clear, floor_z, ceil_z):
    b, x0, y0 = _vm(self, clear, floor_z, ceil_z)
    tall = (ceil_z - floor_z) > WC._VSLICE_TALL_MM
    print(f"  [1 maski] tall={tall} span={ceil_z-floor_z:.0f} pixel={self.pixel_size:.0f} "
          f"maskipikselia={int((b>0).sum()):,}", flush=True)
    cs, _ = cv2.findContours(b, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_NONE)
    lens = sorted((cv2.arcLength(c, True) * self.pixel_size for c in cs), reverse=True)
    print(f"  [2 kontuurit] n={len(cs)} pisimmat(mm)={[round(x) for x in lens[:6]]}", flush=True)
    return b, x0, y0


def c2s(self, contours, x_min, y_min):
    segs = _c2s(self, contours, x_min, y_min)
    if segs:
        ll = sorted((WC._dist(s[0], s[1]) for s in segs), reverse=True)
        print(f"  [3 segmentit] n={len(segs)} pisimmat={[round(x) for x in ll[:8]]} "
              f"min_wall_length={self.min_wall_length:.0f}", flush=True)
        keep = [s for s in segs if WC._dist(s[0], s[1]) >= self.min_wall_length]
        print(f"  [4 pituussuodatus] jaa {len(keep)}/{len(segs)}", flush=True)
    else:
        print("  [3 segmentit] n=0", flush=True)
    return segs


def mc(segments, min_t, max_t):
    out = _mc(segments, min_t, max_t)
    print(f"  [5 merge_collinear] {len(segments)} -> {len(out)}", flush=True)
    return out


def gs(segments, max_t):
    g, u = _gs(segments, max_t)
    print(f"  [6 parit] ryhmia={len(g)} parittomia={len(u)} (max_thickness={max_t:.0f})", flush=True)
    return g, u


def ro(axes, max_t, min_len):
    out = _ro(axes, max_t, min_len)
    print(f"  [7 regularize] {len(axes)} -> {len(out)} akselia", flush=True)
    return out


WC.WallDetectorContour._vertical_mask = vm
WC.WallDetectorContour._contours_to_segments = c2s
WC._merge_collinear = mc
WC._group_segments = gs
WC._regularize_orthogonal = ro

from scan2bim.core.pipeline import Pipeline, PipelineConfig  # noqa: E402

D = Path(str(DATA / "_rohbau/site_07"))
plys = [sc / "cloud.ply" for sc in sorted(p for p in D.iterdir() if p.is_dir())]
cfg = PipelineConfig(detector="contour", auto_voxel=True, export_ifc=False,
                     export_dxf=False, export_qa=False, semantic_filter_mode="pointnet")
models = Pipeline(cfg).run_floors(plys, Path(str(OUTPUT / "_rohbau_chain")))
for i, m in enumerate(models):
    print(f"LOPPU floor_{i}: walls={len(m.walls)} cols={len(m.columns)}")
