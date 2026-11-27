"""Packet versus pearl brightness on an electric CutDroplets DevShot (540x960), wave C biome-electric-liquid.

usage: python packet_measure.py <electric_CutDroplets.png> [packet_x packet_y pearl_x pearl_y chevron_x chevron_y]
Defaults are the DevShot positions at 540x960 (the scenario is deterministic): packet head (440, 379), human pearl
(278, 465), home chevron (300, 487). Prints, per disc, the pixels of sRGB luma >= 235 and the near-white pixels (every
channel >= 230). The near-white count is the fair one for an electric-yellow human, whose saturated neon already
reaches luma 235 without being white.
"""
import sys

import numpy as np
from PIL import Image


def counts(img, cx, cy, r):
    ys, xs = np.mgrid[0:img.shape[0], 0:img.shape[1]]
    disc = np.hypot(xs - cx, ys - cy) <= r
    lum = 0.299 * img[..., 0] + 0.587 * img[..., 1] + 0.114 * img[..., 2]
    return int(((lum >= 235) & disc).sum()), int(((img.min(axis=2) >= 230) & disc).sum())


def main():
    img = np.asarray(Image.open(sys.argv[1]).convert("RGB")).astype(float)
    v = [float(a) for a in sys.argv[2:8]] if len(sys.argv) >= 8 else [440, 379, 278, 465, 300, 487]
    packet = counts(img, v[0], v[1], 10)
    pearl = counts(img, v[2], v[3], 15)
    chevron = counts(img, v[4], v[5], 14)
    print("packet  r10: luma>=235 %4d  near-white %4d" % packet)
    print("pearl   r15: luma>=235 %4d  near-white %4d" % pearl)
    print("chevron r14: luma>=235 %4d  near-white %4d" % chevron)
    for i, name in enumerate(("luma>=235", "near-white")):
        print("packet / pearl (%s): %.2f" % (name, packet[i] / max(pearl[i], 1)))


if __name__ == "__main__":
    main()
