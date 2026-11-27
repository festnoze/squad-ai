"""Gate C regression sheets: Gate B vs wave C final, per biome, High and Medium at 540x960.

usage: python compare.py <gateB dir> <final dir> <out dir>
Writes <biome>_sheet_a.png (menu, thread, cut, fill) and <biome>_sheet_b.png (saved, pocket, caught, results):
columns Gate B High | final High | Gate B Medium | final Medium, each tile 270x480 with a label.
"""
import os
import sys
from PIL import Image, ImageDraw

PAIRS = [("menu", "menu"), ("thread", "ThreadOut"), ("cut", "CutDroplets"), ("fill", "MidFill"),
         ("saved", "SavedReturn"), ("pocket", "PocketPending"), ("caught", "Caught"), ("results", "results")]
TW, TH = 270, 480


def tile(path, label):
    im = Image.new("RGB", (TW, TH), (255, 0, 255))
    if os.path.exists(path):
        src = Image.open(path).convert("RGB").resize((TW, TH), Image.LANCZOS)
        im.paste(src, (0, 0))
    d = ImageDraw.Draw(im)
    d.rectangle((0, 0, TW, 14), fill=(0, 0, 0))
    d.text((3, 1), label, fill=(255, 255, 255))
    return im


def main(gate, final, out):
    os.makedirs(out, exist_ok=True)
    for biome in ("liquid", "fire", "electric"):
        for part, rows in (("a", PAIRS[:4]), ("b", PAIRS[4:])):
            sheet = Image.new("RGB", (TW * 4 + 6, TH * len(rows) + 2 * (len(rows) - 1)), (40, 40, 40))
            for r, (probe_name, ds_name) in enumerate(rows):
                cells = [
                    (os.path.join(gate, f"{biome}_{probe_name}.png"), f"GateB High {probe_name}"),
                    (os.path.join(final, f"{biome}_high_540x960", f"{biome}_{ds_name}.png"), f"C High {ds_name}"),
                    (os.path.join(gate, "medium", f"{biome}_{ds_name}.png"), f"GateB Med {ds_name}"),
                    (os.path.join(final, f"{biome}_medium_540x960", f"{biome}_{ds_name}.png"), f"C Med {ds_name}"),
                ]
                for c, (p, label) in enumerate(cells):
                    sheet.paste(tile(p, label), (c * (TW + 2), r * (TH + 2)))
            sheet.save(os.path.join(out, f"{biome}_sheet_{part}.png"))
            print("wrote", os.path.join(out, f"{biome}_sheet_{part}.png"))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3])
