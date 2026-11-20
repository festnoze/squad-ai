"""
Prepares the garden backdrop picture of OUT OF SIGHT (product owner image of 2026-11-19, docs/LICENSES.md section
Environment).

Source: Assets/Art/Environment/garden_open_horizontal_tile.png, 1254 x 1254 RGB, a painted garden panorama meant to
repeat horizontally: a lawn strip at the bottom, flower beds, shrubs and trees, a clear blue sky at the top. Its last
column repeats its first exactly (measured: mean difference 0.0), so the tile wraps once that duplicate column goes.

Output: Assets/Resources/GardenBackdrop.png, 1024 x 1024 sRGB RGB, never the source itself:
- the duplicate last column dropped, then resampled to a power of two with the horizontal wrap kept (the tile is
  resampled three times side by side and the middle copy kept, so the left and right edges still meet);
- the sky made exactly uniform near the top (SKY over the top SKY_SOLID of the height, blended into the painted sky down
  to SKY_BLEND): the backdrop's top edge then continues into the camera's clear colour (GardenBackdrop.SkyTop in the
  game, which must equal SKY) with no line, whatever the angle;
- the lawn strip at the bottom shifted toward the game's garden grass (its mean moved to LAWN, its grain kept) over the
  bottom LAWN_BLEND of the height, so the backdrop's foot meets the grass plane without a colour step;
- a light haze (HAZE toward HAZE_COLOUR, growing with the height in the picture: the far trees are bluer) so the
  painted garden reads as distance behind the lit house instead of a poster in front of it.

Usage (from the project root): python tools/assets/make_garden_backdrop.py
"""

from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "Assets/Art/Environment/garden_open_horizontal_tile.png"
OUTPUT = ROOT / "Assets/Resources/GardenBackdrop.png"
SIZE = 1024

# The uniform sky at the top (sRGB): the painted sky's own top colour, measured on the source's top rows (127, 190, 253,
# deviation about 1). GardenBackdrop.SkyTop in the game is this colour.
SKY = np.array([127.0, 190.0, 253.0])
SKY_SOLID = 0.06
SKY_BLEND = 0.22

# The lawn strip's target mean (sRGB, picture space): measured on the v1 shots (docs/m9/backdrop/NOTES.md), the painted
# lawn drew (116, 157, 0) after the grade where the grass plane next to it drew (96, 137, 40) (v2: a darker foot, the
# bottom rows of the source are darker than its lawn's mean); each lawn row's mean is moved to LAWN (the grass plane's
# look read back through the grade), at full strength on the bottom LAWN_ROWS / 2 and fading out at LAWN_BLEND of the
# height (its grain kept: only the mean moves).
LAWN = np.array([90.0, 127.0, 68.0])
LAWN_ROWS = 0.10
LAWN_BLEND = 0.16
LAWN_STRENGTH = 1.0

# Aerial haze: at the bottom of the picture HAZE_BOTTOM of the way toward HAZE_COLOUR, at the top HAZE_TOP.
HAZE_COLOUR = np.array([200.0, 220.0, 235.0])
HAZE_BOTTOM = 0.03
HAZE_TOP = 0.14


def smoothstep(e0: float, e1: float, x: np.ndarray) -> np.ndarray:
    t = np.clip((x - e0) / (e1 - e0), 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def main() -> None:
    src = np.asarray(Image.open(SOURCE).convert("RGB"))
    if np.abs(src[:, -1].astype(int) - src[:, 0].astype(int)).mean() < 0.5:
        src = src[:, :-1]
    h, w, _ = src.shape
    seam = np.abs(src[:, -1].astype(float) - src[:, 0].astype(float)).mean()
    step = np.abs(np.diff(src.astype(float), axis=1)).mean()
    print(f"source period {w} x {h}, edge step {seam:.2f} (typical column step {step:.2f})")

    # Wrap-preserving resample: three copies side by side, keep the middle one.
    triple = Image.fromarray(np.concatenate([src, src, src], axis=1))
    big = np.asarray(triple.resize((SIZE * 3, SIZE), Image.LANCZOS)).astype(float)
    img = big[:, SIZE:2 * SIZE].copy()

    # v: 0 at the bottom of the picture, 1 at the top (one value per row).
    v = 1.0 - (np.arange(SIZE) + 0.5) / SIZE
    v = v[:, None, None]

    haze = HAZE_BOTTOM + (HAZE_TOP - HAZE_BOTTOM) * v
    img = img + (HAZE_COLOUR - img) * haze

    # Row by row: each row's mean moves to LAWN (so the foot shows no darker or lighter band), its grain kept.
    shift = LAWN - img.mean(axis=1, keepdims=True)
    lawn = LAWN_STRENGTH * (1.0 - smoothstep(LAWN_ROWS * 0.5, LAWN_BLEND, v))
    img = img + shift * lawn

    sky = smoothstep(1.0 - SKY_BLEND, 1.0 - SKY_SOLID, v)
    img = img + (SKY - img) * sky

    out = np.clip(np.rint(img), 0, 255).astype(np.uint8)
    edge = np.abs(out[:, -1].astype(float) - out[:, 0].astype(float)).mean()
    inner = np.abs(np.diff(out.astype(float), axis=1)).mean()
    print(f"output {SIZE} x {SIZE}: wrap edge step {edge:.2f} (typical column step {inner:.2f}),"
          f" top row {out[0].reshape(-1, 3).mean(0).round(1)}, bottom row {out[-1].reshape(-1, 3).mean(0).round(1)}")
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(out, "RGB").save(OUTPUT, optimize=True)
    print(f"wrote {OUTPUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
