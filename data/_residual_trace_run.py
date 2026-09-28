"""Kellarin tuotantoajo jossa jaannoshaun ehdokkaat ja porttien tuomiot
tallennetaan. Kaytto: _residual_trace_run.py <out_dir>
Tulos: <out_dir>/residual_trace.json (vaihe -> ehdokasseinat / poistetut id:t)."""
import json
import sys
from pathlib import Path

if __name__ == "__main__":
    import psutil
    psutil.Process().nice(psutil.IDLE_PRIORITY_CLASS)
    import ordinate.core.semantics.residual_walls as RW
    import ordinate.core.semantics.contrast_prune as CP
    import ordinate.core.semantics.flatness_prune as FP
    import ordinate.core.semantics.direction_prune as DP
    from ordinate.core.pipeline import Pipeline, PipelineConfig
    trace = []

    def ax(w):
        return [list(map(float, w.axis[0])), list(map(float, w.axis[1]))]

    o_drop = RW._drop_near_existing

    def drop(pairs, walls):
        out = o_drop(pairs, walls)
        kept = {id(p) for p in out}
        trace.append({"stage": "near_existing",
                      "dropped": [[list(map(float, p[0])), list(map(float, p[1]))] for p in pairs if id(p) not in kept],
                      "kept": [[list(map(float, p[0])), list(map(float, p[1]))] for p in out]})
        return out
    RW._drop_near_existing = drop

    for mod, name in ((CP, "prune_uncontrasted_walls"), (FP, "prune_flatless_walls"),
                      (DP, "prune_offdirection_walls")):
        fn = getattr(mod, name)

        def wrap(model, *a, _fn=fn, _n=name, **kw):
            before = {w.id: ax(w) for w in model.walls}
            out = _fn(model, *a, **kw)
            after = {w.id for w in model.walls}
            trace.append({"stage": _n, "removed": {k: v for k, v in before.items() if k not in after}})
            return out
        setattr(mod, name, wrap)

    files = sorted(Path("data/_kellari_nvme").glob("Kellari- Kellari 0*.e57"))
    cfg = PipelineConfig(detector="contour", auto_voxel=True, export_ifc=False, export_dxf=False,
                         export_qa=False, semantic_filter_mode="pointnet")
    out = Path(sys.argv[1])
    Pipeline(cfg, progress=lambda m: print(m, flush=True)).run_floors(files, out)
    (out / "residual_trace.json").write_text(json.dumps(trace), encoding="utf-8")
