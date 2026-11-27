"""Painter.io logo generator: wordmark variants (liquid, fire, electric), the shine mask and the app icons.

Usage (from anywhere; paths are resolved from this file):
    python tools/logo/make_logo.py                 # everything into Assets/
    python tools/logo/make_logo.py --only liquid   # one variant
    python tools/logo/make_logo.py --preview DIR   # also writes previews on the menu navy into DIR

Requires numpy and Pillow only. Deterministic: the same sources give the same PNG files.
"""
import argparse
import sys
from pathlib import Path

import numpy as np
from PIL import Image

sys.dont_write_bytecode = True        # no __pycache__ next to the generator
sys.path.insert(0, str(Path(__file__).resolve().parent))

from geometry import Geometry, ROOT  # noqa: E402
from sdf import (blur, coverage, downsample, hex_rgb, linear_to_srgb, over, premul, shift, smoothstep,  # noqa: E402
                 srgb_to_linear, value_noise)
from shading import letter_height, normal_from_height, shade_liquid  # noqa: E402
from effects import render_electric, render_fire  # noqa: E402

OUT_UI = ROOT / 'Assets' / 'Resources' / 'UI'
WIDTH, HEIGHT, SS = 1600, 640, 2

NAVY = '#1E2A4D'            # the menu background (Palette.Background)
SHADOW_NAVY = '#070B1C'


# ---------------------------------------------------------------------------------------------------------------------
# Shared building blocks


def pearl_normal(g):
    # Sphere normal in the pearl's (stretched) frame, rotated back to the image.
    u, v = g.pearl_u, g.pearl_v
    q2 = np.clip(u * u + v * v, 0.0, 0.9995)
    nz = np.sqrt(1.0 - q2)
    f = g.pearl_fwd
    dx = u * f[0] - v * f[1]
    dy = u * f[1] + v * f[0]
    n = np.stack([dx, -dy, nz * 1.05], axis=-1)
    return n, nz


def thread_normal(g):
    q = np.clip(g.thread_d / g.thread_rad, 0.0, 0.999)
    k = 0.85   # a thread on a table is a slightly flattened tube
    slope = k * q / np.sqrt(1.0 - q * q)
    n = np.stack([g.thread_nx * slope, -g.thread_ny * slope, np.ones_like(q)], axis=-1)
    return n, np.sqrt(1.0 - q * q)


def drop_shadow(g, sdf, offset_em=(0.022, 0.040), sigma_em=0.030, strength=0.62, contact=0.40):
    """Soft lower-right shadow plus a tight contact shadow all around, as one alpha field."""
    cov = coverage(sdf)
    ox, oy = int(round(offset_em[0] * g.em)), int(round(offset_em[1] * g.em))
    soft = blur(shift(cov, ox, oy), sigma_em * g.em) * strength
    tight = blur(shift(cov, int(ox * 0.25), int(oy * 0.25)), 0.008 * g.em) * contact
    return np.clip(np.maximum(soft, tight), 0.0, 1.0)


def finish(img_premul_lin, ss):
    """Working premultiplied linear image -> 8-bit RGBA PIL image (straight alpha, sRGB)."""
    small = downsample(img_premul_lin, ss)
    a = np.clip(small[..., 3], 0.0, 1.0)
    rgb = small[..., :3] / np.maximum(a[..., None], 1e-6)
    rgb = linear_to_srgb(np.clip(rgb, 0.0, 1.0))
    # Fully transparent pixels keep a color close to their neighbors (no dark fringe under bilinear filtering).
    out = np.dstack([rgb, a])
    out = np.clip(np.round(out * 255.0), 0, 255).astype(np.uint8)
    img = Image.fromarray(out, 'RGBA')
    return bleed_transparent(img)


def bleed_transparent(img, passes=24):
    """Fills the rgb of transparent pixels with the average of nearby opaque ones, so filtering never pulls in black."""
    arr = np.asarray(img).astype(np.float32)
    a = arr[..., 3] / 255.0
    rgb = arr[..., :3] * a[..., None]
    w = a.copy()
    known_rgb, known_w = rgb.copy(), w.copy()
    for _ in range(passes):
        known_rgb = blur(known_rgb, 2.0)
        known_w = blur(known_w, 2.0)
    fill = known_rgb / np.maximum(known_w[..., None], 1e-6)
    straight = arr[..., :3]
    out_rgb = np.where(a[..., None] > 0.0, straight, np.clip(fill, 0, 255))
    out = np.dstack([out_rgb, arr[..., 3]])
    return Image.fromarray(np.clip(np.round(out), 0, 255).astype(np.uint8), 'RGBA')


def on_background(img, color):
    """Preview: the RGBA logo composited over a solid color in linear space (as Unity's linear UI does)."""
    arr = np.asarray(img).astype(np.float32) / 255.0
    a = arr[..., 3:4]
    fg = srgb_to_linear(arr[..., :3])
    bg = srgb_to_linear(np.broadcast_to(hex_rgb(color), fg.shape))
    out = linear_to_srgb(fg * a + bg * (1 - a))
    return Image.fromarray(np.clip(np.round(out * 255), 0, 255).astype(np.uint8), 'RGB')


# ---------------------------------------------------------------------------------------------------------------------
# Liquid (primary): glossy coral paint, teal thread

def shade_paint_layer(albedo_srgb, n, thickness, gloss=1.0, absorb=True):
    alb = srgb_to_linear(hex_rgb(albedo_srgb))
    if absorb:
        # F2 depth absorption: a lighter, more translucent rim and a richer thick body.
        expo = 0.86 + 0.30 * np.clip(thickness, 0.0, 1.0)
        alb = np.power(alb[None, None, :], expo[..., None])
    return shade_liquid(alb, n, thickness, lobes=2, gloss=gloss)


def render_liquid(g, coral='#F2674F', teal='#22C4B6'):
    W, H = g.W, g.H
    img = np.zeros((H, W, 4), np.float32)

    # 1. Shadow of everything on the table.
    sh = drop_shadow(g, g.sdf_all)
    img = over(img, premul(srgb_to_linear(hex_rgb(SHADOW_NAVY)), sh))

    # 2. Thread (behind the letters and the pearl), darkened where the front shapes shade it.
    if g.thread_pts is not None:
        n, thick = thread_normal(g)
        col = shade_paint_layer(teal, n, thick * 0.8 + 0.2, gloss=1.0)
        front = coverage(g.sdf_front)
        occl = blur(shift(front, int(0.012 * g.em), int(0.022 * g.em)), 0.016 * g.em)
        col = col * (1.0 - 0.55 * occl)[..., None]
        img = over(img, premul(col, coverage(g.sdf_thread)))

    # 3. Letters.
    hgt, hmax = letter_height(g)
    n = normal_from_height(hgt)
    thick = np.clip(hgt / hmax, 0.0, 1.0)
    col = shade_paint_layer(coral, n, thick)
    col = col + glare(g, g.sdf_letters)[..., None] * 0.55
    img = over(img, premul(col, coverage(g.sdf_letters)))

    # 4. The pearl (pawn head) in front.
    img = over(img, premul(pearl_color(g, coral), coverage(g.sdf_pearl)))
    return img


def glare(g, sdf, offset_em=(0.030, 0.042), inset_em=0.016, soft_em=0.010):
    """Soft gloss crescent along the upper-left inner edge of a shape (the broad softbox reflection of a glossy toy
    logo): inside the shape, outside a copy shifted toward the lower right, away from the very edge."""
    ox, oy = int(round(offset_em[0] * g.em)), int(round(offset_em[1] * g.em))
    inner = smoothstep(inset_em * g.em, inset_em * g.em * 1.8, -sdf)
    moved = shift(sdf, ox, oy, fill=1e4)
    band = inner * smoothstep(-0.004 * g.em, 0.02 * g.em, moved)
    return blur(band, soft_em * g.em) * 0.9


def pearl_color(g, albedo_hex):
    """Glossy pearl: the paint's diffuse (PIO_ShadeLiquid without its streak), a soft window reflection and a hot
    spot on the upper left, a warm bounce from the table on the lower right and the Fresnel rim."""
    n, nz = pearl_normal(g)
    thick = np.clip(nz * 1.4, 0.0, 1.0)
    col = shade_paint_layer(albedo_hex, n, thick, gloss=0.0)
    alb = srgb_to_linear(hex_rgb(albedo_hex))
    # Positions in pearl radii, in the image frame (the pearl's own frame is only used for its teardrop outline).
    px = (g.xx - g.pearl_c[0]) / g.pearl_r
    py = (g.yy - g.pearl_c[1]) / g.pearl_r
    # Window reflection: a soft ellipse tilted along the light, centered up and to the left.
    ang = np.radians(-38.0)
    ex, ey = px + 0.36, py + 0.40
    rx = ex * np.cos(ang) - ey * np.sin(ang)
    ry = ex * np.sin(ang) + ey * np.cos(ang)
    ell = np.sqrt((rx / 0.30) ** 2 + (ry / 0.17) ** 2)
    window = 1.0 - smoothstep(0.55, 1.0, ell)
    # Hot spot and a wide soft sheen.
    spot = np.exp(-((px + 0.30) ** 2 + (py + 0.33) ** 2) / (2 * 0.06 ** 2))
    sheen = np.exp(-((px + 0.25) ** 2 + (py + 0.28) ** 2) / (2 * 0.38 ** 2)) * 0.10
    # Bounce light: a thin crescent inside the lower-right rim.
    r = np.sqrt(px * px + py * py)
    facing = np.clip((px * 0.6 + py * 0.8) / np.maximum(r, 1e-4), 0.0, 1.0)
    bounce = smoothstep(0.70, 0.93, r) * (1.0 - smoothstep(0.93, 1.0, r)) * facing ** 2 * 0.35
    col = col + (window * 0.78 + spot * 0.9 + sheen)[..., None]
    col = col + bounce[..., None] * (alb * 0.8 + 0.2)
    return col.astype(np.float32)


# ---------------------------------------------------------------------------------------------------------------------
# Entry point

VARIANTS = {
    'liquid': render_liquid,
    'fire': render_fire,
    'electric': render_electric,
}


def make_mask(g, out_dir=OUT_UI, factor=2):
    """The shine mask of the menu (logo_mask.png, half size): white letters and pearl, alpha = their coverage. The
    threads, shadows, glows and flames stay out, so the idle shine only crosses the paint itself. The mask is inset by
    0.012 em: uGUI masks are a 1-bit stencil, so its stair-stepped edge must stay inside the letters' own antialiased
    edge."""
    cov = coverage(g.sdf_front + 0.012 * g.em, g.ss * factor)
    small = downsample(cov[..., None], g.ss * factor)[..., 0]
    a = np.clip(np.round(small * 255.0), 0, 255).astype(np.uint8)
    rgba = np.dstack([np.full_like(a, 255)] * 3 + [a])
    path = Path(out_dir) / 'logo_mask.png'
    Image.fromarray(rgba, 'RGBA').save(path, optimize=True)
    print('wrote', path)
    return path


def make_variant(name, preview_dir=None, out_dir=OUT_UI, g=None):
    g = g if g is not None else Geometry(WIDTH, HEIGHT, SS)
    img = finish(VARIANTS[name](g), SS)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / ('logo_%s.png' % name)
    img.save(path, optimize=True)
    print('wrote', path)
    if preview_dir:
        Path(preview_dir).mkdir(parents=True, exist_ok=True)
        on_background(img, NAVY).save(Path(preview_dir) / ('logo_%s_on_navy.png' % name))
        small = img.resize((500, 200), Image.LANCZOS)
        on_background(small, NAVY).save(Path(preview_dir) / ('logo_%s_on_navy_500.png' % name))
    return g, img


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--only', choices=sorted(VARIANTS), default=None)
    ap.add_argument('--preview', default=None)
    ap.add_argument('--out', default=str(OUT_UI))
    ap.add_argument('--icons-out', default=None, help='icon folder (default Assets/Art/Icon)')
    ap.add_argument('--no-icons', action='store_true')
    args = ap.parse_args()
    names = [args.only] if args.only else sorted(VARIANTS)
    g = Geometry(WIDTH, HEIGHT, SS)
    for name in names:
        make_variant(name, args.preview, args.out, g)
    if not args.only:
        make_mask(g, args.out)
    if not args.only and not args.no_icons:
        import icons
        icons.make_icons(args.icons_out or icons.OUT_ICON, args.preview)


if __name__ == '__main__':
    main()
