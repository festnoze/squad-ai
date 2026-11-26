"""
Derives the environment detail and normal maps of OUT OF SIGHT from the product owner's 13 environment images
(Assets/Art/Environment/<surface>.png, 1254 x 1254 RGB), replacing the ambientCG derived ones.

Same contract as derive_textures.py: every detail is a seamless 512 x 512 RGB PNG with r = g = b, imported
LINEAR, mean exactly 240/255 (Tuning.DetailMean), highlights capped at 1.0. The palette colour carries the
meaning, so the detail is grayscale only: the luminance of the source, high-passed with wrap-around filters.

Calm: the contrast of each new detail is matched to the detail it replaces (same std), then lowered further
when its fine detail (mean absolute neighbour difference at 512, 256 and 128 px, a stand-in for what the
Step22d noise probe measures through the mip chain) would exceed the old one's. Walls, floors and the
player lacquer get an extra margin (level 1 read 1.98 of the 2.0 limit with the old set).

Seamless: most sources are nearly but not exactly seamless. Each wrap edge is cross-faded, in a narrow band,
with a copy of the image rolled by about half its size along that axis only (the roll is snapped to the
offset that best matches the pattern, so a weave or a grain stays in phase). Structured sources whose edges
already fall on a joint (tile grout, parquet planks) are left as they are.

Normal maps: the ambientCG ones no longer match these sources, so each surface that had one gets a gentle
tangent space normal map derived from its own new detail (periodic Sobel on the detail as a height), with
at most the xy strength (rms) of the map it replaces and never more fine detail than it (same mips and margin as
the detail), so the tuned Tuning.NormalScale* values keep their meaning and the bump stays calm.
OpenGL convention (green up), like the ambientCG NormalGL maps.

Usage: python tools/assets/derive_env_textures.py   (writes Assets/Art/Environment/Detail/)
The calm targets are read from the retired ambientCG maps, deleted from Assets/ThirdParty/Textures/ambientCG on
2026-11-18: to re-run, restore them first (git checkout fdd2bd36 -- games/OutOfSight/Assets/ThirdParty/Textures).
"""
import json
import os

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, "..", ".."))
SRC = os.path.join(ROOT, "Assets", "Art", "Environment")
OUT = os.path.join(SRC, "Detail")
OLD = os.path.join(ROOT, "Assets", "ThirdParty", "Textures", "ambientCG")
SIZE = 512
MEAN = 240.0 / 255.0
BAND = 28  # cross-fade half width at the source size (1254 px), about 2 %
# Streaky sources (grain or brushing along x): a wider band, so a streak fades instead of stopping at the seam.
WIDE_BAND = {"wood": 220, "lacquer": 220, "metal": 220}

# surface, old ambientCG id, rotate (deg), high pass sigma (px at 512), soften sigma, seam fix, calm margin
SPECS = [
    ("wood", "Wood049", 90, 96.0, 0.8, True, 1.0),
    ("parquet", "WoodFloor051", 90, 160.0, 0.7, False, 0.9),
    ("plaster", "Plaster001", 0, 48.0, 1.0, True, 0.9),
    ("upholstery", "Fabric011", 0, 64.0, 0.9, True, 1.0),
    ("linen", "Fabric036", 0, 64.0, 0.8, True, 1.0),
    ("carpet", "Carpet012", 0, 64.0, 0.9, True, 0.95),
    ("grass", "Grass001", 0, 96.0, 1.6, True, 1.0),
    ("lacquer", "PaintedWood006C", 90, 96.0, 0.8, True, 0.9),
    ("metal", "Metal009", 0, 96.0, 0.6, True, 1.0),
    ("plastic", "Plastic006", 0, 64.0, 0.9, True, 1.0),
    ("foliage", "Moss002", 0, 64.0, 0.8, True, 1.0),
    ("soil", "Ground104", 0, 64.0, 0.8, True, 1.0),
    ("tile", "Tiles049", 0, 160.0, 0.6, False, 0.95),
]
HAS_NORMAL = {"wood", "parquet", "plaster", "upholstery", "linen", "carpet", "grass", "lacquer", "metal", "tile"}


def luminance(path):
    a = np.asarray(Image.open(path).convert("RGB"), dtype=np.float64) / 255.0
    return 0.2126 * a[..., 0] + 0.7152 * a[..., 1] + 0.0722 * a[..., 2]


def best_roll(a, axis):
    """The roll near half the size along an axis that best matches the image with itself (keeps a weave in phase)."""
    n = a.shape[axis]
    best, best_err = n // 2, None
    for s in range(n // 2 - 40, n // 2 + 41):
        err = np.abs(a - np.roll(a, s, axis=axis)).mean()
        if best_err is None or err < best_err:
            best, best_err = s, err
    return best


def fix_seam(a, axis, band=BAND):
    """Cross-fades the wrap edge along one axis with a rolled copy, so the opposite borders meet."""
    n = a.shape[axis]
    rolled = np.roll(a, best_roll(a, axis), axis=axis)
    d = np.minimum(np.arange(n), n - 1 - np.arange(n)).astype(np.float64)
    t = np.clip(d / band, 0.0, 1.0)
    w = t * t * (3.0 - 2.0 * t)  # 0 on the edge (all rolled copy), 1 beyond the band (all original)
    w = w[:, None] if axis == 0 else w[None, :]
    return w * a + (1.0 - w) * rolled


def resize_wrapped(a, size):
    """Resizes a seamless image without a border seam: tile it 3 x 3, resize, keep the centre."""
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


def fine_detail(d):
    """Mean absolute neighbour difference (wrap-around) at 512, 256 and 128 px (box mips)."""
    out = []
    for _ in range(3):
        out.append(0.5 * (np.abs(d - np.roll(d, 1, 0)).mean() + np.abs(d - np.roll(d, 1, 1)).mean()))
        d = 0.25 * (d[0::2, 0::2] + d[1::2, 0::2] + d[0::2, 1::2] + d[1::2, 1::2])
    return np.array(out)


def remap(z, std, darkest):
    d = MEAN * (1.0 + std * z)
    lo = MEAN * darkest
    for _ in range(40):
        d = np.clip(d, lo, 1.0)
        d = d + (MEAN - d.mean())
    return np.clip(d, lo, 1.0)


def normal_from(d, old_xy, margin):
    """
    A gentle tangent space normal map (OpenGL, green up) from the detail as a height: as strong as the old map
    (xy rms) at most, and never with more fine detail than the old map at any of the three mips (times the margin).
    """
    rms = float(np.sqrt(old_xy[..., 0].std() ** 2 + old_xy[..., 1].std() ** 2))
    old_fine = fine_detail(old_xy[..., 0]) + fine_detail(old_xy[..., 1])
    h = d / MEAN
    gx = (np.roll(h, -1, 1) - np.roll(h, 1, 1)) * 2 + (np.roll(np.roll(h, -1, 1), 1, 0) - np.roll(np.roll(h, 1, 1), 1, 0)) \
        + (np.roll(np.roll(h, -1, 1), -1, 0) - np.roll(np.roll(h, 1, 1), -1, 0))
    gy = (np.roll(h, -1, 0) - np.roll(h, 1, 0)) * 2 + (np.roll(np.roll(h, -1, 0), 1, 1) - np.roll(np.roll(h, 1, 0), 1, 1)) \
        + (np.roll(np.roll(h, -1, 0), -1, 1) - np.roll(np.roll(h, 1, 0), -1, 1))
    gx = periodic_blur(gx / 8.0, 0.6)
    gy = periodic_blur(gy / 8.0, 0.6)
    k_lo, k_hi = 0.0, 400.0
    for _ in range(50):  # bisect the strength so the xy rms of the unit normals matches the old map
        k = 0.5 * (k_lo + k_hi)
        nx, ny = -k * gx, k * gy  # image rows grow downwards, texture v upwards
        inv = 1.0 / np.sqrt(nx * nx + ny * ny + 1.0)
        cur = np.sqrt((nx * inv).std() ** 2 + (ny * inv).std() ** 2)
        fine = ((fine_detail(nx * inv) + fine_detail(ny * inv)) / old_fine).max()
        if cur < rms and fine < margin:
            k_lo = k
        else:
            k_hi = k
    n = np.stack([nx * inv, ny * inv, inv], axis=-1)
    return np.clip(np.round((n * 0.5 + 0.5) * 255.0), 0, 255).astype(np.uint8), k, cur, fine


def derive(name, old_id, rotate, hp, soft, seam, margin):
    lum = luminance(os.path.join(SRC, name + ".png"))
    if seam:
        band = WIDE_BAND.get(name, BAND)
        lum = fix_seam(fix_seam(lum, 1, band), 0, BAND)
    if rotate:
        lum = np.rot90(lum, k=rotate // 90)
    lum = resize_wrapped(lum, SIZE)
    lum = lum - periodic_blur(lum, hp) + lum.mean()
    lum = periodic_blur(lum, soft)
    z = (lum - lum.mean()) / lum.std()

    old = np.asarray(Image.open(os.path.join(OLD, f"detail_{name}_{old_id}.png")).convert("L"), dtype=np.float64) / 255.0
    old_std = old.std() / MEAN
    darkest = max(old.min() / MEAN, 0.66)
    old_fine = fine_detail(old)
    std = old_std
    for _ in range(6):  # calm: never more fine detail than the old map at any of the three mips (times the margin)
        d = remap(z, std, darkest)
        ratio = (fine_detail(d) / old_fine).max()
        if ratio <= margin * 1.005:
            break
        std *= margin / ratio
    byte = np.clip(np.round(d * 255.0), 0, 255).astype(np.uint8)
    os.makedirs(OUT, exist_ok=True)
    Image.fromarray(np.stack([byte] * 3, axis=-1), mode="RGB").save(os.path.join(OUT, f"detail_{name}.png"), optimize=True)
    v = byte.astype(np.float64) / 255.0
    stats = {
        "surface": name, "mean": round(float(v.mean()), 5), "std": round(float(v.std()), 5),
        "oldStd": round(float(old.std()), 5), "min": round(float(v.min()), 4), "max": round(float(v.max()), 4),
        "fineVsOld": [round(float(x), 3) for x in fine_detail(v) / old_fine],
    }
    if name in HAS_NORMAL:
        on = np.asarray(Image.open(os.path.join(OLD, f"normal_{name}_{old_id}.png")).convert("RGB"), dtype=np.float64) / 255.0 * 2 - 1
        nrm, k, rms, fine = normal_from(v, on, margin)
        Image.fromarray(nrm, mode="RGB").save(os.path.join(OUT, f"normal_{name}.png"), optimize=True)
        stats["normalRms"] = round(rms, 4)
        stats["oldNormalRms"] = round(float(np.sqrt(on[..., 0].std() ** 2 + on[..., 1].std() ** 2)), 4)
        stats["normalFineVsOld"] = round(fine, 3)
        stats["normalStrength"] = round(k, 2)
    return stats


def main():
    report = [derive(*s) for s in SPECS]
    for r in report:
        print(json.dumps(r))
    with open(os.path.join(HERE, "derive_env_stats.json"), "w", encoding="utf-8") as f:
        json.dump(report, f, indent=1)


if __name__ == "__main__":
    main()
