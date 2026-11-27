"""Measures the actors acceptance numbers on DevShot CutDroplets images.

For each biome directory: parses the [CameraRig] checkpoint CutDroplets line of p.log (view size, center, human, front),
then counts pixels with luma >= 235 (Rec. 601) within 1.5 u of the front and of the human pearl, and measures the
white chevron bounding box near the human pearl. Also writes zoomed crops for visual review.
"""
import re
import sys
import os
import numpy as np
from PIL import Image

RADIUS_U = 1.5


def parse(log_path):
    text = open(log_path, encoding="utf-8", errors="replace").read()
    m = re.search(r"checkpoint CutDroplets .*?view=([\d.]+)x([\d.]+) center=\(([-\d.]+),([-\d.]+)\) human=\(([-\d.]+),([-\d.]+)\).*?front=\(([-\d.]+),([-\d.]+)\)", text)
    if not m:
        return None
    v = [float(x) for x in m.groups()]
    return dict(vw=v[0], vh=v[1], cx=v[2], cy=v[3], hx=v[4], hy=v[5], fx=v[6], fy=v[7])


def to_px(info, w, h, x, y):
    ppu = w / info["vw"]
    return (w / 2 + (x - info["cx"]) * ppu, h / 2 - (y - info["cy"]) * ppu, ppu)


def main(root, biome, tag, outdir):
    d = os.path.join(root)
    info = parse(os.path.join(d, "p.log"))
    img = np.asarray(Image.open(os.path.join(d, biome + "_CutDroplets.png")).convert("RGB")).astype(np.float32)
    h, w, _ = img.shape
    luma = 0.299 * img[..., 0] + 0.587 * img[..., 1] + 0.114 * img[..., 2]
    fx, fy, ppu = to_px(info, w, h, info["fx"], info["fy"])
    hx, hy, _ = to_px(info, w, h, info["hx"], info["hy"])
    yy, xx = np.mgrid[0:h, 0:w]
    r = RADIUS_U * ppu
    near_f = (xx - fx) ** 2 + (yy - fy) ** 2 <= r * r
    near_h = (xx - hx) ** 2 + (yy - hy) ** 2 <= r * r
    bright = luma >= 235
    nf = int((bright & near_f).sum())
    nh = int((bright & near_h).sum())
    ratio = nf / nh if nh > 0 else float("inf")
    # Chevron: near-white pixels (all channels >= 200 and low saturation) within 2.6 u of the pearl center but outside
    # the pearl (radius 0.6 u covers the pearl and its highlight).
    mn = img.min(axis=2)
    mx = img.max(axis=2)
    white = (mn >= 200) & ((mx - mn) <= 40)
    dist2 = (xx - hx) ** 2 + (yy - hy) ** 2
    ring = (dist2 <= (2.6 * ppu) ** 2) & (dist2 >= (0.6 * ppu) ** 2)
    sel = white & ring
    if sel.any():
        ys, xs = np.nonzero(sel)
        bbox = (int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max()))
        cw, ch = bbox[2] - bbox[0] + 1, bbox[3] - bbox[1] + 1
    else:
        bbox, cw, ch = None, 0, 0
    print(f"{tag} {biome}: ppu={ppu:.2f} front=({fx:.0f},{fy:.0f}) human=({hx:.0f},{hy:.0f}) bright_front={nf} bright_pearl={nh} ratio={ratio:.2f} chevron_bbox={bbox} chevron={cw}x{ch}px white_px={int(sel.sum())}")
    if outdir:
        os.makedirs(outdir, exist_ok=True)
        im = Image.open(os.path.join(d, biome + "_CutDroplets.png")).convert("RGB")
        x0 = int(min(fx, hx) - 2.2 * ppu)
        x1 = int(max(fx, hx) + 2.2 * ppu)
        y0 = int(min(fy, hy) - 2.2 * ppu)
        y1 = int(max(fy, hy) + 2.2 * ppu)
        crop = im.crop((max(0, x0), max(0, y0), min(w, x1), min(h, y1)))
        crop = crop.resize((crop.width * 3, crop.height * 3), Image.NEAREST)
        crop.save(os.path.join(outdir, f"{tag}_{biome}_crop.png"))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4] if len(sys.argv) > 4 else None)
