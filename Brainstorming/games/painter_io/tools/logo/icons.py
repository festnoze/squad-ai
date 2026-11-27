"""App icons of Painter.io from the square mark (the coral pearl and its teal thread loop) on the menu navy.

Outputs (Assets/Art/Icon/):
- icon_<n>.png for n in 16, 32, 48, 64, 128, 256, 512, 1024: navy rounded square with the mark (Windows player icon,
  default icon);
- android_adaptive_fg.png and android_adaptive_bg.png (432 x 432, xxxhdpi of the 108 dp adaptive layers; the mark sits
  inside the central 66 dp safe circle, the background is a full-bleed navy);
- android_legacy.png (192 x 192 rounded square) and android_round.png (192 x 192 circle).
Small sizes are rendered directly at their size (4x supersampled) with a minimum thread width, not downscaled.
"""
from pathlib import Path

import numpy as np

from geometry import MarkGeometry, ROOT
from make_logo import drop_shadow, finish, pearl_color, shade_paint_layer, thread_normal, SHADOW_NAVY
from sdf import blur, coverage, hex_rgb, over, premul, shift, smoothstep, srgb_to_linear

OUT_ICON = ROOT / 'Assets' / 'Art' / 'Icon'
CORAL, TEAL = '#F2674F', '#22C4B6'
NAVY_TOP, NAVY_BOTTOM = '#2B3B6B', '#18213F'

# Center of the mark's ink in mark-box units (pearl and loop), used to center it optically.
MARK_INK_CENTER = (0.51, 0.515)


def rounded_square_sdf(w, margin, radius):
    yy, xx = np.mgrid[0:w, 0:w].astype(np.float32) + 0.5
    c = w * 0.5
    half = c - margin
    qx = np.abs(xx - c) - (half - radius)
    qy = np.abs(yy - c) - (half - radius)
    outside = np.sqrt(np.maximum(qx, 0) ** 2 + np.maximum(qy, 0) ** 2)
    return outside + np.minimum(np.maximum(qx, qy), 0.0) - radius


def circle_sdf(w, margin):
    yy, xx = np.mgrid[0:w, 0:w].astype(np.float32) + 0.5
    c = w * 0.5
    return np.sqrt((xx - c) ** 2 + (yy - c) ** 2) - (c - margin)


def background(w, sdf, ss):
    """Navy tile: a soft diagonal gradient from the upper left, a thin light rim on top and a darker one below."""
    yy, xx = np.mgrid[0:w, 0:w].astype(np.float32)
    t = np.clip((xx * 0.35 + yy) / (w * 1.35), 0.0, 1.0)[..., None]
    top, bottom = srgb_to_linear(hex_rgb(NAVY_TOP)), srgb_to_linear(hex_rgb(NAVY_BOTTOM))
    col = top * (1 - t) + bottom * t
    inner = np.clip(-sdf / (0.035 * w), 0.0, 1.0)
    rim = (1.0 - smoothstep(0.0, 1.0, inner))
    lightness = np.clip((w * 0.55 - yy) / (w * 0.55), 0.0, 1.0)
    col = col * (1.0 + 0.35 * rim * lightness)[..., None] * (1.0 - 0.25 * rim * (1 - lightness))[..., None]
    return premul(col, coverage(sdf, ss * 1.0))


def mark_layers(g):
    """Premultiplied linear layers of the mark on a transparent ground: shadow, thread, pearl."""
    img = np.zeros((g.H, g.W, 4), np.float32)
    sh = drop_shadow(g, g.sdf_all, offset_em=(0.018, 0.032), sigma_em=0.028, strength=0.6, contact=0.35)
    img = over(img, premul(srgb_to_linear(hex_rgb(SHADOW_NAVY)), sh))
    n, thick = thread_normal(g)
    col = shade_paint_layer(TEAL, n, thick * 0.8 + 0.2)
    occl = blur(shift(coverage(g.sdf_pearl), int(0.012 * g.em), int(0.022 * g.em)), 0.02 * g.em)
    col = col * (1.0 - 0.55 * occl)[..., None]
    img = over(img, premul(col, coverage(g.sdf_thread)))
    img = over(img, premul(pearl_color(g, CORAL), coverage(g.sdf_pearl)))
    return img


def mark_geometry(size, ss, box_frac, min_thread_px):
    cx = 0.5 + (0.5 - MARK_INK_CENTER[0]) * box_frac
    cy = 0.5 + (0.5 - MARK_INK_CENTER[1]) * box_frac
    return MarkGeometry(size, ss, box_frac=box_frac, center=(cx, cy), min_thread_px=min_thread_px)


def tile_icon(size, shape='square'):
    ss = 4 if size <= 64 else 2
    w = size * ss
    if shape == 'circle':
        sdf = circle_sdf(w, 0.02 * w)
        box = 0.80
    else:
        sdf = rounded_square_sdf(w, 0.02 * w, 0.20 * w)
        box = 0.86
    min_thread = 1.1 if size <= 32 else 0.0
    g = mark_geometry(size, ss, box, min_thread)
    img = background(w, sdf, ss)
    img = over(img, mark_layers(g) * coverage(sdf, ss)[..., None])
    return finish(img, ss)


def adaptive_layers(size=432):
    ss = 2
    w = size * ss
    # Foreground: the mark inside the 66 / 108 safe circle (its farthest point, the pearl's rim, is 0.45 mark boxes
    # from the ink center, so a box of 0.66 keeps it at 0.297 < 0.306 of the canvas), transparent elsewhere.
    g = mark_geometry(size, ss, 0.66, 0.0)
    fg = finish(mark_layers(g), ss)
    # Background: full-bleed navy gradient (the launcher applies its own mask).
    full = np.full((w, w), -1e4, np.float32)
    bg = finish(background(w, full, ss), ss)
    return fg, bg


def make_icons(out_dir=OUT_ICON, preview_dir=None):
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for size in (16, 32, 48, 64, 128, 256, 512, 1024):
        img = tile_icon(size)
        p = out_dir / ('icon_%d.png' % size)
        img.save(p, optimize=True)
        written.append(p)
    tile_icon(192).save(out_dir / 'android_legacy.png', optimize=True)
    tile_icon(192, 'circle').save(out_dir / 'android_round.png', optimize=True)
    fg, bg = adaptive_layers()
    fg.save(out_dir / 'android_adaptive_fg.png', optimize=True)
    bg.save(out_dir / 'android_adaptive_bg.png', optimize=True)
    written += [out_dir / n for n in ('android_legacy.png', 'android_round.png', 'android_adaptive_fg.png',
                                      'android_adaptive_bg.png')]
    for p in written:
        print('wrote', p)
    if preview_dir:
        preview_sheet(out_dir, Path(preview_dir))
    return written


def preview_sheet(icon_dir, preview_dir):
    """Contact sheet: every icon at 1:1 on a light and a dark wallpaper, plus the adaptive layers under three launcher
    masks (circle, squircle, rounded square) at 108 dp scale."""
    from PIL import Image, ImageDraw
    preview_dir.mkdir(parents=True, exist_ok=True)
    sheet = Image.new('RGB', (1500, 760), (236, 238, 242))
    dark = Image.new('RGB', (1500, 380), (40, 44, 52))
    sheet.paste(dark, (0, 380))
    x = 20
    for size in (16, 32, 48, 64, 128, 256):
        ic = Image.open(icon_dir / ('icon_%d.png' % size))
        for y0 in (20, 400):
            sheet.paste(ic, (x, y0 + (256 - size) // 2), ic)
        x += size + 30
    fg = Image.open(icon_dir / 'android_adaptive_fg.png')
    bg = Image.open(icon_dir / 'android_adaptive_bg.png')
    comp = bg.copy()
    comp.alpha_composite(fg)
    # Launchers show the central 72 of 108 dp.
    cut = int(432 * 18 / 108)
    view = comp.crop((cut, cut, 432 - cut, 432 - cut)).resize((192, 192), Image.LANCZOS)
    masks = []
    for kind in ('circle', 'squircle', 'rounded'):
        m = Image.new('L', (192, 192), 0)
        d = ImageDraw.Draw(m)
        if kind == 'circle':
            d.ellipse((0, 0, 191, 191), fill=255)
        elif kind == 'squircle':
            d.rounded_rectangle((0, 0, 191, 191), radius=70, fill=255)
        else:
            d.rounded_rectangle((0, 0, 191, 191), radius=30, fill=255)
        masks.append(m)
    for i, m in enumerate(masks):
        tile = Image.new('RGBA', (192, 192), (0, 0, 0, 0))
        tile.paste(view, (0, 0), m)
        sheet.paste(tile, (760 + i * 240, 60), tile)
        sheet.paste(tile, (760 + i * 240, 440), tile)
    leg = Image.open(icon_dir / 'android_legacy.png')
    rnd = Image.open(icon_dir / 'android_round.png')
    sheet.save(preview_dir / 'icons_sheet.png')
    big = Image.new('RGB', (1024 + 432 + 60, 1024), (236, 238, 242))
    ic = Image.open(icon_dir / 'icon_1024.png')
    big.paste(ic, (0, 0), ic)
    big.paste(comp, (1024 + 30, 0), comp)
    big.paste(leg, (1024 + 30, 480), leg)
    big.paste(rnd, (1024 + 30 + 220, 480), rnd)
    big.save(preview_dir / 'icons_big.png')
