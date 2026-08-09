"""CLI: scan2bim convert input.e57 output/"""
from __future__ import annotations

import sys
from pathlib import Path

import click

from scan2bim._version import __version__


@click.group()
@click.version_option(__version__, prog_name="scan2bim")
def main() -> None:
    """scan2bim — pistepilvi → arkkitehtimalli (IFC/DXF/AutoLISP)."""


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
        click.echo(msg)

    model = Pipeline(cfg, progress=log).run(input_file, output_dir)
    click.echo(f"\n{model.summary()}")
    click.echo(f"Tulokset: {output_dir.resolve()}")
