# Side-by-side sheets for the F2 acceptance: reference | before | after for one shot, every image scaled to the same
# height, with a small caption bar. Usage:
#   python sheet.py <out.png> <height> "<caption>|<path>[@x0,y0,x1,y1]" ...
# The optional @box crops the image (its own pixels) before scaling.
import sys
from PIL import Image, ImageDraw

out, height = sys.argv[1], int(sys.argv[2])
tiles = []
for arg in sys.argv[3:]:
    caption, path = arg.split("|", 1)
    crop = None
    if "@" in path:
        path, box = path.rsplit("@", 1)
        crop = tuple(int(v) for v in box.split(","))
    im = Image.open(path).convert("RGB")
    if crop:
        im = im.crop(crop)
    w = round(im.width * height / im.height)
    im = im.resize((w, height), Image.LANCZOS)
    tiles.append((caption, im))
bar = 28
sheet = Image.new("RGB", (sum(t.width for _, t in tiles) + 8 * (len(tiles) - 1), height + bar), (12, 14, 24))
draw = ImageDraw.Draw(sheet)
x = 0
for caption, im in tiles:
    sheet.paste(im, (x, bar))
    draw.text((x + 6, 7), caption, fill=(235, 235, 235))
    x += im.width + 8
sheet.save(out)
print("saved", out, sheet.size)
