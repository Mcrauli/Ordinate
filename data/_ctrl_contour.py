"""Kontrolli: sama koodi, iso tila -> histogrammi -auto-reititys pois."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import ordinate.core.pipeline as P
P._looks_like_retail = lambda cloud: False
P._occupancy_area_m2 = lambda cloud: 0.0
import _run_rohbau  # ajaa itsessaan
