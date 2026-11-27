"""Measures the home chevron in a DevShot CutDroplets image: the connected blob of light, low-saturation pixels closest
to the human pearl (outside the pearl), its bounding box and pixel count; writes a zoomed crop around it."""
import sys
from collections import deque
import numpy as np
from PIL import Image
sys.path.insert(0, sys.argv[0].rsplit("\\", 1)[0].rsplit("/", 1)[0])
from measure import parse, to_px

root, biome, out, dist_u = sys.argv[1], sys.argv[2], sys.argv[3], float(sys.argv[4])
info = parse(root + "/p.log")
im = Image.open(f"{root}/{biome}_CutDroplets.png").convert("RGB")
img = np.asarray(im).astype(np.int32)
h, w, _ = img.shape
hx, hy, ppu = to_px(info, w, h, info["hx"], info["hy"])
mn = img.min(axis=2)
mx = img.max(axis=2)
light = (mn >= 170) & ((mx - mn) <= 60)
yy, xx = np.mgrid[0:h, 0:w]
d = np.sqrt((xx - hx) ** 2 + (yy - hy) ** 2) / ppu
import re as _re
_m = _re.search(r"checkpoint CutDroplets .*?home=\(([-\d.]+),([-\d.]+)\)", open(root + "/p.log", encoding="utf-8", errors="replace").read())
hmx, hmy = float(_m.group(1)), float(_m.group(2))
_dx, _dy = hmx - info["hx"], hmy - info["hy"]
_n = (_dx * _dx + _dy * _dy) ** 0.5
ecx, ecy, _ = to_px(info, w, h, info["hx"] + _dx / _n * dist_u, info["hy"] + _dy / _n * dist_u)
de = np.sqrt((xx - ecx) ** 2 + (yy - ecy) ** 2) / ppu
cand = light & (de <= 0.9)
d = de
if not cand.any():
    print(biome, "no chevron pixels")
    sys.exit(0)
# Seed: the candidate closest to the pearl; flood fill over light pixels (8-connected) within 3 u.
idx = np.argmin(np.where(cand, de, 1e9))
sy, sx = divmod(int(idx), w)
seen = np.zeros_like(light)
q = deque([(sy, sx)])
seen[sy, sx] = True
pts = []
while q:
    y, x = q.popleft()
    pts.append((y, x))
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            ny, nx = y + dy, x + dx
            if 0 <= ny < h and 0 <= nx < w and not seen[ny, nx] and light[ny, nx] and de[ny, nx] <= 1.0:
                seen[ny, nx] = True
                q.append((ny, nx))
ys = np.array([p[0] for p in pts])
xs = np.array([p[1] for p in pts])
x0, x1, y0, y1 = xs.min(), xs.max(), ys.min(), ys.max()
luma = 0.299 * img[..., 0] + 0.587 * img[..., 1] + 0.114 * img[..., 2]
blob_luma = luma[ys, xs]
print(f"{biome}: chevron blob {len(pts)} px, bbox x {x0}-{x1} y {y0}-{y1} -> {x1 - x0 + 1}x{y1 - y0 + 1} px, "
      f"luma max {blob_luma.max():.0f} mean {blob_luma.mean():.0f}, >=235: {(blob_luma >= 235).sum()}")
cx, cy = (x0 + x1) // 2, (y0 + y1) // 2
r = int(1.6 * ppu)
crop = im.crop((max(0, cx - r), max(0, cy - r), min(w, cx + r), min(h, cy + r)))
crop.resize((crop.width * 6, crop.height * 6), Image.NEAREST).save(out)
