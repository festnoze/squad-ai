"""montage.py framesdir out.png first count x0 y0 x1 y1 [cols]: a labelled grid of consecutive frames, cropped."""
import os
import sys
from PIL import Image, ImageDraw

d, out = sys.argv[1], sys.argv[2]
first, count, x0, y0, x1, y1 = (int(v) for v in sys.argv[3:9])
cols = int(sys.argv[9]) if len(sys.argv) > 9 else 4
names = sorted(f for f in os.listdir(d) if f.endswith(".png"))[first:first + count]
cw, ch = x1 - x0, y1 - y0
rows = (len(names) + cols - 1) // cols
sheet = Image.new("RGB", (cols * cw, rows * (ch + 14)), (0, 0, 0))
draw = ImageDraw.Draw(sheet)
for k, n in enumerate(names):
    im = Image.open(os.path.join(d, n)).convert("RGB").crop((x0, y0, x1, y1))
    cx, cy = (k % cols) * cw, (k // cols) * (ch + 14)
    sheet.paste(im, (cx, cy + 14))
    draw.text((cx + 3, cy + 1), n, fill=(255, 255, 255))
sheet.save(out)
print(out, sheet.size, names[0] if names else None, names[-1] if names else None)
