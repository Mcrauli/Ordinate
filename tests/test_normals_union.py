"""Normals-täydennys: histogrammimalliin lisätään vain seinät joita se ei jo kata,
eikä pilarin pintaa."""
from ordinate.core.pipeline import _column_face, _covered_by, _outward_rib
from ordinate.schemas.model import Column, ColumnProfile, ElementSource, Wall


def _wall(x0, y0, x1, y1):
    return Wall(id="w", confidence=1.0, classification="wall",
                source=ElementSource(method="normals"),
                axis=[[x0, y0], [x1, y1]], height=2700.0, thickness=200.0, z_min=0.0)


def _column(x, y, size=460.0):
    return Column(id="c", confidence=1.0, source=ElementSource(method="cluster"),
                  location=[x, y], base_z=0.0, height=3000.0,
                  profile=ColumnProfile(shape="circle", width=size, depth=size))


def test_wall_on_existing_line_is_covered():
    assert _covered_by(_wall(1000, 100, 5000, 100), [_wall(0, 0, 10000, 0)])


def test_separate_partition_is_not_covered():
    assert not _covered_by(_wall(4000, 1000, 4000, 4000), [_wall(0, 0, 10000, 0)])


def test_parallel_wall_one_metre_away_is_not_covered():
    assert not _covered_by(_wall(1000, 1000, 5000, 1000), [_wall(0, 0, 10000, 0)])


def test_collinear_extension_beyond_end_is_not_covered():
    assert not _covered_by(_wall(12000, 0, 16000, 0), [_wall(0, 0, 10000, 0)])


def test_stub_across_column_is_column_face():
    assert _column_face(_wall(23560, 8250, 24720, 8250), [_column(24000, 8000)])


def test_long_wall_through_column_is_kept():
    assert not _column_face(_wall(20000, 8250, 28000, 8250), [_column(24000, 8000)])


def test_stub_far_from_column_is_kept():
    assert not _column_face(_wall(23560, 9500, 24720, 9500), [_column(24000, 8000)])


def _box():
    return [_wall(0, 0, 20000, 0), _wall(20000, 0, 20000, 15000),
            _wall(20000, 15000, 0, 15000), _wall(0, 15000, 0, 0)]


def test_rib_projecting_out_of_facade_is_dropped():
    assert _outward_rib(_wall(20000 - 200, 5000, 20000 + 1300, 5000), _box())


def test_partition_meeting_facade_from_inside_is_kept():
    assert not _outward_rib(_wall(20000, 5000, 17000, 5000), _box())


def test_free_standing_partition_is_kept():
    assert not _outward_rib(_wall(8000, 3000, 8000, 9000), _box())
