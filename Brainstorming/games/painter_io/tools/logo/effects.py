"""Fire and electric variants of the Painter.io wordmark, built on the same geometry as the liquid one.

Fire: ember letters (white-hot core, orange body, deep red rim with a cooling crust), flame tongues licking up from the
top edges, a fireball pearl and a burning green chemical fuse, warm glow.
Electric: neon plasma letters (white-hot core, neon body, faint hex cells), small jagged arcs jumping between letters
and crawling on them, a plasma-orb pearl and a cyan live wire, neon glow.
"""
import numpy as np
from PIL import Image, ImageDraw

from sdf import blur, coverage, hex_rgb, over, premul, shift, smoothstep, srgb_to_linear, value_noise
from shading import letter_height, normal_from_height, shade_liquid


def ramp(x, stops):
    """Piecewise linear color ramp (sRGB stops) evaluated on x in [0, 1]; returns linear rgb [..., 3]."""
    xs = [s[0] for s in stops]
    cols = np.array([srgb_to_linear(hex_rgb(s[1])) for s in stops], np.float32)
    out = np.empty(x.shape + (3,), np.float32)
    for c in range(3):
        out[..., c] = np.interp(x, xs, cols[:, c])
    return out


def glow_layer(cov, sigma, color_lin, strength):
    a = np.clip(blur(cov, sigma) * strength, 0.0, 1.0)
    return premul(color_lin, a)


def run_down(mask):
    """Distance in rows from each pixel down to the first True pixel of mask in its column (0 on True pixels)."""
    h = mask.shape[0]
    ys = np.arange(h, dtype=np.float32)[:, None]
    rows = np.where(mask, ys, np.float32(4 * h))
    below = np.minimum.accumulate(rows[::-1], axis=0)[::-1]
    return below - ys


def run_up(mask):
    """Distance in rows from each pixel up to the first True pixel of mask in its column."""
    return run_down(mask[::-1])[::-1]


# ---------------------------------------------------------------------------------------------------------------------
# Fire

FIRE_BODY = [(0.00, '#5A0D04'), (0.12, '#B3200A'), (0.34, '#F0460F'), (0.58, '#FF7E1C'), (0.80, '#FFC547'),
             (1.00, '#FFF3C4')]
FLAME = [(0.00, '#7A1604'), (0.25, '#D9340B'), (0.55, '#FF7A18'), (0.80, '#FFC23A'), (1.00, '#FFF0B8')]
FUSE = [(0.00, '#0B5A47'), (0.40, '#16B894'), (0.75, '#5CF5CF'), (1.00, '#E8FFF8')]


def flames(g, cov, length_em=0.24, seed=11):
    """Flame tongues rising from the top edges of a shape: intensity in [0, 1] outside the shape."""
    h, w = cov.shape
    inside = cov > 0.5
    # Wiggle: shift each row sideways by a smooth noise that grows with the height above the letters.
    warp = (value_noise((h, w), 0.09 * g.em, seed, octaves=2) - 0.5) * 2.0
    down = run_down(inside)
    reach = length_em * g.em
    amount = np.clip(down / reach, 0.0, 1.0)
    dx = np.round(warp * amount * 0.07 * g.em).astype(np.int32)
    cols = np.clip(np.arange(w)[None, :] + dx, 0, w - 1)
    down_w = np.take_along_axis(down, cols, axis=1)
    # Tongue length per column only (no change with height, so no flame breaks into floating specks), with sharp
    # peaks so the edge splits into separate licks.
    tongue = value_noise((8, w), 0.045 * g.em, seed + 1, octaves=2)[:1]
    tongue = 0.20 + 1.0 * smoothstep(0.32, 0.85, tongue) ** 1.4
    t = 1.0 - down_w / (reach * tongue)
    inten = np.clip(t, 0.0, 1.0) ** 1.6
    # No fire inside counters: the column must stay open above for a while.
    up = run_up(inside)
    inten *= smoothstep(0.10 * g.em, 0.22 * g.em, up)
    inten *= (down_w > 0)
    return blur(inten, 0.008 * g.em)


def fuse_sparks(g, count=6, seed=41):
    """Hot spots burning on the fuse and two small sparks flying off it, all on the last third, toward the pearl."""
    rng = np.random.default_rng(seed)
    pts = g.thread_pts
    core = np.zeros((g.H, g.W), np.float32)
    for k in range(count):
        s = 0.62 + 0.34 * (k + rng.random() * 0.6) / count
        i = int(np.clip(s * (len(pts) - 1), 1, len(pts) - 2))
        p = pts[i]
        tangent = pts[i + 1] - pts[i - 1]
        nrm = np.array([tangent[1], -tangent[0]]) / max(float(np.hypot(*tangent)), 1e-6)
        if nrm[1] > 0:
            nrm = -nrm                                   # sparks jump upward
        lift = (0.05 + 0.04 * rng.random()) if k % 3 == 2 else 0.0      # most sparks sit on the fuse itself
        q = p + nrm * g.em * lift + rng.normal(0, 0.004 * g.em, 2)
        r = (0.006 + 0.006 * rng.random()) * g.em
        core = np.maximum(core, np.exp(-((g.xx - q[0]) ** 2 + (g.yy - q[1]) ** 2) / (2 * r * r)))
    glow = blur(core, 0.012 * g.em) * 2.5
    col = srgb_to_linear(hex_rgb('#C8FFEC'))
    layer = premul(srgb_to_linear(hex_rgb('#22E0B8')), np.clip(glow, 0, 0.8))
    return over(layer, premul(col, np.clip(core * 1.3, 0, 1)))


def render_fire(g):
    W, H = g.W, g.H
    img = np.zeros((H, W, 4), np.float32)
    front = coverage(g.sdf_front)
    letters = coverage(g.sdf_letters)

    # Warm shadow and an ember glow on the ground.
    sh = blur(shift(coverage(g.sdf_all), int(0.02 * g.em), int(0.035 * g.em)), 0.03 * g.em) * 0.55
    img = over(img, premul(srgb_to_linear(hex_rgb('#0E0503')), sh))
    img = over(img, glow_layer(front, 0.07 * g.em, srgb_to_linear(hex_rgb('#FF5A1A')), 0.55))

    # Flame tongues behind the letters (their base is hidden under the letter edge).
    fl = flames(g, front)
    fl_col = ramp(np.clip(fl, 0, 1) ** 0.8, FLAME)
    img = over(img, premul(fl_col, np.clip(fl * 1.15, 0.0, 1.0)))

    # Burning fuse (the thread), green chemical flame with a hot core and a few sparks.
    if g.thread_pts is not None:
        q = np.clip(g.thread_d / g.thread_rad, 0.0, 1.0)
        core = 1.0 - q
        flick = value_noise((H, W), 0.05 * g.em, 23, octaves=2)
        col = ramp(np.clip(core * (0.75 + 0.5 * flick), 0, 1), FUSE)
        occl = blur(shift(front, int(0.012 * g.em), int(0.022 * g.em)), 0.016 * g.em)
        col = col * (1.0 - 0.6 * occl)[..., None]
        tc = coverage(g.sdf_thread)
        img = over(img, glow_layer(tc, 0.02 * g.em, srgb_to_linear(hex_rgb('#22E0B8')), 0.6))
        img = over(img, premul(col, tc))
        img = over(img, fuse_sparks(g))

    # Ember letters: heat rises toward the stroke center, a cooling crust near the rim, bevel light for the form.
    d = np.maximum(-g.sdf_letters, 0.0)
    half = 0.085 * g.em
    core = np.clip(d / half, 0.0, 1.0)
    n1 = value_noise((H, W), 0.045 * g.em, 31, octaves=3)
    n2 = value_noise((H, W), 0.022 * g.em, 37, octaves=2)
    vertical = np.clip((g.baseline - g.yy) / (0.75 * g.em), 0.0, 1.0)      # a little hotter near the bottom
    heat = 0.16 + 0.84 * core ** 0.75
    heat = heat * (0.86 + 0.28 * n1) + 0.06 * (1.0 - vertical)
    crust = smoothstep(0.64, 0.78, n2) * (1.0 - smoothstep(0.30, 0.70, core))
    heat = np.clip(heat - 0.22 * crust, 0.0, 1.0)
    col = ramp(heat, FIRE_BODY)
    hgt, hmax = letter_height(g)
    n = normal_from_height(hgt)
    lit = shade_liquid(np.full(3, 0.5, np.float32), n, np.clip(hgt / hmax, 0, 1), lobes=2, gloss=0.55)
    col = col * (0.62 + 0.76 * lit[..., :1]) + 0.25 * np.clip(lit - 0.5 * 1.1, 0, None)
    img = over(img, premul(col, letters))

    # Fireball pearl: a white-hot core toward the upper left, swirling orange body, deep red rim, its own glow.
    pc = coverage(g.sdf_pearl)
    r = np.clip(g.pearl_dist / g.pearl_r, 0.0, 1.0)
    ox = (g.xx - (g.pearl_c[0] - 0.22 * g.pearl_r)) / g.pearl_r
    oy = (g.yy - (g.pearl_c[1] - 0.26 * g.pearl_r)) / g.pearl_r
    hot = np.clip(1.0 - np.sqrt(ox * ox + oy * oy) * 0.95, 0.0, 1.0)
    swirl = value_noise((H, W), 0.05 * g.em, 53, octaves=3)
    heat = 0.34 + 0.78 * hot ** 0.6 + 0.14 * (swirl - 0.5) - 0.18 * r ** 8
    col = ramp(np.clip(heat, 0, 1), FIRE_BODY)
    img = over(img, glow_layer(pc, 0.06 * g.em, srgb_to_linear(hex_rgb('#FF8A1F')), 0.9))
    img = over(img, premul(col, pc))
    return img


# ---------------------------------------------------------------------------------------------------------------------
# Electric

NEON = '#FF4D6D'
NEON_DEEP = '#A3123A'
WIRE = '#2EF2FF'


def hex_cells(g, cell_em=0.07):
    """Distance to the nearest hexagon edge, normalized (0 on an edge, 1 at a cell center)."""
    s = cell_em * g.em
    x, y = g.xx / s, g.yy / s
    # Axial hex coordinates (pointy top), rounded to the nearest cell center.
    q = (np.sqrt(3) / 3 * x - y / 3)
    r = 2.0 / 3.0 * y
    cx, cz = q, r
    cy = -cx - cz
    rx, ry, rz = np.round(cx), np.round(cy), np.round(cz)
    dx, dy, dz = np.abs(rx - cx), np.abs(ry - cy), np.abs(rz - cz)
    fix_x = (dx > dy) & (dx > dz)
    fix_y = (~fix_x) & (dy > dz)
    rx = np.where(fix_x, -ry - rz, rx)
    ry = np.where(fix_y, -rx - rz, ry)
    rz = np.where(~fix_x & ~fix_y, -rx - ry, rz)
    px = (np.sqrt(3) * rx + np.sqrt(3) / 2 * rz)
    py = 1.5 * rz
    ex, ey = x - px, y - py
    # Hexagon distance (pointy top, circumradius 1): max of the three slab distances.
    a = np.abs(ex)
    b = np.abs(ex * 0.5 + ey * np.sqrt(3) / 2)
    c = np.abs(ex * 0.5 - ey * np.sqrt(3) / 2)
    hexd = np.maximum(a, np.maximum(b, c)) / (np.sqrt(3) / 2)
    return np.clip(1.0 - hexd, 0.0, 1.0)


def jagged(a, b, rng, depth=5, rough=0.22):
    """Midpoint-displacement lightning between two points."""
    pts = [np.array(a, np.float64), np.array(b, np.float64)]
    for level in range(depth):
        new = [pts[0]]
        for i in range(len(pts) - 1):
            p, q = pts[i], pts[i + 1]
            m = (p + q) * 0.5
            dvec = q - p
            ln = np.hypot(dvec[0], dvec[1])
            nrm = np.array([-dvec[1], dvec[0]]) / max(ln, 1e-6)
            m = m + nrm * rng.normal(0.0, rough * ln * 0.5)
            new += [m, q]
        pts = new
    return pts


def arc_layers(g, seed=5):
    """Short jagged arcs: bridges between neighbouring letters plus small crawlers on letter tops.
    Returns (core, glow) coverage arrays."""
    rng = np.random.default_rng(seed)
    core = Image.new('L', (g.W, g.H), 0)
    draw = ImageDraw.Draw(core)
    em = g.em
    masks = [g.glyph_mask(i) > 0.5 for i in range(len(g.glyphs))]
    arcs = []
    # Bridges across chosen gaps: (left glyph index, height on its right edge, height on the next glyph's left edge),
    # heights in em above the baseline.
    for i, h_left, h_right in ((0, 0.50, 0.30), (3, 0.30, 0.34), (5, 0.42, 0.40)):
        ya, yb = int(g.baseline - h_left * em), int(g.baseline - h_right * em)
        right = np.where(masks[i][ya])[0]
        left = np.where(masks[i + 1][yb])[0]
        if len(right) == 0 or len(left) == 0:
            continue
        arcs.append(((right.max() - 0.012 * em, ya), (left.min() + 0.012 * em, yb), 0.30))
    # The pawn crackles: from the pearl's right side to the stem of the "i" after it.
    i_index = len(g.glyphs) - 2
    yc = int(g.pearl_c[1])
    left = np.where(masks[i_index][yc])[0]
    if len(left):
        arcs.append(((g.pearl_c[0] + g.pearl_r * 0.85, yc - 0.02 * em), (left.min() + 0.012 * em, yc - 0.05 * em), 0.35))
    # Crawlers hugging the top edges of a few letters: (glyph index, start and end in em from its ink left).
    for i, (x0, x1) in ((0, (0.04, 0.30)), (8, (0.06, 0.26))):
        cols = np.where(masks[i].any(axis=0))[0]
        if len(cols) == 0:
            continue
        xa, xb = cols[0] + x0 * em, cols[0] + x1 * em
        ya = np.where(masks[i][:, int(xa)])[0]
        yb = np.where(masks[i][:, int(xb)])[0]
        if len(ya) == 0 or len(yb) == 0:
            continue
        arcs.append(((xa, ya.min() - 0.03 * em), (xb, yb.min() - 0.025 * em), 0.35))
    for a, b, rough in arcs:
        pts = jagged(a, b, rng, depth=5, rough=rough)
        flat = [tuple(map(float, p)) for p in pts]
        draw.line(flat, fill=255, width=max(2, int(0.017 * em)), joint='curve')
        # A small fork off the middle.
        k = len(pts) // 2 + rng.integers(-3, 4)
        p = pts[int(np.clip(k, 1, len(pts) - 2))]
        tip = p + rng.normal(0, 1, 2) * 0.06 * em + np.array([0, -0.04 * em])
        fork = jagged(p, tip, rng, depth=3, rough=0.3)
        draw.line([tuple(map(float, q)) for q in fork], fill=200, width=max(1, int(0.007 * em)), joint='curve')
    c = np.asarray(core, np.float32) / 255.0
    return blur(c, 0.6 * g.ss), c


def render_electric(g):
    W, H = g.W, g.H
    img = np.zeros((H, W, 4), np.float32)
    front = coverage(g.sdf_front)
    letters = coverage(g.sdf_letters)
    neon = srgb_to_linear(hex_rgb(NEON))
    wire = srgb_to_linear(hex_rgb(WIRE))

    sh = blur(shift(coverage(g.sdf_all), int(0.02 * g.em), int(0.035 * g.em)), 0.03 * g.em) * 0.5
    img = over(img, premul(srgb_to_linear(hex_rgb('#03050C')), sh))
    # Neon halo: a wide soft one and a tight bright one.
    img = over(img, glow_layer(front, 0.10 * g.em, neon, 0.40))
    img = over(img, glow_layer(front, 0.035 * g.em, neon, 0.75))

    # Live wire (the thread): cyan tube, white-hot core, jittered glow.
    if g.thread_pts is not None:
        q = np.clip(g.thread_d / g.thread_rad, 0.0, 1.0)
        tc = coverage(g.sdf_thread)
        img = over(img, glow_layer(tc, 0.03 * g.em, wire, 0.9))
        core = smoothstep(0.75, 0.0, q)
        col = wire * (0.55 + 0.45 * (1 - q))[..., None] + core[..., None] * 0.9
        occl = blur(shift(front, int(0.012 * g.em), int(0.022 * g.em)), 0.016 * g.em)
        col = col * (1.0 - 0.5 * occl)[..., None]
        img = over(img, premul(col, tc))

    # Plasma letters: neon body with faint hex cells, a white-hot core along the stroke center, a deep rim.
    d = np.maximum(-g.sdf_letters, 0.0)
    half = 0.085 * g.em
    core = smoothstep(0.50, 1.05, d / half)
    hexes = hex_cells(g)
    cells = smoothstep(0.0, 0.10, hexes)                       # 0 on the cell lines
    deep = srgb_to_linear(hex_rgb(NEON_DEEP))
    rim = smoothstep(0.0, 0.25, d / half)
    body = deep[None, None, :] * (1 - rim)[..., None] + neon[None, None, :] * rim[..., None]
    body = body * (0.80 + 0.20 * cells)[..., None] + (1 - cells)[..., None] * neon * 0.35
    col = body * 1.15 + core[..., None] * np.array([1.0, 0.80, 0.85], np.float32) * 0.85
    hgt, hmax = letter_height(g)
    lit = shade_liquid(np.full(3, 0.5, np.float32), normal_from_height(hgt), np.clip(hgt / hmax, 0, 1), lobes=2, gloss=0.5)
    col = col * (0.75 + 0.5 * lit[..., :1]) + 0.20 * np.clip(lit - 0.55, 0, None)
    img = over(img, premul(col, letters))

    # Plasma orb pearl.
    pc = coverage(g.sdf_pearl)
    r = np.clip(g.pearl_dist / g.pearl_r, 0.0, 1.0)
    col = neon * (0.6 + 0.6 * r ** 2)[..., None] + smoothstep(0.75, 0.0, r)[..., None] * np.array([1.0, 0.9, 0.95])
    img = over(img, glow_layer(pc, 0.05 * g.em, neon, 0.9))
    img = over(img, premul(col.astype(np.float32), pc))

    # Arcs on top: white core with a pink-white glow.
    glow, core_line = arc_layers(g)
    img = over(img, glow_layer(core_line, 0.030 * g.em, wire * 0.75 + neon * 0.25, 4.0))
    img = over(img, glow_layer(core_line, 0.010 * g.em, wire * 0.5 + 0.5, 2.2))
    img = over(img, premul(np.array([1.0, 0.97, 1.0], np.float32), np.clip(glow * 1.3, 0, 1)))
    return img
