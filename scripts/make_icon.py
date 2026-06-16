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
    m = SUP
    img = Image.new("RGBA", (256 * m, 256 * m), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    cw = 12 * m   # crosshair stroke width
    d.rounded_rectangle(
        [22 * m, 22 * m, 234 * m, 234 * m],
        radius=42 * m, fill=BG, outline=LIME, width=13 * m,
    )
    # Crosshair: equal arms, round caps (drawn as line + end discs).
    for a, b in (((128, 68), (128, 188)), ((68, 128), (188, 128))):
        d.line([a[0] * m, a[1] * m, b[0] * m, b[1] * m], fill=CYAN, width=cw)
        for px, py in (a, b):
            d.ellipse(
                [px * m - cw / 2, py * m - cw / 2, px * m + cw / 2, py * m + cw / 2],
                fill=CYAN,
            )
    r = 21 * m
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
