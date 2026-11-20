"""Generate candidate HUD icon pairs, render them and compose comparison sheets."""
import io
import sys
from pathlib import Path

import resvg_py
from PIL import Image, ImageDraw, ImageFont

OUT = Path(__file__).parent / "out"
OUT.mkdir(exist_ok=True)

CREAM = "#FFF0D1"   # Menu.TitleInk (1, 0.94, 0.82)
RED = "#E64236"     # Hud.PrimaryRedHover (0.9, 0.26, 0.23), readable on dark
BG = (26, 26, 31)   # Hud.GaugeBack (0.1, 0.1, 0.12)
SW = 5              # shared stroke width (viewBox units)

HEAD = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64" width="64" height="64">'
        '<g fill="none" stroke-width="{sw}" stroke-linecap="round" stroke-linejoin="round">')


def svg(body, main, accent):
    body = body.replace("MAIN", main).replace("ACC", accent).replace("OVL", "none" if accent == main else accent)
    return HEAD.format(sw=SW) + body + "</g></svg>"


# Each body uses MAIN for the object and ACC for the "signal" (noise / suspicion cue).
CANDIDATES = {
    "A": {
        "name": "Chair + sound arcs / raised-brow eye",
        "creak": (
            # side-view chair (back post, seat, front leg), arcs from the front leg
            '<path stroke="MAIN" d="M14 8 V56 M14 34 H34 V56"/>'
            '<path stroke="ACC" d="M42 38 Q46 45 42 52 M49 33 Q55 45 49 57"/>'
        ),
        "suspicion": (
            # heavy-lidded eye: flat lid, round lower lid, pupil under the lid, raised skewed brow
            '<path stroke="MAIN" d="M7 36 Q32 26 57 34 M7 36 Q32 58 57 34"/>'
            '<path fill="MAIN" stroke="none" d="M24.5 32.6 A7.5 7.5 0 0 0 39.5 31.2 Z"/>'
            '<path stroke="ACC" d="M12 20 Q30 6 52 16"/>'
        ),
    },
    "B": {
        "name": "Leg on bending floor + jolts / squinting side-eyes",
        "creak": (
            '<path stroke="MAIN" d="M28 8 V40 M36 8 V40 M28 40 H36"/>'
            '<path stroke="MAIN" d="M6 50 Q32 58 58 50"/>'
            '<path stroke="ACC" d="M19 36 L13 31 M17 44 L9 43 M45 36 L51 31 M47 44 L55 43"/>'
        ),
        "suspicion": (
            # two narrowed eyes glancing sideways, angled brows
            '<path stroke="MAIN" d="M6 38 Q16 30 28 36 Q16 44 6 38 Z M36 36 Q48 30 58 38 Q48 44 36 36 Z"/>'
            '<circle fill="MAIN" stroke="none" cx="23" cy="37" r="3.6"/>'
            '<circle fill="MAIN" stroke="none" cx="53" cy="37.5" r="3.6"/>'
            '<path stroke="ACC" d="M7 26 L27 22 M37 20 L57 26"/>'
        ),
    },
    "C": {
        "name": "Chair + creak zigzag / eye with alert ticks",
        "creak": (
            '<path stroke="MAIN" d="M12 10 V56 M12 34 H32 V56"/>'
            # jagged creak wave coming out of the seat joint
            '<path stroke="ACC" d="M38 22 L43 14 L48 22 L53 14 L58 22"/>'
            '<path stroke="ACC" d="M40 34 H46 M40 44 H50" />'
        ),
        "suspicion": (
            '<path stroke="MAIN" d="M7 40 Q32 22 57 40 Q32 56 7 40 Z"/>'
            '<path fill="MAIN" stroke="none" d="M25 33 H39 A7 7 0 0 1 25 33 Z"/>'
            '<path stroke="MAIN" d="M7 40 Q32 26 57 40" />'
            '<path stroke="ACC" d="M32 6 V14 M16 11 L20 18 M48 11 L44 18"/>'
        ),
    },
    "D": {
        "name": "Rocking chair-tilt + vibration ticks / brow-down eye",
        "creak": (
            # chair tilted back on its rear leg, vibration ticks at the lifted front foot
            '<g transform="rotate(-14 16 56)"><path stroke="MAIN" d="M16 8 V56 M16 34 H38 V56"/></g>'
            '<path stroke="ACC" d="M8 60 H22"/>'
            '<path stroke="ACC" d="M46 42 L52 38 M47 50 L55 50 M42 56 L48 60"/>'
        ),
        "suspicion": (
            '<path stroke="MAIN" d="M8 38 Q32 22 56 38 Q32 54 8 38 Z"/>'
            '<circle fill="MAIN" stroke="none" cx="40" cy="38" r="6"/>'
            # one brow slanted down (frown), one arched up: "hmm?"
            '<path stroke="ACC" d="M10 22 Q22 16 32 22 M36 16 Q46 8 56 14"/>'
        ),
    },
    "E": {
        "name": "Front chair + wobble arcs / skeptical face",
        "creak": (
            '<path stroke="MAIN" d="M21 30 V12 Q21 7 26 7 H38 Q43 7 43 12 V30"/>'
            '<path stroke="MAIN" d="M15 33 H49 M20 33 L18 56 M44 33 L46 56"/>'
            '<path stroke="ACC" d="M9 38 Q5 45 9 52 M55 38 Q59 45 55 52"/>'
        ),
        "suspicion": (
            '<circle stroke="MAIN" cx="32" cy="33" r="26"/>'
            # brows: left flat and low, right raised and arched
            '<path stroke="ACC" d="M17 25 H27 M37 22 Q42 15 48 20"/>'
            # heavy-lidded eyes looking to the side
            '<path stroke="MAIN" d="M17 32 H28 M37 32 H48"/>'
            '<circle fill="MAIN" stroke="none" cx="25" cy="34.5" r="3.4"/>'
            '<circle fill="MAIN" stroke="none" cx="45" cy="34.5" r="3.4"/>'
            '<path stroke="MAIN" d="M24 46 H40"/>'
        ),
    },
    "F": {
        "name": "Front chair + shake ticks on floor / big narrowed eyes",
        "creak": (
            '<path stroke="MAIN" d="M21 28 V11 Q21 6 26 6 H38 Q43 6 43 11 V28"/>'
            '<path stroke="MAIN" d="M15 31 H49 M20 31 L18 52 M44 31 L46 52"/>'
            '<path stroke="ACC" d="M6 59 H58"/>'
            '<path stroke="ACC" d="M9 46 L4 42 M11 37 L5 35 M55 46 L60 42 M53 37 L59 35"/>'
        ),
        "suspicion": (
            '<path stroke="MAIN" d="M4 38 Q16 28 29 36 Q16 46 4 38 Z M35 36 Q48 28 60 38 Q48 46 35 36 Z"/>'
            '<circle fill="MAIN" stroke="none" cx="23" cy="37" r="4.5"/>'
            '<circle fill="MAIN" stroke="none" cx="54" cy="37.5" r="4.5"/>'
            '<path stroke="ACC" d="M5 22 L27 24 M36 22 Q46 10 58 18"/>'
        ),
    },
    "G": {
        "name": "3/4 chair + sound arcs / heavy-lid skeptical face",
        "creak": (
            # backrest and seat filled, legs stroked
            '<path fill="MAIN" stroke="MAIN" d="M22 27 L22 9 Q22 5 26 5.5 L40 7.5 Q44 8 44 12 L44 30 Z"/>'
            '<path fill="MAIN" stroke="MAIN" d="M8 36 L34 40 L46 32 L22 28 Z"/>'
            '<path stroke="MAIN" d="M9 37 V57 M33 41 V60 M45 33 V52"/>'
            '<path stroke="ACC" d="M50 42 Q54 48 50 55 M56 37 Q62 48 56 59"/>'
        ),
        "suspicion": (
            '<circle stroke="MAIN" cx="32" cy="32" r="27"/>'
            '<path stroke="ACC" d="M16 22 L28 25 M36 21 Q42 11 49 17"/>'
            '<path stroke="MAIN" d="M15 32 H29 M35 32 H49"/>'
            '<path fill="MAIN" stroke="none" d="M21 32 H30 A4.5 4.5 0 0 1 21 32 Z M41 32 H50 A4.5 4.5 0 0 1 41 32 Z"/>'
            '<path stroke="MAIN" d="M25 45 L40 43"/>'
        ),
    },
    "H": {
        "name": "3/4 chair + creak jags / side-glance face, no outline",
        "creak": (
            '<path fill="MAIN" stroke="MAIN" d="M22 27 L22 9 Q22 5 26 5.5 L40 7.5 Q44 8 44 12 L44 30 Z"/>'
            '<path fill="MAIN" stroke="MAIN" d="M8 36 L34 40 L46 32 L22 28 Z"/>'
            '<path stroke="MAIN" d="M9 37 V57 M33 41 V60 M45 33 V52"/>'
            '<path stroke="ACC" d="M51 40 L58 36 M52 49 L60 50 M48 57 L54 62"/>'
        ),
        "suspicion": (
            # head shape as a rounded cap outline with one raised brow
            '<path stroke="MAIN" d="M10 54 V30 Q10 8 32 8 Q54 8 54 30 V54"/>'
            '<path stroke="ACC" d="M17 26 L28 28 M36 25 Q42 16 48 21"/>'
            '<path stroke="MAIN" d="M16 35 H29 M35 35 H48"/>'
            '<path fill="MAIN" stroke="none" d="M21 35 H30 A4.5 4.5 0 0 1 21 35 Z M40 35 H49 A4.5 4.5 0 0 1 40 35 Z"/>'
            '<path stroke="MAIN" d="M26 47 L39 45"/>'
        ),
    },
    "I": {
        "name": "3/4 chair + sound arcs / solid skeptical head (knock-out)",
        "creak": None,  # same as G
        "suspicion": (
            '<mask id="m"><rect width="64" height="64" fill="#fff"/>'
            '<g stroke="#000"><path d="M14 24 L26 27 M37 23 Q43 12 51 18 M26 46 L41 44"/></g>'
            '<path fill="#000" d="M15 32 H30 A7.5 7.5 0 0 1 15 32 Z M35 32 H50 A7.5 7.5 0 0 1 35 32 Z"/>'
            '</mask>'
            '<circle fill="MAIN" cx="32" cy="32" r="28" mask="url(#m)"/>'
            '<path stroke="OVL" d="M14 24 L26 27 M37 23 Q43 12 51 18"/>'
        ),
    },
}
CANDIDATES["I"]["creak"] = CANDIDATES["G"]["creak"]

# Refinement of I: lidded eyes with the pupils glancing sideways (no "sunglasses" read), bigger creak arcs.
CANDIDATES["J"] = {
    "name": "Refined: 3/4 chair + arcs / solid head, lidded side-glance",
    "creak": (
        '<path fill="MAIN" stroke="MAIN" d="M18.5 27 L18.5 9 Q18.5 5 22.5 5.5 L36.5 7.5 Q40.5 8 40.5 12 L40.5 30 Z"/>'
        '<path fill="MAIN" stroke="MAIN" d="M4.5 36 L30.5 40 L42.5 32 L18.5 28 Z"/>'
        '<path stroke="MAIN" d="M5.5 37 V57 M29.5 41 V60 M41.5 33 V52"/>'
        '<path stroke="ACC" d="M48.5 41 Q52.5 47.5 48.5 54 M56.5 35 Q63 47.5 56.5 60"/>'
    ),
    "suspicion": (
        '<mask id="m"><rect width="64" height="64" fill="#fff"/>'
        '<g stroke="#000"><path d="M14 21 L27 24.5 M36 22 Q43 11 51 17 M14 33 H29 M35 33 H50 M26 46 L40 44"/></g>'
        '<path fill="#000" d="M20 33 H29.5 A4.75 4.75 0 0 1 20 33 Z M40.5 33 H50 A4.75 4.75 0 0 1 40.5 33 Z"/>'
        '</mask>'
        '<circle fill="MAIN" cx="32" cy="32" r="28" mask="url(#m)"/>'
        '<path stroke="OVL" d="M14 21 L27 24.5 M36 22 Q43 11 51 17"/>'
    ),
}


def render(svg_text, px):
    data = resvg_py.svg_to_bytes(svg_string=svg_text, width=px, height=px)
    return Image.open(io.BytesIO(bytes(data))).convert("RGBA")


FONT = ImageFont.truetype("C:/Windows/Fonts/arial.ttf", 20)
FONT_B = ImageFont.truetype("C:/Windows/Fonts/arialbd.ttf", 26)


def hud_mock(icon_c, icon_s, scale=1.0):
    """A HUD row like the game's: 46 px icon, label, bar, on a dark plate."""
    w, h = int(760 * scale), int(110 * scale)
    img = Image.new("RGBA", (w, h), (120, 96, 66, 255))  # warm floor colour behind the plate
    d = ImageDraw.Draw(img)
    for i, (icon, label, fill) in enumerate(((icon_c, "Creak", (219, 158, 87)), (icon_s, "Suspicion", (255, 204, 64)))):
        x0 = 20 + i * 380
        d.rounded_rectangle((x0 - 10, 8, x0 + 340, h - 8), 12, fill=BG + (210,))
        img.alpha_composite(icon.resize((46, 46), Image.LANCZOS) if icon.size[0] != 46 else icon, (x0, 14))
        d.text((x0 + 56, 22), label, font=FONT_B, fill=(255, 255, 255))
        d.rectangle((x0, 70, x0 + 320, 92), fill=(60, 58, 54), outline=(255, 247, 230))
        d.rectangle((x0 + 2, 72, x0 + 2 + 90 + 60 * i, 90), fill=fill)
    return img


def sheet(keys, tag, two_tone=True):
    sizes = (32, 64, 128)
    cell = 140
    label_w = 300
    rows = []
    for k in keys:
        c = CANDIDATES[k]
        main, acc = CREAM, (RED if two_tone else CREAM)
        rows.append((k, c["name"], svg(c["creak"], main, acc), svg(c["suspicion"], main, acc)))
    W = label_w + cell * len(sizes) * 2 + 40
    row_h = cell + 130
    H = 50 + row_h * len(rows)
    img = Image.new("RGBA", (W, H), BG + (255,))
    d = ImageDraw.Draw(img)
    for j, s in enumerate(sizes * 2):
        what = "creak" if j < 3 else "suspicion"
        d.text((label_w + j * cell + 10, 14), f"{what} {s}px", font=FONT, fill=(200, 200, 200))
    for r, (k, name, sc, ss) in enumerate(rows):
        y = 50 + r * row_h
        d.text((14, y + 10), k, font=FONT_B, fill=(255, 240, 209))
        words, line, ly = name.split(" "), "", y + 46
        for wd in words:
            if FONT.getlength(line + " " + wd) > label_w - 30:
                d.text((14, ly), line.strip(), font=FONT, fill=(200, 200, 200)); ly += 24; line = ""
            line += " " + wd
        d.text((14, ly), line.strip(), font=FONT, fill=(200, 200, 200))
        for j, s in enumerate(sizes * 2):
            icon = render(sc if j < 3 else ss, s)
            x = label_w + j * cell + (cell - s) // 2
            img.alpha_composite(icon, (x, y + (cell - s) // 2))
        mock = hud_mock(render(sc, 46), render(ss, 46))
        img.alpha_composite(mock, (label_w, y + cell + 6))
    path = OUT / f"sheet_{tag}.png"
    img.convert("RGB").save(path)
    print(path)
    return path


if __name__ == "__main__":
    keys = sys.argv[1] if len(sys.argv) > 1 else "ABCD"
    sheet(list(keys), "candidates_twotone_" + keys, True)
    sheet(list(keys), "candidates_mono_" + keys, False)
