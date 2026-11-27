"""disc <png> <thr> <cx> <cy> <r> [<r> ...]: pixels of luma >= thr inside discs around (cx, cy), and the brightest pixel."""
import sys

import numpy as np
from PIL import Image

img = np.asarray(Image.open(sys.argv[1]).convert("RGB")).astype(np.float64)
thr = float(sys.argv[2])
cx, cy = float(sys.argv[3]), float(sys.argv[4])
lum = 0.299 * img[..., 0] + 0.587 * img[..., 1] + 0.114 * img[..., 2]
ys, xs = np.mgrid[0:img.shape[0], 0:img.shape[1]]
d = np.hypot(xs - cx, ys - cy)
for r in sys.argv[5:]:
    m = d <= float(r)
    sel = (lum >= thr) & m
    if sel.any():
        sy, sx = np.nonzero(sel)
        c = "centroid=(%.1f,%.1f)" % (sx.mean(), sy.mean())
    else:
        c = ""
    print("r=%s count=%d max_luma=%.0f %s" % (r, sel.sum(), lum[m].max(), c))
