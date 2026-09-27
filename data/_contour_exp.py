"""Kokeile lattiakontuurin variantteja: kumpi tuottaa VALIDIN monikulmion
oikealla pinta-alalla. Ei muuta lahdekoodia."""
import numpy as np, cv2
from shapely.geometry import Polygon

P = np.load(r"C:\Users\lauri\scan2bim\data\_work_cloud.npy")
ZF, ZC = -25902.0, -23216.0
G = 25.0


def mask_from(pts, z, band):
    m = np.abs(pts[:, 2] - z) < band
    return pts[m, :2]


def build(sel_list, close_px, dil_px, fill_holes):
    allp = np.vstack(sel_list)
    x0, y0 = allp[:, 0].min(), allp[:, 1].min()
    cols = int((allp[:, 0].max() - x0) / G) + 2
    rows = int((allp[:, 1].max() - y0) / G) + 2
    acc = np.zeros((rows, cols), np.uint8)
    for s in sel_list:
        h, _, _ = np.histogram2d(s[:, 0], s[:, 1], bins=[cols, rows],
                                 range=[[x0, x0 + cols * G], [y0, y0 + rows * G]])
        acc |= (h.T >= 1).astype(np.uint8)
    b = acc * 255
    if close_px:
        b = cv2.morphologyEx(b, cv2.MORPH_CLOSE, np.ones((close_px, close_px), np.uint8))
    if dil_px:
        b = cv2.dilate(b, np.ones((dil_px, dil_px), np.uint8))
    if fill_holes:
        ff = b.copy()
        pad = cv2.copyMakeBorder(ff, 1, 1, 1, 1, cv2.BORDER_CONSTANT, value=0)
        m2 = np.zeros((pad.shape[0] + 2, pad.shape[1] + 2), np.uint8)
        cv2.floodFill(pad, m2, (0, 0), 255)
        outside = pad[1:-1, 1:-1]
        b = np.where(outside == 0, 255, b).astype(np.uint8)
    return b, x0, y0


def contours(b, x0, y0, eps_abs=None, eps_rel=None):
    cs, _ = cv2.findContours(b, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    out = []
    for c in sorted(cs, key=cv2.contourArea, reverse=True):
        if cv2.contourArea(c) * G * G < 1.5e6:
            continue
        eps = eps_abs / G if eps_abs else eps_rel * cv2.arcLength(c, True)
        ap = cv2.approxPolyDP(c, eps, True)
        poly = [(x0 + float(p[0][0]) * G, y0 + float(p[0][1]) * G) for p in ap]
        if len(poly) >= 3:
            out.append(poly)
    return out


flo8 = mask_from(P, ZF, 8.0)
flo40 = mask_from(P, ZF, 40.0)
cei40 = mask_from(P, ZC, 40.0)
print(f"pisteet: lattia+-8={len(flo8)} lattia+-40={len(flo40)} katto+-40={len(cei40)}")

variants = [
    ("V0 nykyinen (lattia+-8, close5, dil3, eps=0.008*arc)", [flo8], 5, 3, False, None, 0.008),
    ("V1 = V0 mutta eps=150mm absoluuttinen",                [flo8], 5, 3, False, 150.0, None),
    ("V2 = V1 + lattiakaista +-40mm",                        [flo40], 5, 3, False, 150.0, None),
    ("V3 = V2 + closing 400mm (16px)",                       [flo40], 16, 3, False, 150.0, None),
    ("V4 = V3 + reikien tayttö",                             [flo40], 16, 3, True, 150.0, None),
    ("V5 = V4 + katto unioniin",                       [flo40, cei40], 16, 3, True, 150.0, None),
    ("V6 = pelkka katto +-40, close5, fill",                 [cei40], 5, 3, True, 150.0, None),
]
for name, sels, ck, dk, fill, ea, er in variants:
    b, x0, y0 = build(sels, ck, dk, fill)
    ps = contours(b, x0, y0, ea, er)
    print(f"\n{name}")
    if not ps:
        print("   ei kontuureja"); continue
    for i, p in enumerate(ps):
        sp = Polygon(p)
        print(f"   #{i} verts={len(p):3d} area={sp.area/1e6:6.2f} m2 valid={sp.is_valid} "
              f"buf0_area={sp.buffer(0).area/1e6:6.2f}")
