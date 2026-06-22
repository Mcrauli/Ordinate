"""Nopea diagnostiikka pistepilvelle: bounds, pisteiden määrä, arvioitu yksikkö."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from scan2bim.core.geometry.loader import load_point_cloud
import numpy as np

path = Path(sys.argv[1])
cloud = load_point_cloud(path)
pts = np.asarray(cloud.points)

mn, mx = pts.min(axis=0), pts.max(axis=0)
span = mx - mn
unit_guess = "METRIT (skaalaa x1000)" if span.max() < 200 else "MILLIMETRIT (ok)"

print(f"Pisteitä:   {len(pts):,}")
print(f"X: {mn[0]:.2f} … {mx[0]:.2f}  (laajuus {span[0]:.2f})")
print(f"Y: {mn[1]:.2f} … {mx[1]:.2f}  (laajuus {span[1]:.2f})")
print(f"Z: {mn[2]:.2f} … {mx[2]:.2f}  (laajuus {span[2]:.2f})")
print(f"Yksikkö:    {unit_guess}")
