"""Histogrammin piikkikynnys globaalista paikalliseen — toinen yritys.

Ensimmainen yritys (peruttu) regressoi kolmea aineistoa, mutta syy ei ollut
tassa vaan detektorivalinnassa: loysatty detektori kaappasi valinnan koska
`_best_detector` palkitsi maarasta. Se on nyt korjattu (F1), joten sama
muutos voidaan mitata uudelleen kestavalta pohjalta.
"""
import pathlib

p = pathlib.Path("src/scan2bim/core/segmentation/wall_histogram.py")
s = p.read_text(encoding="utf-8")

old = """_PEAK_SIGMA = 3.0          # piikki = keskiarvo + tama x keskihajonta"""
if old not in s:
    old = "_PEAK_SIGMA = 3.0          # piikki = keskiarvo + tämä × keskihajonta"
assert old in s, "vakiota ei loytynyt"
s = s.replace(old, "_PEAK_MAD_K = 3.0          # piikki = miehitettyjen binien mediaani + tämä × MAD")

old = """def _peaks_1d(coord, lo, hi):
    nb = int((hi - lo) / _BIN) + 1
    if nb < 1:
        return []
    hist, edges = np.histogram(coord, bins=nb, range=(lo, hi))
    thr = max(hist.mean() + _PEAK_SIGMA * hist.std(), float(_PEAK_MIN_PTS))"""
assert old in s, "peaks_1d ei loytynyt"

new = '''def _peak_threshold(hist: np.ndarray) -> float:
    """Kynnys MIEHITETTYJEN binien mediaanista — ei koko akselin keskiarvosta.

    Aiempi sääntö oli `hist.mean() + 3 * hist.std()`, ja se sulki lyhyet seinät
    ulos RAKENTEELLISESTI: binin pistemäärä on verrannollinen seinän PITUUTEEN,
    joten 30 m perimetriseinä tuottaa biniä kohti moninkertaisesti sen mitä 3 m
    väliseinä — ja samat jättipiikit paisuttavat keskihajonnan, joka nostaa
    kynnystä lisää. Taso, ei suhde.

    Mitattu scene_07002 akseli 0 (`data/_hist_threshold_probe.py`): keskiarvo
    1427, keskihajonta 5042 (3.5x keskiarvo), kynnys 16553 — ja 1642 binistä
    vain **10** ylitti sen. GT-instansseista kynnyksen ylitti:
      yli 4 m  0.86    2-4 m  0.62    1-2 m  **0.00**

    Mediaani ja MAD lasketaan vain miehitetyistä bineistä eivätkä paisu
    muutamasta jättipiikistä. Mitattu viidellä scenellä
    (`data/_hist_rule_sweep.py`, kahdeksan sääntöä, raakadetektorin
    GT-instanssikattavuus): keskiarvo+3σ 0.756 → mediaani+3·MAD **0.836**,
    ja 2-4 m luokka 0.83 → 0.96.

    HUOM: tämä loysaa detektoria. Se on turvallista VASTA sen jälkeen kun
    `_best_detector` valitsee F1:llä eikä pelkällä kattavuudella — ensimmäinen
    yritys peruttiin koska löysätty detektori kaappasi valinnan.
    """
    nz = hist[hist > 0]
    if not len(nz):
        return float(_PEAK_MIN_PTS)
    med = float(np.median(nz))
    mad = float(np.median(np.abs(nz - med))) * 1.4826
    return max(med + _PEAK_MAD_K * mad, float(_PEAK_MIN_PTS))


def _peaks_1d(coord, lo, hi):
    nb = int((hi - lo) / _BIN) + 1
    if nb < 1:
        return []
    hist, edges = np.histogram(coord, bins=nb, range=(lo, hi))
    thr = _peak_threshold(hist)'''
s = s.replace(old, new)
p.write_text(s, encoding="utf-8")
print("histogrammin kynnys korjattu")
