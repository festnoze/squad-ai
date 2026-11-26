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

Tiled walls (product owner request, 2026-11-19, docs/m9/FLOORS_WALLS.md) add two finishes derived, never generated, from
the product owner's own images (their sources stay as given):
- wall_bathroom_white_pastel_blue ("whitetile"): raised white square tiles with black grout above a thin white trim and
  a pastel blue embossed paint;
- wall_kitchen_ivory_sage ("subwaytile"): ivory 3:1 subway tiles in a running bond above a rounded trim and a sage
  paint.
Each image is a whole wall, floor to top: the game maps it ONCE up the wall (Tuning.TiledWallHeight, every room's 2.7 m
wall height) and repeats it only along the wall, so its maps wrap horizontally and are clamped vertically (Unity
imports them Repeat on U, Clamp on V: ModelCatalogBuilder). The tiles already wrap on a grout line split over the two
side edges; the paint and the trim do not (the paint's texture jumps at the wrap), so the script cross-fades those rows
only, within a few centimetres of the wrap, with a copy of themselves rolled by half the width (variance preserving, so
the paint keeps its contrast). The resize to 512 wraps horizontally and clamps vertically; the normal map comes from the
tiles' grout (recessed, a soft bevel), the trim (a rounded bead) and the paint's own relief.

Printed and stone walls (product owner request, 2026-11-19, docs/m9/FLOORS_WALLS.md section 6) add three more finishes
derived from the product owner's own images (sources kept as given). Unlike the tiled walls, each is an all-over pattern
with no band, so it repeats both ways at a metric scale (Tuning.DetailTile*), like the four procedural finishes:
- wall_travertine_greige ("travertine"): a honed greige travertine, cloudy, its pores in horizontal streaks, no joint;
- wall_deco_arches_blue ("arches"): a printed wallpaper, slate blue triple arches in a 4 x 4 lattice on a cream linen;
- wall_linen_pinstripe_olive ("pinstripe"): a beige linen wallpaper, eight olive and taupe pinstripe pairs per repeat.
Their maps are resized through a 3 x 3 wrapped tiling (seamless both ways); where a source jumps a little at its wrap
(the travertine's and the linen's weave), the derived maps cross-fade the rows and the columns within a few centimetres
of each wrap with a copy rolled by half the image along that axis (variance preserving, the mean taken along the blend
axis so a stripe keeps its contrast). The normal map is the image's own fine relief: the stone's pores and grain, the
linen's weave, the print sitting on it.

Walls 4 (product owner request, 2026-11-19, docs/m9/FLOORS_WALLS.md section 7) add two more all-over images of the
product owner, derived the same way (sources kept as given):
- wall_quatrefoil ("quatrefoil"): a printed wallpaper, sage quatrefoils with terracotta stars on a cream paper;
- wall_sage_ribbed ("sageribbed"): a sage painted fluted panel, vertical ribs in real relief.

Usage (from the project root, venv activated):  python tools/assets/make_wall_finishes.py [--only name ...]
(--only wall_bathroom_white_pastel_blue wall_kitchen_ivory_sage remakes just those two; --only wall_travertine_greige
wall_deco_arches_blue wall_linen_pinstripe_olive the three all-over images; --only wall_quatrefoil wall_sage_ribbed the
two of walls 4; no argument remakes everything).
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


def _partition(rng, total, low, high):
    """Random integer lengths in [low, high] summing exactly to <total> (the last ones adjusted to fit)."""
    sizes = []
    left = total
    while left > 0:
        s = int(rng.integers(low, high + 1))
        if left - s < low:
            s = left if left <= high else left - low
        sizes.append(s)
        left -= s
    return sizes


def grasscloth(rng):
    """
    Woven grasscloth in dusty blue: horizontal grass strands laid side by side, each a run of separate pieces of grass
    with their own tone, their own ends and their nodes, held by fine cotton warp threads, and two panels per repeat
    with a slight tone shift and a soft seam, as hung paper shows.

    Stretch fix (2026-11-19, docs/m9/FLOORS_WALLS.md section 7.6): the first version was gaussian noise filtered 70 to
    220 px along x and 1 to 2.5 px across, i.e. horizontally motion-blurred noise. Its strands (1.1 px at 1024) vanished
    in the 512 map, so only smooth streaks with no end were left, about 14 times smoother along the wall than up it at
    play distance, and its normal map was ridges only (xy rms 0.014 along, 0.16 up), which doubled the streaks in the sun:
    the wall read as a texture stretched sideways although the game mapped it exactly. Now every strand is 3 to 8 px
    tall (1.5 to 4 texels of the 512 map, 5 to 14 mm), every piece of grass 120 to 520 px long (21 to 91 cm) with a hard
    end, a node every 40 to 140 px and a warp thread every 8 px, so the weave has edges both ways.
    """
    x = np.arange(N)[None, :].repeat(N, 0)
    blue = np.asarray((0.775, 0.845, 0.900))
    greige_c = np.asarray((0.830, 0.825, 0.785))
    tone = np.zeros((N, N))      # each piece's own light or dark shade (std about 1)
    greige = np.zeros((N, N))    # how much of the undyed greige grass shows (0 to 1)
    profile = np.zeros((N, N))   # the strand's rounded cross section, 0 at its edges, 1 at its middle
    node = np.zeros((N, N))      # the nodes and the cut ends of the pieces
    y = 0
    for h in _partition(rng, N, 3, 8):
        rows = slice(y, y + h)
        across = np.sin(np.pi * (np.arange(h) + 0.5) / h)[:, None]
        profile[rows] = across
        row_tone = np.empty(N)
        row_greige = np.empty(N)
        row_node = np.zeros(N)
        pos = 0
        for length in _partition(rng, N, 120, 520):
            t = rng.standard_normal()
            g = rng.uniform(0.55, 0.95) if rng.random() < 0.22 else rng.uniform(0.0, 0.25)
            # Along a piece its shade drifts a little (thicker and thinner parts of the blade).
            drift = np.cumsum(rng.standard_normal(length)) / np.sqrt(length) * 0.35
            row_tone[pos:pos + length] = t + drift - drift.mean()
            row_greige[pos:pos + length] = g
            # The cut end: a short dark notch where one piece stops and the next starts.
            row_node[pos:pos + 2] = 1.0
            k = pos + int(rng.integers(40, 140))
            while k < pos + length - 4:
                row_node[k:k + 2] = 0.7  # a node of the blade
                k += int(rng.integers(40, 140))
            pos += length
        # Each strand starts its pieces at its own place, so no end lines up with the next strand's.
        shift = int(rng.integers(0, N))
        tone[rows] = np.roll(row_tone, shift)[None, :]
        greige[rows] = np.roll(row_greige, shift)[None, :]
        node[rows] = np.roll(row_node, shift)[None, :] * across
        y += h
    fine = noise(rng, 6, 1.0)  # the fibre grain within a blade
    rgb = blue[None, None, :] * (1.0 - greige[..., None]) + greige_c[None, None, :] * greige[..., None]
    # The panel seams sit a quarter in from the wrap edges, so the wrap check measures the weave, not a seam.
    panel = np.where((x >= N // 4) & (x < 3 * N // 4), 1.012, 0.988)
    warp = (x % 8 < 2).astype(np.float64)  # a cotton thread every 8 px (about 1.4 cm at the 1.8 m repeat), 2 px wide
    seam_d = np.minimum(np.abs(x - N // 4), np.abs(x - 3 * N // 4)).astype(np.float64)
    seam = np.exp(-(seam_d / 1.6) ** 2)
    shade = panel * (1.0 + 0.040 * tone + 0.035 * (profile - 0.7) + 0.008 * fine - 0.050 * node
                     - 0.018 * warp * (1.0 - profile) - 0.05 * seam)
    rgb = rgb * shade[..., None]
    height = 1.0 * profile + 0.15 * tone + 0.6 * node - 0.5 * warp * (1.0 - profile) - 1.2 * seam
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
    ("grasscloth", grasscloth, 37, 0.10),  # was 0.16 of ridges only, which doubled the streaks in the sun
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


# ----- the product owner's tiled walls (2026-11-19): derived, not generated -----

TILED = [
    # source stem, grout ("dark": black grout, cracks and a chipped corner, everything dark is recessed; "courses": a
    # light grout in a running bond, found per course), normal xy rms
    ("wall_bathroom_white_pastel_blue", "dark", 0.12),
    ("wall_kitchen_ivory_sage", "courses", 0.10),
]
TILED_WALL_METRES = 2.7  # Tuning.TiledWallHeight: the image spans the wall once, floor to top
SEAM_BLEND_PX = 48  # source px each side of the wrap cross-faded in the trim and paint rows (about 10 cm)


def runs(mask):
    """The [start, end) runs of True in a 1D boolean array."""
    out = []
    start = None
    for i, m in enumerate(mask):
        if m and start is None:
            start = i
        elif not m and start is not None:
            out.append((start, i))
            start = None
    if start is not None:
        out.append((start, len(mask)))
    return out


def band_rows(rgb):
    """
    The two rows that split a tiled wall image (tiles, then a trim, then paint, top to bottom): (grout_end, paint_top).
    paint_top is the top of the paint: the rows up from the bottom whose mean colour stays near the bottom rows' median.
    Then, going up from it: the trim's shadow and its darker lower edge (rows darker than the tiles' median row), the
    trim's lit face (as bright as the tiles or brighter), and the tiles' last grout line, darker again: grout_end is the
    first row of the trim, just under that grout line.
    """
    rows = rgb.mean(axis=1)
    paint = np.median(rows[-120:], axis=0)
    y = rows.shape[0] - 1
    while y > 0 and np.abs(rows[y - 1] - paint).max() < 0.06:
        y -= 1
    paint_top = y
    prof = luminance(rgb).mean(axis=1)
    lit = np.median(prof[:paint_top]) - 0.05
    y = paint_top - 1
    while y > 0 and prof[y] < lit:
        y -= 1
    while y > 0 and prof[y] >= lit:
        y -= 1
    assert paint_top - y > 4 and prof[y] < lit, "no trim between the tiles and the paint"
    return y + 1, paint_top


def blend_wrap(rgb, top, width):
    """
    Hides the horizontal wrap seam of the rows from <top> down (the trim and the paint; the tiles above wrap on a grout
    line and are left as given): within <width> px of the wrap the rows cross-fade to a copy of themselves rolled by half
    the width (continuous across the wrap), variance preserving (the row mean plus the mixed deviations over
    sqrt(wa^2 + wb^2)), so the fade keeps the texture's grain instead of washing it out.
    """
    out = rgb.copy()
    a = rgb[top:]
    w = a.shape[1]
    b = np.roll(a, w // 2, axis=1)
    x = np.arange(w)
    d = np.minimum(x, w - 1 - x).astype(np.float64)
    t = np.clip(d / width, 0.0, 1.0)
    wa = (t * t * (3.0 - 2.0 * t))[None, :, None]
    wb = 1.0 - wa
    mu = a.mean(axis=1, keepdims=True)
    out[top:] = mu + (wa * (a - mu) + wb * (b - mu)) / np.sqrt(wa * wa + wb * wb)
    return np.clip(out, 0.0, 1.0)


def hwrap_resize(a, size):
    """
    Resizes an H x W x C image to size x size, wrapping horizontally (the repeat along the wall) and clamping vertically
    (the image is mapped once up the wall, never repeated): the image tiled three times across and edge padded top and
    bottom, then the middle copy's box resized (LANCZOS, per channel; the filter reads the neighbours outside the box).
    """
    h, w, c = a.shape
    pad = 24
    big = np.pad(np.concatenate([a, a, a], axis=1), ((pad, pad), (0, 0), (0, 0)), mode="edge")
    out = np.empty((size, size, c))
    for k in range(c):
        im = Image.fromarray(big[..., k].astype(np.float32), mode="F")
        out[..., k] = np.asarray(im.resize((size, size), Image.LANCZOS, box=(w, pad, 2 * w, pad + h)), dtype=np.float64)
    return out


def hwrap_blur(a, sigma):
    """Gaussian blur of a 2D array, periodic horizontally, edge clamped vertically (an FFT over an edge padded copy)."""
    pad = int(np.ceil(4 * sigma)) + 1
    p = np.pad(a, ((pad, pad), (0, 0)), mode="edge")
    fy = np.fft.fftfreq(p.shape[0])[:, None]
    fx = np.fft.fftfreq(p.shape[1])[None, :]
    g = np.exp(-2.0 * np.pi ** 2 * sigma ** 2 * (fx ** 2 + fy ** 2))
    return np.real(np.fft.ifft2(np.fft.fft2(p) * g))[pad:-pad]


def tiled_height(rgb, grout_end, paint_top, mode):
    """
    The relief of a tiled wall image: the tiles proud (1), their grout recessed with a soft bevel (and, "dark" mode,
    the cracks and the chipped corner too), a rounded bead along the trim, the paint set back (0.3) with its own grain
    (its luminance high-pass, the bathroom's embossed paint).
    """
    lum = luminance(rgb)
    h = np.zeros(lum.shape)
    tiles = lum[:grout_end]
    if mode == "dark":
        grout = (tiles < 0.45).astype(np.float64)
    else:
        prof = tiles.mean(axis=1)
        gy = prof < np.median(prof) - 0.06
        grout = np.zeros(tiles.shape)
        grout[gy, :] = 1.0
        for y0, y1 in runs(~gy):
            cp = tiles[y0:y1].mean(axis=0)
            grout[y0:y1, cp < np.median(cp) - 0.05] = 1.0
    bevel = hwrap_blur(grout, 2.0)
    mottling = (tiles - tiles.mean()) / max(tiles.std(), 1e-9)
    h[:grout_end] = 1.0 - bevel + 0.04 * mottling * (1.0 - grout)
    n = paint_top - grout_end
    t = (np.arange(n) + 0.5) / n
    h[grout_end:paint_top] = 0.55 + 0.55 * np.sin(np.pi * t)[:, None]
    paint = lum[paint_top:]
    grain = paint - hwrap_blur(paint, 6.0)
    h[paint_top:] = 0.3 + 0.12 * grain / max(grain.std(), 1e-9)
    return h


def hwrap_normal(height, rms):
    """normal_of, with the height edge padded vertically (no wrap from the wall top to the floor)."""
    p = np.pad(height, ((2, 2), (0, 0)), mode="edge")
    nrm, cur = normal_of(p, rms)
    return nrm[2:-2], cur


def edge_step_h(a):
    """edgeStep across the horizontal wrap only (the vertical one never shows: the image is clamped up the wall)."""
    inner = np.abs(np.diff(a, axis=1)).mean()
    return float(np.abs(a[:, 0] - a[:, -1]).mean() / max(inner, 1e-9))


def heal_defects(rgb, grout_end):
    """
    Walls 4 (docs/m9/FLOORS_WALLS.md section 7): the game now repeats a tiled wall's tile field every image width along
    the wall and every field height up it (15 cm tiles, no longer 27 cm), so the bathroom image's two cracked tiles and
    its chipped corner came back every 1.5 m and read as a pattern. In the derived maps only (the source stays as given),
    each tile cell holding dark pixels that are not grout is replaced by the cell half the image width away (ten tiles
    per width: five tiles exactly, so the grid and the grout stay aligned), when that one is clean. Returns the image and
    the number of cells replaced.
    """
    out = rgb.copy()
    lum = luminance(rgb[:grout_end])
    dark = lum < 0.45
    row_grout = dark.mean(axis=1) > 0.5
    col_grout = dark.mean(axis=0) > 0.5
    w = rgb.shape[1]
    half = w // 2
    rows = [(a, b) for a, b in runs(~row_grout) if b - a > 20]
    cols = [(a, b) for a, b in runs(~col_grout) if b - a > 20]
    # A defect is a cell far from the median cell (every cell cropped to the smallest one, its border margin ignored).
    ch = min(b - a for a, b in rows) - 8
    cw = min(b - a for a, b in cols) - 8
    cells = {(r, c): lum[y0 + 4:y0 + 4 + ch, x0 + 4:x0 + 4 + cw] for r, (y0, y1) in enumerate(rows) for c, (x0, x1) in enumerate(cols)}
    median = np.median(np.stack(list(cells.values())), axis=0)
    error = {k: float(np.abs(v - median).mean()) for k, v in cells.items()}
    typical = float(np.median(list(error.values())))
    bad = {k for k, e in error.items() if e > 3.0 * typical}
    shift = int(round(len(cols) / 2))
    healed = 0
    for (r, c) in sorted(bad):
        y0, y1 = rows[r]
        x0, x1 = cols[c]
        if (r, (c + shift) % len(cols)) in bad:
            continue
        # The cell with half of each grout line around it, so the copy carries its own bevel.
        ya, yb = max(0, y0 - 3), min(grout_end, y1 + 3)
        xa, xb = x0 - 3, x1 + 3
        src = np.take(rgb[ya:yb], np.arange(xa + half, xb + half) % w, axis=1)
        out[ya:yb, np.arange(xa, xb) % w] = src
        healed += 1
    return out, healed


def derive_tiled(stem, mode, rms):
    """Writes the colour, detail and normal maps of one product owner tiled wall image; returns its stats."""
    rgb = np.asarray(Image.open(os.path.join(ENV, stem + ".png")).convert("RGB"), dtype=np.float64) / 255.0
    rows = rgb.shape[0]
    grout_end, paint_top = band_rows(rgb)
    healed = 0
    if mode == "dark":
        rgb, healed = heal_defects(rgb, grout_end)
    fixed = blend_wrap(rgb, grout_end, SEAM_BLEND_PX)
    colour = np.clip(hwrap_resize(fixed, 512), 0.0, 1.0)
    save_rgb(colour, os.path.join(COLOUR, "colour_" + stem + ".png"))
    d = detail_of(colour)
    byte = np.clip(np.round(d * 255.0), 0, 255).astype(np.uint8)
    Image.fromarray(np.stack([byte] * 3, axis=-1), mode="RGB").save(os.path.join(DETAIL, "detail_" + stem + ".png"), optimize=True)
    h = hwrap_resize(tiled_height(fixed, grout_end, paint_top, mode)[..., None], 512)[..., 0]
    nrm, cur = hwrap_normal(h / max(h.std(), 1e-9), rms)
    Image.fromarray(nrm, mode="RGB").save(os.path.join(DETAIL, "normal_" + stem + ".png"), optimize=True)
    q = np.round(colour * 255.0) / 255.0
    split = int(round(grout_end * 512 / rows))
    return {
        "finish": stem, "healedCells": healed, "mean": [round(float(x), 4) for x in q.reshape(-1, 3).mean(0)],
        "trimMetres": [round((rows - paint_top) / rows * TILED_WALL_METRES, 3), round((rows - grout_end) / rows * TILED_WALL_METRES, 3)],
        "edgeStepTiles": round(edge_step_h(q[:split]), 3), "edgeStepPaint": round(edge_step_h(q[split:]), 3),
        "sourceEdgeStepPaint": round(edge_step_h(rgb[paint_top:]), 3),
        "detailMean": round(float(byte.mean() / 255.0), 5), "normalRms": round(float(cur), 4),
    }


# ----- the product owner's all-over walls (2026-11-19): derived, not generated -----

ALLOVER = [
    # source stem, cross-fade the wraps (False where the image already wraps on a plain ground), printed (the ink lies
    # flat on the paper: only the ground's weave makes the relief), high-pass sigma of the relief (512 px), normal xy rms
    ("wall_travertine_greige", True, False, 6.0, 0.12),
    ("wall_deco_arches_blue", False, True, 3.0, 0.05),
    ("wall_linen_pinstripe_olive", True, True, 3.0, 0.08),
    # Walls 4 (2026-11-19, docs/m9/FLOORS_WALLS.md section 7): a printed quatrefoil wallpaper (sage outlines, terracotta
    # stars on a cream paper, an 8 x 8 lattice that wraps on plain paper as given, source edgeStep 0.78), and a sage
    # fluted panel (36 vertical ribs per repeat, real relief; its wrap jumps a little, source edgeStep 1.40, so both
    # wraps are cross-faded: half the width is 18 ribs exactly, so the rolled copy keeps the ribs in phase).
    ("wall_quatrefoil", False, True, 3.0, 0.05),
    ("wall_sage_ribbed", True, False, 6.0, 0.16),
]


def blend_wrap_axis(rgb, width, axis):
    """
    Hides the wrap seam across <axis> (1: the left and right edges, 0: the top and bottom): within <width> px of the
    wrap the image cross-fades to a copy of itself rolled by half the image along <axis> (continuous across the wrap),
    variance preserving around the mean taken along <axis> (a column's mean for the top and bottom wrap, so a vertical
    stripe keeps its colour and contrast; a row's mean for the side wrap).
    """
    n = rgb.shape[axis]
    b = np.roll(rgb, n // 2, axis=axis)
    x = np.arange(n)
    d = np.minimum(x, n - 1 - x).astype(np.float64)
    t = np.clip(d / width, 0.0, 1.0)
    wa = t * t * (3.0 - 2.0 * t)
    wa = wa[None, :, None] if axis == 1 else wa[:, None, None]
    wb = 1.0 - wa
    mu = rgb.mean(axis=axis, keepdims=True)
    out = mu + (wa * (rgb - mu) + wb * (b - mu)) / np.sqrt(wa * wa + wb * wb)
    return np.clip(out, 0.0, 1.0)


def wrap_resize(a, size):
    """Resizes an H x W x C image to size x size through a 3 x 3 wrapped tiling (LANCZOS, per channel): seamless both ways."""
    h, w, c = a.shape
    big = np.tile(a, (3, 3, 1))
    out = np.empty((size, size, c))
    for k in range(c):
        im = Image.fromarray(big[..., k].astype(np.float32), mode="F")
        out[..., k] = np.asarray(im.resize((size, size), Image.LANCZOS, box=(w, h, 2 * w, 2 * h)), dtype=np.float64)
    return out


def wrap_blur(a, sigma):
    """Gaussian blur of a 2D array, periodic both ways (FFT)."""
    fy = np.fft.fftfreq(a.shape[0])[:, None]
    fx = np.fft.fftfreq(a.shape[1])[None, :]
    g = np.exp(-2.0 * np.pi ** 2 * sigma ** 2 * (fx ** 2 + fy ** 2))
    return np.real(np.fft.ifft2(np.fft.fft2(a) * g))


def derive_allover(stem, blend, printed, sigma, rms):
    """Writes the colour, detail and normal maps of one product owner all-over wall image; returns its stats."""
    rgb = np.asarray(Image.open(os.path.join(ENV, stem + ".png")).convert("RGB"), dtype=np.float64) / 255.0
    fixed = rgb
    if blend:
        fixed = blend_wrap_axis(blend_wrap_axis(fixed, SEAM_BLEND_PX, 1), SEAM_BLEND_PX, 0)
    colour = np.clip(wrap_resize(fixed, 512), 0.0, 1.0)
    save_rgb(colour, os.path.join(COLOUR, "colour_" + stem + ".png"))
    d = detail_of(colour)
    byte = np.clip(np.round(d * 255.0), 0, 255).astype(np.uint8)
    Image.fromarray(np.stack([byte] * 3, axis=-1), mode="RGB").save(os.path.join(DETAIL, "detail_" + stem + ".png"), optimize=True)
    # The relief: the luminance's high-pass (dark is recessed: the stone's pores, the weave's gaps), clipped at 2.5 std
    # so a deep pore does not take the whole normal budget. A print's ink lies flat: its lines (darker than the paper by
    # far more than the weave) are masked out, softly, so only the paper's weave shows in the relief.
    lum = luminance(colour)
    flat = np.ones(lum.shape)
    if printed:
        ground = np.median(lum)
        spread = np.median(np.abs(lum - ground))
        ink = wrap_blur((lum < ground - 6.0 * spread).astype(np.float64), 0.8)
        flat = np.clip(1.0 - 1.5 * ink, 0.0, 1.0)
        lum = lum * flat + ground * (1.0 - flat)
    hp = lum - wrap_blur(lum, sigma)
    hp = np.clip(hp / max(hp[flat > 0.99].std(), 1e-9), -2.5, 2.5) * flat
    nrm, cur = normal_of(hp, rms)
    Image.fromarray(nrm, mode="RGB").save(os.path.join(DETAIL, "normal_" + stem + ".png"), optimize=True)
    q = np.round(colour * 255.0) / 255.0
    return {
        "finish": stem, "mean": [round(float(x), 4) for x in q.reshape(-1, 3).mean(0)],
        "std": [round(float(x), 4) for x in q.reshape(-1, 3).std(0)], "edgeStep": round(edge_step(q), 3),
        "sourceEdgeStep": round(edge_step(rgb), 3),
        "detailMean": round(float(byte.mean() / 255.0), 5), "normalRms": round(float(cur), 4),
    }


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Make the wall finishes (all of them when no --only is given).")
    parser.add_argument("--only", nargs="*", default=None,
                        help="finish names (sage, limewash, ...) or tiled wall stems (wall_bathroom_...) to (re)make")
    only = parser.parse_args().only
    for folder in (ENV, COLOUR, DETAIL):
        os.makedirs(folder, exist_ok=True)
    report = []
    for stem, mode, rms in TILED:
        if only is None or stem in only:
            report.append(derive_tiled(stem, mode, rms))
    for stem, blend, printed, sigma, rms in ALLOVER:
        if only is None or stem in only:
            report.append(derive_allover(stem, blend, printed, sigma, rms))
    for name, maker, seed, rms in FINISHES:
        if only is not None and name not in only:
            continue
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
