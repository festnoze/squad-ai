"""Shape matcher: turns a captured frame into a grid of glyph indices, then into pixels.

Pure numpy. Every cell is scored against every glyph with two terms:

  shape: squared distance between the cell, contrast-stretched to [0, 1], and the
         glyph's lightly blurred bitmap (where the ink is, not just how much);
  tone:  squared difference between the cell's mean luminance and the glyph's
         density relative to the densest glyph, so black maps to the space and
         white to the densest glyph, with every level in between.

The two are blended by the cell's contrast: a crisp stroke is decided by shape
alone (its own pixels give back its own glyph), a flat area by tone alone.
A per-cell hysteresis keeps the previous glyph unless a new one wins by a margin,
which removes the glyph flicker every ASCII video renderer suffers from.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from PIL import Image

from .glyphs import GlyphTable


@dataclass
class MatchParams:
    gamma: float = 1.0  # applied to the [0, 1] luminance before matching (> 1 darkens)
    exposure: float = 1.0  # multiplies the luminance before matching
    black_point: float = 0.03  # luminance at or below this is black (maps to the space glyph)
    auto_tone: bool = True  # True: tone spans space..densest glyph. False: literal ink ratio.
    tone_weight: float = 1.5  # weight of the tone term against the shape term
    shape_power: float = 0.5  # shape weight = contrast ** shape_power (below 1 favours structure)
    contrast_floor: float = 0.15  # cells with less contrast than this are not stretched further
    hysteresis: float = 0.04  # a new glyph must beat the previous score by this fraction of D
    blur: bool = True  # compare against blurred glyph maps (alignment tolerance)
    negative: bool = False  # False: bright pixels are ink (screens). True: dark pixels are ink (documents).


@dataclass
class MatchState:
    """Carries the previous glyph indices between frames for the hysteresis."""

    prev_idx: np.ndarray | None = None
    shape: tuple[int, int] = field(default=(0, 0))

    def reset(self) -> None:
        self.prev_idx = None
        self.shape = (0, 0)


_TO_UNIT = (np.arange(256, dtype=np.float32) / 255.0).astype(np.float32)


def luminance(frame_bgra: np.ndarray) -> np.ndarray:
    """(H, W, 4|3) uint8 BGR(A) -> (H, W) float32 luminance in [0, 1] (Rec. 601 weights).

    Pillow's C conversion is three times faster than any numpy formulation measured
    (4.7 ms against 13.5 ms for 1280x720).
    """
    h, w, c = frame_bgra.shape
    raw = np.ascontiguousarray(frame_bgra)
    mode = "BGRA" if c == 4 else "BGR"
    img = Image.frombuffer("RGBA" if c == 4 else "RGB", (w, h), raw, "raw", mode, 0, 1).convert("L")
    return _TO_UNIT[np.asarray(img)]


def to_blocks(gray: np.ndarray, cell_w: int, cell_h: int) -> np.ndarray:
    """(Hc*ch, Wc*cw) -> (Hc*Wc, ch*cw), row-major cells. The frame must be a whole number of cells."""
    h, w = gray.shape
    rows, cols = h // cell_h, w // cell_w
    g = gray[: rows * cell_h, : cols * cell_w]
    return g.reshape(rows, cell_h, cols, cell_w).transpose(0, 2, 1, 3).reshape(rows * cols, cell_h * cell_w)


def match_blocks(blocks: np.ndarray, table: GlyphTable, params: MatchParams, state: MatchState | None = None) -> np.ndarray:
    """Pick one glyph index per block.

    blocks: (N, D) float32 in [0, 1], raw (unblurred) cell pixels, ink-oriented
            (1 = ink). Returns (N,) int32 indices into `table`.

    Shape term: ||blur(b') - g||^2 with b' the contrast-stretched block and g the
    blurred glyph map. The blur is linear, so it is folded into
    `table.match_features` and the block itself is never blurred; the stretch is
    affine, so it is applied to the dot products, not to the pixels. The constant
    ||blur(b')||^2 is dropped (same for every glyph of a block).

    Tone term (auto_tone): D * (mean(b) - coverage_g / coverage_max)^2.
    Blend: c * shape + (1 - c) * tone_weight * tone with c = contrast ** shape_power.

    Literal mode (auto_tone False): ||blur(b) - g||^2 + tone_weight * D * (mean(b) - coverage_g)^2,
    the exact ink ratio, which saturates above ~30 % luminance.
    """
    d = blocks.shape[1]
    feats = table.features  # (K, D), blurred glyph maps
    dot_feats = table.match_features if params.blur else feats
    dots = blocks @ dot_feats.T  # (N, K) = blur(b) . g
    g2 = (feats * feats).sum(axis=1)[None, :]
    mean_b = blocks.mean(axis=1, keepdims=True)  # (N, 1)

    if not params.auto_tone:
        scores = -2.0 * dots + g2
        diff = mean_b - table.coverage[None, :]
        scores += (params.tone_weight * d) * (diff * diff)
    else:
        bmin = blocks.min(axis=1, keepdims=True)
        bmax = blocks.max(axis=1, keepdims=True)
        contrast = bmax - bmin  # (N, 1) in [0, 1]
        scale = 1.0 / np.maximum(contrast, params.contrast_floor)
        # blur(b') = (blur(b) - bmin) * scale, so blur(b').g = (blur(b).g - bmin * sum(g)) * scale
        sum_g = feats.sum(axis=1)[None, :]
        shape = (dots - bmin * sum_g) * scale
        shape *= -2.0
        shape += g2
        density = table.coverage / max(float(table.coverage.max()), 1e-6)
        diff = mean_b - density[None, :]
        tone = (params.tone_weight * d) * (diff * diff)
        c = np.power(contrast, params.shape_power) if params.shape_power != 1.0 else contrast
        scores = c * shape + (1.0 - c) * tone
    best = scores.argmin(axis=1).astype(np.int32)

    if state is not None:
        if state.prev_idx is not None and state.prev_idx.shape == best.shape and params.hysteresis > 0.0:
            prev = state.prev_idx
            prev_scores = np.take_along_axis(scores, prev[:, None], axis=1)[:, 0]
            best_scores = np.take_along_axis(scores, best[:, None], axis=1)[:, 0]
            keep = prev_scores - best_scores < params.hysteresis * d
            best = np.where(keep, prev, best).astype(np.int32)
        state.prev_idx = best
    return best


def frame_to_indices(frame_bgra: np.ndarray, table: GlyphTable, params: MatchParams, state: MatchState | None = None) -> np.ndarray:
    """Full pipeline from a captured frame to a (rows, cols) grid of glyph indices."""
    gray = luminance(frame_bgra)
    if params.negative:
        gray = 1.0 - gray
    if params.gamma != 1.0:
        np.power(gray, params.gamma, out=gray)
    if params.exposure != 1.0:
        gray *= params.exposure
    if params.black_point > 0.0:
        gray -= params.black_point
        gray *= 1.0 / (1.0 - params.black_point)
    if params.exposure != 1.0 or params.black_point > 0.0:
        np.clip(gray, 0.0, 1.0, out=gray)
    h, w = gray.shape
    rows, cols = h // table.cell_h, w // table.cell_w
    if state is not None and state.shape != (rows, cols):
        state.reset()
        state.shape = (rows, cols)
    blocks = to_blocks(gray, table.cell_w, table.cell_h)
    idx = match_blocks(blocks, table, params, state)
    return idx.reshape(rows, cols)


def render(indices: np.ndarray, table: GlyphTable, dark_ink: bool = False) -> np.ndarray:
    """(rows, cols) indices -> (rows*ch, cols*cw) uint8 image, strictly 0 or 255.

    dark_ink only swaps the two display colours (black glyphs on white); it never
    changes which glyphs were chosen.
    """
    rows, cols = indices.shape
    tiles = table.bitmaps[indices]  # (rows, cols, ch, cw)
    img = tiles.transpose(0, 2, 1, 3).reshape(rows * table.cell_h, cols * table.cell_w)
    if dark_ink:
        img = 255 - img
    return np.ascontiguousarray(img)


def to_text(indices: np.ndarray, table: GlyphTable) -> str:
    """(rows, cols) indices -> the frame as text, one line per row."""
    chars = np.array(list(table.chars))
    return "\n".join("".join(row) for row in chars[indices])
