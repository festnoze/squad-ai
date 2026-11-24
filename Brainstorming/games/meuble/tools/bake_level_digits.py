"""LEVELNUM2: bakes the digits 0 to 9 of a few OFL faces into signed distance field atlases for the intro card's level
number (Assets/Scripts/Runtime/CardNumber.cs, LevelDigitFont).

Why a baked SDF: the number zooms from about 6 screen heights down to half the screen height. A coverage atlas (the
legacy Font path of LEVELNUM round 2) is blurred and stair-stepped when magnified that much; a distance field gives a
crisp, one-pixel anti-aliased edge at every zoom step (the mask shader reconstructs the edge with screen derivatives),
and lets the shader draw a hairline inner edge and a soft inner shade at an exact distance from the outline.

Output per face, in Assets/ThirdParty/Fonts/Resources/LevelDigits/:
  <name>.json      metrics: atlas size, spread, per digit advance, ink box, quad box (all in em/1000 units, y up from
                   the baseline) and the quad's UV rect (v from the bottom row);
  <name>_sdf.bytes the atlas, one byte per texel (R8), rows bottom first (Texture2D.LoadRawTextureData order).
                   0.5 (128) is the outline, 1 is <spread> texels inside, 0 is <spread> texels outside.
The OFL license of each face is copied next to them. The source fonts live in tools/fonts (not shipped).

Run (needs Pillow, numpy and scipy):  python tools/bake_level_digits.py [--preview <dir>]
"""

import argparse
import json
import os
import shutil

import numpy as np
from PIL import Image, ImageDraw, ImageFont
from scipy import ndimage

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT = os.path.dirname(HERE)
FONTS = os.path.join(HERE, "fonts")
OUT = os.path.join(PROJECT, "Assets", "ThirdParty", "Fonts", "Resources", "LevelDigits")

DIGITS = "0123456789"
GLYPH_TEXELS = 256      # height of the figure "0" in the atlas, in texels
SPREAD = 28             # distance range on each side of the outline, in atlas texels
SUPER = 4               # rendering supersampling (the distance is measured at SUPER times the atlas resolution)
COLUMNS = 5

# name: (file, variation axes or None, license file)
FACES = {
    "inter": ("Inter-Variable.ttf", [32, 700], "Inter-OFL.txt"),            # Inter Display Bold
    "montserrat": ("Montserrat-Variable.ttf", [700], "Montserrat-OFL.txt"),  # Montserrat Bold
    "bebas": ("BebasNeue-Regular.ttf", None, "BebasNeue-OFL.txt"),           # Bebas Neue
    "dmserif": (os.path.join(PROJECT, "Assets", "ThirdParty", "Fonts", "Resources", "DMSerifDisplay-Regular.ttf"), None,
                os.path.join(PROJECT, "Assets", "ThirdParty", "Fonts", "Resources", "DMSerifDisplay-OFL.txt")),
}


def load_font(path, axes, size):
    font = ImageFont.truetype(path if os.path.isabs(path) else os.path.join(FONTS, path), size)
    if axes is not None:
        font.set_variation_by_axes(axes)
    return font


def bake(name, preview_dir=None):
    file, axes, license_file = FACES[name]
    # Size the face so the figure "0" is GLYPH_TEXELS * SUPER pixels tall at the supersampled resolution.
    probe = load_font(file, axes, 1000)
    zero = probe.getbbox("0", anchor="ls")
    size = int(round(1000 * GLYPH_TEXELS * SUPER / (zero[3] - zero[1])))
    font = load_font(file, axes, size)
    em = size / 1000.0  # supersampled pixels per em/1000 unit

    pad = SPREAD * SUPER + 2 * SUPER
    cells = []
    for ch in DIGITS:
        x0, y0, x1, y1 = font.getbbox(ch, anchor="ls")  # y down, from the baseline
        w = x1 - x0 + 2 * pad
        h = y1 - y0 + 2 * pad
        w += (-w) % SUPER
        h += (-h) % SUPER
        img = Image.new("L", (w, h), 0)
        ImageDraw.Draw(img).text((pad - x0, pad - y0), ch, font=font, fill=255, anchor="ls")
        a = np.asarray(img, dtype=np.float32) / 255.0
        inside = a >= 0.5
        # Signed distance in supersampled pixels, positive inside, measured to the pixel boundary.
        d_in = ndimage.distance_transform_edt(inside)
        d_out = ndimage.distance_transform_edt(~inside)
        sd = np.where(inside, d_in - 0.5, -(d_out - 0.5))
        # Box-average down to atlas texels, then to [0, 1] over +-SPREAD texels.
        sd = sd.reshape(h // SUPER, SUPER, w // SUPER, SUPER).mean(axis=(1, 3)) / SUPER
        v = np.clip(0.5 + sd / (2.0 * SPREAD), 0.0, 1.0)
        # Cell origin (top-left, y down) in supersampled pixels relative to the pen at the baseline.
        left = x0 - pad
        top = y0 - pad
        cells.append({
            "c": ch,
            "advance": font.getlength(ch) / em,
            "ink": [x0 / em, -y1 / em, x1 / em, -y0 / em],
            "quad": [left / em, -(top + h) / em, (left + w) / em, -top / em],
            "data": (v * 255.0 + 0.5).astype(np.uint8),
        })

    # Pack in rows of COLUMNS cells.
    rows = [cells[i:i + COLUMNS] for i in range(0, len(cells), COLUMNS)]
    width = max(sum(c["data"].shape[1] for c in r) for r in rows)
    width += (-width) % 4  # rows a multiple of 4 bytes (texture upload alignment)
    heights = [max(c["data"].shape[0] for c in r) for r in rows]
    height = sum(heights)
    height += (-height) % 4
    atlas = np.zeros((height, width), dtype=np.uint8)  # row 0 = top here
    y = 0
    for r, rh in zip(rows, heights):
        x = 0
        for c in r:
            ch_, cw_ = c["data"].shape
            atlas[y:y + ch_, x:x + cw_] = c["data"]
            # UV with v from the bottom row (the texture's first row once flipped below).
            c["uv"] = [x / width, 1.0 - (y + ch_) / height, (x + cw_) / width, 1.0 - y / height]
            x += cw_
        y += rh

    os.makedirs(OUT, exist_ok=True)
    meta = {
        "name": name,
        "atlasWidth": width,
        "atlasHeight": height,
        "spreadTexels": SPREAD,
        "units": "em/1000, y up from the baseline",
        "glyphs": [{k: (round(v, 3) if isinstance(v, float) else [round(x, 5) for x in v] if isinstance(v, list) else v)
                    for k, v in c.items() if k != "data"} for c in cells],
    }
    with open(os.path.join(OUT, name + ".json"), "w", encoding="utf-8", newline="\n") as f:
        json.dump(meta, f, indent=1)
    with open(os.path.join(OUT, name + "_sdf.bytes"), "wb") as f:
        f.write(np.flipud(atlas).tobytes())
    src_license = license_file if os.path.isabs(license_file) else os.path.join(FONTS, license_file)
    shutil.copyfile(src_license, os.path.join(OUT, name + "-OFL.txt"))
    print(f"{name}: atlas {width} x {height}, {width * height / 1024:.0f} KB")
    if preview_dir:
        os.makedirs(preview_dir, exist_ok=True)
        Image.fromarray(atlas).save(os.path.join(preview_dir, name + "_sdf.png"))
        Image.fromarray(np.where(atlas >= 128, 255, 0).astype(np.uint8)).save(os.path.join(preview_dir, name + "_ink.png"))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--preview", help="also write PNG previews of the atlases to this folder")
    parser.add_argument("faces", nargs="*", default=list(FACES))
    args = parser.parse_args()
    for name in args.faces:
        bake(name, args.preview)


if __name__ == "__main__":
    main()
