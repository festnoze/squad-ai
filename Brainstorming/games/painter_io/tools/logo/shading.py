"""Glossy paint shading of the Painter.io logo: a numpy port of PIO_ShadeLiquid (Assets/Resources/Shaders/LiquidCommon.hlsl)
with the same key light from the upper left, so the logo is lit like the puddles, threads and pearls of the game.

Table space as in the shader: x to the right, y UP, z toward the viewer. Image arrays have y down, so callers build the
normal as (-dh/dx, +dh/dy_image, 1).
"""
import numpy as np

from sdf import blur

LIGHT = np.array([-0.4504282, 0.6005710, 0.6606281], np.float32)
HALF = np.array([-0.2471578, 0.3295437, 0.9112156], np.float32)   # normalize(L + V), V = (0, 0, 1)


def normalize3(n):
    ln = np.sqrt(np.sum(n * n, axis=-1, keepdims=True))
    return n / np.maximum(ln, 1e-6)


def shade_liquid(albedo_lin, n_table, thickness01, lobes=2, gloss=1.0):
    """PIO_ShadeLiquid. albedo_lin: [..., 3] or a color; n_table: [..., 3]; thickness01: [...]. Returns linear rgb.

    gloss scales the specular terms (1 = the game's value).
    """
    n = normalize3(n_table.astype(np.float32))
    wrap, ambient = 0.25, 0.32
    lam = np.clip((np.sum(n * LIGHT, axis=-1) + wrap) / (1.0 + wrap), 0.0, 1.0)
    lam_flat = (0.6606281 + wrap) / (1.0 + wrap)
    diffuse = (ambient + (1.0 - ambient) * lam) / (ambient + (1.0 - ambient) * lam_flat)

    t = np.clip(thickness01, 0.0, 1.0)
    s = np.clip(t / 0.3, 0.0, 1.0)
    foot = 0.80 + 0.20 * (s * s * (3 - 2 * s))
    s2 = np.clip((t - 0.3) / 0.65, 0.0, 1.0)
    thin = 1.0 + 0.06 * (1.0 - s2 * s2 * (3 - 2 * s2))

    ndh = np.clip(np.sum(n * HALF, axis=-1), 0.0, 1.0)
    spec = np.power(ndh, 130.0) * 1.2

    tilt = np.clip(np.sqrt(n[..., 0] ** 2 + n[..., 1] ** 2), 0.0, 1.0)
    tilt_deg = np.degrees(np.arcsin(tilt))
    azimuth = (n[..., 0] * -0.6 + n[..., 1] * 0.8) / np.maximum(tilt, 1e-4)
    w = np.clip((azimuth - 0.35) / (0.88 - 0.35), 0.0, 1.0)
    window = w * w * (3 - 2 * w)
    s1 = (tilt_deg - 19.0) / 5.0
    spec = spec + window * 0.85 * np.exp(-s1 * s1)

    broad = np.maximum(0.0, np.power(ndh, 12.0) - 0.32768) * 0.25 if lobes > 1 else 0.0
    rim = np.power(1.0 - np.clip(n[..., 2], 0.0, 1.0), 3.0) * 0.10

    albedo = np.broadcast_to(np.asarray(albedo_lin, np.float32), n.shape)
    color = albedo * (diffuse * foot * thin)[..., None]
    color = color + ((spec + broad) * gloss)[..., None]
    color = color + rim[..., None] * (albedo * 0.65 + 0.35)
    return color.astype(np.float32)


def normal_from_height(hgt, scale=1.0):
    """Table-space normal of a height field given in pixels of the array (y down in the array, y up in table space)."""
    gy, gx = np.gradient(hgt * scale)
    n = np.stack([-gx, gy, np.ones_like(hgt)], axis=-1)
    return n.astype(np.float32)


def letter_height(g, bevel_em=0.058, dome_em=0.05):
    """Height field of the letters in working pixels: a meniscus bevel (quarter circle, steep at the edge) plus a soft
    dome that makes the thick parts bulge like a drop."""
    d = np.maximum(-g.sdf_letters, 0.0)
    b = bevel_em * g.em
    t = np.clip(d / b, 0.0, 1.0)
    bevel = b * 0.95 * np.sqrt(1.0 - (1.0 - t) ** 2)
    dome = blur(g.cov_letters, dome_em * g.em)
    hgt = bevel + dome * b * 0.9
    return blur(hgt, 0.9 * g.ss), b * 1.85
