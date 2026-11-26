"""
Prepares the garden backdrop pictures of OUT OF SIGHT (product owner images, docs/LICENSES.md section Environment,
docs/m9/backdrop/NOTES.md).

Garden (product owner image of 2026-11-20, replacing garden_open_horizontal_tile.png of 2026-11-19):
Assets/Art/Environment/garden_open_horizontal_tile_wide.png, 5016 x 1254 RGB, a painted garden panorama of four varied
stretches meant to repeat horizontally: a lawn strip at the bottom (about 11 % of the height), flower beds, shrubs and
trees, a clear blue sky with a few wisps at the top. Its last column repeats its first exactly (measured: mean difference
0.0), so the panorama wraps once that duplicate column goes (period 5015 x 1254, aspect 4.0).

Output Assets/Resources/GardenBackdrop.png, 4096 x 1024 sRGB RGB (aspect 4, GardenBackdrop.ImageAspect), never the
source itself:
- the duplicate last column dropped, then resampled with the horizontal wrap kept (the panorama is resampled three
  times side by side and the middle copy kept, so the left and right edges still meet);
- the sky made exactly uniform near the top (SKY over the top SKY_SOLID of the height, blended into the painted sky down
  to SKY_BLEND): the ring's top edge, the band above the picture (the ring is taller than the picture on some levels,
  the texture is clamped in V) and the sky disc's rim are then one colour, with no line;
- the lawn strip at the bottom shifted toward the game's garden grass (each row's mean moved to LAWN, its grain kept),
  fully up to LAWN_FULL of the height and fading out at LAWN_BLEND, so the ring's foot meets the grass plane without a
  colour step;
- a light haze (HAZE toward HAZE_COLOUR, growing with the height in the picture: the far trees are bluer) so the
  painted garden reads as distance behind the lit house instead of a poster in front of it.

Sky (product owner image of 2026-11-20): Assets/Art/Environment/sky_disc_sun_glow.png, 2048 x 2048 RGBA, a round
overhead sky (transparent outside a disc of radius 1000 px centred on the image), a sun and its bloom at the centre,
soft wisps, a uniform blue rim (130, 191, 253) over its outer 10 % that matches the top of the garden panorama.

Output Assets/Resources/GardenSky.png, SKY_SIZE x SKY_SIZE sRGB RGB, the disc filling the square exactly (UV 0 to 1
spans its diameter, GardenBackdrop's ceiling maps it with no stretch):
- cropped to the disc's own square, composited over SKY (no transparent corner bleeds into the rim when filtered);
- the sun moved off centre toward image right by a disc automorphism (a Moebius map of the unit disc: conformal, so the
  sun and the wisps stay round, and the rim stays the rim): SUN_OFFSET of the radius, so seen from inside the house the
  glow stands roughly where the scene's directional light comes from (GardenBackdrop turns image right toward the
  light's azimuth);
- the rim band (beyond SKY_RIM of the radius) made exactly SKY, the colour of the garden's top: the seam between the
  ring and its ceiling does not show.

Usage (from the project root): python tools/assets/make_garden_backdrop.py
"""

from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "Assets/Art/Environment/garden_open_horizontal_tile_wide.png"
OUTPUT = ROOT / "Assets/Resources/GardenBackdrop.png"
WIDTH = 4096
HEIGHT = 1024

SKY_SOURCE = ROOT / "Assets/Art/Environment/sky_disc_sun_glow.png"
SKY_OUTPUT = ROOT / "Assets/Resources/GardenSky.png"
SKY_SIZE = 1024

# The uniform sky at the top of the garden and on the rim of the sky disc (sRGB): the disc's own rim colour (measured:
# exactly 130, 191, 253 over its outer 10 %), which the panorama's top rows also show (128, 192, 252, deviation about
# 4). GardenBackdrop.SkyTop in the game is this colour.
SKY = np.array([130.0, 191.0, 253.0])
SKY_SOLID = 0.06
SKY_BLEND = 0.20

# The lawn strip's target mean (sRGB, picture space): the grass plane's look read back through the grade (calibrated on
# the game camera's shots, docs/m9/backdrop/NOTES.md: v3 of 2026-11-19 gave (90, 127, 68); on the 2026-11-20 shots the
# grass plane by the ring's foot drew (84, 127, 22) and that lawn (86, 122, 47), too blue; v6 (88, 132, 40) drew
# (84, 127, 11), a touch too yellow; v7 keeps its red and green and lifts its blue, v8 shifts the lawn's brightest top
# rows fully too, which drew a light band under the flower beds from close). Each lawn row's mean moves to LAWN
# at full strength up to LAWN_FULL of the height, fading out at LAWN_BLEND (the wide panorama's lawn ends at about 11 % of
# its height, its top rows the brightest; its flower beds start above 12.5 %): only the mean moves, the grain stays.
LAWN = np.array([88.0, 132.0, 50.0])
LAWN_FULL = 0.115
LAWN_BLEND = 0.14
LAWN_STRENGTH = 1.0

# Aerial haze: at the bottom of the picture HAZE_BOTTOM of the way toward HAZE_COLOUR, at the top HAZE_TOP.
HAZE_COLOUR = np.array([200.0, 220.0, 235.0])
HAZE_BOTTOM = 0.03
HAZE_TOP = 0.14

# The sun's distance from the disc's centre after the automorphism, in disc radii (toward image right), and the
# radius beyond which the disc is made exactly SKY.
SUN_OFFSET = 0.45
SKY_RIM = 0.92
# The source's outer sky is not monotone: its ring median dips about 1.5 levels below the rim colour near 0.85 of the
# radius before rising toward the glow, which the grade draws as a faint dark circle. Between RAMP_START and SKY_RIM each
# ring's median is moved onto a smooth ramp from its value at RAMP_START to SKY (only the median moves: the wisps stay).
RAMP_START = 0.70


def smoothstep(e0: float, e1: float, x: np.ndarray) -> np.ndarray:
    t = np.clip((x - e0) / (e1 - e0), 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def garden() -> None:
    src = np.asarray(Image.open(SOURCE).convert("RGB"))
    if np.abs(src[:, -1].astype(int) - src[:, 0].astype(int)).mean() < 0.5:
        src = src[:, :-1]
    h, w, _ = src.shape
    seam = np.abs(src[:, -1].astype(float) - src[:, 0].astype(float)).mean()
    step = np.abs(np.diff(src.astype(float), axis=1)).mean()
    print(f"garden source period {w} x {h} (aspect {w / h:.3f}), edge step {seam:.2f} (typical column step {step:.2f})")

    # Wrap-preserving resample: three copies side by side, keep the middle one.
    triple = Image.fromarray(np.concatenate([src, src, src], axis=1))
    big = np.asarray(triple.resize((WIDTH * 3, HEIGHT), Image.LANCZOS)).astype(float)
    img = big[:, WIDTH:2 * WIDTH].copy()

    # v: 0 at the bottom of the picture, 1 at the top (one value per row).
    v = 1.0 - (np.arange(HEIGHT) + 0.5) / HEIGHT
    v = v[:, None, None]

    haze = HAZE_BOTTOM + (HAZE_TOP - HAZE_BOTTOM) * v
    img = img + (HAZE_COLOUR - img) * haze

    # Row by row: each row's mean moves to LAWN (so the foot shows no darker or lighter band), its grain kept.
    shift = LAWN - img.mean(axis=1, keepdims=True)
    lawn = LAWN_STRENGTH * (1.0 - smoothstep(LAWN_FULL, LAWN_BLEND, v))
    img = img + shift * lawn

    sky = smoothstep(1.0 - SKY_BLEND, 1.0 - SKY_SOLID, v)
    img = img + (SKY - img) * sky

    out = np.clip(np.rint(img), 0, 255).astype(np.uint8)
    edge = np.abs(out[:, -1].astype(float) - out[:, 0].astype(float)).mean()
    inner = np.abs(np.diff(out.astype(float), axis=1)).mean()
    print(f"garden output {WIDTH} x {HEIGHT}: wrap edge step {edge:.2f} (typical column step {inner:.2f}),"
          f" top row {out[0].reshape(-1, 3).mean(0).round(1)}, bottom row {out[-1].reshape(-1, 3).mean(0).round(1)}")
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(out, "RGB").save(OUTPUT, optimize=True)
    print(f"wrote {OUTPUT.relative_to(ROOT)}")


def bilinear(img: np.ndarray, x: np.ndarray, y: np.ndarray) -> np.ndarray:
    """Samples img (h, w, c) at pixel coordinates x, y (pixel centres at integers), edges clamped."""
    h, w, _ = img.shape
    x = np.clip(x, 0.0, w - 1.0)
    y = np.clip(y, 0.0, h - 1.0)
    x0 = np.floor(x).astype(int)
    y0 = np.floor(y).astype(int)
    x1 = np.minimum(x0 + 1, w - 1)
    y1 = np.minimum(y0 + 1, h - 1)
    fx = (x - x0)[..., None]
    fy = (y - y0)[..., None]
    top = img[y0, x0] * (1.0 - fx) + img[y0, x1] * fx
    bottom = img[y1, x0] * (1.0 - fx) + img[y1, x1] * fx
    return top * (1.0 - fy) + bottom * fy


def sky() -> None:
    src = np.asarray(Image.open(SKY_SOURCE).convert("RGBA")).astype(float)
    alpha = src[..., 3]
    ys, xs = np.nonzero(alpha > 127)
    x0, x1, y0, y1 = xs.min(), xs.max(), ys.min(), ys.max()
    size = max(x1 - x0, y1 - y0) + 1
    cx, cy = (x0 + x1) / 2.0, (y0 + y1) / 2.0
    radius = size / 2.0
    rows, cols = np.mgrid[0:src.shape[0], 0:src.shape[1]]
    rim = src[..., :3][(np.hypot(cols - cx, rows - cy) / radius > 0.95) & (alpha > 250)].mean(0)
    print(f"sky source disc centre ({cx:.1f}, {cy:.1f}) radius {radius:.1f}, rim colour {rim.round(1)}")
    # Over the rim colour: the transparent corners take SKY, so no dark or stray colour bleeds in when filtered.
    a = (alpha / 255.0)[..., None]
    rgb = src[..., :3] * a + SKY * (1.0 - a)

    # The outer sky's ring medians onto a smooth ramp toward SKY (see RAMP_START).
    d = np.hypot(cols - cx, rows - cy) / radius
    edges = np.linspace(RAMP_START - 0.04, 1.0, 97)
    mids = 0.5 * (edges[:-1] + edges[1:])
    medians = np.array([np.median(rgb[(d >= lo) & (d < hi)], axis=0) for lo, hi in zip(edges[:-1], edges[1:])])
    start = medians[np.searchsorted(mids, RAMP_START)]
    ramp = start + (SKY - start) * smoothstep(RAMP_START, SKY_RIM, mids)[:, None]
    weight = smoothstep(RAMP_START - 0.04, RAMP_START, mids)[:, None]
    correction = (ramp - medians) * weight
    inside = d >= edges[0]
    for k in range(3):
        rgb[..., k][inside] += np.interp(d[inside], mids, correction[:, k])
    print(f"sky ring medians from {RAMP_START:.2f}: largest correction {np.abs(correction).max():.2f} levels")

    # Output pixel centres in the unit disc (x right, y down as the image rows run).
    t = (np.arange(SKY_SIZE) + 0.5) / SKY_SIZE * 2.0 - 1.0
    ox, oy = np.meshgrid(t, t)
    z = ox + 1j * oy
    # The automorphism phi(z) = (z - c) / (1 - conj(c) z) sends c to the centre: each output pixel z samples the source
    # at phi(z), so the source's centre (the sun) shows at c. The unit circle maps onto itself.
    c = SUN_OFFSET + 0j
    s = (z - c) / (1.0 - np.conj(c) * z)
    sx = cx + s.real * radius
    sy = cy + s.imag * radius
    img = bilinear(rgb, sx, sy)

    # The rim band in the source's own radius (where it is already uniform): a wisp the map pushed toward the rim fades
    # with it instead of being cut by a circle.
    r = np.abs(s)[..., None]
    band = smoothstep(SKY_RIM - 0.04, SKY_RIM, r)
    img = img + (SKY - img) * band
    out = np.clip(np.rint(img), 0, 255).astype(np.uint8)
    ring = out[(np.abs(s) > SKY_RIM) & (np.abs(z) <= 1.0)].reshape(-1, 3)
    print(f"sky output {SKY_SIZE} x {SKY_SIZE}: sun at {SUN_OFFSET:.2f} of the radius toward image right,"
          f" rim band mean {ring.mean(0).round(2)} (max deviation {np.abs(ring.astype(float) - SKY).max():.0f})")
    SKY_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(out, "RGB").save(SKY_OUTPUT, optimize=True)
    print(f"wrote {SKY_OUTPUT.relative_to(ROOT)}")


def main() -> None:
    garden()
    sky()


if __name__ == "__main__":
    main()
