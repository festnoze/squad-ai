"""Gate C tall-screen sheets: one row per checkpoint, columns liquid/fire/electric x High/Medium at 1080x2400.

usage: python tallsheet.py <final dir> <out dir>
"""
import os
import sys
from PIL import Image, ImageDraw

TW, TH = 216, 480


def tile(path, label):
    im = Image.new("RGB", (TW, TH), (255, 0, 255))
    if os.path.exists(path):
        im.paste(Image.open(path).convert("RGB").resize((TW, TH), Image.LANCZOS), (0, 0))
    d = ImageDraw.Draw(im)
    d.rectangle((0, 0, TW, 14), fill=(0, 0, 0))
    d.text((3, 1), label, fill=(255, 255, 255))
    return im


def main(final, out):
    os.makedirs(out, exist_ok=True)
    groups = {"a": ["menu", "ThreadOut", "CutDroplets", "MidFill"], "b": ["SavedReturn", "PocketPending", "Caught", "results"]}
    cols = [(b, q) for b in ("liquid", "fire", "electric") for q in ("high", "medium")]
    for part, rows in groups.items():
        sheet = Image.new("RGB", (len(cols) * (TW + 2), len(rows) * (TH + 2)), (40, 40, 40))
        for r, cp in enumerate(rows):
            for c, (b, q) in enumerate(cols):
                p = os.path.join(final, f"{b}_{q}_1080x2400", f"{b}_{cp}.png")
                sheet.paste(tile(p, f"{b} {q} {cp}"), (c * (TW + 2), r * (TH + 2)))
        sheet.save(os.path.join(out, f"tall_1080x2400_sheet_{part}.png"))
    # UI aspects: menu, CutDroplets, results for 20:9 (1080x2400 medium), 21:9, 3:4 tablet; landscape separately.
    ui = [("liquid_medium_1080x2400", "20:9 1080x2400"), ("ui_liquid_1080x2520_21x9", "21:9 1080x2520"),
          ("ui_liquid_900x1200_tablet", "3:4 900x1200")]
    cps = ["menu", "CutDroplets", "SavedReturn", "results"]
    sheet = Image.new("RGB", (len(cps) * 362, len(ui) * 602), (40, 40, 40))
    for r, (d, label) in enumerate(ui):
        for c, cp in enumerate(cps):
            p = os.path.join(final, d, f"liquid_{cp}.png")
            im = Image.open(p).convert("RGB")
            im.thumbnail((360, 600), Image.LANCZOS)
            t = Image.new("RGB", (360, 600), (20, 20, 20))
            t.paste(im, ((360 - im.width) // 2, 0))
            dr = ImageDraw.Draw(t)
            dr.rectangle((0, 0, 360, 14), fill=(0, 0, 0))
            dr.text((3, 1), f"{label} {cp}", fill=(255, 255, 255))
            sheet.paste(t, (c * 362, r * 602))
    sheet.save(os.path.join(out, "ui_aspects_sheet.png"))
    land = [("ui_liquid_1280x720_landscape", "menu"), ("ui_liquid_1280x720_landscape", "results"),
            ("ui_liquid_1280x720_board", "CutDroplets"), ("ui_liquid_1280x720_board", "SavedReturn")]
    sheet = Image.new("RGB", (2 * 642, 2 * 362 + 2), (40, 40, 40))
    for i, (d, cp) in enumerate(land):
        im = Image.open(os.path.join(final, d, f"liquid_{cp}.png")).convert("RGB").resize((640, 360), Image.LANCZOS)
        dr = ImageDraw.Draw(im)
        dr.rectangle((0, 0, 640, 14), fill=(0, 0, 0))
        dr.text((3, 1), f"landscape 1280x720 {d[-9:]} {cp}", fill=(255, 255, 255))
        sheet.paste(im, ((i % 2) * 642, (i // 2) * 362))
    sheet.save(os.path.join(out, "ui_landscape_sheet.png"))
    print("ok")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
