# ASCII overlay

An always-on-top, resizable Windows window that redraws whatever lies under it as
black and white ASCII characters, up to 20 times a second. Move it over a video, a
game, a document: every 8x16 pixel block under the lens becomes the one printable
ASCII glyph whose displayed pixels best match it, in ink ratio **and** in position.

Every frame is also a text buffer: copy it, paste it anywhere.

## Run

```
run.bat
```

`run.bat` creates the venv and installs the dependencies on first launch. Manually:

```
python -m venv venv
venv\Scripts\activate
pip install PySide6 numpy pillow mss dxcam pytest
python -m ascii_overlay
```

Requires Windows 10 version 2004 (build 19041) or later: the overlay relies on
`WDA_EXCLUDEFROMCAPTURE`, which hides the window from every screen capture path
while it stays visible on the monitor. That is how the app reads the pixels under
itself without capturing its own output recursively.

## Controls

The window has a coloured border (grey, orange when frozen, red when click-through)
and a single-row top bar with every setting: preset cell size, character size in
pixels, character set, font, tone mode, black ink, negative, refresh rate,
gamma, exposure, freeze, click-through, copy, save, live stats, full screen and a
close button.
Drag the bar or the canvas to move the window, drag an edge to resize it. Right
click opens a menu with the same actions and their keys.

| Key | Action |
|---|---|
| `I` | Black ink: the same picture drawn as black glyphs on white instead of white on black |
| `N` | Negative: dark source pixels count as ink instead of bright ones (for light content such as documents) |
| `C` / `Shift+C` | Next / previous preset cell size (4x8, 6x12, 8x16, 12x24, 16x32) |
| `+` / `-` | Character one pixel taller / shorter, from 4 to 128 px (the *Size* box takes any value) |
| `K` / `Shift+K` | Next / previous character set (see *Character sets* below) |
| `O` / `Shift+O` | Next / previous font |
| `A` | Tone mode: auto (default) or literal ink ratio (see *Tone* below) |
| `G` / `Shift+G` | Gamma up / down (tone curve of the source) |
| `E` / `Shift+E` | Exposure up / down |
| `F` or double click | Freeze / resume |
| `R` | Refresh rate: 5, 10 or 20 Hz |
| `T` | Click-through: clicks and keys go to the window underneath the canvas |
| `Ctrl+Alt+A` | Global hotkey that toggles click-through from anywhere |
| `F11` | Full screen on the current monitor (`Esc` leaves it) |
| `Ctrl+C` | Copy the current frame as text |
| `S` | Save PNG + text to `Pictures\ascii_overlay` |
| `H` | Show / hide the HUD |
| `Esc` | Quit |

Settings (geometry, cell size, inversion, gamma, exposure, rate) persist between runs.

### Coming back from click-through

In click-through mode only the canvas lets input through. The border and the top
bar stay solid: move the mouse over the bar and the window takes input again, so
the *Click-through* button can be clicked off, the window moved, resized or closed.
Move the mouse back over the canvas and it is transparent again. `Ctrl+Alt+A`
toggles the mode from anywhere as well, since the canvas cannot receive keys while
it is transparent. The border is red while the mode is on.

## How it works

1. **Glyph table** (`glyphs.py`, pure). The 95 printable ASCII characters are
   rasterised from the bundled DejaVu Sans Mono into the cell size, binarised, and
   deduplicated. Any character height from 4 to 128 px works, the width follows the
   font's aspect; a table is built on first use of a size and cached. For each glyph we keep its displayed bitmap, its ink ratio, and a
   lightly blurred copy of the bitmap as its matching map.
2. **Capture** (`capture.py`). The client rectangle, in physical pixels, is grabbed
   with DXGI Desktop Duplication (`dxcam`, about 5 ms for 1280x720) when it lies on
   the primary monitor, else with GDI (`mss`, about 16 ms). Both are blind to the
   excluded window. Frames identical to the previous one are skipped.
3. **Matching** (`matcher.py`, pure numpy). Luminance, optional inversion, gamma,
   exposure and black point, then the frame is cut into cells and every cell is
   scored against every glyph with two terms:

   `shape = || blur(stretch(cell)) - blur(glyph) ||²`
   `tone  = D · (mean(cell) - ink(glyph) / ink(densest glyph))²`
   `score = c · shape + (1 - c) · w · tone`, with `c = sqrt(contrast of the cell)`

   Shape is where the ink is: the cell is contrast-stretched to [0, 1] and compared
   to the glyph bitmap, blurred so that a stroke one pixel off still scores well.
   Tone is how much ink: the cell's mean luminance against the glyph's density
   relative to the densest glyph, so black is the space, white the densest glyph
   and every grey a glyph in between. A crisp stroke (contrast 1) is decided by
   shape alone, so a displayed glyph always gives back itself; a flat area
   (contrast 0) by tone alone. The blur and the stretch are linear, so both are
   applied to the dot products: the whole match is one matrix product and the frame
   is never blurred. The pull-back of the blur is computed with the blur's adjoint,
   linear in the cell area, so a 64x128 cell costs no 268 MB matrix. A per-cell **hysteresis** keeps the previous glyph unless a new
   one wins by a margin, which removes the flicker that every ASCII video renderer
   shows on static content.
4. **Render**. The chosen bitmaps are gathered into one image that is strictly 0 or
   255, then blitted. No anti-aliasing anywhere.

Measured on this machine, 1280x720, Intel Iris Xe, single thread:

| Cell | Cells | Pipeline |
|---|---|---|
| 4x8 | 28 800 | 38 ms |
| 8x16 | 7 200 | 22 ms |
| 16x32 | 1 760 | 17 ms |

plus the capture. All fit the 50 ms budget of 20 Hz.

### Tone

No ASCII glyph is more than about 30 % ink (`M` in DejaVu Sans Mono at 8x16), so
tone has to be remapped. **Auto** (default) spreads black..white over space..`M`.
**Literal** keeps the exact ink ratio: a 15 % grey becomes a 15 % glyph, and
anything brighter than 30 % saturates to `M`. Exposure and gamma shape the curve in
both modes.

By default bright pixels are the ink, which suits screens, videos and dark themes.
Over a light document that gives a wall of dense glyphs: press `N` (*Negative*) so
that dark pixels are the ink instead; the white page becomes blank and the text
becomes glyphs. *Black ink* (`I`) is independent: it only swaps the two display
colours and never changes which glyphs are chosen.

### Character sets

| Set | Glyphs | Look |
|---|---|---|
| Full ASCII | the 95 printable characters | best shape fidelity, "random text" texture |
| Ramp 10 | ` .:-=+*#%@` | the classic density ramp |
| Ramp 70 | Paul Bourke's 70-character ramp | the usual converter look |
| Symbols | punctuation and slashes only | line drawing, crisp contours |
| Letters & digits | `A-Z a-z 0-9` | code-rain texture |
| Uppercase | `A-Z` | teletype |
| ASCII + blocks | printable ASCII plus `░▒▓█▀▄▌▐` and box drawing | ANSI art with text |
| CP437 blocks | shades, half blocks and box drawing only | BBS / DOS screens, ink up to 100 % |
| Quadrants | the 16 quarter-block combinations | a 2x2 mosaic per cell |
| Braille | the 255 dot patterns | a 2x4 bitmap per cell, maximum fidelity |

The last four are not ASCII. A glyph the chosen font lacks (braille in DejaVu Sans
Mono or Consolas, quadrants in Consolas) is taken from the bundled DejaVu Sans, then
from Segoe UI Symbol, fitted to the same cell; a glyph no font has is dropped instead
of showing up as a box. Every frame copies as text whatever the set, in UTF-8.

### Fonts

The bundled DejaVu Sans Mono, plus whatever is installed among Consolas, Cascadia
Mono, Lucida Console and Courier New. Drop `Px437_IBM_VGA_8x16.ttf` from the
Ultimate Oldschool PC Font Pack into `assets/` and it appears as *IBM VGA 8x16*: at
8x16 it is the exact DOS bitmap, with no binarisation loss.

## Tests

```
venv\Scripts\activate
python -m pytest -q
```

`tests/test_glyphs.py` and `tests/test_matcher.py` are pure and fast. Among them,
the identity test feeds the matcher the displayed pixels of every glyph and requires
that glyph back, at three cell sizes. `tests/test_app_gui.py` opens the real window
and checks capture exclusion, click-through, that a tick yields a two-colour image
of the canvas grid, and that the bar and the keys drive the same state. `tools/probe_exclusion.py` proves the exclusion mechanism
on a machine, `tools/bench.py` times the pipeline.

## Credits

Shape matching against full glyph bitmaps follows
[asciiplay](https://github.com/Fallen-Zen/asciiplay); the alignment tolerance is
the cheap form of the metric in *Structure-based ASCII Art* (Xu, Zhang, Wong,
SIGGRAPH 2010). Font: DejaVu Sans Mono (`assets/DEJAVU_LICENSE.txt`).
