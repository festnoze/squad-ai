"""
Prepares the window picture of OUT OF SIGHT (product owner image of 2026-11-19, docs/LICENSES.md section Environment).

Source: Assets/Art/Environment/window_wood_blurred_garden.png, 1254 x 1254 RGBA, a front view of a four pane wood
window (two short upper panes over two tall lower ones, a mullion, a transom, a sill) with a blurred green garden
behind the glass, transparent outside the frame (a few stray opaque red specks above it).

Output: Assets/Resources/WindowImage.png, 1024 x 1024 sRGB RGB, the source cropped to the frame's own rectangle (the
outer frame from its left to its right edge, from the top of the frame to the bottom of the sill; the sill's small
overhang past the frame and the transparent margin go), resampled to a power of two. Every texel is opaque, so the
window draws with the plain opaque window pane material (no alpha clip, no blending, no new material).

The slicing layout the game uses (LevelBuilder.WindowImageMesh) is measured here once on the crop and printed: in crop
pixels (crop is 1048 x 1109) the frame is 61 px on each side, the mullion 29 px, the top frame 50 px, the transom 30 px
and the bottom band (frame and sill) 93 px. Re-run after replacing the source image and update the constants of
LevelBuilder if the printed layout moves.

Usage (from the project root): python tools/assets/make_window_image.py
"""

from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "Assets/Art/Environment/window_wood_blurred_garden.png"
OUTPUT = ROOT / "Assets/Resources/WindowImage.png"
SIZE = 1024

# The crop, in source pixels (inclusive left/top, exclusive right/bottom): the outer frame's columns (opaque on every
# row from the top frame to the sill) and the rows from the top frame to the bottom of the sill. One pixel inside the
# measured alpha edges, so no half transparent edge texel remains.
CROP = (102, 80, 1150, 1189)


def is_wood(rgb: np.ndarray) -> np.ndarray:
    """Wood texels: clearly warmer than green (the glass shows a green garden)."""
    r, g = rgb[..., 0].astype(int), rgb[..., 1].astype(int)
    return (r - g > 35) & (r > 90)


def runs(mask: np.ndarray):
    """The (value, first, last) runs of a boolean line, runs shorter than 4 dropped."""
    out = []
    start = 0
    for i in range(1, len(mask) + 1):
        if i == len(mask) or mask[i] != mask[start]:
            if i - start >= 4:
                out.append((bool(mask[start]), start, i - 1))
            start = i
    return out


def main() -> None:
    source = np.array(Image.open(SOURCE).convert("RGBA"))
    left, top, right, bottom = CROP
    crop = source[top:bottom, left:right]
    # The glass itself is very slightly translucent in the source (alpha about 248): its colour already shows the
    # garden, so the alpha is simply dropped. The crop's border must be the opaque frame, never the margin.
    alpha = crop[..., 3]
    edge = min(alpha[0].min(), alpha[-1].min(), alpha[:, 0].min(), alpha[:, -1].min())
    assert edge >= 200 and alpha.min() >= 160, f"the crop reaches the transparent margin (edge alpha {edge}, min {alpha.min()})"
    rgb = crop[..., :3]
    wood = is_wood(rgb)
    h, w = wood.shape
    print(f"crop {w} x {h} px from {SOURCE.name}")
    for y in (int(h * 0.15), int(h * 0.55)):
        print(f"  row {y}: wood/glass runs {runs(wood[y])}")
    for x in (int(w * 0.25), int(w * 0.75)):
        print(f"  column {x}: wood/glass runs {runs(wood[:, x])}")
    image = Image.fromarray(rgb, "RGB").resize((SIZE, SIZE), Image.LANCZOS)
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    image.save(OUTPUT, optimize=True)
    print(f"wrote {OUTPUT.relative_to(ROOT)} ({SIZE} x {SIZE})")


if __name__ == "__main__":
    main()
