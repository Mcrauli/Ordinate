"""Detektorivalinta mittaa MAARAA, ei osuvuutta. Korjataan se ensin.

Mitattu: kun `wall_histogram`in piikkikynnysta loysattiin (aito korjaus —
lyhyet seinat eivat mahtuneet globaalin kynnyksen ali), kolme aineistoa
regressoi. Syy ei ollut detektorissa vaan valinnassa:

  kellari kaytti `normals`ia. Loysatty histogrammi voitti valintakisan
  KATTAVUUDELLA 0.103 ja havisi lopputuloksessa: 0.366 -> 0.203, 240 -> 123
  seinaa. retail_l 37 -> 10 seinaa.

`wall_coverage` on pelkka RECALL: se palkitsee jokaisesta lisatysta seinasta
eika rankaise yhdestakaan vaarasta. Detektori joka tuottaa enemman piikkeja
voittaa aina, ovatpa ne oikein tai ei. Sen paalle ei voi rakentaa mitaan
detektorin parannusta.

Korjaus: sama `claimed`-maski antaa jo molemmat luvut, ja
`data/_wall_coverage_nogt.py` (matriisin mittari) laskee ne juuri nain:

    recall    = osuma / pilven seinapinnoista
    tarkkuus  = osuma / mallin kaistasta

Valinta tehdaan naiden F1:lla. Tyhja malli saa 0, ja piikkitulva saa matalan
tarkkuuden -> ei voi enaa kaapata valintaa. Mallin ja mittarin on oltava samaa
mielta, joten funktio menee `core/qa/coverage.py`:hyn eika omaksi kopiokseen.
"""
import pathlib


def patch(path, pairs):
    p = pathlib.Path(path)
    s = p.read_text(encoding="utf-8")
    for old, new in pairs:
        n = s.count(old)
        assert n == 1, "%s: %d osumaa\n%s" % (path, n, old[:160])
        s = s.replace(old, new)
    p.write_text(s, encoding="utf-8")
    print("  " + path)


# --- 1. coverage.py: yksi laskenta, molemmat luvut ---------------------------
patch("src/ordinate/core/qa/coverage.py", [
    (
        'def wall_coverage(pts: np.ndarray, walls, floor_z: float, ceiling_z: float,\n'
        '                  voxel: float = _VOXEL) -> float:\n'
        '    """Osuus pilven seinäpinnoista jotka jokin mallin seinä kattaa.\n'
        '\n'
        '    Palauttaa 0.0 kun pilvestä ei löydy seinäpintaa lainkaan — "ei mitattavaa"\n'
        '    ei saa näyttää täydeltä kattavuudelta, koska silloin tyhjä malli voittaisi\n'
        '    valinnan.\n'
        '    """\n'
        '    z_lo, z_hi = floor_z + 400.0, ceiling_z - 300.0\n'
        '    if z_hi <= z_lo:\n'
        '        return 0.0\n'
        '    is_wall, q = wallish_points(pts, z_lo, z_hi, voxel)\n'
        '    total = int(is_wall.sum())\n'
        '    if total == 0:\n'
        '        return 0.0\n',

        'def wall_scores(pts: np.ndarray, walls, floor_z: float, ceiling_z: float,\n'
        '                voxel: float = _VOXEL) -> tuple[float, float]:\n'
        '    """(kattavuus, tarkkuus) samasta maskista — sama määritelmä kuin\n'
        '    `data/_wall_coverage_nogt.py`:ssä, jotta malli ja mittari ovat samaa mieltä.\n'
        '\n'
        '    kattavuus = osuma / pilven seinäpinnoista  (löytyikö kaikki)\n'
        '    tarkkuus  = osuma / mallin kaistasta       (onko mallissa turhaa)\n'
        '\n'
        '    Molemmat palautetaan koska PELKKÄ kattavuus palkitsee määrää: jokainen\n'
        '    lisätty seinä voi vain nostaa sitä, eikä yksikään väärä laske sitä.\n'
        '    Mitattu: kun histogrammidetektorin piikkikynnystä löysättiin, se voitti\n'
        '    kellarin valintakisan kattavuudella 0.103 ja vei lopputuloksen\n'
        '    0.366 → 0.203 (240 → 123 seinää). Ks. `_best_detector`.\n'
        '    """\n'
        '    z_lo, z_hi = floor_z + 400.0, ceiling_z - 300.0\n'
        '    if z_hi <= z_lo:\n'
        '        return 0.0, 0.0\n'
        '    is_wall, q = wallish_points(pts, z_lo, z_hi, voxel)\n'
        '    total = int(is_wall.sum())\n'
        '    if total == 0:\n'
        '        return 0.0, 0.0\n',
    ),
    (
        '        claimed |= (s > 0) & (s < length) & (np.abs(np.abs(t) - half) < _BAND)\n'
        '    return float((claimed & is_wall).sum()) / total',

        '        claimed |= (s > 0) & (s < length) & (np.abs(np.abs(t) - half) < _BAND)\n'
        '    hit = int((claimed & is_wall).sum())\n'
        '    return hit / total, hit / max(int(claimed.sum()), 1)\n'
        '\n'
        '\n'
        'def wall_coverage(pts: np.ndarray, walls, floor_z: float, ceiling_z: float,\n'
        '                  voxel: float = _VOXEL) -> float:\n'
        '    """Osuus pilven seinäpinnoista jotka jokin mallin seinä kattaa.\n'
        '\n'
        '    Palauttaa 0.0 kun pilvestä ei löydy seinäpintaa lainkaan — "ei mitattavaa"\n'
        '    ei saa näyttää täydeltä kattavuudelta, koska silloin tyhjä malli voittaisi\n'
        '    valinnan.\n'
        '    """\n'
        '    return wall_scores(pts, walls, floor_z, ceiling_z, voxel)[0]',
    ),
])

# --- 2. pipeline.py: valinta F1:lla -----------------------------------------
patch("src/ordinate/core/pipeline.py", [
    (
        "        from ordinate.core.qa.coverage import wall_coverage  # noqa: PLC0415",
        "        from ordinate.core.qa.coverage import wall_scores  # noqa: PLC0415",
    ),
    (
        "            if floor is None or ceiling is None:\n"
        "                cov = 0.0\n",

        "            if floor is None or ceiling is None:\n"
        "                cov = pre = 0.0\n",
    ),
    (
        "                cov = wall_coverage(probe_pts, candidate.walls, floor.elevation,\n"
        "                                    ceiling.elevation)\n"
        "            models_by_name[name] = candidate\n"
        "            self._progress(f\"    {name}: kattavuus {cov:.3f} ({len(candidate.walls)} seinää)\")\n"
        "            scores[name] = cov",

        "                cov, pre = wall_scores(probe_pts, candidate.walls,\n"
        "                                       floor.elevation, ceiling.elevation)\n"
        "            models_by_name[name] = candidate\n"
        "            # F1 EIKÄ pelkkä kattavuus: kattavuus on puhdas recall, jota\n"
        "            # jokainen lisätty seinä voi vain nostaa. Detektori joka tuottaa\n"
        "            # enemmän piikkejä voittaa siis aina, olivatpa ne oikein tai ei.\n"
        "            # Mitattu: histogrammin piikkikynnyksen löysääminen (aito korjaus\n"
        "            # lyhyille seinille) vei kellarin valinnan `normals`ilta\n"
        "            # kattavuudella 0.103 ja lopputuloksen 0.366 → 0.203, retail_l:n\n"
        "            # 37 → 10 seinää. Tarkkuus rankaisee piikkitulvasta, joten\n"
        "            # valintaa ei voi enää kaapata määrällä.\n"
        "            f1 = 0.0 if cov + pre <= 0.0 else 2.0 * cov * pre / (cov + pre)\n"
        "            self._progress(f\"    {name}: F1 {f1:.3f} \"\n"
        "                           f\"(kattavuus {cov:.3f}, tarkkuus {pre:.3f}, \"\n"
        "                           f\"{len(candidate.walls)} seinää)\")\n"
        "            scores[name] = f1",
    ),
    (
        '        self._progress(f"  valittu {best_name} (kattavuus {best_cov:.3f})")',
        '        self._progress(f"  valittu {best_name} (F1 {best_cov:.3f})")',
    ),
])
print("valinnan korjaus sovellettu")
