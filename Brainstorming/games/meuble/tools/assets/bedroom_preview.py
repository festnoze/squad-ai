"""A tiny numpy z-buffer rasterizer for the procedural handoff models (room_dressing.Model): flat shaded, back faces
culled exactly as Unity's wall shader culls them (two sided materials excepted), COLOR_0 tints, atlas texels per pixel.
Used by bedroom_handoff.py to write Build/bedroom/preview/*.png without opening Unity."""

import math

import numpy as np
from PIL import Image, ImageDraw

LIGHT = np.array((0.45, 1.0, 0.65)) / np.linalg.norm((0.45, 1.0, 0.65))
BACKGROUND = (38, 41, 48)


def gather(model):
    tris, cols, uvs, textured, two = [], [], [], [], []
    for material, pieces in model.parts.items():
        _, _, texture, double_sided, _ = model.materials[material]
        for v, _, t, c, f in pieces:
            tris.append(v[f])
            cols.append(np.clip(c[f][:, :, :3], 0, 1) ** (1 / 2.2))
            uvs.append(t[f])
            textured.append(np.full(len(f), texture is not None))
            two.append(np.full(len(f), double_sided))
    return (np.concatenate(tris).astype(float), np.concatenate(cols), np.concatenate(uvs), np.concatenate(textured),
            np.concatenate(two))


def render(model, atlas, yaw=30.0, pitch=32.0, size=(360, 300), floor=True):
    tris, cols, uvs, textured, two = gather(model)
    a, p = math.radians(yaw), math.radians(pitch)
    eye = np.array((math.sin(a) * math.cos(p), math.sin(p), math.cos(a) * math.cos(p)))
    right = np.cross(UPV, eye)
    right /= np.linalg.norm(right)
    up = np.cross(eye, right)
    pts = tris.reshape(-1, 3)
    sx, sy = pts @ right, pts @ up
    w, h = size
    span = max(sx.max() - sx.min(), (sy.max() - sy.min()) * w / h) * 1.18
    scale = w / span
    cx, cy = (sx.max() + sx.min()) / 2, (sy.max() + sy.min()) / 2
    image = np.zeros((h, w, 3))
    image[:] = np.array(BACKGROUND) / 255
    depth = np.full((h, w), -1e9)
    tex = np.asarray(atlas, dtype=float) / 255 if atlas is not None else None
    if floor:
        # A floor grid line at y = 0 (10 cm squares) so the contact reads.
        lo, hi = pts.min(axis=0) - 0.08, pts.max(axis=0) + 0.08
        for x in np.arange(math.floor(lo[0] * 10) / 10, hi[0], 0.1):
            draw_line(image, depth, np.array((x, 0, lo[2])), np.array((x, 0, hi[2])), right, up, eye, cx, cy, scale)
        for z in np.arange(math.floor(lo[2] * 10) / 10, hi[2], 0.1):
            draw_line(image, depth, np.array((lo[0], 0, z)), np.array((hi[0], 0, z)), right, up, eye, cx, cy, scale)
    for i, tri in enumerate(tris):
        normal = np.cross(tri[1] - tri[0], tri[2] - tri[0])
        length = np.linalg.norm(normal)
        if length < 1e-12:
            continue
        normal /= length
        if normal @ eye <= 0:
            if not two[i]:
                continue
            normal = -normal
        px = (tri @ right - cx) * scale + w / 2
        py = h / 2 - (tri @ up - cy) * scale
        pz = tri @ eye
        x0, x1 = int(max(math.floor(px.min()), 0)), int(min(math.ceil(px.max()), w - 1))
        y0, y1 = int(max(math.floor(py.min()), 0)), int(min(math.ceil(py.max()), h - 1))
        if x1 < x0 or y1 < y0:
            continue
        gy, gx = np.mgrid[y0:y1 + 1, x0:x1 + 1] + 0.5
        d = (py[1] - py[2]) * (px[0] - px[2]) + (px[2] - px[1]) * (py[0] - py[2])
        if abs(d) < 1e-9:
            continue
        b0 = ((py[1] - py[2]) * (gx - px[2]) + (px[2] - px[1]) * (gy - py[2])) / d
        b1 = ((py[2] - py[0]) * (gx - px[2]) + (px[0] - px[2]) * (gy - py[2])) / d
        b2 = 1 - b0 - b1
        inside = (b0 >= -1e-4) & (b1 >= -1e-4) & (b2 >= -1e-4)
        z = b0 * pz[0] + b1 * pz[1] + b2 * pz[2]
        region = depth[y0:y1 + 1, x0:x1 + 1]
        mask = inside & (z > region)
        if not mask.any():
            continue
        color = b0[..., None] * cols[i][0] + b1[..., None] * cols[i][1] + b2[..., None] * cols[i][2]
        if textured[i] and tex is not None:
            u = b0 * uvs[i][0][0] + b1 * uvs[i][1][0] + b2 * uvs[i][2][0]
            v = b0 * uvs[i][0][1] + b1 * uvs[i][1][1] + b2 * uvs[i][2][1]
            tx = np.clip((u * tex.shape[1]).astype(int), 0, tex.shape[1] - 1)
            ty = np.clip((v * tex.shape[0]).astype(int), 0, tex.shape[0] - 1)
            color = color * tex[ty, tx]
        shade = 0.42 + 0.68 * max(normal @ LIGHT, 0.0)
        region[mask] = z[mask]
        image[y0:y1 + 1, x0:x1 + 1][mask] = np.clip(color * shade, 0, 1)[mask]
    return Image.fromarray((image * 255).astype(np.uint8))


UPV = np.array((0.0, 1.0, 0.0))


def draw_line(image, depth, a, b, right, up, eye, cx, cy, scale):
    h, w = depth.shape
    for t in np.linspace(0, 1, 200):
        p = a + (b - a) * t
        x = int((p @ right - cx) * scale + w / 2)
        y = int(h / 2 - (p @ up - cy) * scale)
        if 0 <= x < w and 0 <= y < h:
            image[y, x] = (0.24, 0.26, 0.30)


def render_all(models, assets, atlas_path, out_dir):
    out_dir.mkdir(parents=True, exist_ok=True)
    atlas = Image.open(atlas_path).convert("RGB")
    tiles = []
    for model, info in zip(models, assets):
        front = render(model, atlas, 30, 30)
        top = render(model, atlas, 200, 62)
        shot = Image.new("RGB", (720, 300))
        shot.paste(front, (0, 0))
        shot.paste(top, (360, 0))
        shot.save(out_dir / f"{model.name}.png")
        tile = Image.new("RGB", (360, 340), BACKGROUND)
        tile.paste(front, (0, 0))
        label = f"{info['name']}  {info['size_m'][0]:.2f} x {info['size_m'][1]:.2f} x {info['size_m'][2]:.2f} m  {info['triangles']} tris"
        ImageDraw.Draw(tile).text((8, 312), label, fill=(225, 222, 214))
        tiles.append(tile)
    columns = 3
    rows = math.ceil(len(tiles) / columns)
    sheet = Image.new("RGB", (columns * 360, rows * 340), BACKGROUND)
    for i, tile in enumerate(tiles):
        sheet.paste(tile, ((i % columns) * 360, (i // columns) * 340))
    sheet.save(out_dir / "bedroom_set.png")
    print("previews:", out_dir)
