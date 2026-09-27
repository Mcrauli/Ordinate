"""Kierros 3: toimituspaksuuden snap ja pistevalin mittaus.

`_snap_delivery_thickness` on sama kuvio kuin jo korjatut: `pts[:, :2] - p0`
koko pilvelle jokaista seinaa kohti (33.8 s omaa aikaa yhdella kutsulla).
Rajaus on puhdas: kaista on |perp| < th/2 + 60 ja t valilla (0, L), eika
mitaan paatosta lasketa kaistan ulkopuolelta.

`_nn_spacing` rakentaa cKDTree:n KOKO pilvelle (24 M pistetta) vaikka kysyy
vain 20 000 pisteen naapurit — 5.8 s per kutsu, kuusi kutsua. Puu on
rakennettava koko pilvelle jotta naapuri on oikea, mutta scipy:n
`balanced_tree`/`compact_nodes` ovat rakennusaikaisia optimointeja: kysely on
tarkka kummallakin, ja `d[:, 1]` on ETAISYYS, ei indeksi, joten arvo on sama
vaikka sidokset katkeaisivat eri jarjestyksessa.
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


patch("src/ordinate/core/pipeline.py", [
    (
        "    pts = np.asarray(cloud.points)\n"
        "    out = []\n"
        "    for w in walls:\n"
        "        measured = round(w.thickness, 1)",

        "    pts = np.asarray(cloud.points)\n"
        "    index = _xy_index(pts, walls, cloud)\n"
        "    out = []\n"
        "    for w in walls:\n"
        "        measured = round(w.thickness, 1)",
    ),
    (
        "                u = (p1 - p0) / L\n"
        "                n = np.array([-u[1], u[0]])\n"
        "                rel = pts[:, :2] - p0\n"
        "                t = rel @ u\n"
        "                perp = rel @ n\n"
        "                zm = (pts[:, 2] > w.z_min + 200.0) & (pts[:, 2] < w.z_min + w.height - 200.0)\n"
        "                band = zm & (t > 0) & (t < L) & (np.abs(perp) < w.thickness / 2.0 + 60.0)",

        "                u = (p1 - p0) / L\n"
        "                n = np.array([-u[1], u[0]])\n"
        "                q, _ = _xy_subset(pts, index, p0, u, n,\n"
        "                                  w.thickness / 2.0 + 60.0, 0.0, L)\n"
        "                rel = q[:, :2] - p0\n"
        "                t = rel @ u\n"
        "                perp = rel @ n\n"
        "                zm = (q[:, 2] > w.z_min + 200.0) & (q[:, 2] < w.z_min + w.height - 200.0)\n"
        "                band = zm & (t > 0) & (t < L) & (np.abs(perp) < w.thickness / 2.0 + 60.0)",
    ),
])

patch("src/ordinate/core/geometry/loader.py", [
    (
        "    d, _ = cKDTree(xyz).query(xyz[idx], k=2)",

        "    # balanced_tree/compact_nodes ovat RAKENNUSAJAN optimointeja: kysely on\n"
        "    # tarkka kummallakin ja `d[:, 1]` on etäisyys, ei indeksi, joten arvo on\n"
        "    # sama. 24 M pisteen puu rakentuu näin murto-osassa ajasta.\n"
        "    tree = cKDTree(xyz, balanced_tree=False, compact_nodes=False)\n"
        "    d, _ = tree.query(xyz[idx], k=2)",
    ),
])
print("kierros 3 sovellettu")
