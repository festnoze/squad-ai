"""Bake the bedroom handoff pack: procedural low-poly GLBs, one shared texture atlas, inventory, ZIP and previews.

Run from tools/assets with its venv: python bedroom_handoff.py
Outputs ArtHandoff/Bedroom/ (GLBs, bedroom_textiles.png, inventory.json), Build/bedroom/Bedroom.zip and
Build/bedroom/preview/ (software renders: bedroom_set.png and one PNG per item).

Every model: metres, Y up, front +Z, pivot at the bottom centre (contact point). Plain finishes are COLOR_0, the textured
ones sample one 512 px atlas (four quadrants: denim, knit, pale oak, wicker) tinted by COLOR_0, so the whole set needs one
image (in game: one dressing slice of the wall arrays).
"""

import json
import math
import zipfile

import numpy as np
from PIL import Image

from room_dressing import Model, OUT, UP, grid_faces, rotated

DESTINATION = OUT.parent / "Bedroom"
BUILD = OUT.parents[1] / "Build" / "bedroom"
ATLAS = "bedroom_textiles.png"
QUADS = {"denim": (0.0, 0.0), "knit": (0.5, 0.0), "wood": (0.0, 0.5), "wicker": (0.5, 0.5)}
RNG = np.random.default_rng(7)


# ----- The atlas -----

def make_atlas(path):
    size = 512
    half = size // 2
    y, x = np.mgrid[0:half, 0:half].astype(float)
    noise = RNG.random((half, half))

    # Denim: indigo 3/1 twill, diagonal ribs with white weft flecks and soft fading streaks.
    twill = (((x + y) // 2) % 4 < 2).astype(float)
    fade = 0.5 + 0.5 * np.sin(x / 23.0 + np.sin(y / 31.0) * 2.0)
    denim = np.stack([62 + 18 * twill, 88 + 20 * twill, 128 + 22 * twill], -1)
    denim = denim * (0.9 + 0.12 * fade[..., None]) + (noise[..., None] - 0.5) * 22
    flecks = (RNG.random((half, half)) > 0.985)[..., None]
    denim = np.where(flecks, denim + 45, denim)

    # Knit: near white V stitches in columns, so the vertex tint gives the yarn its colour.
    cx = (x % 10) - 5
    cy = (y + np.abs(cx) * 0.9) % 8
    stitch = 0.80 + 0.20 * np.clip(np.sin(cy / 8 * math.pi), 0, 1) * (1 - np.abs(cx) / 7)
    knit = np.repeat((246 * stitch + (noise - 0.5) * 10)[..., None], 3, -1)

    # Pale oak: honey base, grain running along u (image x), fine pores.
    wobble = np.sin(x / 41.0) * 6 + np.sin(x / 13.0 + y / 50.0) * 2
    rings = 0.5 + 0.5 * np.sin((y + wobble) / 5.5 + np.sin(y / 37.0) * 3)
    grain = 0.88 + 0.12 * rings - 0.06 * (RNG.random((half, half)) > 0.93)
    wood = np.stack([214 * grain, 174 * grain, 124 * grain], -1) + (noise[..., None] - 0.5) * 8

    # Wicker: a basket weave of 32 px cells, strands alternating across and along, each shaded round.
    cell = ((x // 32) + (y // 32)) % 2
    along = np.where(cell == 0, (y % 8) / 8, (x % 8) / 8)
    strand = 0.72 + 0.28 * np.sin(along * math.pi)
    wicker = np.stack([200 * strand, 160 * strand, 104 * strand], -1) + (noise[..., None] - 0.5) * 12

    atlas = np.zeros((size, size, 3))
    atlas[:half, :half] = denim
    atlas[:half, half:] = knit
    atlas[half:, :half] = wood
    atlas[half:, half:] = wicker
    Image.fromarray(np.clip(atlas, 0, 255).astype(np.uint8)).save(path, optimize=True)


def atlas_uv(quad, s, t):
    """A point of a quadrant, s and t in [0, 1] (clamped), kept off the quadrant's edge for the mip levels."""
    u0, v0 = QUADS[quad]
    s = min(max(s, 0.0), 1.0)
    t = min(max(t, 0.0), 1.0)
    return (u0 + 0.02 + s * 0.46, v0 + 0.02 + t * 0.46)


# ----- Geometry helpers -----

def add_outward(model, material, points, tris, color, uv=None, inside=None):
    """Adds triangles turned so their normals point away from inside(centroid) (a point inside the solid)."""
    points = [tuple(map(float, p)) for p in points]
    fixed = []
    for a, b, c in tris:
        pa, pb, pc = (np.array(points[i]) for i in (a, b, c))
        normal = np.cross(pb - pa, pc - pa)
        centroid = (pa + pb + pc) / 3
        if np.dot(normal, centroid - np.asarray(inside(centroid))) < 0:
            b, c = c, b
        fixed.append((a, b, c))
    if isinstance(color, list):
        # One colour per vertex: split per colour is not needed, Model.add takes one colour; paint via groups.
        raise TypeError("use add_painted for per vertex colours")
    model.add(material, points, fixed, color, uv)


def add_painted(model, material, points, tris, colors, uv, inside):
    """add_outward with one colour per vertex: the triangles are grouped by their first vertex's colour."""
    groups = {}
    for tri in tris:
        groups.setdefault(colors[tri[0]], []).append(tri)
    for color, group in groups.items():
        used = sorted({i for tri in group for i in tri})
        remap = {old: new for new, old in enumerate(used)}
        add_outward(model, material, [points[i] for i in used], [tuple(remap[i] for i in tri) for tri in group], color,
                    [uv[i] for i in used] if uv else None, inside)


def tex_box(model, material, center, size, quad, color, scale=0.5, grain=0):
    """A box whose six faces sample one quadrant, the grain (image u) along axis `grain` when it lies in the face."""
    center = np.asarray(center, dtype=float)
    half = np.asarray(size, dtype=float) / 2
    axes = np.eye(3)
    for face in range(3):
        u, v = (face + 1) % 3, (face + 2) % 3
        if v == grain or (grain == face and half[v] > half[u]):
            u, v = v, u
        for side in (-1, 1):
            corners = ((-1, -1), (1, -1), (1, 1), (-1, 1))
            points = [center + side * half[face] * axes[face] + a * half[u] * axes[u] + b * half[v] * axes[v] for a, b in corners]
            uv = [atlas_uv(quad, 0.5 + a * half[u] / scale, 0.5 + b * half[v] / scale) for a, b in corners]
            add_outward(model, material, points, ((0, 1, 2), (0, 2, 3)), color, uv, lambda _: center)


def flat_box(model, material, center, size, color, yaw=0):
    model.box(material, center, size, color, yaw)


def soft_tube(model, material, path, width, height, sides, colors, quad=None, length_scale=0.6, caps=(True, True), squash=True,
              side_axis=None):
    """
    A flattened cloth tube along a path (a sleeve, a trouser leg, a sock), its cross-section an ellipse of half width
    `width` and half height `height` (numbers or one per path point), its bottom pressed flat on the floor when `squash`.
    `colors` is one colour or one per path point (rings). UV: along the path in `quad`, around the section.
    """
    path = np.asarray(path, dtype=float)
    count = len(path)
    widths = np.broadcast_to(np.asarray(width, dtype=float), (count,))
    heights = np.broadcast_to(np.asarray(height, dtype=float), (count,))
    ring_colors = colors if isinstance(colors, (list, tuple)) else [colors] * count
    points, uv, paint = [], [], []
    distance = 0.0
    for i, centre in enumerate(path):
        if i:
            distance += float(np.linalg.norm(path[i] - path[i - 1]))
        tangent = path[min(i + 1, count - 1)] - path[max(i - 1, 0)]
        tangent /= np.linalg.norm(tangent)
        side = np.cross(UP, tangent) if side_axis is None else np.asarray(side_axis, dtype=float)
        side = side / np.linalg.norm(side) if np.linalg.norm(side) > 1e-6 else np.array((1.0, 0, 0))
        up = np.cross(tangent, side)
        for j in range(sides + 1):
            angle = 2 * math.pi * j / sides
            p = centre + side * math.cos(angle) * widths[i] + up * math.sin(angle) * heights[i]
            if squash:
                p[1] = max(p[1], 0.002)
            points.append(p)
            uv.append(atlas_uv(quad, distance / length_scale, j / sides) if quad else (0, 0))
            paint.append(ring_colors[i])
    columns = sides + 1
    tris = grid_faces(count, columns)
    centres = path

    def inside(p):
        return centres[int(np.argmin(np.linalg.norm(centres - p, axis=1)))]

    for end, enabled in ((0, caps[0]), (count - 1, caps[1])):
        if not enabled:
            continue
        hub = len(points)
        points.append(path[end].copy())
        uv.append(uv[end * columns])
        paint.append(ring_colors[end])
        tris += [(hub, end * columns + j, end * columns + j + 1) for j in range(sides)]
    # Caps: the inside point of a cap's triangle is a step back along the path.
    def inside_capped(p):
        nearest = int(np.argmin(np.linalg.norm(centres - p, axis=1)))
        if nearest == 0:
            return centres[0] + (centres[1] - centres[0]) * 0.5
        if nearest == count - 1:
            return centres[-1] + (centres[-2] - centres[-1]) * 0.5
        return centres[nearest]

    add_painted(model, material, points, _drop_degenerate(points, tris), paint, uv if quad else None,
                inside_capped if any(caps) else inside)


def _drop_degenerate(points, tris):
    kept = []
    for a, b, c in tris:
        pa, pb, pc = (np.asarray(points[i]) for i in (a, b, c))
        if np.linalg.norm(np.cross(pb - pa, pc - pa)) > 1e-9:
            kept.append((a, b, c))
    return kept


def ellipsoid(model, material, center, radii, segments, rings, color, quad=None, bottom=True, noise=0.0, seed=0, ground=False):
    """An ellipsoid (poles on Y), optionally lumpy, with its own UV square in `quad` and no bottom pole when bottom=False."""
    rng = np.random.default_rng(seed)
    bumps = 1 + noise * (rng.random((rings + 1, segments + 1)) - 0.5)
    bumps[:, -1] = bumps[:, 0]
    center = np.asarray(center, dtype=float)
    points, uv = [], []
    first = 0 if bottom else 1
    for r in range(first, rings + 1):
        phi = math.pi * r / rings - math.pi / 2
        for j in range(segments + 1):
            theta = 2 * math.pi * j / segments
            k = bumps[r, j] if 0 < r < rings else 1
            p = center + np.array((math.cos(phi) * math.cos(theta) * radii[0] * k, math.sin(phi) * radii[1] * k,
                                   math.cos(phi) * math.sin(theta) * radii[2] * k))
            if ground:
                p[1] = max(p[1], 0.0015)
            points.append(p)
            uv.append(atlas_uv(quad, j / segments, (r - first) / max(rings - first, 1)) if quad else (0, 0))
    tris = _drop_degenerate(points, grid_faces(rings + 1 - first, segments + 1))
    add_outward(model, material, points, tris, color, uv if quad else None, lambda _: center)


def lathe_uv(model, material, profile, segments, color, quad, center=(0, 0, 0), repeats=1, t_scale=None):
    """A lathe (rings of (radius, y), no pole) whose UV wraps `repeats` times around in `quad`, seams duplicated."""
    center = np.asarray(center, dtype=float)
    per = segments // repeats
    heights = [y for _, y in profile]
    span = t_scale or (max(heights) - min(heights)) or 1
    for block in range(repeats):
        points, uv = [], []
        for radius, y in profile:
            for k in range(per + 1):
                angle = 2 * math.pi * (block * per + k) / segments
                points.append(center + np.array((radius * math.cos(angle), y, radius * math.sin(angle))))
                uv.append(atlas_uv(quad, k / per, (y - min(heights)) / span))
        tris = _drop_degenerate(points, grid_faces(len(profile), per + 1))
        model.add(material, points, tris, color, uv)


def cylinder_z(model, material, cx, cy, z0, z1, radius, segments, color, front_color=None):
    """A short cylinder on the Z axis (front cap at z1), for the alarm clock's body and face."""
    rim = [(cx + radius * math.cos(2 * math.pi * i / segments), cy + radius * math.sin(2 * math.pi * i / segments)) for i in range(segments)]
    points = [(x, y, z0) for x, y in rim] + [(x, y, z1) for x, y in rim]
    tris = []
    for i in range(segments):
        j = (i + 1) % segments
        tris += [(i, j, segments + j), (i, segments + j, segments + i)]
    axis = lambda p: (cx, cy, p[2])
    add_outward(model, material, points, tris, color, inside=axis)
    for z, tint in ((z0, color), (z1, front_color or color)):
        cap = [(cx, cy, z)] + [(x, y, z) for x, y in rim]
        add_outward(model, material, cap, [(0, i + 1, (i + 1) % segments + 1) for i in range(segments)], tint,
                    inside=lambda p, z=z: (cx, cy, z - math.copysign(0.01, z - (z0 + z1) / 2)))


# ----- The items -----

def bedside_table():
    model = Model("bedside_table")
    oak = model.material("Bedroom textiles", roughness=0.66, texture=ATLAS)
    matte = model.material("Bedroom matte")
    for x in (-0.180, 0.180):
        for z in (-0.155, 0.155):
            tex_box(model, oak, (x, 0.045, z), (0.032, 0.090, 0.032), "wood", "#D9CDBE", grain=1)
    tex_box(model, oak, (0, 0.100, 0), (0.43, 0.020, 0.37), "wood", "#E8DFD3")
    for x in (-0.205, 0.205):
        tex_box(model, oak, (x, 0.316, 0), (0.020, 0.412, 0.37), "wood", "#FFFFFF", grain=1)
    tex_box(model, oak, (0, 0.316, -0.178), (0.39, 0.412, 0.014), "wood", "#9F8E7C", grain=0)
    tex_box(model, oak, (0, 0.375, 0.002), (0.39, 0.018, 0.36), "wood", "#E8DFD3")
    tex_box(model, oak, (0, 0.536, 0), (0.45, 0.028, 0.40), "wood", "#FFFFFF")
    tex_box(model, oak, (0, 0.454, 0.181), (0.384, 0.130, 0.020), "wood", "#F6EEE4")
    flat_box(model, matte, (0, 0.454, 0.199), (0.060, 0.016, 0.016), "#B08D4E")
    return model


def bedside_lamp():
    model = Model("bedside_lamp")
    glaze = model.material("Bedroom glaze", roughness=0.4)
    matte = model.material("Bedroom matte")
    shade = model.material("Pleated shade", roughness=0.9, double_sided=True)
    model.lathe(glaze, ((0, 0), (0.046, 0), (0.060, 0.016), (0.068, 0.044), (0.062, 0.074), (0.042, 0.097),
                        (0.016, 0.108), (0, 0.110)), 10, "#C99A3B")
    model.lathe(matte, ((0.009, 0.104), (0.009, 0.176)), 6, "#B08D4E")
    model.lathe(matte, ((0, 0.170), (0.020, 0.178), (0.028, 0.196), (0.023, 0.216), (0, 0.229)), 8, "#FFF4D6")
    pleats = 24
    rings = ((0.115, 0.140), (0.072, 0.300))
    points, paint = [], []
    for radius, y in rings:
        for i in range(pleats):
            a = 2 * math.pi * i / pleats
            r = radius * (1.0 if i % 2 == 0 else 0.93)
            points.append((r * math.cos(a), y, r * math.sin(a)))
            paint.append("#F3E8D4" if i % 2 == 0 else "#D8C4A4")
    tris = []
    for i in range(pleats):
        j = (i + 1) % pleats
        tris += [(i, j, pleats + j), (i, pleats + j, pleats + i)]
    add_painted(model, shade, points, tris, paint, None, lambda p: (0, p[1], 0))
    return model


def alarm_clock():
    model = Model("alarm_clock")
    glaze = model.material("Bedroom glaze", roughness=0.4)
    matte = model.material("Bedroom matte")
    metal = model.material("Bedroom brass", roughness=0.35, metallic=0.7)
    body = "#3E7D7A"
    cylinder_z(model, glaze, 0, 0.066, -0.022, 0.018, 0.048, 12, body)
    cylinder_z(model, matte, 0, 0.066, 0.018, 0.022, 0.041, 12, "#F2EBDC")
    for angle in range(0, 360, 90):
        a = math.radians(angle)
        flat_box(model, matte, (0.034 * math.sin(a), 0.066 + 0.034 * math.cos(a), 0.0228), (0.004, 0.004, 0.002), "#2B2F33")
    flat_box(model, matte, (0.008, 0.074, 0.0235), (0.004, 0.022, 0.002), "#2B2F33", yaw=0)
    flat_box(model, matte, (0.010, 0.064, 0.0235), (0.024, 0.004, 0.002), "#2B2F33")
    for side in (-1, 1):
        model.lathe(metal, ((0, 0), (0.024, 0), (0.022, 0.012), (0.012, 0.022), (0, 0.025)), 8, "#C9A44E",
                    center=(side * 0.032, 0.104, -0.002))
        flat_box(model, matte, (side * 0.030, 0.008, -0.002), (0.010, 0.016, 0.010), "#2B2F33")
    flat_box(model, metal, (0, 0.120, -0.002), (0.012, 0.010, 0.006), "#C9A44E")
    return model


def clothes_heap():
    model = Model("clothes_heap")
    cloth = model.material("Bedroom textiles", roughness=0.95, texture=ATLAS)
    matte = model.material("Bedroom matte")
    denim, band = "#FFFFFF", "#9FB0C8"
    angle = math.radians(24)
    c, s = math.cos(angle), math.sin(angle)

    def jeans(points):
        return [(-0.10 + x * c + z * s, y, -0.02 + z * c - x * s) for x, y, z in points]

    # Jeans lying flat, read from above as a Y: the wide hips with a lighter waistband, two legs, the right one folded back.
    soft_tube(model, cloth, jeans([(0, 0.020, -0.23), (0, 0.020, -0.15), (0, 0.020, -0.05)]), (0.165, 0.165, 0.15), 0.018, 6,
              [band, denim, denim], "denim", 0.6)
    soft_tube(model, cloth, jeans([(-0.075, 0.018, -0.07), (-0.095, 0.018, 0.10), (-0.11, 0.017, 0.27)]), (0.07, 0.062, 0.055),
              0.016, 6, denim, "denim", 0.6)
    soft_tube(model, cloth, jeans([(0.075, 0.018, -0.07), (0.10, 0.018, 0.08), (0.15, 0.022, 0.20), (0.08, 0.042, 0.19)]),
              (0.07, 0.062, 0.056, 0.055), 0.016, 6, [denim, denim, denim, band], "denim", 0.6)
    button = jeans([(0, 0.039, -0.225)])[0]
    flat_box(model, matte, button, (0.016, 0.006, 0.016), "#B08D4E")
    # The sweater: a flat crumpled body over the hips and two sleeves, one flung out, one across.
    mustard = "#D9A441"
    ellipsoid(model, cloth, (0.17, 0.035, -0.07), (0.19, 0.055, 0.15), 12, 4, mustard, "knit", bottom=False, noise=0.36, seed=3,
              ground=True)
    soft_tube(model, cloth, [(0.33, 0.035, -0.03), (0.40, 0.022, 0.08), (0.34, 0.020, 0.20)], (0.045, 0.040, 0.036), 0.020, 5,
              [mustard, mustard, "#C99434"], "knit", 0.5, caps=(False, True))
    soft_tube(model, cloth, [(0.05, 0.060, -0.12), (-0.07, 0.058, -0.17), (-0.18, 0.050, -0.13)], (0.045, 0.040, 0.036), 0.018, 5,
              [mustard, mustard, "#C99434"], "knit", 0.5, caps=(False, True), squash=False)
    return model


def odd_socks():
    model = Model("odd_socks")
    knit = model.material("Bedroom textiles", roughness=0.95, texture=ATLAS)
    sock = [(-0.010, 0.012, -0.120), (-0.006, 0.013, -0.060), (0.000, 0.012, 0.000), (0.020, 0.012, 0.035),
            (0.070, 0.011, 0.050), (0.115, 0.010, 0.055)]
    widths = (0.036, 0.034, 0.034, 0.036, 0.034, 0.026)
    ones = ["#E8E2D6", "#4F7FA0", "#4F7FA0", "#E0DAD0", "#4F7FA0", "#E0DAD0"]
    soft_tube(model, knit, [(x - 0.07, y, z) for x, y, z in sock], widths, 0.012, 6, ones, "knit", 0.4)
    yaw = math.radians(-62)
    c, s = math.cos(yaw), math.sin(yaw)
    other = [(0.06 + x * c + z * s, y, 0.03 + z * c - x * s) for x, y, z in sock]
    twos = ["#F0EBE2", "#D9A441", "#D9A441", "#8C8478", "#D9A441", "#8C8478"]
    soft_tube(model, knit, other, widths, 0.012, 6, twos, "knit", 0.4)
    return model


def slipper(model, plush, matte, offset, yaw, color):
    angle = math.radians(yaw)
    c, s = math.cos(angle), math.sin(angle)

    def place(p):
        x, y, z = p
        return (offset[0] + x * c + z * s, y, offset[1] + z * c - x * s)

    # The sole: a foot outline (toe at +z), extruded 2.2 cm.
    outline = [(0.000, -0.130), (0.034, -0.118), (0.042, -0.060), (0.048, 0.020), (0.050, 0.080), (0.038, 0.122),
               (0.000, 0.136), (-0.036, 0.122), (-0.046, 0.080), (-0.044, 0.020), (-0.038, -0.060), (-0.032, -0.118)]
    n = len(outline)
    low = [place((x, 0.0, z)) for x, z in outline]
    high = [place((x, 0.022, z)) for x, z in outline]
    tris = [(i, (i + 1) % n, n + (i + 1) % n) for i in range(n)] + [(i, n + (i + 1) % n, n + i) for i in range(n)]
    hub = place((0.0, 0.011, 0.0))
    add_outward(model, matte, low + high, tris, "#E9E1D3", inside=lambda _: hub)
    top = [place((0, 0.022, 0))] + high
    add_outward(model, matte, top, [(0, i + 1, (i + 1) % n + 1) for i in range(n)], "#D8CCB8",
                inside=lambda _: place((0, 0.0, 0)))
    # The plush upper: a half shell over the front, open toward the heel.
    steps = ((-0.010, 0.046, 0.052), (0.040, 0.050, 0.056), (0.085, 0.046, 0.046), (0.118, 0.034, 0.030), (0.134, 0.012, 0.012))
    cols = 7
    points, uv = [], []
    for row, (z, w, h) in enumerate(steps):
        for k in range(cols):
            a = math.pi * k / (cols - 1)
            points.append(place((w * math.cos(a), 0.020 + h * math.sin(a), z)))
            uv.append(atlas_uv("knit", k / (cols - 1), row / (len(steps) - 1)))
    tris = _drop_degenerate(points, grid_faces(len(steps), cols))
    add_outward(model, plush, points, tris, color, uv, inside=lambda p: place((0, 0.02, 0.05)))
    # The opening's dark lining, a half disc just inside the shell's back edge.
    z, w, h = steps[0]
    lining = [place((0, 0.022, z + 0.004))] + [place((w * 0.92 * math.cos(math.pi * k / 6), 0.021 + h * 0.9 * math.sin(math.pi * k / 6), z + 0.004)) for k in range(7)]
    add_outward(model, matte, lining, [(0, k + 1, k + 2) for k in range(6)], "#5E6670",
                inside=lambda _: place((0, 0.03, z + 0.05)))


def slippers():
    model = Model("slippers")
    plush = model.material("Bedroom textiles", roughness=0.97, texture=ATLAS)
    matte = model.material("Bedroom matte")
    slipper(model, plush, matte, (-0.065, 0.0), 6, "#8796A8")
    slipper(model, plush, matte, (0.070, 0.015), -10, "#8796A8")
    return model


def laundry_basket():
    model = Model("laundry_basket")
    weave = model.material("Bedroom textiles", roughness=0.9, texture=ATLAS)
    matte = model.material("Bedroom matte")
    lathe_uv(model, weave, ((0.165, 0.0), (0.178, 0.03), (0.212, 0.425)), 12, "#FFFFFF", "wicker", repeats=3, t_scale=0.9)
    lathe_uv(model, weave, ((0.212, 0.425), (0.219, 0.442), (0.207, 0.456), (0.195, 0.441), (0.190, 0.395)), 12, "#C9A87A",
             "wicker", repeats=3, t_scale=0.9)
    for side in (-1, 1):
        x = side * 0.2095
        quad = [(x + side * 0.003, 0.385, -0.045), (x + side * 0.003, 0.385, 0.045), (x + side * 0.003, 0.410, 0.045),
                (x + side * 0.003, 0.410, -0.045)]
        add_outward(model, matte, quad, ((0, 1, 2), (0, 2, 3)), "#5A4632", inside=lambda _: (0, 0.4, 0))
    ellipsoid(model, weave, (0.0, 0.395, 0.0), (0.19, 0.055, 0.19), 10, 4, "#7E9C8E", "knit", bottom=False, noise=0.3, seed=5)
    # A towel over the rim at 45 degrees, lying flat against the outer wall.
    soft_tube(model, weave, [(0.09, 0.425, 0.09), (0.135, 0.462, 0.135), (0.162, 0.44, 0.162), (0.163, 0.38, 0.163), (0.162, 0.32, 0.162)],
              0.045, 0.012, 5, "#E0D4BC", "knit", 0.4, caps=(False, True), squash=False, side_axis=(-0.7071, 0, 0.7071))
    return model


def floor_book_stack():
    model = Model("floor_book_stack")
    matte = model.material("Bedroom matte")
    books = ((0.240, 0.170, 0.034, 0, "#2F4858"), (0.222, 0.156, 0.030, 7, "#C9A227"),
             (0.200, 0.142, 0.040, -5, "#4F7A5A"), (0.165, 0.118, 0.026, 13, "#6B5B8C"))
    y = 0.0
    for w, d, t, yaw, color in books:
        board = 0.004
        flat_box(model, matte, (0, y + board / 2, 0), (w, board, d), color, yaw)
        flat_box(model, matte, (0, y + t - board / 2, 0), (w, board, d), color, yaw)
        spine = [(-w / 2 + 0.004, y + t / 2, 0)]
        flat_box(model, matte, rotated(spine, yaw, (0, 0, 0))[0], (0.008, t, d), color, yaw)
        page = rotated([(0.004, y + t / 2, 0)], yaw, (0, 0, 0))[0]
        flat_box(model, matte, page, (w - 0.012, t - 2 * board, d - 0.008), "#EDE5D2", yaw)
        y += t
    return model


def teddy_bear():
    model = Model("teddy_bear")
    fur = model.material("Bedroom textiles", roughness=0.97, texture=ATLAS)
    matte = model.material("Bedroom matte")
    honey, light = "#B8844E", "#E2C9A3"
    ellipsoid(model, fur, (0, 0.085, 0), (0.070, 0.085, 0.062), 8, 4, honey, "knit")
    ellipsoid(model, fur, (0, 0.205, 0.012), (0.060, 0.056, 0.055), 8, 4, honey, "knit")
    ellipsoid(model, fur, (0, 0.193, 0.062), (0.026, 0.020, 0.020), 6, 3, light, "knit")
    for side in (-1, 1):
        ellipsoid(model, fur, (side * 0.044, 0.252, 0.004), (0.022, 0.020, 0.010), 6, 2, honey, "knit")
        soft_tube(model, fur, [(side * 0.060, 0.140, 0.020), (side * 0.078, 0.100, 0.050), (side * 0.080, 0.070, 0.075)],
                  0.021, 0.021, 5, honey, "knit", 0.4, squash=False)
        soft_tube(model, fur, [(side * 0.040, 0.028, 0.020), (side * 0.050, 0.026, 0.080), (side * 0.054, 0.028, 0.125)],
                  0.027, 0.026, 5, [honey, honey, light], "knit", 0.4)
        flat_box(model, matte, (side * 0.022, 0.218, 0.063), (0.010, 0.010, 0.006), "#1F1F22")
    flat_box(model, matte, (0, 0.203, 0.082), (0.014, 0.009, 0.006), "#2B2422")
    return model


ITEMS = [
    # maker, English name, French name, category, hosts, suggested placement
    (bedside_table, "Bedside table", "Table de chevet", "look", ["nightstand"],
     "Dress look of a nightstand prop (0.45 x 0.55 x 0.40). Drawer and open shelf face +Z: the game turns looks by 180 deg so the drawer faces the prop's front (-z)."),
    (bedside_lamp, "Bedside lamp", "Lampe de chevet", "decor", ["nightstand", "cabinet", "table"],
     "On a bedside table, off centre toward the bed (x about -0.09 m on a 0.45 m stand). Pleated cream shade, mustard ball base, bulb visible from above."),
    (alarm_clock, "Alarm clock", "Réveil", "decor", ["nightstand", "cabinet", "bookshelf", "table"],
     "On a bedside table beside the lamp (x about +0.14 m), dial toward the bed or the room."),
    (clothes_heap, "Clothes heap", "Vêtements en vrac", "floor", ["floor"],
     "On the floor at the foot or the side of a bed, or before a wardrobe. Jeans and a mustard sweater in one object."),
    (odd_socks, "Odd socks", "Chaussettes dépareillées", "floor", ["floor"],
     "On the floor near the bed or the clothes heap, two odd socks lying apart."),
    (slippers, "Slippers", "Chaussons", "floor", ["floor"],
     "On the floor by the bed side, toes (+Z) pointing away from the bed."),
    (laundry_basket, "Laundry basket", "Panier à linge", "floor", ["floor"],
     "On the floor in a room corner or against a wall, never in a passage. 0.46 m tall, a towel over the rim."),
    (floor_book_stack, "Book stack", "Pile de livres", "floor", ["floor", "nightstand", "cabinet", "table"],
     "On the floor by the bed or a bookshelf, or on a nightstand top."),
    (teddy_bear, "Teddy bear", "Ours en peluche", "floor", ["floor", "nightstand", "cabinet", "bookshelf"],
     "Child's room: sitting on the floor against a bed or wall, or on a nightstand or chest of drawers, facing +Z."),
]


def main():
    DESTINATION.mkdir(parents=True, exist_ok=True)
    BUILD.mkdir(parents=True, exist_ok=True)
    make_atlas(DESTINATION / ATLAS)
    assets, models = [], []
    for maker, name, name_fr, category, hosts, placement in ITEMS:
        model = maker()
        info = model.save(DESTINATION)
        lo, hi = info["bounds_min_m"], info["bounds_max_m"]
        assets.append({
            "id": model.name, "name": name, "name_fr": name_fr, "file": f"{model.name}.glb",
            "category": {"look": "furniture look (dress)", "decor": "decor on a host top", "floor": "floor decor"}[category],
            "hosts": hosts, "placement": placement, "pivot": "bottom centre (contact point), Y up, front +Z",
            "size_m": [round(hi[0] - lo[0], 3), round(hi[1] - lo[1], 3), round(hi[2] - lo[2], 3)],
            "materials": list(model.parts.keys()), "textures": sorted({m[2] for m in model.materials.values() if m[2]}),
            **info,
        })
        models.append(model)
    inventory = {
        "project": "Out of Sight / games/out_of_sight",
        "pack": "Bedroom",
        "format": "GLB 2.0, metres, Y up, front +Z, identity node, pivot at the bottom centre",
        "generator": "tools/assets/bedroom_handoff.py (procedural, own creation)",
        "integration": [
            "Plain finishes are COLOR_0 (linear). Textured parts sample bedroom_textiles.png, tinted by COLOR_0.",
            "bedroom_textiles.png is a 512 px atlas of four quadrants: denim (top left), knit (top right, near white: the tint is "
            "the yarn colour), pale oak (bottom left), wicker (bottom right). UVs stay inside their quadrant, no repeat.",
            "Shared materials: 'Bedroom textiles' (the atlas), 'Bedroom matte', 'Bedroom glaze', 'Bedroom brass', and the "
            "two sided 'Pleated shade'.",
            "Floor items are visual only: no collider, no occluder, no NavMesh source.",
        ],
        "textures": {ATLAS: "Procedural (numpy): denim twill, V-stitch knit, pale oak grain, wicker basket weave."},
        "props": assets,
    }
    (DESTINATION / "inventory.json").write_text(json.dumps(inventory, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    with zipfile.ZipFile(BUILD / "Bedroom.zip", "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(DESTINATION.iterdir()):
            archive.write(path, f"Bedroom/{path.name}")
    for item in assets:
        print(f"{item['file']}: {item['triangles']} tris, {item['material_slots']} materials, size {item['size_m']}, "
              f"x {item['bounds_min_m'][0]}..{item['bounds_max_m'][0]} z {item['bounds_min_m'][2]}..{item['bounds_max_m'][2]}")
    try:
        from bedroom_preview import render_all
        render_all(models, assets, DESTINATION / ATLAS, BUILD / "preview")
    except ImportError:
        pass


if __name__ == "__main__":
    main()
