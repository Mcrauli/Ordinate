"""Siirrettävät polut QA-/vision-kehitystyökaluille (data/_*.py).

Nämä skriptit EIVÄT päädy asiakkaan exe:hen — ne lukevat paikallista testidataa
ja kirjoittavat QA-artefakteja. Historiallisesti ne kovakoodasivat yhden
kehittäjän koneen (C:\\Users\\lauri\\...) → eivät ajaneet muualla. Tämä ratkoo
polut repo-suhteellisina ja käyttäjän kotihakemistosta, joten työkalut ajavat
millä koneella tahansa.

Skannidatan juuren (Downloads) voi ohittaa ympäristömuuttujalla:
    SCAN2BIM_DOWNLOADS=D:\\skannit  python data/_run_contour.py
"""
import os
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]          # <repo>/data/_paths.py -> <repo>
DATA = REPO / "data"
OUTPUT = DATA / "output"
REFERENCE = REPO / "reference"
DOWNLOADS = Path(os.environ.get("SCAN2BIM_DOWNLOADS") or (Path.home() / "Downloads"))
