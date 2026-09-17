"""Glyph table: the printable ASCII characters rasterised into fixed cells.

Pure module (numpy + Pillow only, no Qt, no Win32). A `GlyphTable` holds, for one
cell size, the binary bitmap of every glyph as it will be displayed, plus the
derived quantities the matcher needs. The binary bitmap is the ground truth:
the matcher compares screen blocks against what will actually be drawn, so the
"exact black/white ratio" of a glyph is the ratio of its displayed pixels.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

ASSETS_DIR = Path(__file__).resolve().parent.parent / "assets"
DEFAULT_FONT = ASSETS_DIR / "DejaVuSansMono.ttf"

# Printable ASCII, space first so that index 0 is always the blank glyph.
PRINTABLE = "".join(chr(c) for c in range(32, 127))

# Preset cell sizes offered by the app: (width, height) in pixels.
CELL_SIZES: tuple[tuple[int, int], ...] = ((4, 8), (6, 12), (8, 16), (12, 24), (16, 32))
# Any character height in this range is allowed; the width follows the font's aspect.
MIN_CELL_HEIGHT = 4
MAX_CELL_HEIGHT = 128
CELL_ASPECT = 0.5  # width / height of a DejaVu Sans Mono cell (advance 0.602 em, line 1.17 em)


def cell_for_height(height: int) -> tuple[int, int]:
    """(width, height) of a cell for a character height in pixels, clamped to the allowed range."""
    h = max(MIN_CELL_HEIGHT, min(MAX_CELL_HEIGHT, int(height)))
    return max(2, round(h * CELL_ASPECT)), h


@dataclass(frozen=True)
class GlyphTable:
    """All glyphs of one font at one cell size.

    bitmaps:  (K, ch, cw) uint8, 0 or 255, the displayed glyph pixels.
    chars:    the K characters, in the same order (chars[0] == " ").
    features: (K, D) float32 in [0, 1], the matching map of each glyph
              (lightly blurred bitmap flattened, D == ch * cw).
    coverage: (K,) float32, ink ratio of each displayed glyph in [0, 1].
    match_features: (K, D) float32, `features` pulled back through the blur:
              dot(blur(block), features[k]) == dot(block, match_features[k]),
              so the frame itself never has to be blurred.
    """

    cell_w: int
    cell_h: int
    chars: str
    bitmaps: np.ndarray
    features: np.ndarray
    coverage: np.ndarray
    match_features: np.ndarray

    @property
    def count(self) -> int:
        return len(self.chars)

    @property
    def dim(self) -> int:
        return self.cell_w * self.cell_h

    def index_of(self, ch: str) -> int:
        return self.chars.index(ch)


def box_blur_3x3(img: np.ndarray) -> np.ndarray:
    """3x3 box blur with edge replication, over the last two axes.

    Applied identically to glyph maps and to screen blocks so that a stroke one
    pixel away from a glyph stroke still scores well (the cheap form of the
    alignment tolerance of structure-based ASCII art).
    """
    p = np.pad(img, [(0, 0)] * (img.ndim - 2) + [(1, 1), (1, 1)], mode="edge")
    out = np.zeros(img.shape, dtype=np.float32)
    for dy in range(3):
        for dx in range(3):
            out += p[..., dy : dy + img.shape[-2], dx : dx + img.shape[-1]]
    out *= 1.0 / 9.0
    return out


def blur_matrix(cell_w: int, cell_h: int) -> np.ndarray:
    """(D, D) matrix M such that blur(b).ravel() == M @ b.ravel() for a (ch, cw) block."""
    d = cell_w * cell_h
    basis = np.eye(d, dtype=np.float32).reshape(d, cell_h, cell_w)
    return box_blur_3x3(basis).reshape(d, d).T


def blur_adjoint_3x3(img: np.ndarray) -> np.ndarray:
    """Adjoint of `box_blur_3x3` over the last two axes: dot(blur(a), b) == dot(a, blur_adjoint(b)).

    The blur pads by edge replication then sums 3x3; its adjoint spreads each pixel
    over its 3x3 neighbourhood in the padded frame, then folds the padding back onto
    the edge rows and columns. O(D) per image, where the matrix form is O(D^2).
    """
    h, w = img.shape[-2], img.shape[-1]
    lead = img.shape[:-2]
    y = np.zeros(lead + (h + 2, w + 2), dtype=np.float32)
    for dy in range(3):
        for dx in range(3):
            y[..., dy : dy + h, dx : dx + w] += img
    out = y[..., 1:-1, 1:-1].copy()
    out[..., 0, :] += y[..., 0, 1:-1]
    out[..., -1, :] += y[..., -1, 1:-1]
    out[..., :, 0] += y[..., 1:-1, 0]
    out[..., :, -1] += y[..., 1:-1, -1]
    out[..., 0, 0] += y[..., 0, 0]
    out[..., 0, -1] += y[..., 0, -1]
    out[..., -1, 0] += y[..., -1, 0]
    out[..., -1, -1] += y[..., -1, -1]
    out *= 1.0 / 9.0
    return out


def fold_blur(features: np.ndarray, cell_w: int, cell_h: int) -> np.ndarray:
    """Pull the blurred glyph maps back through the blur: dot(blur(b), f) == dot(b, fold(f))."""
    k = features.shape[0]
    return blur_adjoint_3x3(features.reshape(k, cell_h, cell_w)).reshape(k, cell_w * cell_h).astype(np.float32)


def _fit_font(font_path: Path, cell_w: int, cell_h: int) -> tuple[ImageFont.FreeTypeFont, int]:
    """Largest font size whose advance fits the cell width and whose line fits the height.

    Returns the font and the baseline y offset inside the cell.
    """
    best = None
    for size in range(max(2, cell_h // 2), cell_h * 2 + 1):
        font = ImageFont.truetype(str(font_path), size)
        advance = font.getlength("M")
        ascent, descent = font.getmetrics()
        if advance <= cell_w + 0.01 and ascent + descent <= cell_h:
            best = (font, ascent, descent)
        elif best is not None:
            break
    if best is None:
        font = ImageFont.truetype(str(font_path), max(2, cell_h // 2))
        ascent, descent = font.getmetrics()
        best = (font, ascent, descent)
    font, ascent, descent = best
    # Centre the line box vertically inside the cell.
    baseline = ascent + (cell_h - (ascent + descent)) // 2
    return font, baseline


def rasterize(chars: str, cell_w: int, cell_h: int, font_path: Path = DEFAULT_FONT) -> np.ndarray:
    """Binary bitmaps (K, ch, cw) uint8 {0, 255} of `chars` in a (cw, ch) cell."""
    font, baseline = _fit_font(font_path, cell_w, cell_h)
    bitmaps = np.zeros((len(chars), cell_h, cell_w), dtype=np.uint8)
    for k, ch in enumerate(chars):
        img = Image.new("L", (cell_w, cell_h), 0)
        draw = ImageDraw.Draw(img)
        # Anchor "ls": left, baseline. Centre horizontally on the advance width.
        advance = font.getlength(ch)
        x = (cell_w - advance) / 2.0
        draw.text((x, baseline), ch, fill=255, font=font, anchor="ls")
        arr = np.asarray(img)
        bitmaps[k] = np.where(arr >= 128, 255, 0).astype(np.uint8)
    return bitmaps


def build_table(cell_w: int, cell_h: int, font_path: Path = DEFAULT_FONT, chars: str = PRINTABLE) -> GlyphTable:
    """Rasterise `chars`, drop glyphs that became identical after binarisation, derive features."""
    bitmaps = rasterize(chars, cell_w, cell_h, font_path)
    keep: list[int] = []
    seen: set[bytes] = set()
    for k in range(len(chars)):
        key = bitmaps[k].tobytes()
        if key in seen:
            continue
        seen.add(key)
        keep.append(k)
    bitmaps = bitmaps[keep]
    kept_chars = "".join(chars[k] for k in keep)
    ink = (bitmaps > 0).astype(np.float32)
    features = box_blur_3x3(ink).reshape(len(keep), cell_w * cell_h).astype(np.float32)
    coverage = ink.reshape(len(keep), -1).mean(axis=1).astype(np.float32)
    return GlyphTable(cell_w, cell_h, kept_chars, bitmaps, features, coverage, fold_blur(features, cell_w, cell_h))


def save_table(table: GlyphTable, path: Path) -> None:
    np.savez_compressed(
        path,
        cell_w=table.cell_w,
        cell_h=table.cell_h,
        chars=np.array(table.chars),
        bitmaps=table.bitmaps,
        features=table.features,
        coverage=table.coverage,
    )


def load_table(path: Path) -> GlyphTable:
    z = np.load(path)
    cell_w, cell_h = int(z["cell_w"]), int(z["cell_h"])
    features = z["features"]
    return GlyphTable(cell_w, cell_h, str(z["chars"]), z["bitmaps"], features, z["coverage"], fold_blur(features, cell_w, cell_h))


_CACHE: dict[tuple[int, int, str], GlyphTable] = {}


def get_table(cell_w: int, cell_h: int, font_path: Path = DEFAULT_FONT) -> GlyphTable:
    """Memoised `build_table`: rasterising 95 glyphs takes a few milliseconds, once per size."""
    key = (cell_w, cell_h, str(font_path))
    if key not in _CACHE:
        _CACHE[key] = build_table(cell_w, cell_h, font_path)
    return _CACHE[key]
