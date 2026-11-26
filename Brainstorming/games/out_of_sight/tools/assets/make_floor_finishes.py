"""
Makes the alternative floor finishes of OUT OF SIGHT (M8 ROOMS_PLAN.md section 4: floors that vary without changing
the "floor" gameplay property). Own creation, fully procedural (no source image, no third party asset), dedicated to
the public domain (CC0 1.0), following the same approach as tools/assets/make_wall_finishes.py.

Three finishes, real-colour and matched to the existing floor palette (Assets/Art/Environment/parquet.png,
tile.png) and resolution, kept low in contrast; none of them is red or orange (PRD 7.2: the player furniture is the
only red thing):
- carpet:      wall-to-wall carpet, warm grey-beige loop pile, fine isotropic nap at a few scales with rare darker
               tufts; no visible large motif at its 1 m repeat (Tuning.DetailTileCarpetFinish). Only valid on a
               "soft" room (LevelValidator): a carpet always means quiet;
- marble:      white-grey slabs with fine meandering veins (a zero crossing of a few elongated noise fields, thin
               bright ridges) and a thin joint centred on the wrap edge, half on each side, so adjacent 0.6 m slabs
               (Tuning.DetailTileMarble) meet in one continuous grout line;
- herringbone: darker oak herringbone parquet, boards at +-45 degrees in a classic woven chevron. Built in the 45
               degree rotated frame (u = x + y, v = x - y): a checkerboard of 2w x 2w super-cells, each filled with
               two boards along u (an "even" super-cell) or two boards along v (an "odd" one). Seamless because this
               pattern is independently periodic in u and in v with period 4w, a power-of-two divisor of N, so
               shifting the source image by N in x or in y always lands back on the same pattern.

For each finish (stem floor_<name>, so the library's source checks hold):
- Assets/Art/Environment/floor_<name>.png: the 1024 x 1024 sRGB source (not referenced by any shipped asset);
- Assets/Art/Environment/Colour/colour_floor_<name>.png: the 512 x 512 sRGB colour map (a 2 x 2 box average of the
  source, which keeps the wrap), as tools/assets/derive_env_colours.py prepares the other surfaces;
- Assets/Art/Environment/Detail/detail_floor_<name>.png: the 512 grayscale detail (linear, mean 240/255, highlights
  capped at 1.0: the contract of derive_env_textures.py; only an inhabitant ever shows a detail, so this is never
  seen in practice for a floor, but the library still requires one per textured surface);
- Assets/Art/Environment/Detail/normal_floor_<name>.png: the 512 tangent space normal map, a periodic Sobel of the
  finish's own height, OpenGL convention (green up), scaled to a fixed xy rms per finish.

Seamless by construction: every noise is white noise filtered in the Fourier domain (periodic); the marble joint is
centred on the wrap edge (so it tiles into a continuous grout line); the herringbone chevron is independently
periodic in its own rotated frame with a period dividing N. The script checks the wrap (edgeStep: the colour jump
across the wrap edges over the mean jump between neighbours, 1 = invisible, a deliberately higher value expected at
the marble joint itself) and prints the stats.

M9 floors (2026-11-19) add two generated finishes and derive two product owner images:
- lightoak:    wide light oak planks, the third parquet: pale natural oak, 25 cm boards with staggered butt joints and
               a long fine grain, lighter and greyer than parquet.png, far from the dark herringbone;
- verde:       dark green verde marble, the second marble: deep green clouds and thin pale turbulent-sine veins,
               four 0.8 m slabs per 1.6 m repeat, joints on the wrap edge (as marble) and through the middle;
- tile_bathroom_small_ivory, tile_bathroom_large_teal: the product owner's bathroom tiles (not generated: their
  sources stay as given). Both have their grout split over the two wrap edges, so they tile as is; the script
  resizes them to the 512 colour map through a 3 x 3 wrapped tiling (no clamped border) and builds the normal map
  from the grout grid found per column and per row (tiles up, grout down, a slight bevel).

Usage (from the project root, venv activated): python tools/assets/make_floor_finishes.py [--only name ...]
(--only lightoak verde tile_bathroom_small_ivory ... remakes just those; no argument remakes everything).
"""
import json
import os

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, "..", ".."))
ENV = os.path.join(ROOT, "Assets", "Art", "Environment")
COLOUR = os.path.join(ENV, "Colour")
DETAIL = os.path.join(ENV, "Detail")
N = 1024  # source size
MEAN = 240.0 / 255.0  # Tuning.DetailMean
DETAIL_STD = 0.02  # relative std of the grayscale detail (calm, as the other surfaces')


# ----- periodic noise (tools/assets/make_wall_finishes.py) -----

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
    """
    Per pixel mix of two sRGB colours (or two full N x N x 3 images, or one of each) by t in [0, 1]: a plain colour
    (shape (3,)) is broadcast over the image, an image (shape N, N, 3) is used as is.
    """
    a = np.asarray(a, dtype=np.float64)
    b = np.asarray(b, dtype=np.float64)
    if a.ndim == 1:
        a = a[None, None, :]
    if b.ndim == 1:
        b = b[None, None, :]
    return a * (1.0 - t[..., None]) + b * t[..., None]


# ----- the three finishes: (sRGB colour 0..1, height) at N x N -----

def carpet(rng):
    """
    Wall-to-wall carpet, warm grey-beige loop pile: fine isotropic nap at a few scales, rare darker tufts (where the
    pile catches less light), a very soft large scale cloud so the floor does not look perfectly flat. No visible
    motif at its 1 m repeat (Tuning.DetailTileCarpetFinish): a believable wall-to-wall carpet seen from above, calmer
    and greyer than the rug/soft-floor Carpet surface (product owner's carpet.png).
    """
    nap = 0.5 * noise(rng, 2.0) + 0.3 * noise(rng, 4.5) + 0.2 * noise(rng, 10.0)
    specks = np.clip(noise(rng, 2.5) - 1.6, 0.0, None)
    clouds = noise(rng, 220.0)
    t = smooth(0.8 * clouds)
    rgb = mix((0.585, 0.550, 0.495), (0.625, 0.585, 0.525), t)
    shade = 1.0 + 0.035 * nap - 0.05 * specks
    rgb = rgb * shade[..., None]
    height = 1.0 * nap - 0.8 * specks
    return rgb, height


def marble(rng):
    """
    White-grey marble slabs with fine meandering veins and a thin joint: one 0.6 m slab per repeat
    (Tuning.DetailTileMarble), its joint centred on the wrap edge (half the width on each side) so adjacent slabs
    meet in one continuous grout line when tiled. The veins are the (near) zero crossing of a few elongated noise
    fields at random angles: a network of thin bright ridges, never a brown or warm tone.
    """
    x = np.arange(N)
    X, Y = np.meshgrid(x, x)
    clouds = 0.6 * noise(rng, 180.0) + 0.4 * noise(rng, 70.0)
    t = smooth(1.0 * clouds)
    rgb = mix((0.830, 0.818, 0.790), (0.880, 0.865, 0.828), t)
    vein_field = (0.6 * noise(rng, 190.0, 26.0, float(rng.uniform(0.0, 180.0)))
                  + 0.4 * noise(rng, 110.0, 16.0, float(rng.uniform(0.0, 180.0)))
                  + 0.25 * noise(rng, 70.0, 10.0, float(rng.uniform(0.0, 180.0))))
    vein_field /= max(vein_field.std(), 1e-9)
    vein = np.exp(-(vein_field / 0.10) ** 2)
    rgb = mix(rgb, (0.555, 0.558, 0.565), np.clip(vein * 0.8, 0.0, 1.0))
    grain = noise(rng, 2.0)
    rgb = rgb * (1.0 + 0.006 * grain)[..., None]
    # The joint: a thin band centred on the wrap edge of either axis (so it tiles as a continuous grout line).
    joint_width = 14.0
    edge_x = np.minimum(X, N - X).astype(np.float64)
    edge_y = np.minimum(Y, N - Y).astype(np.float64)
    edge = np.minimum(edge_x, edge_y)
    joint = np.clip(1.0 - edge / (joint_width * 0.5), 0.0, 1.0)
    rgb = mix(rgb, (0.620, 0.615, 0.600), joint * 0.85)
    height = 0.6 * vein + 0.2 * grain - 1.5 * joint
    return np.clip(rgb, 0.0, 1.0), height


def herringbone(rng, w=128):
    """
    Darker oak herringbone parquet: boards at +-45 degrees in a classic woven chevron, each board its own slight
    tone and a dark seam at its long edges (and, fainter, its short ends). Built in the 45 degree rotated frame
    (u = x + y, v = x - y, both integers on the pixel grid): a checkerboard of 2w x 2w super-cells (w the board
    width in that frame, the board length 2w), each filled with two boards running along u (an "even" super-cell,
    <see> Iu + Iv even) or along v (an "odd" one). The combined pattern is independently periodic in u and in v with
    period 4w; with w a power-of-two divisor of N / 4 (128 here, N = 1024) the source tiles exactly.
    """
    x = np.arange(N)
    X, Y = np.meshgrid(x, x)
    u = (X + Y).astype(np.int64)
    v = (X - Y).astype(np.int64)
    iu = u // w
    iv = v // w
    Iu = iu // 2
    Iv = iv // 2
    horizontal = ((Iu + Iv) % 2) == 0
    # A horizontal board spans the full 2w of its super-cell along u, at the fixed row iv (0..w across).
    along_h = (u - Iu * 2 * w).astype(np.float64)
    across_h = (v - iv * w).astype(np.float64)
    board_h = Iu * 1000003 + iv
    # A vertical board spans the full 2w along v, at the fixed column iu.
    along_v = (v - Iv * 2 * w).astype(np.float64)
    across_v = (u - iu * w).astype(np.float64)
    board_v = Iv * 1000003 + iu
    along = np.where(horizontal, along_h, along_v)
    across = np.where(horizontal, across_h, across_v)
    board = np.where(horizontal, board_h, board_v)

    # A stable pseudo random tone per board from its own id (no python loop: a large odd multiplier and a mod).
    salt = (board * 2654435761) % (2 ** 31)
    tone = (salt % 1000) / 999.0

    board_length = 2.0 * w
    edge_across = np.minimum(across, w - across)
    edge_along = np.minimum(along, board_length - along)
    seam = np.clip(np.exp(-(edge_across / 1.6) ** 2) + 0.5 * np.exp(-(edge_along / 2.2) ** 2), 0.0, 1.0)

    grain = noise(rng, 7.0)

    base = (0.300, 0.210, 0.145)
    light = (0.345, 0.248, 0.176)
    rgb = mix(base, light, tone)
    shade = np.clip(1.0 + 0.04 * grain - 0.45 * seam, 0.3, 1.2)
    rgb = rgb * shade[..., None]
    height = 0.6 * grain - 2.0 * seam
    return np.clip(rgb, 0.0, 1.0), height


def lightoak(rng, boards=8):
    """
    Wide light oak planks (M9 floors, 2026-11-19), the third parquet: pale natural oak, clearly lighter and greyer than
    the honey parquet.png and the dark herringbone. <boards> boards side by side per repeat (25 cm each at the 2 m
    repeat of Tuning.DetailTileLightOak), running along the image y axis. Each board column has two butt joints at its
    own random offsets (so a board is 0.4 to 1.6 m long and the joints never line up), every board piece its own slight
    tone, a long fine grain along the board (elongated periodic noise), a few soft knots, a dark thin seam on its long
    edges and, fainter, at its butt joints. Seamless: the columns divide N, every offset wraps modulo N, the noises are
    periodic.
    """
    x = np.arange(N)
    X, Y = np.meshgrid(x, x)
    w = N // boards
    col = X // w
    across = (X - col * w).astype(np.float64)
    # Two joints per column, at random offsets at least a quarter of the repeat apart.
    first = rng.integers(0, N, boards)
    second = (first + rng.integers(N // 4, 3 * N // 4, boards)) % N
    j1 = first[col]
    j2 = second[col]
    lo = np.minimum(j1, j2)
    hi = np.maximum(j1, j2)
    piece = np.where((Y >= lo) & (Y < hi), 0, 1)
    board_id = col * 2 + piece
    tones = rng.uniform(0.0, 1.0, boards * 2)
    tone = tones[board_id]
    # Distance to the nearest butt joint of this column (wrapping).
    d1 = np.abs(Y - j1)
    d1 = np.minimum(d1, N - d1)
    d2 = np.abs(Y - j2)
    d2 = np.minimum(d2, N - d2)
    edge_along = np.minimum(d1, d2).astype(np.float64)
    edge_across = np.minimum(across, w - across)
    seam = np.clip(np.exp(-(edge_across / 1.4) ** 2) + 0.6 * np.exp(-(edge_along / 1.6) ** 2), 0.0, 1.0)

    # Grain along y (angle 90 degrees: image y), long and thin; a second finer streak; soft large clouds.
    grain = 0.65 * noise(rng, 90.0, 1.6, 90.0) + 0.35 * noise(rng, 30.0, 0.9, 90.0)
    clouds = noise(rng, 160.0)
    knots = np.clip(noise(rng, 9.0) - 2.6, 0.0, None)

    base = (0.745, 0.655, 0.525)
    light = (0.815, 0.735, 0.610)
    rgb = mix(base, light, np.clip(0.5 * tone + 0.25 + 0.12 * clouds, 0.0, 1.0))
    shade = np.clip(1.0 + 0.045 * grain - 0.14 * knots - 0.38 * seam, 0.3, 1.2)
    rgb = rgb * shade[..., None]
    height = 0.5 * grain - 0.6 * knots - 2.0 * seam
    return np.clip(rgb, 0.0, 1.0), height


def verde(rng):
    """
    Dark green verde marble (M9 floors, 2026-11-19), the second marble: a deep forest green with darker clouds and a
    network of thin pale veins, four 0.8 m slabs per 1.6 m repeat (Tuning.DetailTileVerde), joints on the wrap edge
    (as marble()'s) and through the middle. Clearly distinct from the white-grey marble. The veins are the classic turbulent sine: the zero
    crossings of sin(2 pi (m x + n y) / N + a * turbulence), with integer m and n and a periodic turbulence, so they
    wrap exactly; two such families at different angles cross like real veining. No red or orange (PRD 7.2).
    """
    x = np.arange(N)
    X, Y = np.meshgrid(x, x)
    clouds = 0.6 * noise(rng, 150.0) + 0.4 * noise(rng, 55.0)
    t = smooth(1.1 * clouds)
    rgb = mix((0.085, 0.170, 0.135), (0.150, 0.265, 0.210), t)
    turb1 = 0.6 * noise(rng, 120.0) + 0.3 * noise(rng, 40.0) + 0.1 * noise(rng, 12.0)
    turb2 = 0.6 * noise(rng, 100.0) + 0.3 * noise(rng, 35.0) + 0.1 * noise(rng, 10.0)
    phase1 = 2.0 * np.pi * (2 * X + 1 * Y) / N + 1.7 * turb1
    phase2 = 2.0 * np.pi * (-1 * X + 3 * Y) / N + 1.5 * turb2
    vein1 = np.exp(-(np.sin(phase1) / 0.06) ** 2)
    vein2 = np.exp(-(np.sin(phase2) / 0.04) ** 2) * smooth(1.5 * noise(rng, 200.0))
    vein = np.clip(vein1 + 0.7 * vein2, 0.0, 1.0)
    rgb = mix(rgb, (0.700, 0.760, 0.720), np.clip(vein * 0.85, 0.0, 1.0))
    grain = noise(rng, 2.0)
    rgb = rgb * (1.0 + 0.012 * grain)[..., None]
    # Joints on the wrap edge and through the middle: four 0.8 m slabs per repeat, so one slab's veins never repeat
    # next to themselves.
    joint_width = 10.0
    half_n = N // 2
    xm = X % half_n
    ym = Y % half_n
    edge_x = np.minimum(xm, half_n - xm).astype(np.float64)
    edge_y = np.minimum(ym, half_n - ym).astype(np.float64)
    edge = np.minimum(edge_x, edge_y)
    joint = np.clip(1.0 - edge / (joint_width * 0.5), 0.0, 1.0)
    rgb = mix(rgb, (0.060, 0.090, 0.075), joint * 0.8)
    height = 0.6 * vein + 0.2 * grain - 1.5 * joint
    return np.clip(rgb, 0.0, 1.0), height


# ----- the product owner's bathroom tiles (M9 floors, 2026-11-19): derived, not generated -----

def periodic_resize(a, size):
    """
    Resizes a seamless square image (H x W x C floats) to size x size, keeping the wrap: the image is tiled 3 x 3,
    resized by the same factor (LANCZOS, per channel) and the centre cut out, so the filter sees the wrapped
    neighbours at every edge instead of a clamped border.
    """
    n = a.shape[0]
    big = np.tile(a, (3, 3, 1))
    out = np.empty((size * 3, size * 3, a.shape[2]))
    for c in range(a.shape[2]):
        im = Image.fromarray(big[..., c].astype(np.float32), mode="F")
        out[..., c] = np.asarray(im.resize((size * 3, size * 3), Image.LANCZOS), dtype=np.float64)
    del n
    return out[size:2 * size, size:2 * size]


def grout_mask_1d(profile):
    """
    The grout of a tile image along one axis: True where the mean luminance of that column (or row) departs strongly
    from the tiles' median (a straight grout line, darker or lighter than the tiles).
    """
    med = np.median(profile)
    dev = np.abs(profile - med)
    return dev > dev.mean() + 2.0 * dev.std()


def tile_source(stem):
    """
    A product owner tile image (Assets/Art/Environment/<stem>.png, a square grid of tiles with grout on both wrap
    edges): its sRGB colour at full size and a height (tiles up, grout down, a slight bevel, plus a faint trace of
    the tile's own mottling), both at the source size. The grout is found per column and per row (the grid is
    axis aligned), so the height is clean and periodic whatever the grout's colour (darker for the ivory tiles,
    lighter for the teal ones).
    """
    rgb = np.asarray(Image.open(os.path.join(ENV, stem + ".png")).convert("RGB"), dtype=np.float64) / 255.0
    lum = luminance(rgb)
    gx = grout_mask_1d(lum.mean(axis=0))
    gy = grout_mask_1d(lum.mean(axis=1))
    grout = np.maximum(gx[None, :], gy[:, None]).astype(np.float64)
    # A soft bevel: a periodic gaussian blur of the grout mask.
    n = grout.shape[0]
    f = np.fft.fftfreq(n)
    g = np.exp(-2.0 * np.pi ** 2 * (2.0 ** 2) * (f[:, None] ** 2 + f[None, :] ** 2))
    bevel = np.real(np.fft.ifft2(np.fft.fft2(grout) * g))
    mottling = (lum - lum.mean()) / max(lum.std(), 1e-9)
    height = -2.0 * bevel + 0.08 * mottling * (1.0 - grout)
    return rgb, height


def derive_tile(stem, rms):
    """Writes the colour, detail and normal maps of one product owner tile image; returns its stats."""
    rgb, height = tile_source(stem)
    colour = np.clip(periodic_resize(rgb, 512), 0.0, 1.0)
    save_rgb(colour, os.path.join(COLOUR, "colour_" + stem + ".png"))
    d = detail_of(colour)
    byte = np.clip(np.round(d * 255.0), 0, 255).astype(np.uint8)
    Image.fromarray(np.stack([byte] * 3, axis=-1), mode="RGB").save(os.path.join(DETAIL, "detail_" + stem + ".png"), optimize=True)
    h = periodic_resize(height[..., None], 512)[..., 0]
    nrm, cur = normal_of(h / max(h.std(), 1e-9), rms)
    Image.fromarray(nrm, mode="RGB").save(os.path.join(DETAIL, "normal_" + stem + ".png"), optimize=True)
    q = np.round(colour * 255.0) / 255.0
    return {
        "finish": stem, "mean": [round(float(x), 4) for x in q.reshape(-1, 3).mean(0)],
        "std": [round(float(x), 4) for x in q.reshape(-1, 3).std(0)], "edgeStep": round(edge_step(q), 3),
        "sourceEdgeStep": round(edge_step(rgb), 3),
        "detailMean": round(float(byte.mean() / 255.0), 5), "normalRms": round(float(cur), 4),
    }


# ----- derived maps (tools/assets/make_wall_finishes.py) -----

FINISHES = [
    # name, maker, seed, normal xy rms (the crepi's normal_plaster.png measures 0.37; the wall finishes 0.05 to 0.16)
    ("carpet", carpet, 53, 0.10),
    ("marble", marble, 61, 0.06),
    ("herringbone", herringbone, 73, 0.18),
    # M9 floors (2026-11-19): the third parquet and the second marble.
    ("lightoak", lightoak, 89, 0.14),
    ("verde", verde, 97, 0.06),
]

# M9 floors (2026-11-19): the product owner's bathroom tiles (source stem, normal xy rms), derived, never regenerated.
TILES = [
    ("tile_bathroom_small_ivory", 0.12),
    ("tile_bathroom_large_teal", 0.10),
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
    import argparse
    parser = argparse.ArgumentParser(description="Make the floor finishes (all of them when no --only is given).")
    parser.add_argument("--only", nargs="*", default=None,
                        help="finish names (carpet, marble, ...) or tile stems (tile_bathroom_...) to (re)make")
    only = parser.parse_args().only
    for folder in (ENV, COLOUR, DETAIL):
        os.makedirs(folder, exist_ok=True)
    report = []
    for stem, rms in TILES:
        if only is None or stem in only:
            report.append(derive_tile(stem, rms))
    for name, maker, seed, rms in FINISHES:
        if only is not None and name not in only:
            continue
        stem = "floor_" + name
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
