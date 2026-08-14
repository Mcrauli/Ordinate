"""Kontrolliajo: sama koodi, pintatuen mittaus pois -> paljonko se maksaa oikeasti."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import scan2bim.core.qa.deviation as _dev

_dev.measure_wall_support = lambda model, cloud: None

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _scale_run

sys.argv = ["_scale_run", "data/_retail_s.ply", "--out", "data/output/_ctrl_s"]
_scale_run.main()
