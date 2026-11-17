"""
Derives the M4.2 grayscale detail textures of UN, DEUX, TROIS, MEUBLE from ambientCG 1K-JPG downloads.

Every output is a seamless 512 x 512 RGB PNG with r = g = b, imported LINEAR (sRGB off): a texel is the
multiplier applied to the palette colour. Every texture has the same mean (MEAN, 240/255), so a material's
base colour divided by MEAN keeps the palette colour on average whatever detail a renderer shows. Highlights
are capped at 1.0 (dark details on a flat base): the brightest texel is MEAN x 1.0625, never more.

All filters wrap around (FFT), so the outputs tile like their sources.
"""
import json
import os
import sys

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(HERE, "raw")
OUT = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "out")
SIZE = 512
MEAN = 240.0 / 255.0

# name, ambientCG id, extra multiplicative map, rotate (deg), high pass sigma (px at 512), soften sigma,
# relative std, darkest (relative to MEAN)
SPECS = [
    ("wood", "Wood049", None, 90, 96.0, 0.8, 0.100, 0.70),
    ("parquet", "WoodFloor051", "AmbientOcclusion", 90, 160.0, 0.7, 0.060, 0.72),
    ("plaster", "Plaster001", None, 0, 48.0, 1.0, 0.030, 0.88),
    ("upholstery", "Fabric011", None, 0, 64.0, 0.9, 0.140, 0.68),
    ("linen", "Fabric036", None, 0, 64.0, 0.8, 0.080, 0.74),
    ("carpet", "Carpet012", None, 0, 64.0, 0.9, 0.090, 0.72),
]


def load_gray(asset, kind):
    path = os.path.join(RAW, asset, f"{asset}_1K-JPG_{kind}.jpg")
    im = Image.open(path).convert("RGB")
    a = np.asarray(im, dtype=np.float64) / 255.0
    return 0.2126 * a[..., 0] + 0.7152 * a[..., 1] + 0.0722 * a[..., 2]


def resize_wrapped(a, size):
    """Resizes a seamless image without a border seam: tile it 3 x 3, resize, keep the centre."""
    h, w = a.shape
    big = np.tile(a, (3, 3))
    im = Image.fromarray(big.astype(np.float32), mode="F").resize((3 * size, 3 * size), Image.LANCZOS)
    r = np.asarray(im, dtype=np.float64)
    return r[size:2 * size, size:2 * size]


def periodic_blur(a, sigma):
    if sigma <= 0:
        return a
    h, w = a.shape
    fy = np.fft.fftfreq(h)[:, None]
    fx = np.fft.fftfreq(w)[None, :]
    g = np.exp(-2.0 * (np.pi * sigma) ** 2 * (fx ** 2 + fy ** 2))
    return np.real(np.fft.ifft2(np.fft.fft2(a) * g))


def derive(name, asset, extra, rotate, hp, soft, std, darkest):
    lum = load_gray(asset, "Color")
    if extra:
        lum = lum * load_gray(asset, extra) ** 1.5
    if rotate:
        lum = np.rot90(lum, k=rotate // 90)
    lum = resize_wrapped(lum, SIZE)
    mean = lum.mean()
    lum = lum - periodic_blur(lum, hp) + mean
    lum = periodic_blur(lum, soft)
    z = (lum - lum.mean()) / lum.std()
    d = MEAN * (1.0 + std * z)
    lo = MEAN * darkest
    for _ in range(40):
        d = np.clip(d, lo, 1.0)
        d = d + (MEAN - d.mean())
    d = np.clip(d, lo, 1.0)
    byte = np.clip(np.round(d * 255.0), 0, 255).astype(np.uint8)
    rgb = np.stack([byte, byte, byte], axis=-1)
    file = f"detail_{name}_{asset}.png"
    Image.fromarray(rgb, mode="RGB").save(os.path.join(OUT, file), optimize=True)
    v = byte.astype(np.float64) / 255.0
    stats = {
        "file": file, "asset": asset, "mean": round(float(v.mean()), 5), "std": round(float(v.std()), 5),
        "min": round(float(v.min()), 4), "max": round(float(v.max()), 4),
        "p01": round(float(np.percentile(v, 1)), 4), "p99": round(float(np.percentile(v, 99)), 4),
        "atMax": round(float((byte == byte.max()).mean()), 4),
    }
    return stats


def main():
    os.makedirs(OUT, exist_ok=True)
    report = [derive(*s) for s in SPECS]
    for r in report:
        print(json.dumps(r))
    with open(os.path.join(HERE, "derive_stats.json"), "w", encoding="utf-8") as f:
        json.dump(report, f, indent=1)


if __name__ == "__main__":
    main()
