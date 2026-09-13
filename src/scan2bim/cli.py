"""CLI: scan2bim convert input.e57 output/"""
from __future__ import annotations

import sys
from pathlib import Path

import click

from scan2bim._version import __version__


def force_utf8_output() -> None:
    """Kirjoita UTF-8:na riippumatta siitä mitä konsoli sanoo osaavansa.

    Windowsin oletuskonsoli on cp1252, johon raportin `→` ja `≥` eivät mahdu.
    Ilman tätä `scan2bim inspect` kaatuu UnicodeEncodeErroriin kesken
    tulostuksen — ja koska open3d on jo varannut säikeensä, prosessi ei edes
    poistu siististi vaan näyttää jumittuneelta. `errors="replace"` on toinen
    lukko: uusi merkki korvautuu kysymysmerkillä eikä kaada ajoa.
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            try:
                reconfigure(encoding="utf-8", errors="replace")
            except (ValueError, OSError):   # suljettu tai uudelleenohjattu stream
                pass


# Windowsin konsolin oletuskoodisivu on cp1252, eika se osaa nuolta tai
# aaskosia. Pakatussa CLI:ssa se KAATAA ohjelman heti (`--help` riitti:
# UnicodeEncodeError '→'), koska kehitysajossa PYTHONIOENCODING=utf-8
# peittaa asian eika vika nay missaan. Pakota UTF-8 ja korvaa se mita
# konsoli ei osaa — teksti voi nayttaa vajaalta, mutta ajo ei kaadu siihen.
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


@click.group()
@click.version_option(__version__, prog_name="scan2bim")
def main() -> None:
    """scan2bim — pistepilvi → arkkitehtimalli (IFC/DXF/AutoLISP)."""
    force_utf8_output()


@main.command()
@click.argument("input_file", type=click.Path(exists=True, path_type=Path))
def inspect(input_file: Path) -> None:
    """Lue skannin oletukset (mittakaava, tasot, kerrokset, tiheys) ennen ajoa."""
    from scan2bim.core.inspect import format_report, inspect_scan

    click.echo(format_report(inspect_scan(input_file)), file=sys.stdout)


@main.command()
@click.argument("input_file", type=click.Path(exists=True, path_type=Path))
@click.argument("output_dir", type=click.Path(path_type=Path), default=Path("output"))
@click.option("--voxel-size", default=20.0, show_default=True, help="Voxel-koko mm")
@click.option(
    "--detector",
    type=click.Choice(["contour", "histogram", "ransac", "density"]),
    default="contour",
    show_default=True,
    help="Seinädetektori (oletus contour = tuotannon oletus; iso tila/liiketila "
         "vaihtaa automaattisesti histogrammiin. ransac/density ovat fallbackeja.)",
)
@click.option("--no-ifc", is_flag=True, help="Älä tuota IFC")
@click.option("--no-dxf", is_flag=True, help="Älä tuota DXF")
@click.option(
    "--semantic-filter",
    type=click.Choice(["auto", "off", "pointnet"]),
    default="auto",
    show_default=True,
    help="Kalustesuodatin: auto = päälle vain liiketilassa (poistaa hyllyvaleseinät), "
         "off = ei koskaan, pointnet = aina",
)
def convert(
    input_file: Path,
    output_dir: Path,
    voxel_size: float,
    detector: str,
    no_ifc: bool,
    no_dxf: bool,
    semantic_filter: str,
) -> None:
    """Konvertoi pistepilvi arkkitehtimalliksi."""
    import logging
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    from scan2bim.core.pipeline import Pipeline, PipelineConfig

    cfg = PipelineConfig(
        voxel_size=voxel_size,
        detector=detector,
        export_ifc=not no_ifc,
        export_dxf=not no_dxf,
        semantic_filter_mode=semantic_filter,
    )

    def log(msg: str) -> None:
        click.echo(msg, file=sys.stdout)

    model = Pipeline(cfg, progress=log).run(input_file, output_dir)
    click.echo(f"\n{model.summary()}")
    click.echo(f"Tulokset: {output_dir.resolve()}", file=sys.stdout)


@main.command(name="run")
@click.argument("inputs", nargs=-1, required=True,
                type=click.Path(exists=True, path_type=Path))
@click.option("--out", required=True, type=click.Path(path_type=Path),
              help="Tuloshakemisto")
@click.option("--config", type=click.Path(exists=True, path_type=Path),
              help="PipelineConfig JSON-tiedostona")
def run_floors_cmd(inputs: tuple[Path, ...], out: Path, config: Path | None) -> None:
    """Tuotantoajo (run_floors): N skannia -> kerrosjako -> mallit.

    EI logging.basicConfig(INFO): GUI lukee taman stdoutin lokipaneeliinsa,
    ja ezdxf tulvii sinne "creating ACAD_* dictionary" -rivit. Kayttajan
    nakemat viestit tulevat progress-callbackista.
    """
    import json

    from scan2bim.core.pipeline import Pipeline, PipelineConfig

    cfg = PipelineConfig()
    if config is not None:
        raw = json.loads(Path(config).read_text(encoding="utf-8"))
        smp = raw.get("semantic_model_path")
        raw["semantic_model_path"] = Path(smp) if smp else None
        cfg = PipelineConfig(**raw)

    def log(msg: str) -> None:
        click.echo(msg, file=sys.stdout)
        try:
            sys.stdout.flush()
        except Exception:
            pass

    models = Pipeline(cfg, progress=log).run_floors(list(inputs), Path(out))
    log(f"VALMIS kerroksia={len(models)}")


@main.command(name="selftest-paths", hidden=True)
def selftest_paths() -> None:
    """Ratkaiseeko GUI komentorivin polun oikein TASSA paketissa.

    GUI ajaa putken aliprosessina `cli_command()`:n palauttamalla komennolla.
    Se haara joka lukee `sys.frozen`in ja etsii `scan2bim-cli.exe`n GUI-exen
    vierelta ei aja kehityksessa KOSKAAN — juuri sita lajia joka toimii
    venvissa ja hajoaa asiakkaalla. Savutesti ajaa taman paketista.
    """
    from scan2bim.gui.process_worker import cli_command

    cmd = cli_command()
    click.echo("CLI: " + " ".join(cmd))
    if getattr(sys, "frozen", False):
        cli = Path(cmd[0])
        gui = cli.with_name("scan2bim.exe")
        missing = [str(f) for f in (cli, gui) if not f.exists()]
        if missing:
            raise SystemExit("PUUTTUU: " + ", ".join(missing))
    click.echo("POLUT OK")


if __name__ == "__main__":
    main()
