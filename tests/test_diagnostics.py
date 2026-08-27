"""Diagnostiikan on kerrottava MIKSI ajo kaatui, ei vain missä vaiheessa."""
from scan2bim.core.qa.diagnostics import DiagnosticsLog, _is_memory_error


def test_memory_errors_are_recognised():
    for msg in ("bad allocation", "MemoryError: ...", "std::bad_alloc",
                "Unable to allocate 12.4 GiB"):
        assert _is_memory_error(msg), msg


def test_an_ordinary_error_gets_no_memory_hint():
    assert not _is_memory_error("ValueError: axis out of bounds")


def test_report_names_the_stage_that_used_most_memory():
    """Kaatuessa ratkaisee mikä vaihe söi muistin, ei se mikä oli viimeinen."""
    d = DiagnosticsLog()
    d.log("kevyt vaihe")
    d.peak_gb, d.peak_at = 12.4, "Ladataan keskikaista paksuusmittaukseen"
    text = d.render()
    assert "muistihuippu: 12.4 GB" in text
    assert "paksuusmittaukseen" in text


def test_a_memory_error_gets_actionable_advice():
    """Käyttäjä ei voi korjata 'bad allocation' -viestiä ilman ohjetta."""
    d = DiagnosticsLog()
    d.error = "bad allocation"
    text = d.render()
    assert "MUISTI LOPPUI" in text
    assert "ICP" in text


def test_stage_lines_carry_duration_and_memory():
    d = DiagnosticsLog()
    d.log("vaihe A")
    line = d.lines[0]
    assert line.startswith("[")
    assert "+" in line, "vaiheen kesto puuttuu"
    assert "vaihe A" in line


def test_counts_and_traceback_reach_the_report():
    d = DiagnosticsLog()
    d.count(walls=430, spaces=12)
    d.traceback = "Traceback (most recent call last):\n  File ..."
    text = d.render()
    assert "walls=430" in text
    assert "Traceback" in text


def test_the_report_carries_no_coordinates_or_paths(tmp_path):
    """Raportti on tarkoitettu jaettavaksi — asiakkaan sijainti ei saa vuotaa."""
    d = DiagnosticsLog()
    d.add_input(tmp_path / "Kellari 001.e57")
    d.log("Ladataan")
    text = d.render()
    assert "Kellari" not in text
    assert str(tmp_path) not in text
