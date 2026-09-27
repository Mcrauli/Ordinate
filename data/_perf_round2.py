"""Kierros 2: samat kaistahaut lopuille koko pilven skannauksille.

Profiloitu kellarilla (1140 s): `_wall_openings` 94 s, `_split_one` 57 s,
`overstretch._coverage` 35 s, `residual._claimed` 23 s — kaikki samaa kuviota
kuin jo korjatut kiertopassit: projektio lasketaan KOKO pistetaulukolle ja
sitten poimitaan kapea kaista.

Jokainen muutos on ylijoukko + sama ehto -> tulos bitilleen sama.
Ajetaan kerran; muutokset menevat lahdekoodiin.
"""
import pathlib


def patch(path, pairs):
    p = pathlib.Path(path)
    s = p.read_text(encoding="utf-8")
    for old, new in pairs:
        n = s.count(old)
        assert n == 1, "%s: %d osumaa\n%s" % (path, n, old[:140])
        s = s.replace(old, new)
    p.write_text(s, encoding="utf-8")
    print("  " + path)


# --- 1. opening_detector -----------------------------------------------------
patch("src/ordinate/core/segmentation/opening_detector.py", [
    (
        "    pts = np.asarray(cloud.points)\n"
        "    origins = [np.asarray(o, dtype=float) for o in (scanner_origins or [])]\n"
        "    openings: list[Opening] = []\n"
        "    counter = 0\n"
        "    for wall in walls:\n"
        "        new = _wall_openings(wall, pts, floor_z, counter, walls)",

        "    pts = np.asarray(cloud.points)\n"
        "    index = None\n"
        "    if len(pts) >= 300_000 and len(walls) >= 3:\n"
        "        from ordinate.core.geometry.xy_index import index_for  # noqa: PLC0415\n"
        "        index = index_for(cloud, pts)\n"
        "    origins = [np.asarray(o, dtype=float) for o in (scanner_origins or [])]\n"
        "    openings: list[Opening] = []\n"
        "    counter = 0\n"
        "    for wall in walls:\n"
        "        new = _wall_openings(wall, pts, floor_z, counter, walls, index)",
    ),
    (
        "def _wall_openings(\n"
        "    wall: Wall, pts: np.ndarray, floor_z: float, start_idx: int,\n"
        "    all_walls: list[Wall],\n"
        ") -> list[Opening]:",

        "def _wall_openings(\n"
        "    wall: Wall, pts: np.ndarray, floor_z: float, start_idx: int,\n"
        "    all_walls: list[Wall], index=None,\n"
        ") -> list[Opening]:",
    ),
    (
        "    normal = np.array([-along[1], along[0]])\n"
        "    plane_D = float(np.dot(normal, p0))\n"
        "\n"
        "    signed_dist = pts[:, :2] @ normal - plane_D",

        "    normal = np.array([-along[1], along[0]])\n"
        "    plane_D = float(np.dot(normal, p0))\n"
        "\n"
        "    if index is not None:\n"
        "        # Säde kattaa MOLEMMAT pinnat (±th/2 ± _FACE_TOL) ja keskilinjan.\n"
        "        # Akselin suuntaista rajausta EI saa tehdä: pinnanvalinta (pos/neg)\n"
        "        # lasketaan koko tasokaistalta, ja rajaus muuttaisi sen laskennan.\n"
        "        from ordinate.core.geometry.xy_index import subset  # noqa: PLC0415\n"
        "        pts, _ = subset(pts, index, p0, along, normal,\n"
        "                        wall.thickness / 2.0 + _FACE_TOL)\n"
        "\n"
        "    signed_dist = pts[:, :2] @ normal - plane_D",
    ),
])

# --- 2. split_gaps -----------------------------------------------------------
patch("src/ordinate/core/semantics/split_gaps.py", [
    (
        "def split_walls_at_gaps(walls: list, pts: np.ndarray) -> list:",
        "def split_walls_at_gaps(walls: list, pts: np.ndarray, index=None) -> list:",
    ),
    (
        "    if pts is None or len(pts) == 0:\n"
        "        return walls\n"
        "    out: list = []\n"
        "    for w in walls:\n"
        "        pieces = _split_one(w, pts)",

        "    if pts is None or len(pts) == 0:\n"
        "        return walls\n"
        "    # Kaistahaku rajaa pisteet seinän ympäriltä, mutta `band`-varasääntö\n"
        "    # (alle 50 pistettä z-kaistalla -> koko pilvi) lasketaan KOKO pilvestä,\n"
        "    # muuten ehto muuttuisi. Lajiteltu z antaa saman luvun haulla.\n"
        "    z_sorted = np.sort(pts[:, 2]) if index is not None else None\n"
        "    out: list = []\n"
        "    for w in walls:\n"
        "        pieces = _split_one(w, pts, index, z_sorted)",
    ),
    (
        "def _split_one(w, pts: np.ndarray) -> list:",
        "def _split_one(w, pts: np.ndarray, index=None, z_sorted=None) -> list:",
    ),
    (
        "    u = (b - a) / length\n"
        "    n = np.array([-u[1], u[0]])\n"
        "    half = float(getattr(w, \"thickness\", 200.0)) / 2.0\n"
        "    z_min = float(getattr(w, \"z_min\", pts[:, 2].min()))\n"
        "    height = float(getattr(w, \"height\", 0.0))\n"
        "    band = pts\n"
        "    if height > 1.0:\n"
        "        lo, hi = z_min + 0.25 * height, z_min + 0.75 * height\n"
        "        band = pts[(pts[:, 2] > lo) & (pts[:, 2] < hi)]\n"
        "        if len(band) < 50:\n"
        "            band = pts",

        "    u = (b - a) / length\n"
        "    n = np.array([-u[1], u[0]])\n"
        "    half = float(getattr(w, \"thickness\", 200.0)) / 2.0\n"
        "    _zm = getattr(w, \"z_min\", None)\n"
        "    z_min = float(_zm) if _zm is not None else float(pts[:, 2].min())\n"
        "    height = float(getattr(w, \"height\", 0.0))\n"
        "    if index is not None:\n"
        "        from ordinate.core.geometry.xy_index import subset  # noqa: PLC0415\n"
        "        pts, _ = subset(pts, index, a, u, n, half + _BAND_MM,\n"
        "                        -_COL_MM, length + _COL_MM)\n"
        "    band = pts\n"
        "    if height > 1.0:\n"
        "        lo, hi = z_min + 0.25 * height, z_min + 0.75 * height\n"
        "        sub = pts[(pts[:, 2] > lo) & (pts[:, 2] < hi)]\n"
        "        n_full = (len(sub) if z_sorted is None else\n"
        "                  int(np.searchsorted(z_sorted, hi, \"left\")\n"
        "                      - np.searchsorted(z_sorted, lo, \"right\")))\n"
        "        band = sub if n_full >= 50 else pts",
    ),
])

# --- 3. overstretch ----------------------------------------------------------
patch("src/ordinate/core/semantics/overstretch.py", [
    (
        "def _coverage(w, xy: np.ndarray) -> tuple[np.ndarray, float, np.ndarray, np.ndarray]:",
        "def _coverage(w, xy: np.ndarray, index=None) -> tuple[np.ndarray, float, np.ndarray, np.ndarray]:",
    ),
    (
        "    u = d / L\n"
        "    n = np.array([-u[1], u[0]])\n"
        "    rel = xy - a\n"
        "    s = rel @ u",

        "    u = d / L\n"
        "    n = np.array([-u[1], u[0]])\n"
        "    if index is not None:\n"
        "        # Histogrammin range on (0, L), joten sen ulkopuoliset pisteet\n"
        "        # putoavat joka tapauksessa -> sama rajaus indeksiin.\n"
        "        from ordinate.core.geometry.xy_index import subset  # noqa: PLC0415\n"
        "        xy, _ = subset(xy, index, a, u, n, w.thickness / 2.0 + _TOL, 0.0, L)\n"
        "    rel = xy - a\n"
        "    s = rel @ u",
    ),
    (
        "    prof = [_coverage(w, xy) for w in model.walls]",

        "    index = None\n"
        "    if len(xy) >= 300_000 and len(model.walls) >= 3:\n"
        "        from ordinate.core.geometry.xy_index import XYIndex  # noqa: PLC0415\n"
        "        index = XYIndex(xy)\n"
        "    prof = [_coverage(w, xy, index) for w in model.walls]",
    ),
])

# --- 4. residual_walls._claimed ---------------------------------------------
patch("src/ordinate/core/semantics/residual_walls.py", [
    (
        "def _claimed(band: np.ndarray, walls: list[Wall]) -> np.ndarray:\n"
        "    claimed = np.zeros(len(band), dtype=bool)\n"
        "    xy = band[:, :2]\n"
        "    for w in walls:\n"
        "        a = np.asarray(w.axis[0], dtype=float)\n"
        "        b = np.asarray(w.axis[1], dtype=float)\n"
        "        L = float(np.linalg.norm(b - a))\n"
        "        if L < 500.0:\n"
        "            continue\n"
        "        u = (b - a) / L\n"
        "        n = np.array([-u[1], u[0]])\n"
        "        d = xy - a\n"
        "        s, t = d @ u, d @ n\n"
        "        claimed |= ((s > -_CLAIM_END) & (s < L + _CLAIM_END)\n"
        "                    & (np.abs(t) < w.thickness / 2.0 + _CLAIM_BAND))\n"
        "    return claimed",

        "def _claimed(band: np.ndarray, walls: list[Wall]) -> np.ndarray:\n"
        "    claimed = np.zeros(len(band), dtype=bool)\n"
        "    xy = band[:, :2]\n"
        "    index = None\n"
        "    if len(band) >= 300_000 and len(walls) >= 3:\n"
        "        from ordinate.core.geometry.xy_index import XYIndex  # noqa: PLC0415\n"
        "        index = XYIndex(xy)\n"
        "    for w in walls:\n"
        "        a = np.asarray(w.axis[0], dtype=float)\n"
        "        b = np.asarray(w.axis[1], dtype=float)\n"
        "        L = float(np.linalg.norm(b - a))\n"
        "        if L < 500.0:\n"
        "            continue\n"
        "        u = (b - a) / L\n"
        "        n = np.array([-u[1], u[0]])\n"
        "        r = w.thickness / 2.0 + _CLAIM_BAND\n"
        "        if index is None:\n"
        "            d = xy - a\n"
        "            s, t = d @ u, d @ n\n"
        "            claimed |= ((s > -_CLAIM_END) & (s < L + _CLAIM_END)\n"
        "                        & (np.abs(t) < r))\n"
        "            continue\n"
        "        sel = index.near_segment(a, u, n, r, -_CLAIM_END, L + _CLAIM_END)\n"
        "        if not len(sel):\n"
        "            continue\n"
        "        d = xy[sel] - a\n"
        "        s, t = d @ u, d @ n\n"
        "        claimed[sel] |= ((s > -_CLAIM_END) & (s < L + _CLAIM_END)\n"
        "                         & (np.abs(t) < r))\n"
        "    return claimed",
    ),
])

# --- 5. pipeline valittaa indeksin split_walls_at_gaps:lle ------------------
patch("src/ordinate/core/pipeline.py", [
    (
        "            model.walls = split_walls_at_gaps(model.walls, np.asarray(cloud.points))",

        "            _sg_pts = np.asarray(cloud.points)\n"
        "            model.walls = split_walls_at_gaps(\n"
        "                model.walls, _sg_pts, _xy_index(_sg_pts, model.walls, cloud))",
    ),
])
print("kierros 2 sovellettu")
