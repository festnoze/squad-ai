"""Bake the chosen pair (J) into single filled paths, write SVG + PNG deliverables and the final sheet."""
import io
import re
import sys
from pathlib import Path

import numpy as np
import resvg_py
import skia
from PIL import Image, ImageDraw

import gen

PROJECT = Path(r"C:\Dev\squad-ai\Brainstorming\games\out_of_sight")
ICONS = PROJECT / "Assets/Art/UI/Icons"
DOCS = PROJECT / "docs/m9/icons"
ICONS.mkdir(parents=True, exist_ok=True)
DOCS.mkdir(parents=True, exist_ok=True)

SW = gen.SW


def parse(d):
    """Minimal SVG path parser (absolute M L H V Q A Z) into a skia.Path."""
    p = skia.Path()
    toks = re.findall(r"[MLHVQAZ]|-?\d*\.?\d+", d)
    i, cmd, x, y = 0, None, 0.0, 0.0
    while i < len(toks):
        t = toks[i]
        if t.isalpha():
            cmd = t
            i += 1
            if cmd == "Z":
                p.close()
                continue
        n = lambda k: float(toks[i + k])
        if cmd == "M":
            x, y = n(0), n(1); p.moveTo(x, y); i += 2; cmd = "L"
        elif cmd == "L":
            x, y = n(0), n(1); p.lineTo(x, y); i += 2
        elif cmd == "H":
            x = n(0); p.lineTo(x, y); i += 1
        elif cmd == "V":
            y = n(0); p.lineTo(x, y); i += 1
        elif cmd == "Q":
            p.quadTo(n(0), n(1), n(2), n(3)); x, y = n(2), n(3); i += 4
        elif cmd == "A":
            rx, ry, rot, large, sweep, x, y = (n(k) for k in range(7))
            p.arcTo(rx, ry, rot,
                    skia.Path.ArcSize.kLarge_ArcSize if large else skia.Path.ArcSize.kSmall_ArcSize,
                    skia.PathDirection.kCW if sweep else skia.PathDirection.kCCW, x, y)
            i += 7
    return p


def stroked(d):
    paint = skia.Paint(Style=skia.Paint.kStroke_Style, StrokeWidth=SW,
                       StrokeCap=skia.Paint.kRound_Cap, StrokeJoin=skia.Paint.kRound_Join)
    out = skia.Path()
    paint.getFillPath(parse(d), out)
    return out


def union(*paths):
    acc = paths[0]
    for q in paths[1:]:
        acc = skia.Op(acc, q, skia.PathOp.kUnion_PathOp)
    return acc


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


# Geometry of the chosen pair J (kept identical to gen.CANDIDATES["J"]).
BACKREST = "M18.5 27 L18.5 9 Q18.5 5 22.5 5.5 L36.5 7.5 Q40.5 8 40.5 12 L40.5 30 Z"
SEAT = "M4.5 36 L30.5 40 L42.5 32 L18.5 28 Z"
LEGS = "M5.5 37 V57 M29.5 41 V60 M41.5 33 V52"
ARCS = "M48.5 41 Q52.5 47.5 48.5 54 M56.5 35 Q63 47.5 56.5 60"
FEATURES = "M14 21 L27 24.5 M36 22 Q43 11 51 17 M14 33 H29 M35 33 H50 M26 46 L40 44"
PUPILS = "M20 33 H29.5 A4.75 4.75 0 0 1 20 33 Z M40.5 33 H50 A4.75 4.75 0 0 1 40.5 33 Z"

creak_path = union(parse(BACKREST), stroked(BACKREST), parse(SEAT), stroked(SEAT), stroked(LEGS), stroked(ARCS))
head = skia.Path(); head.addCircle(32, 32, 28)
sus_path = skia.Op(head, union(stroked(FEATURES), parse(PUPILS)), skia.PathOp.kDifference_PathOp)

WHITE = "#FFFFFF"
HEADER = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64" width="64" height="64">\n'
          '  <!-- Out of Sight HUD icon "{name}", original work (2026-11-19). One filled path, white so the HUD can\n'
          '       tint it (Image.color). Built from 5-unit round strokes by docs/m9/icons/final.py. -->\n'
          '  <path fill="{fill}" fill-rule="nonzero" d="{d}"/>\n'
          '</svg>\n')


def baked_svg(path, name, fill=WHITE):
    return HEADER.format(name=name, fill=fill, d=to_d(path))


def render(svg_text, px):
    return Image.open(io.BytesIO(bytes(resvg_py.svg_to_bytes(svg_string=svg_text, width=px, height=px)))).convert("RGBA")


def check_same(baked, source, label):
    a = np.asarray(render(baked, 256))[..., 3].astype(int)
    b = np.asarray(render(source, 256))[..., 3].astype(int)
    diff = np.abs(a - b)
    print(f"{label}: max alpha diff {diff.max()}, pixels > 64: {(diff > 64).sum()}")


def main():
    files = {}
    for name, path, cand_key in (("creak", creak_path, "creak"), ("suspicion", sus_path, "suspicion")):
        text = baked_svg(path, name)
        (ICONS / f"{name}.svg").write_text(text, encoding="utf-8", newline="\n")
        # Pure white RGB everywhere, coverage in alpha only: no dark fringe when Unity filters or mips it.
        alpha = render(text, 256).getchannel("A")
        png = Image.new("RGBA", (256, 256), (255, 255, 255, 0))
        png.putalpha(alpha)
        png.save(ICONS / f"{name}.png", optimize=True)
        check_same(text, gen.svg(gen.CANDIDATES["J"][cand_key], WHITE, WHITE), name)
        files[name] = text
    final_sheet(files)


def tinted(svg_text, colour, px):
    return render(svg_text.replace(WHITE, colour), px)


def final_sheet(files):
    from PIL import ImageFont
    font = ImageFont.truetype("C:/Windows/Fonts/arial.ttf", 18)
    cream = gen.CREAM
    rows = [
        ("cream on HUD plate", gen.BG, {"creak": cream, "suspicion": cream}),
        ("tinted like the bars", gen.BG, {"creak": "#DB9E57", "suspicion": "#FFCC40"}),
        ("alarm tint (accent red)", gen.BG, {"creak": "#E64236", "suspicion": "#E64236"}),
        ("on the floor (no plate)", (190, 150, 100), {"creak": cream, "suspicion": cream}),
    ]
    sizes = (32, 46, 64, 128)
    cell, label_w = 150, 240
    W = label_w + cell * len(sizes) * 2 + 20
    H = 44 + len(rows) * cell + 140
    img = Image.new("RGBA", (W, H), gen.BG + (255,))
    d = ImageDraw.Draw(img)
    for j, s in enumerate(sizes * 2):
        d.text((label_w + j * cell + 14, 14), f"{'creak' if j < 4 else 'suspicion'} {s}px", font=font, fill=(200, 200, 200))
    for r, (label, bg, tints) in enumerate(rows):
        y = 44 + r * cell
        d.rectangle((label_w, y, W, y + cell - 6), fill=tuple(bg) + (255,))
        d.text((14, y + cell // 2 - 10), label, font=font, fill=(220, 220, 220))
        for j, s in enumerate(sizes * 2):
            key = "creak" if j < 4 else "suspicion"
            icon = tinted(files[key], tints[key], s)
            img.alpha_composite(icon, (label_w + j * cell + (cell - s) // 2, y + (cell - 6 - s) // 2))
    mock = gen.hud_mock(tinted(files["creak"], cream, 46), tinted(files["suspicion"], cream, 46))
    img.alpha_composite(mock, (label_w, 44 + len(rows) * cell + 10))
    img.convert("RGB").save(DOCS / "sheet_final.png")
    print(DOCS / "sheet_final.png")


if __name__ == "__main__":
    main()
