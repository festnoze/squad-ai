"""Arc statistics in a box of a DevShot (elec-arcs, wave D F3).

usage: python arcstats.py <x0> <y0> <x1> <y1> <image> [<image> ...]
Per image, inside the box: hot = pixels whose every channel is >= 170 (the white-hot arc cores on a neon surface,
whose darkest channel is far lower), white = sRGB luma >= 235 (the 25.5 readability threshold: arcs must add none),
mean luma. Works for any player color except yellow, whose neon surface already has two bright channels.
"""
import sys

import numpy as np
from PIL import Image


def main():
    box = [int(v) for v in sys.argv[1:5]]
    for path in sys.argv[5:]:
        img = np.asarray(Image.open(path).convert("RGB")).astype(float)[box[1]:box[3], box[0]:box[2]]
        lum = 0.299 * img[..., 0] + 0.587 * img[..., 1] + 0.114 * img[..., 2]
        hot = int((img.min(axis=2) >= 170).sum())
        white = int((lum >= 235).sum())
        print("%-70s hot %5d  luma>=235 %5d  mean luma %6.1f" % (path[-70:], hot, white, lum.mean()))


if __name__ == "__main__":
    main()
