"""E57:n lohkoluku: sama pistejoukko kuin koko tiedoston luvulla.

`read_scan` varaa koko skannin kerralla, ja iso keilaus on YKSI skanni (mitattu
gargage.e57: 0.56 GB -> 27.8 M pistetta, 2.79 GB RSS ~= 5 GB per tiedosto-GB),
joten 32 GB tiedosto ei latautuisi lainkaan. Sama libE57-lukija palvelee
lohkoittain.
"""
import numpy as np
import pytest

pye57 = pytest.importorskip("pye57")

from scan2bim.core.geometry.loader import (  # noqa: E402
    _e57_is_chunkable, e57_band_chunks, e57_point_count, e57_z_range,
    read_e57_xyz_band, read_e57_z,
)

_N = 30_000


def _write(path, xyz, rotation=None, translation=None):
    with pye57.E57(str(path), mode="w") as f:
        f.write_scan_raw(
            {"cartesianX": xyz[:, 0], "cartesianY": xyz[:, 1], "cartesianZ": xyz[:, 2]},
            rotation=rotation, translation=translation,
        )


@pytest.fixture
def e57_file(tmp_path):
    rng = np.random.default_rng(0)
    # metreja (kuten oikeat e57:t) -> loaderin pitaa skaalata mm:eiksi
    xyz = np.column_stack([
        rng.uniform(0.0, 12.0, _N),
        rng.uniform(0.0, 8.0, _N),
        rng.uniform(0.0, 3.0, _N),
    ])
    p = tmp_path / "scan.e57"
    _write(p, xyz)
    return p, xyz * 1000.0


def test_band_chunks_match_full_read(e57_file):
    path, mm = e57_file
    lo, hi = 1000.0, 2000.0
    ref = mm[(mm[:, 2] >= lo) & (mm[:, 2] <= hi)]
    got = np.concatenate(list(e57_band_chunks(path, lo, hi, chunk=4096)))
    assert len(got) == len(ref)
    assert np.allclose(np.sort(got, axis=0), np.sort(ref, axis=0))


def test_band_read_is_chunked_not_one_shot(e57_file):
    """Pieni lohko -> monta erää; muuten koko skanni olisi taas kerralla muistissa."""
    path, _ = e57_file
    n = sum(1 for _ in e57_band_chunks(path, -1e9, 1e9, chunk=4096))
    assert n > 1, f"luku ei lohkoutunut ({n} era)"


def test_metre_file_is_scaled_to_mm(e57_file):
    # e57 tallentaa skaalattuina kokonaislukuina -> mm-tason kvantisointi
    path, mm = e57_file
    lo, hi = e57_z_range(path)
    assert lo == pytest.approx(mm[:, 2].min(), abs=2.0)
    assert hi == pytest.approx(mm[:, 2].max(), abs=2.0)
    assert hi > 200.0, "metrit jaivat skaalaamatta"


def test_max_points_thins_without_leaving_band(e57_file):
    path, mm = e57_file
    lo, hi = 500.0, 2500.0
    out = read_e57_xyz_band(path, lo, hi, max_points=1000)
    assert len(out) <= 1000
    assert out[:, 2].min() >= lo and out[:, 2].max() <= hi


def test_pose_is_applied(tmp_path):
    """Ilman posea kaista osuisi vaaraan korkeuteen."""
    xyz = np.column_stack([
        np.zeros(_N), np.zeros(_N), np.linspace(0.0, 3.0, _N),
    ])
    p = tmp_path / "posed.e57"
    _write(p, xyz, rotation=np.array([1.0, 0.0, 0.0, 0.0]),
           translation=np.array([0.0, 0.0, 10.0]))
    lo, hi = e57_z_range(p)
    assert lo == pytest.approx(10_000.0, abs=5.0), lo
    assert hi == pytest.approx(13_000.0, abs=5.0), hi


def test_z_samples_cover_full_range(e57_file):
    path, mm = e57_file
    z = read_e57_z(path)
    assert len(z) > 0
    assert z.min() == pytest.approx(mm[:, 2].min(), abs=1.0)


def test_small_file_keeps_the_validated_full_read(e57_file):
    """Lohkoluku EI ole tulokseltaan neutraali (voxelointi lohkorajoilla,
    desimoitu kerroshistogrammi) -> sita kaytetaan vain kun koko tiedosto ei
    muuten mahtuisi. Mitattu gargage.e57: kaista 2.60 -> 2.57 m, 11 -> 9 seinaa."""
    path, _ = e57_file
    assert e57_point_count(path) == _N
    assert _e57_is_chunkable(path) is False
