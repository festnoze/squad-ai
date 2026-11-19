"""
Makes the alternative wall finishes of OUT OF SIGHT (product owner request of 2026-11-19: wall textures that go with the
cream crepi, varied in texture, one of them a printed wallpaper). Own creation, fully procedural (no source image, no
third party asset), dedicated to the public domain (CC0 1.0).

Four finishes, each in the warm cosy palette of the crepi (Colour/colour_plaster.png), the parquet and the wood, kept
light and low in contrast so the inhabitants, the vision cones and the red player stay readable; none of them is red or
orange (PRD 7.2: the player furniture is the only red thing):
- sage:       soft painted plaster, muted sage green, cloudy trowel marks and a fine sand grain;
- limewash:   warm clay limewash, pale and powdery, large soft clouds crossed by faint brush strokes;
- grasscloth: woven grasscloth wallpaper, dusty blue fibres running horizontally, two 0.9 m panels per repeat;
- wallpaper:  a printed wallpaper, pale sage stripes and small botanical sprigs in a half drop, on a warm off-white.

For each finish (stem wall_<name>, so the library's source checks hold):
- Assets/Art/Environment/wall_<name>.png: the 1024 x 1024 sRGB source (not referenced by any shipped asset);
- Assets/Art/Environment/Colour/colour_wall_<name>.png: the 512 x 512 sRGB colour map (a 2 x 2 box average of the source,
  which keeps the wrap), as tools/assets/derive_env_colours.py prepares the other surfaces;
- Assets/Art/Environment/Detail/detail_wall_<name>.png: the 512 grayscale detail (linear, mean 240/255, highlights capped
  at 1.0: the contract of derive_env_textures.py; only an inhabitant ever shows a detail);
- Assets/Art/Environment/Detail/normal_wall_<name>.png: the 512 tangent space normal map, a periodic Sobel of the finish's
  own height (the plaster approach; a print has no relief of its own, so the wallpaper's height is its paper grain),
  OpenGL convention (green up), scaled to a fixed xy rms per finish, well under the crepi's 0.37.

Seamless by construction: every noise is white noise filtered in the Fourier domain (periodic), every motif is drawn
wrapped around the tile. The script checks the wrap (edgeStep: the colour jump across the wrap edges over the mean jump
between neighbours, 1 = invisible) and prints the stats.

Usage (from the project root, venv activated):  python tools/assets/make_wall_finishes.py
"""
import json
import os

import numpy as np
from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, "..", ".."))
ENV = os.path.join(ROOT, "Assets", "Art", "Environment")
COLOUR = os.path.join(ENV, "Colour")
DETAIL = os.path.join(ENV, "Detail")
N = 1024  # source size
MEAN = 240.0 / 255.0  # Tuning.DetailMean
DETAIL_STD = 0.02  # relative std of the grayscale detail (calm, as the crepi's)


# ----- periodic noise -----

def noise(rng, along, across=None, angle=0.0, n=N):
    """
    Periodic gaussian-filtered white noise, mean 0, std 1. Correlation lengths in px: <along> along the direction at
    <angle> degrees (0 = image x), <across> across it (default: isotropic).
    """
    across = along if across is None else across
    w = rng.standard_normal((n, n))
    fy = np.fft.fftfreq(n)[:, None]
    fx = np.fft.fftfreq(n)[None, :]
    a = np.radians(angle)
    u = fx * np.cos(a) + fy * np.sin(a)
    v = -fx * np.sin(a) + fy * np.cos(a)
    g = np.exp(-2.0 * np.pi ** 2 * ((along * u) ** 2 + (across * v) ** 2))
    r = np.real(np.fft.ifft2(np.fft.fft2(w) * g))
    return (r - r.mean()) / max(r.std(), 1e-9)


def smooth(t):
    return 0.5 + 0.5 * np.tanh(t)


def mix(a, b, t):
    """Per pixel mix of two sRGB colours by t in [0, 1]."""
    a = np.asarray(a, dtype=np.float64)
    b = np.asarray(b, dtype=np.float64)
    return a[None, None, :] * (1.0 - t[..., None]) + b[None, None, :] * t[..., None]


# ----- the four finishes: (sRGB colour 0..1, height) at N x N -----

def sage(rng):
    """Soft painted plaster in a muted sage: cloudy trowel marks, a fine sand grain, a faint sheen of the paint."""
    clouds = 0.6 * noise(rng, 110) + 0.4 * noise(rng, 36)
    rgb = mix((0.815, 0.872, 0.748), (0.765, 0.828, 0.712), smooth(1.1 * clouds))
    # Trowel marks: long soft arcs at a few angles, the ridges of the plaster under the paint.
    trowel = np.zeros((N, N))
    for angle in rng.uniform(0.0, 180.0, 5):
        trowel += noise(rng, 140, 9, angle)
    trowel /= trowel.std()
    grain = noise(rng, 0.8)
    shade = 1.0 + 0.012 * trowel + 0.010 * grain
    rgb = rgb * shade[..., None]
    height = 1.0 * trowel + 0.35 * grain + 0.25 * clouds
    return rgb, height


def limewash(rng):
    """Warm clay limewash: pale and powdery, large soft clouds, faint crossed brush strokes, a fine mineral grain."""
    clouds = 0.55 * noise(rng, 170) + 0.30 * noise(rng, 60) + 0.15 * noise(rng, 20)
    t = smooth(1.5 * clouds)
    rgb = mix((0.885, 0.775, 0.660), (0.945, 0.872, 0.775), t)
    # The brush strokes of a limewash: short sweeps in every direction (no regular crossing, which would read as a
    # woven fabric), stronger where the wash is thin.
    strokes = np.zeros((N, N))
    for angle in rng.uniform(0.0, 180.0, 9):
        strokes += noise(rng, rng.uniform(45, 95), rng.uniform(4, 7), angle) * rng.uniform(0.5, 1.0)
    strokes /= strokes.std()
    grain = noise(rng, 0.7)
    shade = 1.0 + (0.008 + 0.008 * (1.0 - t)) * strokes + 0.008 * grain
    rgb = rgb * shade[..., None]
    height = 0.8 * strokes + 0.3 * grain
    return rgb, height


def grasscloth(rng):
    """
    Woven grasscloth in dusty blue: horizontal grass fibres (slubs of every length), fine cotton warp threads, and two
    panels per repeat with a slight tone shift and a soft seam, as hung paper shows.
    """
    x = np.arange(N)[None, :].repeat(N, 0)
    fibres = 0.55 * noise(rng, 70, 1.1) + 0.30 * noise(rng, 220, 2.5) + 0.15 * noise(rng, 18, 0.8)
    fibres /= fibres.std()
    # A few lighter, sheeny strands and the natural greige of the undyed grass showing through here and there.
    strands = np.clip(noise(rng, 160, 1.4) - 1.6, 0.0, None)
    greige = smooth(1.2 * (noise(rng, 260, 6) - 0.9))
    rgb = mix((0.775, 0.845, 0.900), (0.830, 0.825, 0.785), 0.45 * greige)
    # The panel seams sit a quarter in from the wrap edges, so the wrap check measures the weave, not a seam.
    panel = np.where((x >= N // 4) & (x < 3 * N // 4), 1.012, 0.988)
    warp = np.cos(2.0 * np.pi * x / 8.0) ** 16  # a thin thread every 8 px (about 1.4 cm at the 1.8 m repeat)
    seam_d = np.minimum(np.abs(x - N // 4), np.abs(x - 3 * N // 4)).astype(np.float64)
    seam = np.exp(-(seam_d / 1.6) ** 2)
    shade = panel * (1.0 + 0.045 * fibres + 0.05 * strands - 0.02 * warp - 0.05 * seam)
    rgb = rgb * shade[..., None]
    height = 1.0 * fibres + 0.6 * strands - 0.4 * warp - 1.2 * seam
    return rgb, height


def _sprig(draw, cx, cy, s, mirror, ink):
    """One botanical sprig at (cx, cy), about 2 * s tall: a curved stem, paired leaves, three small buds."""
    leaf, stem, bud = ink
    sign = -1.0 if mirror else 1.0
    pts = []
    for i in range(41):  # the stem: a gentle S from the bottom to the top
        t = i / 40.0
        pts.append((cx + sign * s * 0.18 * np.sin(np.pi * (t - 0.15)) , cy + s * (1.0 - 2.0 * t)))
    w = max(2, int(s * 0.035))
    draw.line(pts, fill=stem, width=w, joint="curve")
    for k, t in enumerate((0.18, 0.36, 0.54, 0.72)):
        i = int(t * 40)
        px, py = pts[i]
        for side in (-1.0, 1.0):
            length = s * (0.40 - 0.12 * t)
            ang = np.radians(-90.0 + side * (52.0 - 18.0 * t) + sign * 6.0)
            ex, ey = px + np.cos(ang) * length, py + np.sin(ang) * length
            # A leaf: a pointed ellipse along (px, py) -> (ex, ey), drawn as a polygon.
            dx, dy = ex - px, ey - py
            nx, ny = -dy, dx
            poly = []
            for j in range(25):
                u = j / 24.0
                bulge = 0.30 * np.sin(np.pi * u) ** 0.9
                poly.append((px + dx * u + nx * bulge, py + dy * u + ny * bulge))
            for j in range(24, -1, -1):
                u = j / 24.0
                bulge = 0.30 * np.sin(np.pi * u) ** 0.9
                poly.append((px + dx * u - nx * bulge, py + dy * u - ny * bulge))
            draw.polygon(poly, fill=leaf)
    tx, ty = pts[-1]
    r = s * 0.075
    for bx, by in ((tx, ty - r * 0.6), (tx - r * 1.9, ty + r * 1.2), (tx + r * 1.9, ty + r * 1.2)):
        draw.ellipse((bx - r, by - r, bx + r, by + r), fill=bud)


def wallpaper(rng):
    """
    A printed wallpaper: pale sage stripes edged by fine pinlines, and small botanical sprigs in a half drop between
    them, on a warm off-white paper. Drawn 4 x supersampled, wrapped around the tile (seamless), then box filtered.
    """
    ss = 4
    big = N * ss
    ground = (0.940, 0.912, 0.846)
    stripe = (0.862, 0.880, 0.808)
    pin = (0.790, 0.825, 0.752)
    leaf = (0.700, 0.765, 0.705)
    stem = (0.655, 0.720, 0.660)
    bud = (0.715, 0.760, 0.835)

    def c8(c):
        return tuple(int(round(v * 255)) for v in c)

    canvas = Image.new("RGB", (big, big), c8(ground))
    draw = ImageDraw.Draw(canvas)
    period = big // 2  # two stripes per repeat
    band = int(0.20 * period)
    pinw = int(0.012 * period)
    gap = int(0.022 * period)
    for k in range(-1, 3):
        x0 = k * period - band // 2
        draw.rectangle((x0, 0, x0 + band, big), fill=c8(stripe))
        for edge in (x0 - gap - pinw, x0 + band + gap):
            draw.rectangle((edge, 0, edge + pinw, big), fill=c8(pin))
    s = 0.30 * period
    ink = (c8(leaf), c8(stem), c8(bud))
    for col in range(2):
        cx = col * period + period // 2
        for row in range(2):
            cy = row * period + (period // 2 if col == 1 else 0)
            for ox in (-big, 0, big):  # wrapped: every copy that can touch the tile
                for oy in (-big, 0, big):
                    _sprig(draw, cx + ox, cy + oy, s, col == 1, ink)
    a = np.asarray(canvas, dtype=np.float64) / 255.0
    rgb = a.reshape(N, ss, N, ss, 3).mean(axis=(1, 3))
    # Ink coverage (how far a pixel is from the paper ground) for the print irregularity and the slight relief.
    ink_amount = np.clip(np.abs(rgb - np.asarray(ground)[None, None, :]).sum(-1) / 0.25, 0.0, 1.0)
    mottle = noise(rng, 3.0)
    grain = noise(rng, 0.8)
    paper_fibre = noise(rng, 6, 1.0, 90.0)
    rgb = rgb * (1.0 + 0.015 * mottle * ink_amount + 0.006 * grain + 0.004 * paper_fibre)[..., None]
    height = 1.0 * grain + 0.6 * paper_fibre + 0.5 * ink_amount
    return rgb, height


# ----- derived maps -----

FINISHES = [
    # name, maker, seed, normal xy rms (the crepi's normal_plaster.png measures 0.37)
    ("sage", sage, 11, 0.08),
    ("limewash", limewash, 23, 0.09),
    ("grasscloth", grasscloth, 37, 0.16),
    ("wallpaper", wallpaper, 41, 0.05),
]


def half(a):
    """2 x 2 box average: 1024 -> 512, keeps the wrap exact."""
    n = a.shape[0] // 2
    return a.reshape(n, 2, n, 2, *a.shape[2:]).mean(axis=(1, 3))


def srgb_to_linear(c):
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def luminance(rgb):
    return 0.2126 * rgb[..., 0] + 0.7152 * rgb[..., 1] + 0.0722 * rgb[..., 2]


def edge_step(a):
    inner = 0.5 * (np.abs(np.diff(a, axis=0)).mean() + np.abs(np.diff(a, axis=1)).mean())
    edge = 0.5 * (np.abs(a[0] - a[-1]).mean() + np.abs(a[:, 0] - a[:, -1]).mean())
    return edge / max(inner, 1e-9)


def detail_of(rgb):
    """The grayscale detail: linear luminance, mean exactly 240/255, relative std DETAIL_STD, highlights capped at 1.0."""
    lum = luminance(srgb_to_linear(rgb))
    z = (lum - lum.mean()) / max(lum.std(), 1e-9)
    d = MEAN * (1.0 + DETAIL_STD * z)
    lo = MEAN * 0.66
    for _ in range(40):
        d = np.clip(d, lo, 1.0)
        d = d + (MEAN - d.mean())
    return np.clip(d, lo, 1.0)


def normal_of(height, rms):
    """Tangent space normal map (OpenGL, green up) of a periodic height, its xy rms set to <rms> by bisection."""
    h = height
    gx = (np.roll(h, -1, 1) - np.roll(h, 1, 1)) * 2 + (np.roll(np.roll(h, -1, 1), 1, 0) - np.roll(np.roll(h, 1, 1), 1, 0)) \
        + (np.roll(np.roll(h, -1, 1), -1, 0) - np.roll(np.roll(h, 1, 1), -1, 0))
    gy = (np.roll(h, -1, 0) - np.roll(h, 1, 0)) * 2 + (np.roll(np.roll(h, -1, 0), 1, 1) - np.roll(np.roll(h, 1, 0), 1, 1)) \
        + (np.roll(np.roll(h, -1, 0), -1, 1) - np.roll(np.roll(h, 1, 0), -1, 1))
    gx, gy = gx / 8.0, gy / 8.0
    lo, hi = 0.0, 1000.0
    for _ in range(60):
        k = 0.5 * (lo + hi)
        nx, ny = -k * gx, k * gy  # image rows grow downwards, texture v upwards
        inv = 1.0 / np.sqrt(nx * nx + ny * ny + 1.0)
        cur = np.sqrt((nx * inv).std() ** 2 + (ny * inv).std() ** 2)
        if cur < rms:
            lo = k
        else:
            hi = k
    n = np.stack([nx * inv, ny * inv, inv], axis=-1)
    return np.clip(np.round((n * 0.5 + 0.5) * 255.0), 0, 255).astype(np.uint8), cur


def save_rgb(a, path):
    Image.fromarray(np.clip(np.round(a * 255.0), 0, 255).astype(np.uint8), mode="RGB").save(path, optimize=True)


def main():
    for folder in (ENV, COLOUR, DETAIL):
        os.makedirs(folder, exist_ok=True)
    report = []
    for name, maker, seed, rms in FINISHES:
        stem = "wall_" + name
        rgb, height = maker(np.random.default_rng(seed))
        rgb = np.clip(rgb, 0.0, 1.0)
        save_rgb(rgb, os.path.join(ENV, stem + ".png"))
        colour = np.clip(half(rgb), 0.0, 1.0)
        save_rgb(colour, os.path.join(COLOUR, "colour_" + stem + ".png"))
        d = detail_of(colour)
        byte = np.clip(np.round(d * 255.0), 0, 255).astype(np.uint8)
        Image.fromarray(np.stack([byte] * 3, axis=-1), mode="RGB").save(os.path.join(DETAIL, "detail_" + stem + ".png"), optimize=True)
        h = half(height)
        nrm, cur = normal_of(h / max(h.std(), 1e-9), rms)
        Image.fromarray(nrm, mode="RGB").save(os.path.join(DETAIL, "normal_" + stem + ".png"), optimize=True)
        q = np.round(colour * 255.0) / 255.0
        report.append({
            "finish": name, "mean": [round(float(x), 4) for x in q.reshape(-1, 3).mean(0)],
            "std": [round(float(x), 4) for x in q.reshape(-1, 3).std(0)], "edgeStep": round(edge_step(q), 3),
            "detailMean": round(float(byte.mean() / 255.0), 5), "normalRms": round(float(cur), 4),
        })
    for r in report:
        print(json.dumps(r))


if __name__ == "__main__":
    main()
