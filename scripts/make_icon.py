"""Generate assets/scan2bim.ico + .png from the canonical brand mark.

The mark mirrors assets/scan2bim.svg and the site logo (docs/site): a dark
rounded "scan bay" square, lime border, cyan registration crosshair, lime
centre dot. Drawn at 4x and downscaled for crisp small sizes.

Run:  .venv\\Scripts\\python scripts\\make_icon.py
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "assets"
BG, LIME, CYAN = "#0a0e14", "#c6f24e", "#39d0d8"
SUP = 4  # supersample factor for antialiasing


def _draw() -> Image.Image:
    s = 256 * SUP
    m = SUP
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle(
        [20 * m, 20 * m, 236 * m, 236 * m],
        radius=40 * m, fill=BG, outline=LIME, width=12 * m,
    )
    d.line([128 * m, 74 * m, 128 * m, 182 * m], fill=CYAN, width=12 * m)
    d.line([74 * m, 128 * m, 182 * m, 128 * m], fill=CYAN, width=12 * m)
    r = 26 * m
    d.ellipse([128 * m - r, 128 * m - r, 128 * m + r, 128 * m + r], fill=LIME)
    return img


def main() -> None:
    ASSETS.mkdir(exist_ok=True)
    big = _draw()
    png = big.resize((256, 256), Image.LANCZOS)
    png.save(ASSETS / "scan2bim.png")
    sizes = [16, 32, 48, 64, 128, 256]
    png.save(ASSETS / "scan2bim.ico", sizes=[(x, x) for x in sizes])
    print("wrote", ASSETS / "scan2bim.ico", "and scan2bim.png")


if __name__ == "__main__":
    main()
