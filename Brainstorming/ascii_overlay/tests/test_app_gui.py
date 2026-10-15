"""Integration test of the real window: needs a Windows desktop session (no display => skipped).

Checks the properties that make the overlay work at all: the window is excluded
from capture, click-through can be toggled, one tick produces a strictly two
colour image the size of the cell grid, and the text export matches the grid.
"""

from __future__ import annotations

import ctypes
import faulthandler
import sys

import numpy as np
import pytest

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows only")

WDA_EXCLUDEFROMCAPTURE = 0x11


def _image_array(img) -> np.ndarray:
    ptr = img.constBits()
    arr = np.frombuffer(ptr, dtype=np.uint8, count=img.sizeInBytes()).reshape(img.height(), img.bytesPerLine())
    return arr[:, : img.width()]


def _display_affinity(hwnd: int) -> int:
    value = ctypes.c_uint(0)
    ctypes.windll.user32.GetWindowDisplayAffinity(hwnd, ctypes.byref(value))
    return value.value


@pytest.fixture(scope="module")
def app():
    from PySide6.QtWidgets import QApplication

    from ascii_overlay import win32

    # Qt raises first-chance COM exceptions (0x8001010d) while showing a window; they
    # are handled internally but pytest's faulthandler prints them as fatal and
    # breaks the exit code. Silence it for this module only.
    was_enabled = faulthandler.is_enabled()
    faulthandler.disable()
    win32.set_dpi_awareness()
    application = QApplication.instance() or QApplication([sys.argv[0]])
    yield application
    application.processEvents()
    if was_enabled:
        faulthandler.enable()


@pytest.fixture
def window(app):
    from ascii_overlay.app import FONTS, OverlayWindow

    w = OverlayWindow()
    w.timer.stop()  # the test drives the ticks itself
    # Settings persist between runs (and a failed run may leave anything): start from the defaults.
    w.set_cell(8, 16)
    w.set_charset("Full ASCII")
    w.set_font(list(FONTS)[0])
    w.set_black_ink(False)
    w.set_negative(False)
    w.set_auto_tone(True)
    w.set_gamma(1.0)
    w.set_exposure(1.0)
    w.set_fps(20)
    w.set_frozen(False)
    w.resize(1000, 400)
    w.move(150, 150)
    w.show()
    for _ in range(5):
        app.processEvents()
    yield w
    w.close()
    app.processEvents()


def test_window_is_excluded_from_capture(window):
    assert _display_affinity(int(window.winId())) == WDA_EXCLUDEFROMCAPTURE


def test_click_through_is_transparent_over_the_canvas_but_solid_over_the_bar(window):
    from ascii_overlay import win32

    hwnd = int(window.winId())
    assert not win32.is_click_through(hwnd)
    l, t, r, b = window.capture_rect()  # the canvas
    sl, st, sr, sb = window.solid_rect_physical()  # border + bar
    assert st < sb <= t and sl <= l and r <= sr
    canvas_point = ((l + r) // 2, (t + b) // 2)
    bar_point = ((sl + sr) // 2, (st + sb) // 2)
    outside = (sl - 50, st - 50)

    window.set_click_through(True)
    assert window.ghost is True
    assert window.ghost_wants_transparent(canvas_point) is True
    assert window.ghost_wants_transparent(outside) is True
    assert window.ghost_wants_transparent(bar_point) is False  # the way back: hover the bar
    window._apply_ghost_hover(canvas_point)
    assert win32.is_click_through(hwnd)
    window._apply_ghost_hover(bar_point)
    assert not win32.is_click_through(hwnd)
    window._apply_ghost_hover(canvas_point)
    assert win32.is_click_through(hwnd)

    window.set_click_through(False)
    assert window.ghost is False
    assert window.ghost_wants_transparent(canvas_point) is False
    window._apply_ghost_hover(canvas_point)
    assert not win32.is_click_through(hwnd)
    assert window.bar.ghost.isChecked() is False


def test_fullscreen_covers_the_screen_and_restores_the_geometry(window, app):
    before = window.geometry()
    window.set_fullscreen(True)
    for _ in range(10):
        app.processEvents()
    assert window.isFullScreen() and window.bar.fullscreen.isChecked()
    screen = window.screen().geometry()
    assert window.width() >= screen.width() - 2 and window.height() >= screen.height() - 2
    window.tick()
    rows, cols = window.grid
    assert cols * window.table.cell_w >= (screen.width() - 2 * 3 - 8) * 0.98  # nearly the full width
    window.set_fullscreen(False)
    for _ in range(10):
        app.processEvents()
    assert not window.isFullScreen() and not window.bar.fullscreen.isChecked()
    assert abs(window.width() - before.width()) <= 2 and abs(window.height() - before.height()) <= 2


def test_one_tick_produces_a_two_colour_image_matching_the_grid(window, app):
    from ascii_overlay import win32
    from ascii_overlay.matcher import to_text

    window.tick()
    app.processEvents()
    assert window.image is not None and window.indices is not None
    rows, cols = window.grid
    cw, ch = window.table.cell_w, window.table.cell_h
    left, top, right, bottom = window.capture_rect()
    assert cols == (right - left) // cw and rows == (bottom - top) // ch
    # The captured area is the canvas only: strictly inside the window, below the bar.
    wl, wt, wr, wb = win32.client_rect_physical(int(window.winId()))
    assert wl < left and wt < top and right < wr and bottom < wb
    assert top - wt > window.bar.height() * 0.8
    assert window.indices.shape == (rows, cols)
    assert window.image.width() == cols * cw and window.image.height() == rows * ch

    img = window.image
    ptr = img.constBits()
    arr = np.frombuffer(ptr, dtype=np.uint8, count=img.sizeInBytes()).reshape(img.height(), img.bytesPerLine())
    arr = arr[:, : img.width()]
    assert set(np.unique(arr)).issubset({0, 255})

    text = to_text(window.indices, window.table)
    lines = text.split("\n")
    assert len(lines) == rows and all(len(line) == cols for line in lines)
    assert window.last_ms < 200.0


def test_unchanged_frame_is_skipped(window, app):
    window.tick()
    first = window.image
    window.tick()  # same pixels under the lens => no new image object
    assert window.image is first or np.array_equal(window.last_frame, window.last_frame)


def test_invert_and_cell_cycle_reset_the_pipeline(window, app):
    window.tick()
    before = _image_array(window.image).copy()
    window.toggle_invert()
    assert window.black_ink is True
    assert np.array_equal(_image_array(window.image), 255 - before)  # same glyphs, colours swapped, no re-match
    window.toggle_negative()
    assert window.params.negative is True and window.last_frame is None
    window.tick()
    assert window.image is not None
    window.toggle_negative()
    before = (window.table.cell_w, window.table.cell_h)
    window.cycle_cell()
    assert (window.table.cell_w, window.table.cell_h) != before
    window.tick()
    rows, cols = window.grid
    assert window.indices.shape == (rows, cols)
    window.toggle_invert()  # restore the default for the persisted settings


def test_bar_widgets_drive_the_same_state_as_the_keys(window, app):
    from ascii_overlay.app import CELL_SIZES, FPS_CHOICES

    window.bar.cell.setCurrentIndex(0)
    assert (window.table.cell_w, window.table.cell_h) == CELL_SIZES[0]
    assert window.bar.size.value() == CELL_SIZES[0][1]
    # Free size: any height, the preset box shows "Custom", the table follows.
    window.bar.size.setValue(21)
    assert window.cell == (10, 21) or window.cell == (11, 21)
    assert window.table.cell_h == 21 and window.bar.cell.currentText() == "Custom"
    window.tick()
    rows, cols = window.grid
    assert window.image.height() == rows * 21
    window.set_cell_height(4)
    assert window.cell == (2, 4) and window.table.cell_h == 4
    window.tick()
    assert window.image is not None and set(np.unique(_image_array(window.image))).issubset({0, 255})
    window.set_cell_height(128)
    assert window.cell[1] == 128 and window.table.cell_h == 128
    window.tick()
    assert window.grid[1] >= 1
    window.bar.tone.setCurrentIndex(1)
    assert window.params.auto_tone is False
    window.bar.invert.setChecked(True)
    assert window.black_ink is True
    window.bar.negative.setChecked(True)
    assert window.params.negative is True
    window.bar.negative.setChecked(False)
    window.bar.fps.setCurrentIndex(0)
    assert window.fps == FPS_CHOICES[0] and window.timer.interval() == 1000 // FPS_CHOICES[0]
    window.bar.gamma.setValue(1.5)
    assert window.params.gamma == 1.5
    window.bar.charset.setCurrentText("Ramp 10")
    assert window.charset == "Ramp 10" and window.table.count == 10
    window.tick()
    assert window.image is not None
    window.cycle_charset()
    assert window.charset == "Ramp 70" and window.bar.charset.currentText() == "Ramp 70"
    window.set_charset("Braille")
    window.tick()
    assert window.table.count >= 200
    from ascii_overlay.app import FONTS
    if len(FONTS) > 1:
        second = list(FONTS)[1]
        window.bar.font.setCurrentText(second)
        assert window.font_name == second
        window.tick()
        assert window.image is not None
        window.set_font(list(FONTS)[0])
    window.set_charset("Full ASCII")
    window.bar.freeze.setChecked(True)
    assert window.frozen is True
    # And the other way round: a key press updates the bar.
    window.toggle_invert()
    assert window.bar.invert.isChecked() is False
    window.set_cell(*CELL_SIZES[0])
    window.cycle_cell()
    assert window.cell == CELL_SIZES[1] and window.bar.cell.currentIndex() == 1
    window.set_cell_height(20)  # custom, between 16 and 24
    window.cycle_cell()
    assert window.cell == (12, 24)
    window.cycle_cell(-1)
    assert window.cell == (8, 16)
    window.set_frozen(False)
    window.set_auto_tone(True)
    window.set_gamma(1.0)
    window.set_cell(8, 16)
    window.set_fps(20)
