"""Side-by-side sheets and zoomed crops for the elec-arcs package (wave D, docs/WAVE_D_FEEDBACK.md F3).

usage:
  python sheet.py pair <out.png> <scale> <x0> <y0> <x1> <y1> <label>=<image> [<label>=<image> ...]
      the same crop box from every image, upscaled by <scale> (nearest), side by side with a label strip
  python sheet.py grid <out.png> <columns> <width> <label>=<image> [...]
      whole images resized to <width> px wide, in a grid with labels
"""
import sys

from PIL import Image, ImageDraw


def labelled(img, label):
    strip = 22
    out = Image.new("RGB", (img.width, img.height + strip), (12, 14, 24))
    out.paste(img, (0, strip))
    ImageDraw.Draw(out).text((6, 4), label, fill=(235, 235, 235))
    return out


def parse(items):
    pairs = []
    for it in items:
        label, path = it.split("=", 1)
        pairs.append((label, Image.open(path).convert("RGB")))
    return pairs


def pair(out, scale, box, items):
    tiles = []
    for label, img in parse(items):
        c = img.crop(box)
        c = c.resize((c.width * scale, c.height * scale), Image.NEAREST)
        tiles.append(labelled(c, label))
    w = sum(t.width for t in tiles) + 6 * (len(tiles) - 1)
    h = max(t.height for t in tiles)
    sheet = Image.new("RGB", (w, h), (40, 40, 40))
    x = 0
    for t in tiles:
        sheet.paste(t, (x, 0))
        x += t.width + 6
    sheet.save(out)


def grid(out, cols, width, items):
    tiles = []
    for label, img in parse(items):
        h = round(img.height * width / img.width)
        tiles.append(labelled(img.resize((width, h), Image.LANCZOS), label))
    rows = (len(tiles) + cols - 1) // cols
    th = max(t.height for t in tiles)
    sheet = Image.new("RGB", (cols * width + 6 * (cols - 1), rows * th + 6 * (rows - 1)), (40, 40, 40))
    for i, t in enumerate(tiles):
        sheet.paste(t, ((i % cols) * (width + 6), (i // cols) * (th + 6)))
    sheet.save(out)


def main():
    mode = sys.argv[1]
    if mode == "pair":
        out, scale = sys.argv[2], int(sys.argv[3])
        box = tuple(int(v) for v in sys.argv[4:8])
        pair(out, scale, box, sys.argv[9:] if sys.argv[8] == "--" else sys.argv[8:])
    elif mode == "grid":
        grid(sys.argv[2], int(sys.argv[3]), int(sys.argv[4]), sys.argv[5:])
    else:
        raise SystemExit(__doc__)


if __name__ == "__main__":
    main()
