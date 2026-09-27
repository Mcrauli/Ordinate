"""Rosoinen maski pilkkoo kontuurit sirpaleiksi (mitattu: 1448/1513 segmenttia
alle 500 mm). Kokeile morfologiavariantteja YHDELLA ajolla ja raportoi kuinka
moni segmentti selviaa pituussuodatuksesta."""
from pathlib import Path
import numpy as np
import cv2

import ordinate.core.segmentation.wall_contour as WC
from _paths import DATA, OUTPUT  # portable dev-tool paths

_vm = WC.WallDetectorContour._vertical_mask


def _segments(binary, pixel_size, dp_tol, min_len):
    cs, _ = cv2.findContours(binary, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_NONE)
    n_seg = 0
    keep = 0
    total = 0.0
    for c in cs:
        approx = cv2.approxPolyDP(c, dp_tol / pixel_size, True)
        pts = [(float(p[0][0]), float(p[0][1])) for p in approx]
        for i in range(len(pts)):
            a, b = pts[i - 1], pts[i]
            L = float(np.hypot(b[0] - a[0], b[1] - a[1])) * pixel_size
            n_seg += 1
            if L >= min_len:
                keep += 1
                total += L
    return len(cs), n_seg, keep, total


def traced(self, clear, floor_z, ceil_z):
    binary, x0, y0 = _vm(self, clear, floor_z, ceil_z)
    if (ceil_z - floor_z) <= WC._VSLICE_TALL_MM:
        return binary, x0, y0
    px = self.pixel_size
    print(f"  [VARIANTIT] pixel={px:.0f} dp_tol={self.dp_tol:.0f} "
          f"min_len={self.min_wall_length:.0f} maskipikselia={int((binary>0).sum()):,}",
          flush=True)
    print(f"  {'variantti':22s} {'kontuurit':>9s} {'segm':>6s} {'>=min':>6s} {'yht.pituus m':>12s}",
          flush=True)
    for name, op in [
        ("nykyinen", None),
        ("open3", ("open", 3)),
        ("open5", ("open", 5)),
        ("open3+close9", ("oc", 3, 9)),
        ("open5+close9", ("oc", 5, 9)),
        ("open5+close15", ("oc", 5, 15)),
        ("median5", ("med", 5)),
        ("median5+close9", ("medc", 5, 9)),
    ]:
        b = binary.copy()
        if op is None:
            pass
        elif op[0] == "open":
            b = cv2.morphologyEx(b, cv2.MORPH_OPEN, np.ones((op[1], op[1]), np.uint8))
        elif op[0] == "oc":
            b = cv2.morphologyEx(b, cv2.MORPH_OPEN, np.ones((op[1], op[1]), np.uint8))
            b = cv2.morphologyEx(b, cv2.MORPH_CLOSE, np.ones((op[2], op[2]), np.uint8))
        elif op[0] == "med":
            b = cv2.medianBlur(b, op[1])
        elif op[0] == "medc":
            b = cv2.medianBlur(b, op[1])
            b = cv2.morphologyEx(b, cv2.MORPH_CLOSE, np.ones((op[2], op[2]), np.uint8))
        nc, ns, kp, tot = _segments(b, px, self.dp_tol, self.min_wall_length)
        print(f"  {name:22s} {nc:9d} {ns:6d} {kp:6d} {tot/1000:12.1f}", flush=True)
    return binary, x0, y0


WC.WallDetectorContour._vertical_mask = traced

from ordinate.core.pipeline import Pipeline, PipelineConfig  # noqa: E402

D = Path(str(DATA / "_rohbau/site_07/scene_07000/cloud.ply"))
cfg = PipelineConfig(detector="contour", auto_voxel=True, export_ifc=False,
                     export_dxf=False, export_qa=False, semantic_filter_mode="pointnet")
Pipeline(cfg).run_floors([D], Path(str(OUTPUT / "_mask_var")))
