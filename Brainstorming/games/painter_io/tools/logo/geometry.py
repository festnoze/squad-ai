"""Shapes of the Painter.io logo: the wordmark (Nunito Black from Assets/Resources/Fonts), the pearl that replaces the dot
of ".io" and the liquid thread it pulls, as signed distance fields at a working scale.

The thread leaves from behind the stem of the "P" (home), sweeps around under the whole word and reaches the pearl from
behind (the head), like a pawn that left its puddle and is about to close its loop. It never touches the letters in
front: it passes behind the P and behind the pearl, so the coral and teal paints never mix.
"""
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from sdf import sdf_from_coverage, coverage

ROOT = Path(__file__).resolve().parents[2]
FONT_PATH = ROOT / 'Assets' / 'Resources' / 'Fonts' / 'Nunito-Black.ttf'

WORD_LEFT = 'Painter'
WORD_RIGHT = 'io'

# Layout in final pixels of the 1600 x 640 wordmark (em = font size).
FONT_SIZE = 288.0
TRACKING = {  # extra advance after a glyph, in em (negative = tighter)
    'P': -0.020, 'a': -0.012, 'i': -0.006, 'n': -0.014, 't': -0.020, 'e': -0.014, 'r': 0.0, 'o': 0.0,
}
PEARL_RADIUS_EM = 0.175
PEARL_GAP_BEFORE_EM = 0.050
PEARL_GAP_AFTER_EM = 0.060
PEARL_SINK_EM = 0.006          # the pearl rests on the baseline and settles very slightly into it
THREAD_RADIUS_EM = 0.036

# Thread control polygon in em around two anchors: P = (ink left of the P, baseline), D = pearl center. A clamped uniform
# cubic B-spline follows it (curvature continuous, so the thread never kinks).
THREAD_PATH_P = [(0.13, -0.52), (0.02, -0.40), (-0.12, -0.16), (-0.13, 0.16), (0.10, 0.34), (0.70, 0.40)]
THREAD_PATH_D = [(-1.60, 0.40), (-0.70, 0.36), (-0.30, 0.22), (-0.10, 0.06), (0.0, 0.0)]
THREAD_TAPER = 0.72           # thread radius where it leaves the P, relative to its radius at the pearl
PEARL_STRETCH = 1.16           # the pearl is a slight teardrop, longer on the side of its thread (F2)


class Geometry:
    """All signed distances at the working scale ss (pixels of the working array)."""

    def __init__(self, width, height, ss, font_size=FONT_SIZE, baseline=None, thread_path=True):
        self.width, self.height, self.ss = width, height, ss
        self.W, self.H = width * ss, height * ss
        self.em = font_size * ss
        self.font = ImageFont.truetype(str(FONT_PATH), int(round(self.em)))
        self.baseline = (baseline if baseline is not None else height * 0.61) * ss
        self.with_thread = thread_path
        # Pass 1 at x = 0 to measure, pass 2 centered.
        self._place(0.0)
        x0, x1 = self._extent()
        self._place((self.W - (x1 - x0)) * 0.5 - x0)
        self._build_fields()

    # -- layout -----------------------------------------------------------------------------------------------------

    def _place(self, x_offset):
        em = self.em
        x = x_offset
        self.glyphs = []          # (char, pen x on the baseline)
        for ch in WORD_LEFT:
            self.glyphs.append((ch, x))
            x += self.font.getlength(ch) + TRACKING.get(ch, 0.0) * em
        x += PEARL_GAP_BEFORE_EM * em
        r = PEARL_RADIUS_EM * em
        self.pearl_c = np.array([x + r, self.baseline - r + PEARL_SINK_EM * em], np.float32)
        self.pearl_r = r
        x += 2 * r + PEARL_GAP_AFTER_EM * em
        for ch in WORD_RIGHT:
            self.glyphs.append((ch, x))
            x += self.font.getlength(ch) + TRACKING.get(ch, 0.0) * em
        self.cov_letters = self._draw_letters()
        cols = np.where(self.cov_letters.max(axis=0) > 0.0)[0]
        p_ink = self._glyph_ink(0)
        self.p_anchor = np.array([p_ink, self.baseline], np.float32)
        self.ink_x = (float(cols[0]), float(cols[-1])) if len(cols) else (0.0, 0.0)
        self.thread_pts = self._thread_polyline() if self.with_thread else None

    def _extent(self):
        x0, x1 = self.ink_x
        if self.thread_pts is not None:
            r = THREAD_RADIUS_EM * self.em
            x0 = min(x0, float(self.thread_pts[:, 0].min() - r))
            x1 = max(x1, float(self.thread_pts[:, 0].max() + r))
        return x0, x1

    def _draw_letters(self):
        img = Image.new('L', (self.W, self.H), 0)
        draw = ImageDraw.Draw(img)
        for ch, x in self.glyphs:
            draw.text((x, self.baseline), ch, font=self.font, fill=255, anchor='ls')
        return np.asarray(img, np.float32) / 255.0

    def glyph_mask(self, index):
        """Coverage (0..1) of one glyph alone, at the working scale."""
        ch, x = self.glyphs[index]
        img = Image.new('L', (self.W, self.H), 0)
        ImageDraw.Draw(img).text((x, self.baseline), ch, font=self.font, fill=255, anchor='ls')
        return np.asarray(img, np.float32) / 255.0

    def _glyph_ink(self, index):
        cols = np.where(self.glyph_mask(index).max(axis=0) > 0.5)[0]
        return float(cols[0]) if len(cols) else self.glyphs[index][1]

    def _thread_polyline(self):
        em = self.em
        pts = [self.p_anchor + np.array(p, np.float32) * em for p in THREAD_PATH_P]
        pts += [self.pearl_c + np.array(p, np.float32) * em for p in THREAD_PATH_D]
        return bspline(np.array(pts, np.float32), samples_per_segment=64)

    # -- fields -----------------------------------------------------------------------------------------------------

    def _build_fields(self):
        reach = int(0.22 * self.em)
        self.sdf_letters = sdf_from_coverage(self.cov_letters, reach)
        build_pawn_fields(self, THREAD_RADIUS_EM * self.em)
        self.sdf_front = np.minimum(self.sdf_letters, self.sdf_pearl)
        self.sdf_all = np.minimum(self.sdf_front, self.sdf_thread)
    def cov(self, sdf):
        return coverage(sdf, 1.0)


def build_pawn_fields(obj, thread_radius):
    """Pearl and thread fields of obj (needs W, H, pearl_c, pearl_r, thread_pts or None): xx, yy, the teardrop pearl
    frame (pearl_u, pearl_v in pearl radii, pearl_fwd, pearl_dist) and sdf_pearl, the thread distance, direction,
    arc length, tapered radius and sdf_thread."""
    yy, xx = np.mgrid[0:obj.H, 0:obj.W].astype(np.float32)
    obj.xx, obj.yy = xx, yy
    # Teardrop pearl: in the pearl's frame (u forward = away from its thread, v across), the rear half is stretched.
    dx, dy = xx - obj.pearl_c[0], yy - obj.pearl_c[1]
    if obj.thread_pts is not None:
        back = obj.thread_pts[-24] - obj.pearl_c
        fwd = -back / max(float(np.linalg.norm(back)), 1e-6)
    else:
        fwd = np.array([1.0, 0.0], np.float32)
    obj.pearl_fwd = fwd.astype(np.float32)
    u = dx * fwd[0] + dy * fwd[1]
    v = -dx * fwd[1] + dy * fwd[0]
    u = np.where(u < 0.0, u / PEARL_STRETCH, u)
    obj.pearl_u, obj.pearl_v = u / obj.pearl_r, v / obj.pearl_r
    obj.pearl_dist = np.sqrt(u * u + v * v)
    # Distance in the stretched frame, scaled back to pixels on the rear side (close enough for a 1 px ramp).
    scale = np.where(obj.pearl_u < 0.0, PEARL_STRETCH, 1.0)
    obj.sdf_pearl = ((obj.pearl_dist - obj.pearl_r) * scale).astype(np.float32)
    if obj.thread_pts is not None:
        obj.thread_r = thread_radius
        d, nx, ny, s = polyline_distance(obj.thread_pts, obj.W, obj.H, thread_radius * 3.0)
        obj.thread_d, obj.thread_nx, obj.thread_ny, obj.thread_s = d, nx, ny, s
        # Slight taper: thinner at its far end, full width where the pearl pulls it.
        obj.thread_rad = thread_radius * (THREAD_TAPER + (1.0 - THREAD_TAPER) * np.clip(s, 0.0, 1.0))
        obj.sdf_thread = (d - obj.thread_rad).astype(np.float32)
    else:
        obj.sdf_thread = np.full((obj.H, obj.W), 1e4, np.float32)


# The square mark of the app icons, in units of the mark box (0..1, y down): the pearl and the loop of thread it pulls.
# The thread runs from its free end (first point) almost all the way around and back to the pearl (last point): the
# pawn is about to close its loop, which is the whole game in one picture.
MARK_PEARL_RADIUS = 0.165
MARK_THREAD_RADIUS = 0.036
MARK_LOOP_CENTER = (0.49, 0.53)
MARK_LOOP_RADII = (0.32, 0.30)
# Image angles (y down). The thread starts at FROM and turns counterclockwise on screen to TO, where the pearl is; the
# 60 degree gap left ahead of the pearl is the stretch it still has to cover to close the loop.
MARK_LOOP_FROM_DEG, MARK_LOOP_TO_DEG = 252.0, -42.0


def _mark_thread():
    cx, cy = MARK_LOOP_CENTER
    rx, ry = MARK_LOOP_RADII
    pts = []
    for a in np.linspace(MARK_LOOP_FROM_DEG, MARK_LOOP_TO_DEG, 11):
        t = np.radians(a)
        wobble = 1.0 + 0.035 * np.sin(2.0 * t + 0.9)         # hand-drawn, not a compass circle
        pts.append((cx + rx * wobble * np.cos(t), cy + ry * wobble * np.sin(t)))
    return pts


MARK_THREAD = _mark_thread()
MARK_PEARL = MARK_THREAD[-1]


class MarkGeometry:
    """Pearl and thread loop of the app icon, drawn in a square of size px (working pixels), the mark box placed at
    (ox, oy) with side box."""

    def __init__(self, size, ss, box_frac=1.0, center=(0.5, 0.5), min_thread_px=0.0):
        self.ss = ss
        self.W = self.H = int(size * ss)
        box = box_frac * self.W
        self.em = box                                  # effects scale with the mark box
        ox = center[0] * self.W - box * 0.5
        oy = center[1] * self.H - box * 0.5
        to_px = lambda p: np.array([ox + p[0] * box, oy + p[1] * box], np.float32)  # noqa: E731
        self.pearl_c = to_px(MARK_PEARL)
        self.pearl_r = MARK_PEARL_RADIUS * box
        self.thread_pts = bspline(np.array([to_px(p) for p in MARK_THREAD], np.float32), samples_per_segment=48)
        radius = max(MARK_THREAD_RADIUS * box, min_thread_px * ss)
        build_pawn_fields(self, radius)
        self.sdf_letters = np.full((self.H, self.W), 1e4, np.float32)
        self.cov_letters = np.zeros((self.H, self.W), np.float32)
        self.sdf_front = self.sdf_pearl
        self.sdf_all = np.minimum(self.sdf_pearl, self.sdf_thread)


def bspline(pts, samples_per_segment=32):
    """Clamped uniform cubic B-spline of a control polygon (end points tripled so the curve starts and ends on them)."""
    p = np.vstack([pts[0], pts[0], pts, pts[-1], pts[-1]])
    out = []
    for i in range(len(p) - 3):
        p0, p1, p2, p3 = p[i], p[i + 1], p[i + 2], p[i + 3]
        t = np.linspace(0.0, 1.0, samples_per_segment, endpoint=False, dtype=np.float32)[:, None]
        t2, t3 = t * t, t * t * t
        b0 = (1 - t) ** 3 / 6.0
        b1 = (3 * t3 - 6 * t2 + 4) / 6.0
        b2 = (-3 * t3 + 3 * t2 + 3 * t + 1) / 6.0
        b3 = t3 / 6.0
        out.append(b0 * p0 + b1 * p1 + b2 * p2 + b3 * p3)
    out.append(pts[-1][None, :])
    return np.vstack(out).astype(np.float32)


def polyline_distance(pts, w, h, reach):
    """Distance from each pixel to a polyline (exact, per segment inside its padded box), with the unit direction from
    the nearest point to the pixel and the normalized arc length (0 at the first point, 1 at the last) of that point."""
    d = np.full((h, w), 1e4, np.float32)
    nx = np.zeros((h, w), np.float32)
    ny = np.zeros((h, w), np.float32)
    s = np.zeros((h, w), np.float32)
    seg_len = np.sqrt(np.sum(np.diff(pts, axis=0) ** 2, axis=1))
    cum = np.concatenate([[0.0], np.cumsum(seg_len)]).astype(np.float32)
    total = max(float(cum[-1]), 1e-6)
    for i in range(len(pts) - 1):
        a, b = pts[i], pts[i + 1]
        x0 = int(max(0, np.floor(min(a[0], b[0]) - reach)))
        x1 = int(min(w, np.ceil(max(a[0], b[0]) + reach) + 1))
        y0 = int(max(0, np.floor(min(a[1], b[1]) - reach)))
        y1 = int(min(h, np.ceil(max(a[1], b[1]) + reach) + 1))
        if x0 >= x1 or y0 >= y1:
            continue
        yy, xx = np.mgrid[y0:y1, x0:x1].astype(np.float32)
        ab = b - a
        l2 = max(float(np.dot(ab, ab)), 1e-9)
        t = np.clip(((xx - a[0]) * ab[0] + (yy - a[1]) * ab[1]) / l2, 0.0, 1.0)
        px, py = a[0] + t * ab[0], a[1] + t * ab[1]
        ex, ey = xx - px, yy - py
        dist = np.sqrt(ex * ex + ey * ey)
        sub = d[y0:y1, x0:x1]
        better = dist < sub
        inv = 1.0 / np.maximum(dist, 1e-6)
        sub[better] = dist[better]
        nx[y0:y1, x0:x1][better] = (ex * inv)[better]
        ny[y0:y1, x0:x1][better] = (ey * inv)[better]
        s[y0:y1, x0:x1][better] = ((cum[i] + t * np.sqrt(l2)) / total)[better]
    return d, nx, ny, s
