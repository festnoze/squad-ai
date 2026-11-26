"""Composes Assets/Art/Characters/Resources/DogFur.png (the black Labrador) on the Husky's UV0 atlas (make_husky.py v2).

Sources (never modified): Assets/Art/Characters/labrador_black_fur_albedo.png (strands top to bottom) and
labrador_black_face_front.png (front face, transparent outside the head).
- Fur tiled at TILE px per 1024 source px: about 3 cm strands on the 1.5x dog.
- Strand direction per region: the flank (side region, snout to the right) takes the fur ROTATED 90 deg (strands along
  the body, head to tail) above the belly line and the fur as is (downward) on the legs, blended over a band; the back,
  belly, chest/front legs and rump regions are laid out with "down the image" = head to tail or downward, so they take
  the fur as is.
- The face picture goes into the FACE region over the fur, its silhouette feathered so it melts into the fur, the fur's
  gain matched to the picture's own fur near its edge (no seam where face triangles meet neck triangles).
- v5 (DOGFACE): soft tan brow marks over the eyes, a mouth line along the mesh's lip cut (husky_uv.json 'mouth_line'),
  and the mouth's inside (dark palate to pink tongue) in the MOUTH region the open jaw's strips map to.
Prints the dog's area-weighted mean colour and its CIE76 distance to every floor of the shipped dog levels.
"""
import json, math, os, sys
from PIL import Image, ImageFilter, ImageChops
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ART = r'C:\Dev\squad-ai\Brainstorming\games\out_of_sight\Assets\Art\Characters'
OUT = os.path.join(ART, 'Resources', 'DogFur.png')
S = 2048
TILE = 512  # v3: 512 (was 256): strand clumps about 6 cm on the dog, wide enough to survive the mipmaps at game distance

uv = json.load(open(os.path.join(HERE, 'husky_uv.json')))
REG = uv['regions']
K, U0, U1, F0, F1, R = uv['K'], uv['U0'], uv['U1'], uv['F0'], uv['F1'], uv['R']
FACE = uv['face_size']

fur_src = Image.open(os.path.join(ART, 'labrador_black_fur_albedo.png')).convert('RGB')
face_src = Image.open(os.path.join(ART, 'labrador_black_face_front.png')).convert('RGBA')

# v3 (product owner, 2026-11-21: "the fur is not visible"): the strands of the source are within a few levels of its
# black, so they average out to flat black on screen. The tile's fine detail (the source minus its 3 px blur) is boosted
# DETAIL times, then both the fur and the face picture are lifted by the same gamma LIFT (darks up, blacks stay black),
# so the strands show as highlights and the coat keeps a sheen, still a black dog.
DETAIL = 2.3
LIFT = 0.78
_fur_small = fur_src.resize((TILE, TILE), Image.LANCZOS)
_fs = np.asarray(_fur_small, dtype=np.float32)
_fb = np.asarray(_fur_small.filter(ImageFilter.GaussianBlur(5)), dtype=np.float32)
fur_tile = np.clip(_fb + DETAIL * (_fs - _fb), 0, 255)
fur_tile = 255.0 * (fur_tile / 255.0) ** LIFT
fur_down = np.tile(fur_tile, (S // TILE, S // TILE, 1))               # strands top to bottom (as given)
fur_along = np.tile(np.rot90(fur_tile, 1), (S // TILE, S // TILE, 1))  # strands left to right (rotated copy)

# Gain: the fur's mean against the face picture's own fur in a ring inside its silhouette edge.
face_src = Image.merge('RGBA', [Image.fromarray(np.clip(255.0 * (np.asarray(c, dtype=np.float32) / 255.0) ** LIFT, 0, 255).astype(np.uint8)) for c in face_src.split()[:3]] + [face_src.getchannel('A')])
fa = np.asarray(face_src, dtype=np.float32)
alpha = fa[..., 3] / 255.0
solid = alpha > 0.95
inner = np.asarray(Image.fromarray((solid * 255).astype(np.uint8)).filter(ImageFilter.MinFilter(61))) > 127
ring = solid & ~inner
ring_mean = fa[..., :3][ring].mean(axis=0)
fur_mean = fur_tile.reshape(-1, 3).mean(axis=0)
gain = ring_mean / np.maximum(fur_mean, 1.0)
print('face ring mean', ring_mean.round(1), 'fur mean', fur_mean.round(1), 'gain', gain.round(3))

canvas = fur_down * gain

# Flank: along the body above the belly line, downward on the legs.
ox, oy = REG['side']
x0, y0 = int(ox * S), int(oy * S)
w, h = int(round((F1 - F0) * K * S)), int(round((U1 - U0) * K * S))
ys = np.arange(y0, y0 + h)
u = U1 - (ys / S - oy) / K
t = np.clip((0.0135 - u) / (0.0135 - 0.0105), 0.0, 1.0)
leg = (t * t * (3 - 2 * t))[:, None, None]
canvas[y0:y0 + h, x0:x0 + w] = (fur_along[y0:y0 + h, x0:x0 + w] * (1 - leg) + fur_down[y0:y0 + h, x0:x0 + w] * leg) * gain

# Face: the picture over the fur, its silhouette feathered.
fx, fy = int(REG['face'][0] * S), int(REG['face'][1] * S)
fs = int(round(FACE * S))
face = face_src.resize((fs, fs), Image.LANCZOS)
a = face.getchannel('A').filter(ImageFilter.MinFilter(9)).filter(ImageFilter.GaussianBlur(9))
fa2 = np.asarray(face.convert('RGB'), dtype=np.float32)
a2 = (np.asarray(a, dtype=np.float32) / 255.0)[..., None]
canvas[fy:fy + fs, fx:fx + fs] = fa2 * a2 + canvas[fy:fy + fs, fx:fx + fs] * (1 - a2)

# ----- v5 (DOGFACE, 2026-11-22): the face reads on the black dog, the open mouth shows its inside -----
from PIL import ImageDraw


def paint(mask_img, colour, strength):
    """Blends colour into the canvas through a soft greyscale mask (0..255) at the given peak strength."""
    m = (np.asarray(mask_img, dtype=np.float32) / 255.0 * strength)[..., None]
    canvas[:] = canvas * (1 - m) + np.array(colour, dtype=np.float32) * m


def face_px(x, y):
    """A point of the 1024 face picture in atlas pixels."""
    return fx + x * fs / 1024.0, fy + y * fs / 1024.0


# Brows: a soft warm tan mark over each eye (inner end higher, a Labrador's soft "worried" brow), lighter than the coat
# but not a tan-pointed dog's: BROW_COLOUR at BROW_STRENGTH, feathered.
BROW_COLOUR = (140, 112, 90)
BROW_STRENGTH = 0.5
brow = Image.new('L', (S, S), 0)
bd = ImageDraw.Draw(brow)
for cx, tilt in ((372.0, -1.0), (668.0, 1.0)):
    pts = []
    for i in range(25):
        a = math.pi * 2 * i / 24
        x, y = 62.0 * math.cos(a), 20.0 * math.sin(a)
        ang = math.radians(14.0) * tilt
        pts.append(face_px(cx + x * math.cos(ang) - y * math.sin(ang), 316.0 + x * math.sin(ang) + y * math.cos(ang)))
    bd.polygon(pts, fill=255)
paint(brow.filter(ImageFilter.GaussianBlur(9)), BROW_COLOUR, BROW_STRENGTH)

# The mouth line: drawn along the mesh's own cut (make_husky.py v5 'mouth_line', the upper lip's face UVs), a muted rose
# core with a lighter grey lip edge just above it, so the shut mouth shows as a line on the black muzzle.
segs = uv.get('mouth_line') or []
if segs:
    edge = Image.new('L', (S, S), 0)
    core = Image.new('L', (S, S), 0)
    ed, cd = ImageDraw.Draw(edge), ImageDraw.Draw(core)
    for seg in segs:
        a, b = seg[0], seg[1]
        pa, pb = (a[0] * S, a[1] * S), (b[0] * S, b[1] * S)
        if abs(pb[1] - pa[1]) > abs(pb[0] - pa[0]):
            # A steep segment: the muzzle's sides, where the front projection folds the face UVs over themselves (the
            # picture's rows zigzag); a line painted there smears over the folded triangles. Only the front's part is drawn.
            continue
        if len(seg) > 2 and seg[2] < 0.9:
            continue  # toward the corners the side's squeezed UVs stretch the line into a pink smear (runtime shot, run 3)
        if not (fx <= pa[0] <= fx + fs and fx <= pb[0] <= fx + fs):
            continue  # only the face region's part of the line
        ed.line([(pa[0], pa[1] - 7), (pb[0], pb[1] - 7)], fill=255, width=7)
        cd.line([pa, pb], fill=255, width=11)
    paint(edge.filter(ImageFilter.GaussianBlur(3)), (140, 134, 128), 0.6)
    paint(core.filter(ImageFilter.GaussianBlur(2)), (130, 72, 80), 0.95)

# The mouth's inside (the strips the jaw opens, make_husky.py v5 'mouth_region'): s across = left corner, front, right
# corner; v down = the upper lip (dark palate) to the lower lip (the tongue's pink, widest at the front), with a bleed
# margin for the mipmaps.
mr = uv.get('mouth_region')
if mr:
    mx, my, mw, mh = [c * S for c in mr]
    pad = 16
    xs = np.arange(int(mx) - pad, int(mx + mw) + pad)
    ys = np.arange(int(my) - pad, int(my + mh) + pad)
    s = np.clip((xs - mx) / mw, 0, 1)[None, :]
    v = np.clip((ys - my) / mh, 0, 1)[:, None]
    palate = np.array([58, 18, 26], dtype=np.float32)
    throat = np.array([118, 36, 50], dtype=np.float32)
    tongue = np.array([232, 122, 138], dtype=np.float32)
    front = np.exp(-((s - 0.5) / 0.28) ** 2)             # 1 at the front, 0 toward the corners
    tv = np.clip((v - 0.30) / 0.40, 0, 1) * front          # the tongue rises from the lower lip at the front
    dv = np.clip(v / 0.5, 0, 1)
    col = palate * (1 - dv)[..., None] + throat * dv[..., None]
    col = col * (1 - tv)[..., None] + tongue * tv[..., None]
    col = col * (0.55 + 0.45 * front)[..., None] ** 0.5    # the corners in shadow
    groove = np.exp(-((s - 0.5) / 0.012) ** 2) * tv         # the tongue's middle groove
    col = col * (1 - 0.25 * groove)[..., None]
    canvas[ys[0]:ys[-1] + 1, xs[0]:xs[-1] + 1] = col

img = Image.fromarray(np.clip(canvas, 0, 255).astype(np.uint8), 'RGB')
os.makedirs(os.path.dirname(OUT), exist_ok=True)
img.save(OUT)
print('wrote', OUT, img.size)

# Preview with the UV wireframe (scratchpad only).
prev = img.copy().convert('RGB')
from PIL import ImageDraw
d = ImageDraw.Draw(prev)
col = {'face': (250, 250, 120), 'side': (230, 180, 90), 'top': (120, 200, 230), 'bottom': (200, 130, 220), 'front': (140, 220, 120), 'back': (240, 120, 120)}
for tri, area, g in uv['triangles']:
    d.polygon([(p[0] * S, p[1] * S) for p in tri], outline=col[g])
prev.save(os.path.join(HERE, 'dogfur_preview.png'))
prev.crop((fx, fy, fx + fs, fy + fs)).save(os.path.join(HERE, 'dogfur_face_preview.png'))

# The dog's mean colour: every triangle sampled at 7 barycentric points, weighted by its bind pose area, averaged in
# linear light (what the eye integrates), back to sRGB.
arr = np.asarray(img, dtype=np.float32) / 255.0
lin = np.where(arr <= 0.04045, arr / 12.92, ((arr + 0.055) / 1.055) ** 2.4)
bary = [(1 / 3, 1 / 3, 1 / 3), (0.6, 0.2, 0.2), (0.2, 0.6, 0.2), (0.2, 0.2, 0.6), (0.5, 0.5, 0), (0, 0.5, 0.5), (0.5, 0, 0.5)]
acc = np.zeros(3)
wsum = 0.0
for tri, area, g in uv['triangles']:
    for b in bary:
        px = sum(b[i] * tri[i][0] for i in range(3)) * S
        py = sum(b[i] * tri[i][1] for i in range(3)) * S
        acc += lin[min(int(py), S - 1), min(int(px), S - 1)] * area
        wsum += area
m_lin = acc / wsum
m = np.where(m_lin <= 0.0031308, m_lin * 12.92, 1.055 * m_lin ** (1 / 2.4) - 0.055)
hexc = '#%02X%02X%02X' % tuple(int(round(c * 255)) for c in m)
print('dog mean colour (area weighted, linear average)', hexc, (m * 255).round(1))
plain = arr.reshape(-1, 3).mean(axis=0)
print('atlas plain pixel mean (sRGB)', '#%02X%02X%02X' % tuple(int(round(c * 255)) for c in plain))
json.dump({'mean_hex': hexc}, open(os.path.join(HERE, 'dogfur_mean.json'), 'w'))
