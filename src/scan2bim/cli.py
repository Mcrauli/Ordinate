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


def _view_one(args):
    """Yksi tiedosto harvennettuna. Moduulitason funktio, jotta se on
    poimittavissa prosessipoolille (Windows spawn)."""
    import numpy as np

    from scan2bim.core.geometry.loader import load_point_cloud

    path, per = args
    c = load_point_cloud(Path(path), e57_colors=True)
    q = np.asarray(c.points, dtype=np.float32)
    if not len(q):
        return None, None
    st = max(1, -(-len(q) // per))
    pts = np.ascontiguousarray(q[::st])
    rgb = np.ascontiguousarray(
        np.asarray(c.colors, dtype=np.float32)[::st] if c.has_colors()
        else np.full((len(pts), 3), 0.6, np.float32))
    return pts, rgb


def _view_workers(n_files: int) -> int:
    """Rinnakkaisuus rajattuna muistilla: yksi 0.8 GB e57 vie lukiessa
    moninkertaisesti oman kokonsa (mitattu ~5 GB per tiedosto-GB)."""
    if n_files < 2:
        return 1
    w = 4
    try:
        import psutil  # noqa: PLC0415
        free_gb = psutil.virtual_memory().available / 1e9
        w = max(1, min(w, int(free_gb // 6)))
    except Exception:
        w = 2
    return max(1, min(w, n_files))


@main.command(name="viewcloud", hidden=True)
@click.argument("inputs", nargs=-1, type=click.Path(exists=True, path_type=Path))
@click.option("--out", required=True, type=click.Path(path_type=Path))
@click.option("--max-points", default=1_500_000, show_default=True)
@click.option("--model", "model_json", type=click.Path(exists=True, path_type=Path),
              default=None, help="Malli jonka residuaali lasketaan valmiiksi")
@click.option("--reuse", type=click.Path(exists=True, path_type=Path), default=None,
              help="Aiemman ajon npz: pisteet sieltä, skanneja ei lueta")
def viewcloud(inputs: tuple[Path, ...], out: Path, max_points: int,
              model_json: Path | None, reuse: Path | None) -> None:
    """3D-tarkastuksen pilvi VALMIIKSI laskettuna (GUI ajaa tämän aliprosessina).

    Ikkunaprosessi ei tee pilvelle mitään numpy-työtä: se kaatui kolme kertaa
    muistin suojausvirheeseen juuri kun se rakensi 1.5 M pisteen väritaulua
    näytönohjaimen latauksen jälkeen — viimeksi rivillä joka kirjoitti
    taulukkoon joka oli varattu edellisellä rivillä. Kaikki taulut lasketaan
    tässä, ja ikkuna vain lataa ne.

    E57-lukija ei myöskään vapauta GIL:iä (mitattu 4.2 s pysähdys toisessa
    säikeessä yhdellä tiedostolla), joten luku kuuluu omaan prosessiinsa.
    """
    import json as _json

    import numpy as np

    from scan2bim.core.qa.residual import classify_explained

    if reuse is not None:
        with np.load(Path(reuse)) as z:
            pts = np.ascontiguousarray(z["pts"], dtype=np.float32)
            rgb = np.ascontiguousarray(z["rgb8"], dtype=np.float32) / 255.0
        click.echo("  pisteet edellisestä latauksesta")
    else:
        if not inputs:
            raise SystemExit("anna skannit tai --reuse")
        per = max(1, int(max_points) // max(len(inputs), 1))
        jobs = [(str(p), per) for p in inputs]
        workers = _view_workers(len(jobs))
        chunks, cols = [], []

        def _collect(i: int, name: str, res) -> None:
            click.echo(f"  [{i}/{len(jobs)}] {name}")
            try:
                sys.stdout.flush()
            except Exception:
                pass
            p_, c_ = res
            if p_ is not None:
                chunks.append(p_)
                cols.append(c_)

        if workers > 1:
            # Mitattu 4 tiedostolla: 2 prosessia 1.53x, 4 prosessia 2.24x, 6 ei
            # enaa parane (levy rajoittaa). Tulos on bitilleen sama.
            from concurrent.futures import ProcessPoolExecutor  # noqa: PLC0415
            with ProcessPoolExecutor(max_workers=workers) as ex:
                for i, (job, res) in enumerate(zip(jobs, ex.map(_view_one, jobs)), 1):
                    _collect(i, Path(job[0]).name, res)
        else:
            for i, job in enumerate(jobs, 1):
                try:
                    _collect(i, Path(job[0]).name, _view_one(job))
                except Exception as e:  # noqa: BLE001
                    click.echo(f"  VAROITUS: {Path(job[0]).name} ohitettiin — {e}")
        if not chunks:
            raise SystemExit("pilvi on tyhja")
        pts = np.vstack(chunks)
        rgb = np.vstack(cols)
        n = min(len(pts), len(rgb))
        pts, rgb = pts[:n], rgb[:n]
        step = max(1, -(-len(pts) // int(max_points)))
        pts = np.ascontiguousarray(pts[::step])
        rgb = np.ascontiguousarray(rgb[::step])

    offset = pts.astype(np.float64).mean(axis=0)
    pts_c = np.ascontiguousarray(pts - offset.astype(np.float32), dtype=np.float32)
    rgba = np.empty((len(pts), 4), np.float32)
    rgba[:, :3] = rgb
    rgba[:, 3] = 1.0
    arrays = dict(pts=pts, rgb8=np.clip(rgb * 255.0, 0, 255).astype(np.uint8),
                  offset=offset, pts_c=pts_c, rgba=rgba)

    if model_json is not None:
        click.echo("  lasketaan residuaalia…")
        model = _json.loads(Path(model_json).read_text(encoding="utf-8"))
        expl = classify_explained(pts, model)
        res = np.empty((len(pts), 4), np.float32)
        res[:, 0], res[:, 1], res[:, 2], res[:, 3] = 0.95, 0.12, 0.12, 1.0
        res[expl, :3] = rgb[expl] * 0.3
        miss = ~expl
        arrays.update(res=res,
                      pts_miss=np.ascontiguousarray(pts_c[miss]),
                      res_miss=np.ascontiguousarray(res[miss]),
                      n_miss=np.int64(int(miss.sum())))

    np.savez(Path(out), **arrays)
    click.echo(f"VALMIS pisteita={len(pts)}")


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
    # PyInstaller + multiprocessing: lapsiprosessi kaynnistyy samasta exesta
    # `--multiprocessing-fork` -argumentilla. Ilman tata Click yrittaisi
    # jasentaa sen komennoksi ja jokainen lapsi kaatuisi.
    import multiprocessing

    multiprocessing.freeze_support()
    main()
