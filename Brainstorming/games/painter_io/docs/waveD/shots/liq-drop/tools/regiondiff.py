# Splits the pixel differences of two DevShots into "ground" (dark pixels in both images, luma < 60: the table, the
# shadows, the contact darkening) and "bright" (territory, threads, pearls, effects). Used for the electric biome, whose
# territory interior gained the F3 arcs of another wave D package in the same source tree: the rest must not change.
# Usage: python regiondiff.py <imgA> <imgB> [threshold=24] [skip_hud_px=130]
import sys
import numpy as np
from PIL import Image

a = np.asarray(Image.open(sys.argv[1]).convert("RGB")).astype(np.int16)
b = np.asarray(Image.open(sys.argv[2]).convert("RGB")).astype(np.int16)
thr = int(sys.argv[3]) if len(sys.argv) > 3 else 24
hud = int(sys.argv[4]) if len(sys.argv) > 4 else 130
a, b = a[hud:], b[hud:]
luma = lambda x: 0.299 * x[..., 0] + 0.587 * x[..., 1] + 0.114 * x[..., 2]
ground = (luma(a) < 60) & (luma(b) < 60)
d = np.abs(a - b).max(axis=2)
big = d > thr
print(f"ground {ground.mean() * 100:5.1f} % of px: diff>{thr} {big[ground].mean() * 100:6.3f} %, mean {d[ground].mean():5.3f} | "
      f"bright: diff>{thr} {big[~ground].mean() * 100:6.3f} %, mean {d[~ground].mean():5.3f}")
