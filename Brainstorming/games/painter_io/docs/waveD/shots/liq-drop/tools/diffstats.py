# Pixel difference statistics between two DevShot folders (same file names): per shot, the mean absolute difference
# (0-255 per channel) and the share of pixels whose largest channel difference exceeds a threshold. Used to show that
# the fire and electric composites did not change: compare (before run 1, before run 2) of the same build to get the
# noise floor of the time-animated shaders, then (before, after).
# Usage: python diffstats.py <dirA> <dirB> [threshold=24] [skip_hud_px=130]
import os, sys
import numpy as np
from PIL import Image

a_dir, b_dir = sys.argv[1], sys.argv[2]
thr = int(sys.argv[3]) if len(sys.argv) > 3 else 24
hud = int(sys.argv[4]) if len(sys.argv) > 4 else 130
for name in sorted(os.listdir(a_dir)):
    if not name.endswith(".png"):
        continue
    pa, pb = os.path.join(a_dir, name), os.path.join(b_dir, name)
    if not os.path.exists(pb):
        print(f"{name}: missing in B")
        continue
    a = np.asarray(Image.open(pa).convert("RGB")).astype(np.int16)
    b = np.asarray(Image.open(pb).convert("RGB")).astype(np.int16)
    if a.shape != b.shape:
        print(f"{name}: size {a.shape} vs {b.shape}")
        continue
    a, b = a[hud:], b[hud:]              # the HUD timer and percentages move between runs
    d = np.abs(a - b)
    big = (d.max(axis=2) > thr).mean() * 100.0
    print(f"{name:32s} mean {d.mean():6.3f}  >{thr}: {big:6.3f} %")
