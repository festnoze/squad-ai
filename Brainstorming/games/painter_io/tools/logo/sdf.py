"""Signed distance fields, blurs and small image helpers for the Painter.io logo generator (numpy only).

Conventions: arrays are float32, indexed [y, x] with y pointing down. Distances are in pixels of the array they come
from. A signed distance is negative inside a shape and positive outside it.
"""
import numpy as np


def edt(mask, reach):
    """Exact Euclidean distance from every pixel to the nearest True pixel of mask, capped at reach (+1).

    Separable: the row pass is exact at any range (nearest True on the left and on the right through cumulative
    maxima); the column pass takes the minimum of g(y + j)^2 + j^2 over |j| <= reach, so the result is exact for every
    distance up to reach.
    """
    h, w = mask.shape
    big = np.float32(reach + 1)
    xs = np.arange(w, dtype=np.float32)[None, :]
    left = np.where(mask, xs, np.float32(-1e9))
    left = np.maximum.accumulate(left, axis=1)
    g = xs - left
    right = np.where(mask, xs, np.float32(1e9))
    right = np.minimum.accumulate(right[:, ::-1], axis=1)[:, ::-1]
    g = np.minimum(g, right - xs)
    g = np.minimum(g, big)
    g2 = g * g
    d2 = g2.copy()
    for j in range(1, reach + 1):
        jj = np.float32(j * j)
        np.minimum(d2[j:], g2[:-j] + jj, out=d2[j:])
        np.minimum(d2[:-j], g2[j:] + jj, out=d2[:-j])
    return np.minimum(np.sqrt(d2), big)


def sdf_from_coverage(cov, reach):
    """Signed distance of an antialiased coverage image (0..1), sub-pixel accurate near the edge."""
    inside = cov >= 0.5
    d_out = edt(inside, reach)
    d_in = edt(~inside, reach)
    sdf = np.where(inside, 0.5 - d_in, d_out - 0.5).astype(np.float32)
    # Near the contour the coverage itself is the better estimate (a straight edge through the pixel).
    edge = (cov > 0.0) & (cov < 1.0) & (np.abs(sdf) < 1.0)
    sdf = np.where(edge, 0.5 - cov, sdf).astype(np.float32)
    return sdf


def box_blur_axis(a, r, axis):
    """Box blur of radius r (width 2r+1) along one axis, zero outside, through a cumulative sum."""
    if r <= 0:
        return a
    a = np.moveaxis(a, axis, -1)
    pad = np.zeros(a.shape[:-1] + (r + 1,), np.float32)
    padded = np.concatenate([pad, a, pad[..., :r]], axis=-1)
    c = np.cumsum(padded, axis=-1, dtype=np.float64)
    out = (c[..., 2 * r + 1:] - c[..., :-2 * r - 1]) / (2 * r + 1)
    out = out[..., :a.shape[-1]].astype(np.float32)
    return np.moveaxis(out, -1, axis)


def blur(a, sigma):
    """Gaussian-like blur (three box passes per axis) of a 2D or [y, x, c] array."""
    if sigma <= 0.3:
        return a.astype(np.float32)
    n = 3
    wide = np.sqrt(12.0 * sigma * sigma / n + 1.0)
    r = max(1, int(round((wide - 1.0) / 2.0)))
    out = a.astype(np.float32)
    for _ in range(n):
        out = box_blur_axis(out, r, 0)
        out = box_blur_axis(out, r, 1)
    return out


def shift(a, dx, dy, fill=0.0):
    """Integer shift of a 2D array by (dx, dy) pixels (content moves right and down for positive values)."""
    out = np.full_like(a, fill)
    h, w = a.shape[:2]
    xs0, xs1 = max(0, -dx), min(w, w - dx)
    ys0, ys1 = max(0, -dy), min(h, h - dy)
    out[ys0 + dy:ys1 + dy, xs0 + dx:xs1 + dx] = a[ys0:ys1, xs0:xs1]
    return out


def smoothstep(e0, e1, x):
    t = np.clip((x - e0) / (e1 - e0), 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def coverage(sdf, px=1.0):
    """Antialiased coverage of a signed distance (one pixel wide ramp)."""
    return np.clip(0.5 - sdf / px, 0.0, 1.0).astype(np.float32)


def srgb_to_linear(c):
    c = np.asarray(c, np.float32)
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4).astype(np.float32)


def linear_to_srgb(c):
    c = np.clip(np.asarray(c, np.float32), 0.0, None)
    return np.where(c <= 0.0031308, c * 12.92, 1.055 * np.power(c, 1.0 / 2.4) - 0.055).astype(np.float32)


def hex_rgb(h):
    h = h.lstrip('#')
    return np.array([int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4)], np.float32)


def value_noise(shape, cell, seed, octaves=3):
    """Smooth fBm value noise in [0, 1] (bicubic upsampled random grids), deterministic for a seed."""
    from PIL import Image
    h, w = shape
    rng = np.random.default_rng(seed)
    total = np.zeros(shape, np.float32)
    amp, norm = 1.0, 0.0
    c = float(cell)
    for _ in range(octaves):
        gh, gw = max(2, int(h / c) + 3), max(2, int(w / c) + 3)
        grid = rng.random((gh, gw)).astype(np.float32)
        img = Image.fromarray(grid, 'F').resize((int(gw * c), int(gh * c)), Image.BICUBIC)
        arr = np.asarray(img, np.float32)[:h, :w]
        total += amp * arr
        norm += amp
        amp *= 0.5
        c /= 2.0
    return np.clip(total / norm, 0.0, 1.0)


def over(dst, src):
    """Premultiplied 'over': both are [y, x, 4] arrays with premultiplied rgb and alpha in channel 3."""
    a = src[..., 3:4]
    return src + dst * (1.0 - a)


def premul(rgb, alpha):
    """[y, x, 4] premultiplied layer from straight rgb [y, x, 3] (or a color) and an alpha [y, x]."""
    rgb = np.broadcast_to(np.asarray(rgb, np.float32), alpha.shape + (3,))
    out = np.empty(alpha.shape + (4,), np.float32)
    out[..., :3] = rgb * alpha[..., None]
    out[..., 3] = alpha
    return out


def downsample(img, factor):
    """Box downsample of a premultiplied [y, x, c] image by an integer factor."""
    if factor == 1:
        return img
    h, w = img.shape[:2]
    h2, w2 = h // factor, w // factor
    img = img[:h2 * factor, :w2 * factor]
    return img.reshape(h2, factor, w2, factor, -1).mean(axis=(1, 3))
