# V5 check (colors stay saturated, close to the palette): for each palette color, the pixels of a shot whose hue is
# within 12 degrees of it and saturation > 0.35 (the puddles of that color, highlights and the darkest shadow excluded),
# their median sRGB and median HSV saturation and value. Usage: python paintstats.py <shot.png> [<shot2.png> ...]
import colorsys, sys
import numpy as np
from PIL import Image

PALETTE = {"coral": (0xF2, 0x67, 0x4F), "teal": (0x22, 0xC4, 0xB6), "saffron": (0xF5, 0xB7, 0x31), "lilac": (0x8E, 0x6C, 0xEF)}
for path in sys.argv[1:]:
    im = np.asarray(Image.open(path).convert("RGB"))[130:].reshape(-1, 3) / 255.0
    mx, mn = im.max(axis=1), im.min(axis=1)
    sat = np.where(mx > 0, (mx - mn) / np.maximum(mx, 1e-6), 0)
    hsv = np.array([colorsys.rgb_to_hsv(*p) for p in im[::7]])
    sub = im[::7]
    out = []
    for name, rgb in PALETTE.items():
        h0 = colorsys.rgb_to_hsv(*(np.array(rgb) / 255.0))[0]
        dh = np.minimum(np.abs(hsv[:, 0] - h0), 1 - np.abs(hsv[:, 0] - h0)) * 360
        m = (dh < 12) & (hsv[:, 1] > 0.35) & (hsv[:, 2] > 0.25)
        if m.sum() < 50:
            continue
        med = np.median(sub[m], axis=0) * 255
        out.append(f"{name}: n={m.sum()} median sRGB ({med[0]:.0f},{med[1]:.0f},{med[2]:.0f}) palette {rgb} S={np.median(hsv[m, 1]):.2f} V={np.median(hsv[m, 2]):.2f}")
    print(path.split("/")[-3] + "/" + path.split("/")[-2] + "/" + path.split("/")[-1] + ": " + " | ".join(out))
