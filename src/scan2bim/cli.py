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
    type=click.Choice(["ransac", "density"]),
    default="ransac",
    show_default=True,
    help="Seinädetektori",
)
@click.option("--no-ifc", is_flag=True, help="Älä tuota IFC")
@click.option("--no-dxf", is_flag=True, help="Älä tuota DXF")
def convert(
    input_file: Path,
    output_dir: Path,
    voxel_size: float,
    detector: str,
    no_ifc: bool,
    no_dxf: bool,
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
    )

    def log(msg: str) -> None:
        click.echo(msg)

    model = Pipeline(cfg, progress=log).run(input_file, output_dir)
    click.echo(f"\n{model.summary()}")
    click.echo(f"Tulokset: {output_dir.resolve()}")
