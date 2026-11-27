"""sheet <dir> <out> <from> <to> <step> <cols> <scale> [x0 y0 x1 y1]: contact sheet of frames f*.png, labelled."""
import glob
import os
import sys

from PIL import Image, ImageDraw

d, out = sys.argv[1], sys.argv[2]
a, b, step, cols = (int(v) for v in sys.argv[3:7])
scale = float(sys.argv[7])
box = tuple(int(v) for v in sys.argv[8:12]) if len(sys.argv) >= 12 else None
fs = sorted(glob.glob(os.path.join(d, "f*.png")))[a:b + 1:step]
ims = []
for f in fs:
    im = Image.open(f).convert("RGB")
    if box:
        im = im.crop(box)
    ims.append((os.path.basename(f)[:-4], im.resize((int(im.width * scale), int(im.height * scale)), Image.LANCZOS)))
tw, th = ims[0][1].size
rows = (len(ims) + cols - 1) // cols
sheet = Image.new("RGB", (tw * cols, (th + 14) * rows), (0, 0, 0))
dr = ImageDraw.Draw(sheet)
for n, (name, im) in enumerate(ims):
    x, y = (n % cols) * tw, (n // cols) * (th + 14)
    sheet.paste(im, (x, y + 14))
    dr.text((x + 2, y + 1), name, fill=(255, 255, 255))
sheet.save(out)
print("saved", out, len(ims), "frames")
