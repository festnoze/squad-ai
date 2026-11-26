"""Options menu icons (2026-11-20): Defaults (reset arrow), Back (left arrow), French and US flags.

Bakes every icon into plain filled paths (Skia path ops: strokes outlined, flag bands clipped to the rounded rectangle),
then writes the SVG sources and the 256x256 RGBA PNG renders into Assets/Art/UI/Icons, and a review sheet (the icons on
the Options row plates, at the sizes the menu draws them) into the folder given as the first argument.

Run it in a throwaway venv outside the repo: pip install resvg-py skia-python pillow numpy.
Usage: python options_icons.py <sheet output folder> [--candidates]
"""
import io
import math
import sys
from pathlib import Path

import numpy as np
import resvg_py
import skia
from PIL import Image, ImageDraw, ImageFont

PROJECT = Path(r"C:\Dev\squad-ai\Brainstorming\games\out_of_sight")
ICONS = PROJECT / "Assets/Art/UI/Icons"

SW = 6.0  # stroke width of the line glyphs, viewBox units (the HUD pair uses 5 on solid shapes; these are all line)
WHITE = "#FFFFFF"

# Flag colours: flat, the commonly used screen values, a little brighter than the official navy so the blue reads on
# the dark brown Options plate.
FR_BLUE = "#1F5BC4"
FR_WHITE = "#FFFFFF"
FR_RED = "#E8333A"
US_RED = "#C8283C"
US_WHITE = "#FFFFFF"
US_BLUE = "#33417F"
OUTLINE = (0, 0, 0, 0.42)  # the thin dark rim that keeps a flag's edge on any plate (the red selected one too)


# ----- path helpers -----

def stroked(path, width=SW, cap=skia.Paint.kRound_Cap, join=skia.Paint.kRound_Join):
    paint = skia.Paint(Style=skia.Paint.kStroke_Style, StrokeWidth=width, StrokeCap=cap, StrokeJoin=join)
    out = skia.Path()
    paint.getFillPath(path, out)
    return out


def union(*paths):
    acc = paths[0]
    for q in paths[1:]:
        acc = skia.Op(acc, q, skia.PathOp.kUnion_PathOp)
    return acc


def intersect(a, b):
    return skia.Op(a, b, skia.PathOp.kIntersect_PathOp)


def difference(a, b):
    return skia.Op(a, b, skia.PathOp.kDifference_PathOp)


def rrect(x0, y0, x1, y1, r):
    p = skia.Path()
    p.addRRect(skia.RRect.MakeRectXY(skia.Rect.MakeLTRB(x0, y0, x1, y1), r, r))
    return p


def rect(x0, y0, x1, y1):
    p = skia.Path()
    p.addRect(skia.Rect.MakeLTRB(x0, y0, x1, y1))
    return p


def polygon(points):
    p = skia.Path()
    p.moveTo(*points[0])
    for pt in points[1:]:
        p.lineTo(*pt)
    p.close()
    return p


def star(cx, cy, r_out, r_in=None, rot=-90.0):
    r_in = r_in if r_in is not None else r_out * 0.42
    pts = []
    for k in range(10):
        r = r_out if k % 2 == 0 else r_in
        a = math.radians(rot + k * 36.0)
        pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    return polygon(pts)


def to_d(path):
    """skia.Path to an SVG d string (conics converted to quads)."""
    f = lambda v: f"{v:.2f}".rstrip("0").rstrip(".")
    parts = []
    it = skia.Path.Iter(path, False)
    while True:
        verb, pts = it.next()
        if verb == skia.Path.Verb.kDone_Verb:
            break
        if verb == skia.Path.Verb.kMove_Verb:
            parts.append(f"M{f(pts[0].x())} {f(pts[0].y())}")
        elif verb == skia.Path.Verb.kLine_Verb:
            parts.append(f"L{f(pts[1].x())} {f(pts[1].y())}")
        elif verb == skia.Path.Verb.kQuad_Verb:
            parts.append(f"Q{f(pts[1].x())} {f(pts[1].y())} {f(pts[2].x())} {f(pts[2].y())}")
        elif verb == skia.Path.Verb.kConic_Verb:
            quads = skia.Path.ConvertConicToQuads(pts[0], pts[1], pts[2], it.conicWeight(), 2)
            for k in range(1, len(quads), 2):
                parts.append(f"Q{f(quads[k].x())} {f(quads[k].y())} {f(quads[k + 1].x())} {f(quads[k + 1].y())}")
        elif verb == skia.Path.Verb.kCubic_Verb:
            parts.append("C" + " ".join(f"{f(q.x())} {f(q.y())}" for q in pts[1:4]))
        elif verb == skia.Path.Verb.kClose_Verb:
            parts.append("Z")
    return "".join(parts)


# ----- glyphs (64 unit grid, y down) -----

def reset_glyph(variant="A"):
    """An anticlockwise open-circle arrow: the arc runs from its tail at the upper left down the left side, along the
    bottom, up the right side and over the top, its solid head at the top pointing left into the gap."""
    cx, cy, r = 32.0, 34.0, 19.0
    head_len, head_half = 13.0, 10.5
    if variant == "B":
        cx, cy, r = 32.0, 33.5, 20.0
        head_len, head_half = 12.0, 9.5
    # Skia angles: degrees clockwise from +x (y down). The tail at 205 deg (west, a little up), the arc sweeping
    # anticlockwise on screen means negative sweep in Skia: from 205 back through 180 (west), 90 (south), 0 (east),
    # -90 (north) and stopping where the head starts.
    tail = 208.0
    # The head's base sits on the circle at angle base_a; the arc stops there.
    base_a = 268.0  # just right of north on screen (north is 270)
    arc = skia.Path()
    oval = skia.Rect.MakeLTRB(cx - r, cy - r, cx + r, cy + r)
    arc.addArc(oval, tail, -(tail - (base_a - 360.0)))
    line = stroked(arc)
    # Head: a triangle whose base is centred on the arc end, pointing along the anticlockwise tangent (screen west at
    # north). Rounded by a thin round-join stroke of its own outline.
    a = math.radians(base_a)
    bx, by = cx + r * math.cos(a), cy + r * math.sin(a)
    # tangent for anticlockwise motion on screen (decreasing Skia angle): d/dθ of (cos, sin) times -1
    tx, ty = math.sin(a), -math.cos(a)
    nx, ny = math.cos(a), math.sin(a)
    tip = (bx + tx * head_len, by + ty * head_len)
    b1 = (bx + nx * head_half, by + ny * head_half)
    b2 = (bx - nx * head_half, by - ny * head_half)
    tri = polygon([tip, b1, b2])
    head = union(tri, stroked(tri, 2.5))
    return union(line, head)


def back_glyph(variant="A"):
    """A left arrow: a round-capped shaft and a round-capped chevron head (the Material arrow_back grammar)."""
    if variant == "B":
        # Solid head variant.
        shaft = skia.Path(); shaft.moveTo(52, 32); shaft.lineTo(26, 32)
        tri = polygon([(9, 32), (29, 17), (29, 47)])
        return union(stroked(shaft), tri, stroked(tri, 3.0))
    p = skia.Path()
    p.moveTo(52, 32); p.lineTo(13, 32)
    p.moveTo(28, 16.5); p.lineTo(12.5, 32); p.lineTo(28, 47.5)
    return stroked(p)


FLAG = (3.0, 12.0, 61.0, 50.67)   # 58 x 38.67: the 3:2 ratio
FLAG_R = 5.0


def flag_outline():
    """The dark rim: a full rounded rectangle 1.4 units larger, drawn first, under the flag (no seam at its inner edge)."""
    x0, y0, x1, y1 = FLAG
    return rrect(x0 - 1.4, y0 - 1.4, x1 + 1.4, y1 + 1.4, FLAG_R + 1.4)


# The layers of a flag are drawn in order, each over the last: the whole body in white first, then the colours on top, so
# two colours never just abut (abutting anti-aliased edges leave a see-through seam).

def fr_flag():
    x0, y0, x1, y1 = FLAG
    body = rrect(x0, y0, x1, y1, FLAG_R)
    w = (x1 - x0) / 3.0
    return [
        (FR_WHITE, body),
        (FR_BLUE, intersect(body, rect(x0 - 1, y0 - 1, x0 + w, y1 + 1))),
        (FR_RED, intersect(body, rect(x0 + 2 * w, y0 - 1, x1 + 1, y1 + 1))),
    ]


def us_flag(stripes=13):
    x0, y0, x1, y1 = FLAG
    body = rrect(x0, y0, x1, y1, FLAG_R)
    h = (y1 - y0) / stripes
    reds = None
    for k in range(0, stripes, 2):
        s = rect(x0 - 1, y0 + k * h, x1 + 1, y0 + (k + 1) * h)
        reds = s if reds is None else union(reds, s)
    canton_rows = 7 if stripes == 13 else 4
    cw = (x1 - x0) * (0.40 if stripes == 13 else 0.44)
    ch = h * canton_rows
    canton = intersect(body, rect(x0 - 1, y0 - 1, x0 + cw, y0 + ch))
    # Stars: a staggered grid (rows of 4 and 3), small enough to read as stars when big and as a light speckle small.
    stars = None
    rows = 5 if stripes == 13 else 4
    for row in range(rows):
        # Rows of 4 at 1/8, 3/8, 5/8, 7/8 of the canton's width, rows of 3 between them at 2/8, 4/8, 6/8.
        n = 4 if row % 2 == 0 else 3
        yy = y0 + ch * (row + 0.5) / rows
        for i in range(n):
            xx = x0 + cw * ((i + 0.5) / 4.0 if row % 2 == 0 else (i + 1.0) / 4.0)
            st = star(xx, yy, 1.55 if stripes == 13 else 1.75)
            stars = st if stars is None else union(stars, st)
    stars = intersect(stars, canton)
    return [
        (US_WHITE, body),
        (US_RED, intersect(body, reds)),
        (US_BLUE, canton),
        (US_WHITE, stars),
    ]


# ----- output -----

def svg_mono(path, name, note):
    return ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64" width="64" height="64">\n'
            f'  <!-- Out of Sight Options icon "{name}", original work (2026-11-20). {note}\n'
            '       One filled path, white so the UI can tint it (Image.color). Built by docs/m9/icons/options_icons.py. -->\n'
            f'  <path fill="{WHITE}" fill-rule="nonzero" d="{to_d(path)}"/>\n'
            '</svg>\n')


def svg_flag(layers, name, note):
    rgba = "#000000"
    out = ['<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64" width="64" height="64">',
           f'  <!-- Out of Sight Options icon "{name}", original work (2026-11-20). {note}',
           '       Flat colour paths (no clip, mask or CSS), drawn as is (not tinted). Built by docs/m9/icons/options_icons.py. -->',
           f'  <path fill="{rgba}" fill-opacity="{OUTLINE[3]}" d="{to_d(flag_outline())}"/>']
    for colour, path in layers:
        out.append(f'  <path fill="{colour}" d="{to_d(path)}"/>')
    out.append('</svg>')
    return "\n".join(out) + "\n"


def render(svg_text, px):
    return Image.open(io.BytesIO(bytes(resvg_py.svg_to_bytes(svg_string=svg_text, width=px, height=px)))).convert("RGBA")


def white_png(svg_text):
    alpha = render(svg_text, 256).getchannel("A")
    png = Image.new("RGBA", (256, 256), (255, 255, 255, 0))
    png.putalpha(alpha)
    return png


def colour_png(svg_text):
    img = render(svg_text, 256)
    a = np.asarray(img).astype(np.float32)
    # resvg returns premultiplied-then-unpremultiplied RGBA: fully transparent pixels are black. Fill them with the
    # nearest opaque colour's average so mipmaps and bilinear filtering never pull a dark fringe in (alpha unchanged).
    rgb, alpha = a[..., :3], a[..., 3:]
    mask = alpha[..., 0] > 0
    if mask.any():
        mean = rgb[mask].mean(axis=0)
        rgb[~mask] = mean
    out = np.concatenate([rgb, alpha], axis=-1).clip(0, 255).astype(np.uint8)
    return Image.fromarray(out, "RGBA")


def tinted(svg_text, colour, px):
    return render(svg_text.replace(WHITE, colour), px)


def sheet(icons, out_dir, file_name):
    font = ImageFont.truetype("C:/Windows/Fonts/arial.ttf", 18)
    plates = [
        ("rest plate", (43, 29, 22)),
        ("hover plate", (75, 54, 41)),
        ("selected (red)", (204, 51, 41)),
    ]
    sizes = (32, 46, 52, 58, 128)
    cell = 150
    label_w = 170
    W = label_w + cell * len(sizes)
    H = 40 + len(icons) * len(plates) * 110 + 20
    img = Image.new("RGBA", (W, H), (20, 16, 14, 255))
    d = ImageDraw.Draw(img)
    for j, s in enumerate(sizes):
        d.text((label_w + j * cell + 30, 12), f"{s}px", font=font, fill=(200, 200, 200))
    y = 40
    for name, svg_text, tint in icons:
        for plate_name, colour in plates:
            d.rectangle((label_w, y, W - 4, y + 104), fill=colour + (255,))
            d.text((10, y + 30), name, font=font, fill=(230, 230, 230))
            d.text((10, y + 54), plate_name, font=font, fill=(150, 150, 150))
            for j, s in enumerate(sizes):
                pic = tinted(svg_text, tint, s) if tint else render(svg_text, s)
                if s > 100:
                    pic = pic.resize((96, 96), Image.LANCZOS)
                    s = 96
                img.alpha_composite(pic, (label_w + j * cell + (cell - s) // 2, y + (104 - s) // 2))
            y += 110
    path = Path(out_dir) / file_name
    img.convert("RGB").save(path)
    print(path)


def main():
    out_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(".")
    out_dir.mkdir(parents=True, exist_ok=True)
    cream = "#FFF0D1"
    if "--candidates" in sys.argv:
        icons = [
            ("reset A", svg_mono(reset_glyph("A"), "reset", ""), cream),
            ("reset B", svg_mono(reset_glyph("B"), "reset", ""), cream),
            ("back A", svg_mono(back_glyph("A"), "back", ""), cream),
            ("back B", svg_mono(back_glyph("B"), "back", ""), cream),
            ("FR", svg_flag(fr_flag(), "flag_fr", ""), None),
            ("US 13", svg_flag(us_flag(13), "flag_us", ""), None),
            ("US 7", svg_flag(us_flag(7), "flag_us", ""), None),
        ]
        sheet(icons, out_dir, "candidates.png")
        return
    files = {
        "reset": svg_mono(reset_glyph("A"), "reset",
                          "The Options page's Defaults (Par defaut) button: an anticlockwise open-circle arrow."),
        "back": svg_mono(back_glyph("B"), "back", "The Options page's Back (Retour) button: a left arrow."),
        "flag_fr": svg_flag(fr_flag(), "flag_fr", "The Language row while the game is in French: the French flag."),
        "flag_us": svg_flag(us_flag(13), "flag_us", "The Language row while the game is in English: the US flag."),
    }
    for name, text in files.items():
        (ICONS / f"{name}.svg").write_text(text, encoding="utf-8", newline="\n")
        png = white_png(text) if name in ("reset", "back") else colour_png(text)
        png.save(ICONS / f"{name}.png", optimize=True)
        print(ICONS / f"{name}.png")
    sheet([("reset", files["reset"], cream), ("back", files["back"], cream),
           ("flag_fr", files["flag_fr"], None), ("flag_us", files["flag_us"], None)], out_dir, "final.png")


if __name__ == "__main__":
    main()
