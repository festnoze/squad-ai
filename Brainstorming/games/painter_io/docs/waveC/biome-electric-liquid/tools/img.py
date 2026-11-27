"""Image helpers for the biome-electric-liquid acceptance checks.

zoom  <png> <x0> <y0> <x1> <y1> <scale> <out>          nearest-neighbour crop and upscale
pair  <a.png> <b.png> <x0> <y0> <x1> <y1> <scale> <out> two crops side by side (a left, b right)
blobs <png> <thr> [x0 y0 x1 y1]                         connected components of luma >= thr (8-connected)
diff  <a.png> <b.png> [x0 y0 x1 y1]                     per-pixel difference stats (max channel diff)
"""
import sys
from collections import deque

import numpy as np
from PIL import Image


def load(path):
    return np.asarray(Image.open(path).convert("RGB")).astype(np.int32)


def luma(rgb):
    return 0.299 * rgb[..., 0] + 0.587 * rgb[..., 1] + 0.114 * rgb[..., 2]


def crop(img, box):
    if box is None:
        return img, (0, 0)
    x0, y0, x1, y1 = box
    return img[y0:y1, x0:x1], (x0, y0)


def zoom(src, box, scale):
    im = Image.open(src).convert("RGB").crop(box)
    return im.resize((im.width * scale, im.height * scale), Image.NEAREST)


def blobs(path, thr, box):
    img, (ox, oy) = crop(load(path), box)
    mask = luma(img) >= thr
    h, w = mask.shape
    seen = np.zeros_like(mask)
    found = []
    for y in range(h):
        for x in range(w):
            if not mask[y, x] or seen[y, x]:
                continue
            q = deque([(y, x)])
            seen[y, x] = True
            pts = []
            while q:
                cy, cx = q.popleft()
                pts.append((cy, cx))
                for dy in (-1, 0, 1):
                    for dx in (-1, 0, 1):
                        ny, nx = cy + dy, cx + dx
                        if 0 <= ny < h and 0 <= nx < w and mask[ny, nx] and not seen[ny, nx]:
                            seen[ny, nx] = True
                            q.append((ny, nx))
            ys = [p[0] for p in pts]
            xs = [p[1] for p in pts]
            found.append((len(pts), min(xs) + ox, min(ys) + oy, max(xs) + ox, max(ys) + oy,
                          sum(xs) / len(xs) + ox, sum(ys) / len(ys) + oy))
    found.sort(reverse=True)
    for b in found[:25]:
        print("area=%4d bbox=(%d,%d)-(%d,%d) c=(%.1f,%.1f)" % b)
    print("total components:", len(found), "total area:", sum(b[0] for b in found))


def diff(a, b, box):
    ia, _ = crop(load(a), box)
    ib, _ = crop(load(b), box)
    d = np.abs(ia - ib).max(axis=2)
    print("pixels=%d max=%d mean=%.3f >8:%d >16:%d >32:%d" % (d.size, d.max(), d.mean(), (d > 8).sum(), (d > 16).sum(), (d > 32).sum()))
    if (d > 16).any():
        ys, xs = np.nonzero(d > 16)
        print("bbox of >16: (%d,%d)-(%d,%d)" % (xs.min() + (box[0] if box else 0), ys.min() + (box[1] if box else 0),
                                                xs.max() + (box[0] if box else 0), ys.max() + (box[1] if box else 0)))


def main():
    cmd = sys.argv[1]
    a = sys.argv[2:]
    if cmd == "zoom":
        box = tuple(int(v) for v in a[1:5])
        zoom(a[0], box, int(a[5])).save(a[6])
    elif cmd == "pair":
        box = tuple(int(v) for v in a[2:6])
        s = int(a[6])
        za, zb = zoom(a[0], box, s), zoom(a[1], box, s)
        out = Image.new("RGB", (za.width * 2 + 6, za.height), (255, 0, 255))
        out.paste(za, (0, 0))
        out.paste(zb, (za.width + 6, 0))
        out.save(a[7])
    elif cmd == "blobs":
        box = tuple(int(v) for v in a[2:6]) if len(a) >= 6 else None
        blobs(a[0], float(a[1]), box)
    elif cmd == "diff":
        box = tuple(int(v) for v in a[2:6]) if len(a) >= 6 else None
        diff(a[0], a[1], box)


if __name__ == "__main__":
    main()
