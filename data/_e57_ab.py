"""A/B: sama koodi, lohkoluku paalla vs. pois -> sama malli, eri muisti."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

if "--off" in sys.argv:
    import scan2bim.core.geometry.loader as _ld
    _ld._e57_is_chunkable = lambda p: False
    import scan2bim.core.geometry.streaming as _st
    import scan2bim.core.geometry.floor_splitter as _fs
    tag = "off"
else:
    tag = "on"

import _scale_run
sys.argv = ["_scale_run", str(Path.home() / "Downloads" / "gargage.e57"),
            "--out", f"data/output/_e57ab_{tag}"]
_scale_run.main()
