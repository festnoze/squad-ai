"""
Derives the real-colour maps of OUT OF SIGHT (docs/CONTRACT_M7.md 5, product owner decision of 2026-11-18) from the
product owner's environment images (Assets/Art/Environment/<surface>.png, 1254 x 1254 RGB): each image becomes the base
map of its surface, in its own colours, drawn under a white base colour (PrimitiveKit.SurfaceMaterial).

Same geometry as derive_env_textures.py, so the gentle normal maps under Detail/ stay aligned with the colour: each wrap
edge is cross-faded with a copy rolled by about half the image (the roll is found on the luminance, exactly as the
detail derivation finds it, then applied to every channel), wood, parquet and lacquer are turned 90 degrees so the grain
or the planks run along V (the meshes' longer side), and the result is resized to 512 x 512 with a wrap-around filter.
The colours themselves are not touched: no high pass, no remap, sRGB in and sRGB out.

The player furniture (PRD 7.2: the one red thing in every frame): the owner's red image when one is in the folder
(PLAYER_SOURCES; red_metal_source.png, "vivid red painted metal", prepared the same way and drawn without a normal map:
painted metal is optically flat, its finish comes from the material's smoothness and metallic); otherwise the lacquer
grain tinted red: Detail/detail_lacquer.png (so normal_lacquer.png stays aligned) over the player red #D7263D, at a
contrast that reads at play distance and with the red kept on average.

Usage: python tools/assets/derive_env_colours.py   (writes Assets/Art/Environment/Colour/)
"""
import glob
import json
import os

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, "..", ".."))
SRC = os.path.join(ROOT, "Assets", "Art", "Environment")
DETAIL = os.path.join(SRC, "Detail")
OUT = os.path.join(SRC, "Colour")
SIZE = 512
BAND = 28  # cross-fade half width at the source size (1254 px), as derive_env_textures.py
WIDE_BAND = {"wood": 220, "lacquer": 220, "metal": 220}

# surface, rotate (deg), seam fix: the same values as derive_env_textures.py's SPECS.
SPECS = [
    ("wood", 90, True),
    ("parquet", 90, False),
    ("plaster", 0, True),
    ("upholstery", 0, True),
    ("linen", 0, True),
    ("carpet", 0, True),
    ("grass", 0, True),
    ("lacquer", 90, True),
    ("metal", 0, True),
    ("plastic", 0, True),
    ("foliage", 0, True),
    ("soil", 0, True),
    ("tile", 0, False),
]

# The owner's red texture for the player furniture, first match wins (file stems in Assets/Art/Environment or Assets/Art).
PLAYER_SOURCES = ["red*", "player*", "lacquer_red*", "*_red", "*red*"]
PLAYER_RED = (0xD7, 0x26, 0x3D)
# Fallback only: the relative contrast (linear std over the mean) of the lacquer grain on the player red.
PLAYER_GRAIN = 0.10


def luminance(rgb):
    return 0.2126 * rgb[..., 0] + 0.7152 * rgb[..., 1] + 0.0722 * rgb[..., 2]


def best_roll(a, axis):
    """The roll near half the size along an axis that best matches the image with itself (keeps a weave in phase)."""
    n = a.shape[axis]
    best, best_err = n // 2, None
    for s in range(n // 2 - 40, n // 2 + 41):
        err = np.abs(a - np.roll(a, s, axis=axis)).mean()
        if best_err is None or err < best_err:
            best, best_err = s, err
    return best


def fix_seam(rgb, axis, band):
    """Cross-fades the wrap edge along one axis with a rolled copy (roll found on the luminance), every channel alike."""
    n = rgb.shape[axis]
    roll = best_roll(luminance(rgb), axis)
    rolled = np.roll(rgb, roll, axis=axis)
    d = np.minimum(np.arange(n), n - 1 - np.arange(n)).astype(np.float64)
    t = np.clip(d / band, 0.0, 1.0)
    w = t * t * (3.0 - 2.0 * t)  # 0 on the edge (all rolled copy), 1 beyond the band (all original)
    w = w[:, None, None] if axis == 0 else w[None, :, None]
    return w * rgb + (1.0 - w) * rolled


def resize_wrapped(a, size):
    """Resizes one seamless channel without a border seam: tile it 3 x 3, resize, keep the centre."""
    big = np.tile(a, (3, 3))
    im = Image.fromarray(big.astype(np.float32), mode="F").resize((3 * size, 3 * size), Image.LANCZOS)
    r = np.asarray(im, dtype=np.float64)
    return r[size:2 * size, size:2 * size]


def prepare(path, rotate, seam, band):
    rgb = np.asarray(Image.open(path).convert("RGB"), dtype=np.float64) / 255.0
    if seam:
        rgb = fix_seam(fix_seam(rgb, 1, band), 0, BAND)
    if rotate:
        rgb = np.rot90(rgb, k=rotate // 90, axes=(0, 1))
    out = np.stack([resize_wrapped(rgb[..., c], SIZE) for c in range(3)], axis=-1)
    return np.clip(out, 0.0, 1.0)


def save_rgb(a, path):
    Image.fromarray(np.clip(np.round(a * 255.0), 0, 255).astype(np.uint8), mode="RGB").save(path, optimize=True)


def edge_step(a):
    """Mean colour jump across the wrap edges over the mean jump between neighbours (1 = invisible seam)."""
    inner = 0.5 * (np.abs(np.diff(a, axis=0)).mean() + np.abs(np.diff(a, axis=1)).mean())
    edge = 0.5 * (np.abs(a[0] - a[-1]).mean() + np.abs(a[:, 0] - a[:, -1]).mean())
    return edge / max(inner, 1e-9)


def player_source():
    for folder in (SRC, os.path.join(ROOT, "Assets", "Art")):
        for pattern in PLAYER_SOURCES:
            hits = sorted(p for p in glob.glob(os.path.join(folder, pattern + ".png")) if os.path.isfile(p))
            if hits:
                return hits[0]
    return None


def srgb_to_linear(c):
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def linear_to_srgb(c):
    c = np.clip(c, 0.0, 1.0)
    return np.where(c <= 0.0031308, c * 12.92, 1.055 * np.power(c, 1.0 / 2.4) - 0.055)


def derive_player(report):
    source = player_source()
    if source is not None:
        rgb = prepare(source, 0, True, BAND)
        save_rgb(rgb, os.path.join(OUT, "colour_player.png"))
        report.append({"surface": "player", "source": os.path.relpath(source, ROOT).replace("\\", "/"),
                       "mean": [round(float(x), 4) for x in rgb.reshape(-1, 3).mean(0)], "edgeStep": round(edge_step(rgb), 3),
                       "normal": None})
        return
    # Fallback: the lacquer grain (its detail, in phase with normal_lacquer.png) over the player red.
    d = np.asarray(Image.open(os.path.join(DETAIL, "detail_lacquer.png")).convert("L"), dtype=np.float64) / 255.0
    z = (d - d.mean()) / max(d.std(), 1e-6)
    red = srgb_to_linear(np.array(PLAYER_RED, dtype=np.float64) / 255.0)
    lin = red[None, None, :] * (1.0 + PLAYER_GRAIN * z)[..., None]
    rgb = linear_to_srgb(lin)
    save_rgb(rgb, os.path.join(OUT, "colour_player.png"))
    report.append({"surface": "player", "source": "Detail/detail_lacquer.png over #D7263D (no red image in the folder)",
                   "mean": [round(float(x), 4) for x in rgb.reshape(-1, 3).mean(0)], "edgeStep": round(edge_step(rgb), 3),
                   "normal": None})


def main():
    os.makedirs(OUT, exist_ok=True)
    report = []
    for name, rotate, seam in SPECS:
        path = os.path.join(SRC, name + ".png")
        if not os.path.exists(path):
            print(f"missing {path}: {name} skipped")
            continue
        rgb = prepare(path, rotate, seam, WIDE_BAND.get(name, BAND))
        save_rgb(rgb, os.path.join(OUT, f"colour_{name}.png"))
        report.append({"surface": name, "mean": [round(float(x), 4) for x in rgb.reshape(-1, 3).mean(0)],
                       "std": [round(float(x), 4) for x in rgb.reshape(-1, 3).std(0)], "edgeStep": round(edge_step(rgb), 3)})
    derive_player(report)
    for r in report:
        print(json.dumps(r))
    with open(os.path.join(HERE, "derive_env_colour_stats.json"), "w", encoding="utf-8") as f:
        json.dump(report, f, indent=1)


if __name__ == "__main__":
    main()
