"""Flicker statistics of a seqcap.py sequence (elec-arcs, wave D F3): is the territory steady while its arcs crackle?

usage: python flicker.py <seqdir> <t_start_s> <t_end_s> <x0> <y0> <x1> <y1>
For the frames whose capture time is in [t_start, t_end], inside the box: the pink territory mask (R >= 150 and
R - G >= 60, the coral-pink neon surface of palette index 0) united with its hot pixels (every channel >= 170, the arc
cores and white rims); per frame the mean sRGB luma over that mask and the hot pixel count. Prints the frame-to-frame
statistics: a full-screen strobe would show as large swings of the mean luma, lively arcs as a changing hot set at a
steady mean. 'changed' is the share of hot pixels that are not hot in the previous frame (arcs re-jagging, moving).
"""
import glob
import os
import sys

import numpy as np
from PIL import Image


def main():
    d, t0, t1 = sys.argv[1], float(sys.argv[2]), float(sys.argv[3])
    x0, y0, x1, y1 = (int(v) for v in sys.argv[4:8])
    rows = []
    prev = None
    for p in sorted(glob.glob(os.path.join(d, "f*.png"))):
        t = int(os.path.basename(p)[6:11]) / 1000.0
        if t < t0 or t > t1:
            continue
        a = np.asarray(Image.open(p).convert("RGB")).astype(float)[y0:y1, x0:x1]
        r, g, b = a[..., 0], a[..., 1], a[..., 2]
        hot = a.min(axis=2) >= 170
        terr = ((r >= 150) & (r - g >= 60)) | hot
        lum = 0.299 * r + 0.587 * g + 0.114 * b
        mean = lum[terr].mean() if terr.any() else 0.0
        changed = (hot & ~prev).sum() / max(hot.sum(), 1) if prev is not None else float("nan")
        rows.append((t, mean, int(hot.sum()), changed))
        prev = hot
    means = np.array([m for _, m, _, _ in rows])
    hots = np.array([h for _, _, h, _ in rows])
    steps = np.abs(np.diff(means))
    ch = np.array([c for _, _, _, c in rows[1:]])
    print("%s: %d frames %.2f-%.2f s" % (d[-40:], len(rows), rows[0][0], rows[-1][0]))
    print("  territory mean luma %.1f (min %.1f max %.1f), frame-to-frame |step| mean %.2f max %.2f (%.1f %% of the mean)"
          % (means.mean(), means.min(), means.max(), steps.mean(), steps.max(), 100.0 * steps.max() / means.mean()))
    print("  hot pixels per frame mean %.0f (min %d max %d), changed share frame to frame %.0f %%"
          % (hots.mean(), hots.min(), hots.max(), 100.0 * np.nanmean(ch)))


if __name__ == "__main__":
    main()
