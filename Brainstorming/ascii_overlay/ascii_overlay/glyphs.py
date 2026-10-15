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

_LETTERS_DIGITS = "".join(chr(c) for c in range(48, 58)) + "".join(chr(c) for c in range(65, 91)) + "".join(chr(c) for c in range(97, 123))
_BLOCKS = "\u2591\u2592\u2593\u2588\u2580\u2584\u258c\u2590"  # ░ ▒ ▓ █ ▀ ▄ ▌ ▐
_BOX = "\u2500\u2502\u250c\u2510\u2514\u2518\u251c\u2524\u252c\u2534\u253c"  # ─ │ ┌ ┐ └ ┘ ├ ┤ ┬ ┴ ┼
_QUADRANTS = "\u2598\u259d\u2580\u2596\u258c\u259e\u259b\u2597\u259a\u2590\u259c\u2584\u2599\u259f\u2588"
_BRAILLE = "".join(chr(0x2800 + i) for i in range(1, 256))

# Character sets offered by the app. Every set starts with the space (index 0 = blank).
# Sets beyond the first six are not ASCII: they need a font that has the glyphs
# (DejaVu Sans Mono has them all); missing glyphs are dropped at build time.
CHARSETS: dict[str, str] = {
    "Full ASCII": PRINTABLE,
    "Ramp 10": " .:-=+*#%@",
    "Ramp 70": " .'`^\",:;Il!i><~+_-?][}{1)(|\\/tfjrxnuvczXYUJCLQ0OZmwqpdbkhao*#MW&8%B@$",
    "Symbols": " .,:;'`\"^~-_=+*/\\|()[]{}<>!?",
    "Letters & digits": " " + _LETTERS_DIGITS,
    "Uppercase": " " + "".join(chr(c) for c in range(65, 91)),
    "ASCII + blocks": PRINTABLE + _BLOCKS + _BOX,
    "CP437 blocks": " " + _BLOCKS + _BOX,
    "Quadrants": " " + _QUADRANTS,
    "Braille": " " + _BRAILLE,
}
DEFAULT_CHARSET = "Full ASCII"

# Fonts: the bundled one first, then Windows monospace fonts when present.
_WINDOWS_FONTS = Path("C:/Windows/Fonts")
_FONT_CANDIDATES: tuple[tuple[str, Path], ...] = (
    ("DejaVu Sans Mono", DEFAULT_FONT),
    ("IBM VGA 8x16", ASSETS_DIR / "Px437_IBM_VGA_8x16.ttf"),
    ("Consolas", _WINDOWS_FONTS / "consola.ttf"),
    ("Cascadia Mono", _WINDOWS_FONTS / "CascadiaMono.ttf"),
    ("Lucida Console", _WINDOWS_FONTS / "lucon.ttf"),
    ("Courier New", _WINDOWS_FONTS / "cour.ttf"),
)
FONTS: dict[str, Path] = {name: path for name, path in _FONT_CANDIDATES if path.is_file()}
DEFAULT_FONT_NAME = "DejaVu Sans Mono"

# Fonts tried, in order, for a character the chosen font lacks (braille in DejaVu Sans
# Mono or Consolas, for instance). Only the glyph comes from the fallback; it is
# fitted to the same cell.
FALLBACK_FONTS: tuple[Path, ...] = tuple(
    p for p in (ASSETS_DIR / "DejaVuSans.ttf", _WINDOWS_FONTS / "seguisym.ttf") if p.is_file()
)

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


def _fit_font(font_path: Path, cell_w: int, cell_h: int, ref: str = "M") -> tuple[ImageFont.FreeTypeFont, int]:
    """Largest font size whose widest `ref` character fits the cell width and whose line fits the height.

    Returns the font and the baseline y offset inside the cell.
    """
    best = None
    ref_chars = sorted(set(ref)) or ["M"]
    for size in range(max(2, cell_h // 2), cell_h * 2 + 1):
        font = ImageFont.truetype(str(font_path), size)
        advance = max(font.getlength(c) for c in ref_chars)
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
    """Binary bitmaps (K, ch, cw) uint8 {0, 255} of `chars` in a (cw, ch) cell, from one font."""
    font, baseline = _fit_font(font_path, cell_w, cell_h, chars)
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


# Block elements and box drawing are drawn geometrically, not taken from the font:
# a font's full block is a glyph with side bearings and line gaps (77 % of the cell
# in DejaVu Sans Mono at 8x16), which breaks the tiling and the tone. Drawn here they
# fill the cell exactly: the full block is 100 % ink, the shades 25 / 50 / 75 %.
_QUADRANT_BITS = {  # code point -> (top-left, top-right, bottom-left, bottom-right)
    0x2598: (1, 0, 0, 0), 0x259D: (0, 1, 0, 0), 0x2580: (1, 1, 0, 0), 0x2596: (0, 0, 1, 0),
    0x258C: (1, 0, 1, 0), 0x259E: (0, 1, 1, 0), 0x259B: (1, 1, 1, 0), 0x2597: (0, 0, 0, 1),
    0x259A: (1, 0, 0, 1), 0x2590: (0, 1, 0, 1), 0x259C: (1, 1, 0, 1), 0x2584: (0, 0, 1, 1),
    0x2599: (1, 0, 1, 1), 0x259F: (0, 1, 1, 1), 0x2588: (1, 1, 1, 1),
}
_SHADE_QUARTERS = {0x2591: 1, 0x2592: 2, 0x2593: 3}  # ░ ▒ ▓ : ink pixels per 2x2 tile
_BOX_ARMS = {  # code point -> (up, down, left, right)
    0x2500: (0, 0, 1, 1), 0x2502: (1, 1, 0, 0), 0x250C: (0, 1, 0, 1), 0x2510: (0, 1, 1, 0),
    0x2514: (1, 0, 0, 1), 0x2518: (1, 0, 1, 0), 0x251C: (1, 1, 0, 1), 0x2524: (1, 1, 1, 0),
    0x252C: (0, 1, 1, 1), 0x2534: (1, 0, 1, 1), 0x253C: (1, 1, 1, 1),
}


def synthesize(ch: str, cell_w: int, cell_h: int) -> np.ndarray | None:
    """Exact bitmap (ch, cw) uint8 {0, 255} for block elements and box drawing, else None."""
    cp = ord(ch)
    bm = np.zeros((cell_h, cell_w), dtype=np.uint8)
    if cp in _QUADRANT_BITS:
        tl, tr, bl, br = _QUADRANT_BITS[cp]
        hw, hh = cell_w // 2, cell_h // 2
        if tl:
            bm[:hh, :hw] = 255
        if tr:
            bm[:hh, hw:] = 255
        if bl:
            bm[hh:, :hw] = 255
        if br:
            bm[hh:, hw:] = 255
        return bm
    if cp in _SHADE_QUARTERS:
        n = _SHADE_QUARTERS[cp]
        yy, xx = np.mgrid[0:cell_h, 0:cell_w]
        phase = (yy % 2) * 2 + (xx % 2)  # 2x2 ordered dither: 0 3 / 2 1 lights up in this order
        order = np.array([0, 3, 2, 1])[phase]
        bm[order < n] = 255
        return bm
    if cp in _BOX_ARMS:
        up, down, left, right = _BOX_ARMS[cp]
        t = max(1, round(cell_h / 16))  # line thickness
        cx, cy = cell_w // 2, cell_h // 2
        x0, x1 = cx - t // 2, cx - t // 2 + t
        y0, y1 = cy - t // 2, cy - t // 2 + t
        if up:
            bm[:y1, x0:x1] = 255
        if down:
            bm[y0:, x0:x1] = 255
        if left:
            bm[y0:y1, :x1] = 255
        if right:
            bm[y0:y1, x0:] = 255
        return bm
    return None


def _missing_mask(bitmaps: np.ndarray, chars: str, cell_w: int, cell_h: int, font_path: Path) -> np.ndarray:
    """True where the font rendered its 'missing glyph' box (compared with an undefined code point)."""
    notdef = rasterize("\uffff", cell_w, cell_h, font_path)[0]
    missing = np.zeros(len(chars), dtype=bool)
    if notdef.any():
        for k, ch in enumerate(chars):
            missing[k] = ch != " " and np.array_equal(bitmaps[k], notdef)
    return missing


def rasterize_with_fallback(
    chars: str, cell_w: int, cell_h: int, font_path: Path = DEFAULT_FONT, fallbacks: tuple[Path, ...] = FALLBACK_FONTS
) -> tuple[np.ndarray, np.ndarray]:
    """Bitmaps of `chars` from `font_path`, glyphs it lacks taken from the fallback fonts.

    Returns (bitmaps, present) where present[k] is False when no font had the glyph.
    """
    bitmaps = rasterize(chars, cell_w, cell_h, font_path)
    missing = _missing_mask(bitmaps, chars, cell_w, cell_h, font_path)
    for k, ch in enumerate(chars):
        drawn = synthesize(ch, cell_w, cell_h)
        if drawn is not None:
            bitmaps[k] = drawn
            missing[k] = False
    for fb in fallbacks:
        if not missing.any():
            break
        idx = np.nonzero(missing)[0]
        sub = "".join(chars[k] for k in idx)
        sub_bitmaps = rasterize(sub, cell_w, cell_h, fb)
        sub_missing = _missing_mask(sub_bitmaps, sub, cell_w, cell_h, fb)
        for j, k in enumerate(idx):
            if not sub_missing[j]:
                bitmaps[k] = sub_bitmaps[j]
                missing[k] = False
    return bitmaps, ~missing


def build_table(cell_w: int, cell_h: int, font_path: Path = DEFAULT_FONT, chars: str = PRINTABLE) -> GlyphTable:
    """Rasterise `chars`, drop missing glyphs and duplicates after binarisation, derive features.

    The space is always first, so index 0 is the blank glyph whatever the set. A
    character the font lacks is taken from the fallback fonts, and dropped when none
    has it, so a "missing glyph" box never becomes a candidate.
    """
    if not chars.startswith(" "):
        chars = " " + chars.replace(" ", "")
    bitmaps, present = rasterize_with_fallback(chars, cell_w, cell_h, font_path)
    keep: list[int] = []
    seen: set[bytes] = set()
    for k in range(len(chars)):
        if not present[k]:
            continue
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


_CACHE: dict[tuple[int, int, str, str], GlyphTable] = {}


def get_table(cell_w: int, cell_h: int, font_path: Path = DEFAULT_FONT, chars: str = PRINTABLE) -> GlyphTable:
    """Memoised `build_table`: rasterising a set takes a few milliseconds, once per (size, font, set)."""
    key = (cell_w, cell_h, str(font_path), chars)
    if key not in _CACHE:
        _CACHE[key] = build_table(cell_w, cell_h, font_path, chars)
    return _CACHE[key]
