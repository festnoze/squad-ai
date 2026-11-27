"""Crop a region of a PNG and upscale it (nearest) for inspection: crop.py in.png out.png x0 y0 x1 y1 scale"""
import sys
from PIL import Image

src, dst = sys.argv[1], sys.argv[2]
x0, y0, x1, y1, s = (int(v) for v in sys.argv[3:8])
im = Image.open(src).convert("RGB").crop((x0, y0, x1, y1))
im = im.resize((im.width * s, im.height * s), Image.NEAREST)
im.save(dst)
print(dst, im.size)
