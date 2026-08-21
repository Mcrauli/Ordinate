"""CLI-testit: varmista ettei komentorivin oletukset eroa tuotannon oletuksista."""
import scan2bim.core.segmentation.wall_contour    # noqa: F401 — rekisteröi detektorit
import scan2bim.core.segmentation.wall_density     # noqa: F401
import scan2bim.core.segmentation.wall_histogram   # noqa: F401
import scan2bim.core.segmentation.wall_ransac      # noqa: F401
from scan2bim.cli import convert
from scan2bim.core.pipeline import PipelineConfig
from scan2bim.core.segmentation.base import DetectorRegistry


def _detector_option():
    return next(p for p in convert.params if getattr(p, "name", None) == "detector")


def test_cli_detector_default_matches_pipeline():
    """CLI-oletus = PipelineConfigin oletus (contour). Aiemmin CLI pakotti
    ransacin → CLI-käyttäjä sai hitaan epädeterministisen fallbackin."""
    opt = _detector_option()
    assert opt.default == PipelineConfig().detector == "contour"


def test_cli_detector_choices_are_registered():
    """Jokainen CLI-valinta on oikeasti rekisteröity detektori."""
    opt = _detector_option()
    for name in opt.type.choices:
        assert DetectorRegistry.get(name) is not None, f"detektoria ei rekisteröity: {name}"
    assert "histogram" in opt.type.choices    # liiketiladetektori valittavissa


def test_report_characters_survive_a_cp1252_console():
    """CLI ei saa kaatua siihen ettei konsoli osaa raportin merkkejä.

    Mitattu: `scan2bim inspect` kaatui UnicodeEncodeErroriin Windowsin
    oletuskonsolissa (cp1252) heti kun raporttiin tuli `→`. Poikkeus tuli
    kesken tulostuksen eikä prosessi poistunut siististi, joten vika näytti
    jumilta eikä kaatumiselta.
    """
    import io
    import sys

    from scan2bim.cli import force_utf8_output

    raw = io.BytesIO()
    stdout, stderr = sys.stdout, sys.stderr
    sys.stdout = io.TextIOWrapper(raw, encoding="cp1252", newline="")
    sys.stderr = io.TextIOWrapper(io.BytesIO(), encoding="cp1252", newline="")
    try:
        force_utf8_output()
        sys.stdout.write("  → vapaa korkeus 2.80 m  ≥ 3.1 M pistettä")
        sys.stdout.flush()
    finally:
        out = sys.stdout
        sys.stdout, sys.stderr = stdout, stderr
    assert "→" in raw.getvalue().decode("utf-8")
    assert out.encoding.lower().replace("-", "") == "utf8"
