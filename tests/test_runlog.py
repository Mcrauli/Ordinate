"""Ajokirjanpito: koneluettava rivi per ajo, ilman asiakkaan sijaintitietoa."""
import json

from scan2bim.core.qa.runlog import RunLog, load_runs


def test_run_is_written_as_one_json_line(tmp_path):
    target = tmp_path / "runs.jsonl"
    log = RunLog("9.9.9")
    log.scan(points=1000, occupancy_area_m2=42.0)
    log.choice("detector", "contour", {"contour": 0.45, "histogram": 0.09})
    log.result(walls=23, spaces=4)
    log.write(target)

    rows = target.read_text(encoding="utf-8").splitlines()
    assert len(rows) == 1
    row = json.loads(rows[0])
    assert row["version"] == "9.9.9"
    assert row["scan"]["occupancy_area_m2"] == 42.0
    assert row["choices"]["detector"]["chosen"] == "contour"
    assert row["choices"]["detector"]["scores"]["histogram"] == 0.09
    assert row["result"]["walls"] == 23
    assert "secs" in row


def test_runs_accumulate(tmp_path):
    target = tmp_path / "runs.jsonl"
    for i in range(3):
        log = RunLog("9.9.9")
        log.result(walls=i)
        log.write(target)
    rows = load_runs(target)
    assert [r["result"]["walls"] for r in rows] == [0, 1, 2]


def test_a_broken_line_does_not_kill_the_log(tmp_path):
    """Vioittunut rivi ei saa estää kertyneen tiedon lukemista."""
    target = tmp_path / "runs.jsonl"
    target.write_text('{"version": "1"}\nEI OLE JSONIA\n{"version": "2"}\n',
                      encoding="utf-8")
    assert [r["version"] for r in load_runs(target)] == ["1", "2"]


def test_writing_never_raises_even_when_the_path_is_unusable(tmp_path):
    """Kirjanpito ei saa koskaan kaataa ajoa — tulos on tärkeämpi kuin loki."""
    blocker = tmp_path / "blocker"
    blocker.write_text("olen tiedosto, en hakemisto", encoding="utf-8")
    log = RunLog("9.9.9")
    log.result(walls=1)
    log.write(blocker / "sub" / "runs.jsonl")      # ei saa nostaa poikkeusta


def test_no_paths_or_coordinates_are_recorded(tmp_path):
    """Sijainti on asiakkaan tietoa: mitat kirjataan, paikka ei.

    Tuote lupaa ettei aineisto liiku minnekään; kirjanpito ei saa olla se
    paikka jossa lupaus vuotaa.
    """
    target = tmp_path / "runs.jsonl"
    log = RunLog("9.9.9")
    log.scan(points=10, span_mm=[1000, 2000, 2600])
    log.write(target)
    row = json.loads(target.read_text(encoding="utf-8"))
    text = json.dumps(row)
    assert "span_mm" in row["scan"]
    for forbidden in ("path", "file", "C:", "/", "\\"):
        assert forbidden not in text, f"kirjanpitoon vuoti {forbidden!r}"
