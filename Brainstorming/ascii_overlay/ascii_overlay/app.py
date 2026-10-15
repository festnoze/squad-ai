"""The overlay window: always on top, frameless, resizable, refreshed up to 20 times a second.

Layout: a coloured border, a top bar with every setting, and below it the ASCII
canvas. Only the canvas rectangle is captured; the window itself is excluded from
capture, so what is read is what lies under it.
"""

from __future__ import annotations

import sys
import time
from datetime import datetime
from pathlib import Path

import numpy as np
from PySide6.QtCore import QPoint, QRect, QSettings, QStandardPaths, Qt, QTimer
from PySide6.QtGui import QAction, QColor, QFont, QImage, QKeySequence, QMouseEvent, QPainter
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDoubleSpinBox,
    QHBoxLayout,
    QLabel,
    QMenu,
    QPushButton,
    QSizePolicy,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from . import win32
from .capture import Capture
from .glyphs import (
    CELL_SIZES,
    CHARSETS,
    DEFAULT_CHARSET,
    DEFAULT_FONT_NAME,
    FONTS,
    MAX_CELL_HEIGHT,
    MIN_CELL_HEIGHT,
    GlyphTable,
    cell_for_height,
    get_table,
)
from .matcher import MatchParams, MatchState, frame_to_indices, render, to_text

APP_NAME = "ascii_overlay"
HOTKEY_SOLID_ID = 1
VK_A = 0x41
BORDER = 3  # logical pixels
RESIZE_MARGIN = 10  # logical pixels
FPS_CHOICES = (5, 10, 20)
GAMMA_STEPS = (0.5, 0.7, 0.85, 1.0, 1.2, 1.5, 2.0)
EXPOSURE_STEPS = (0.2, 0.3, 0.4, 0.55, 0.7, 0.85, 1.0, 1.3, 1.6, 2.0)

COLOR_BORDER = QColor(90, 90, 90)
COLOR_BORDER_FROZEN = QColor(230, 160, 40)
COLOR_BORDER_GHOST = QColor(200, 60, 60)

BAR_STYLE = """
QWidget#bar { background: #202020; }
QLabel { color: #c8c8c8; font: 9pt 'Segoe UI'; }
QPushButton, QComboBox, QDoubleSpinBox, QSpinBox {
    color: #e6e6e6; background: #333; border: 1px solid #555; border-radius: 3px;
    padding: 1px 5px; min-height: 20px; font: 9pt 'Segoe UI';
}
QPushButton:hover, QComboBox:hover, QDoubleSpinBox:hover, QSpinBox:hover { background: #3d3d3d; }
QPushButton:checked { background: #2d6cdf; border-color: #4b86ea; }
QPushButton#close { color: #f0f0f0; font-weight: bold; padding: 1px 8px; }
QPushButton#close:hover { background: #c0392b; }
QComboBox QAbstractItemView { background: #2a2a2a; color: #e6e6e6; selection-background-color: #2d6cdf; }
QDoubleSpinBox::up-button, QDoubleSpinBox::down-button, QSpinBox::up-button, QSpinBox::down-button { width: 12px; }
"""


def _step(values: tuple[float, ...], current: float, step: int) -> float:
    cur = min(range(len(values)), key=lambda i: abs(values[i] - current))
    return values[max(0, min(len(values) - 1, cur + step))]


class TopBar(QWidget):
    """Every setting as a widget. Reads from and writes to the window; never owns state."""

    def __init__(self, window: OverlayWindow) -> None:
        super().__init__(window)
        self.window_ = window
        self.setObjectName("bar")
        self.setAutoFillBackground(True)
        self.setStyleSheet(BAR_STYLE)
        self.setMouseTracking(True)
        # One single row: no separate labels, every control shows its own value
        # (a prefix or a suffix where a bare number would be ambiguous).
        lay = QHBoxLayout(self)
        lay.setContentsMargins(4, 2, 4, 2)
        lay.setSpacing(4)

        self.cell = QComboBox()
        for cw, ch in CELL_SIZES:
            self.cell.addItem(f"{cw}x{ch}")
        self.cell.addItem("Custom")
        self.cell.setToolTip("Cell: preset sizes (C / Shift+C)")
        self.cell.currentIndexChanged.connect(self._preset_chosen)
        lay.addWidget(self.cell)

        self.size = QSpinBox()
        self.size.setRange(MIN_CELL_HEIGHT, MAX_CELL_HEIGHT)
        self.size.setSuffix(" px")
        self.size.setToolTip(
            f"Character height in pixels, {MIN_CELL_HEIGHT} to {MAX_CELL_HEIGHT}; the width follows the font (+ / -).\n"
            "Small: more characters, finer picture. Large: fewer, bigger characters."
        )
        self.size.valueChanged.connect(window.set_cell_height)
        lay.addWidget(self.size)

        self.charset = QComboBox()
        self.charset.addItems(list(CHARSETS))
        self.charset.setToolTip(
            "Character set (K / Shift+K).\n"
            "The first six are pure ASCII; blocks, quadrants and braille are drawn or taken from a fallback font."
        )
        self.charset.currentTextChanged.connect(window.set_charset)
        lay.addWidget(self.charset)

        self.font = QComboBox()
        self.font.addItems(list(FONTS))
        self.font.setToolTip("Font the glyphs are rasterised from (O / Shift+O)")
        self.font.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.font.setMinimumContentsLength(12)
        self.font.setMaximumWidth(170)
        self.font.currentTextChanged.connect(window.set_font)
        lay.addWidget(self.font)

        self.tone = QComboBox()
        self.tone.addItems(["Auto tone", "Literal"])
        self.tone.setToolTip("Auto: black is the space, white the densest glyph.\nLiteral: exact ink ratio (A).")
        self.tone.currentIndexChanged.connect(lambda i: window.set_auto_tone(i == 0))
        lay.addWidget(self.tone)

        self.invert = QPushButton("Black ink")
        self.invert.setCheckable(True)
        self.invert.setToolTip("Draw the same picture as black glyphs on white instead of white on black (I)")
        self.invert.toggled.connect(window.set_black_ink)
        lay.addWidget(self.invert)

        self.negative = QPushButton("Negative")
        self.negative.setCheckable(True)
        self.negative.setToolTip(
            "Dark pixels count as ink instead of bright ones (N).\n"
            "Use it over light content such as documents: the white page becomes blank and the text becomes glyphs."
        )
        self.negative.toggled.connect(window.set_negative)
        lay.addWidget(self.negative)

        self.gamma = QDoubleSpinBox()
        self.gamma.setRange(0.2, 4.0)
        self.gamma.setSingleStep(0.1)
        self.gamma.setDecimals(2)
        self.gamma.setPrefix("\u03b3 ")
        self.gamma.setToolTip("Gamma: tone curve of the source, above 1 darkens (G / Shift+G)")
        self.gamma.valueChanged.connect(window.set_gamma)
        lay.addWidget(self.gamma)

        self.exposure = QDoubleSpinBox()
        self.exposure.setRange(0.1, 4.0)
        self.exposure.setSingleStep(0.1)
        self.exposure.setDecimals(2)
        self.exposure.setPrefix("exp ")
        self.exposure.setToolTip("Exposure: multiplies the source luminance (E / Shift+E)")
        self.exposure.valueChanged.connect(window.set_exposure)
        lay.addWidget(self.exposure)

        self.fps = QComboBox()
        self.fps.addItems([f"{f} Hz" for f in FPS_CHOICES])
        self.fps.setToolTip("Refresh rate (R)")
        self.fps.currentIndexChanged.connect(lambda i: window.set_fps(FPS_CHOICES[i]))
        lay.addWidget(self.fps)

        self.freeze = QPushButton("Freeze")
        self.freeze.setCheckable(True)
        self.freeze.setToolTip("Stop refreshing (F, or double click the canvas)")
        self.freeze.toggled.connect(window.set_frozen)
        lay.addWidget(self.freeze)

        self.ghost = QPushButton("Click-thru")
        self.ghost.setCheckable(True)
        self.ghost.setToolTip(
            "Click-through: clicks and keys go to the window underneath the canvas (T).\n"
            "This bar stays clickable: hover it to get the controls back, or press Ctrl+Alt+A."
        )
        self.ghost.toggled.connect(window.set_click_through)
        lay.addWidget(self.ghost)

        self.copy = QPushButton("Copy")
        self.copy.setToolTip("Copy the frame as text (Ctrl+C)")
        self.copy.clicked.connect(window.copy_text)
        lay.addWidget(self.copy)

        self.save = QPushButton("Save")
        self.save.setToolTip("Save PNG + text to Pictures\\ascii_overlay (S)")
        self.save.clicked.connect(window.save_frame)
        lay.addWidget(self.save)

        lay.addStretch(1)
        self.stats = QLabel("")
        self.stats.setToolTip("columns x rows  |  glyphs in the set  |  pipeline time (the HUD, H, shows more)")
        # Reserve the room the widest stats text can need, so the window's minimum
        # width (derived from this bar's size hint) never squeezes the other controls.
        self.stats.setMinimumWidth(self.stats.fontMetrics().horizontalAdvance("9999x999 · 999 · 99 ms") + 8)
        lay.addWidget(self.stats)

        self.fullscreen = QPushButton("\u26f6")
        self.fullscreen.setCheckable(True)
        self.fullscreen.setToolTip("Full screen on the current monitor (F11)")
        self.fullscreen.toggled.connect(window.set_fullscreen)
        lay.addWidget(self.fullscreen)

        self.close_btn = QPushButton("\u2715")
        self.close_btn.setObjectName("close")
        self.close_btn.setToolTip("Quit (Esc)")
        self.close_btn.clicked.connect(window.close)
        lay.addWidget(self.close_btn)

        for w in self.findChildren(QWidget):
            w.setFocusPolicy(Qt.NoFocus)  # keys stay with the window
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def _preset_chosen(self, index: int) -> None:
        if 0 <= index < len(CELL_SIZES):
            self.window_.set_cell(*CELL_SIZES[index])
        else:
            self.refresh()  # "Custom" is a display state, not a choice

    def refresh(self) -> None:
        w = self.window_
        widgets = (
            self.cell, self.size, self.charset, self.font, self.tone, self.invert, self.negative, self.fps,
            self.gamma, self.exposure, self.freeze, self.ghost, self.fullscreen,
        )
        for widget in widgets:
            widget.blockSignals(True)
        self.cell.setCurrentIndex(CELL_SIZES.index(w.cell) if w.cell in CELL_SIZES else len(CELL_SIZES))
        self.size.setValue(w.cell[1])
        self.charset.setCurrentText(w.charset)
        self.font.setCurrentText(w.font_name)
        self.tone.setCurrentIndex(0 if w.params.auto_tone else 1)
        self.invert.setChecked(w.black_ink)
        self.negative.setChecked(w.params.negative)
        self.fps.setCurrentIndex(FPS_CHOICES.index(w.fps))
        self.gamma.setValue(w.params.gamma)
        self.exposure.setValue(w.params.exposure)
        self.freeze.setChecked(w.frozen)
        self.ghost.setChecked(w.ghost)
        self.ghost.setText("Click-thru ON" if w.ghost else "Click-thru")
        self.fullscreen.setChecked(w.isFullScreen())
        for widget in widgets:
            widget.blockSignals(False)
        self.stats.setText(w.stats_text())

    # The bar's empty area moves the window like a title bar.
    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.LeftButton:
            self.window_.begin_drag(event.globalPosition().toPoint())

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        self.window_.update_cursor(event.globalPosition().toPoint(), self)

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        pass  # a title-bar double click must not toggle freeze


class AsciiCanvas(QWidget):
    """Paints the current ASCII image and the optional HUD; forwards mouse to the window."""

    def __init__(self, window: OverlayWindow) -> None:
        super().__init__(window)
        self.window_ = window
        self.setAttribute(Qt.WA_OpaquePaintEvent, True)
        self.setMouseTracking(True)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setMinimumSize(64, 32)

    def paintEvent(self, event) -> None:  # noqa: N802
        w = self.window_
        p = QPainter(self)
        bg = QColor(255, 255, 255) if w.black_ink else QColor(0, 0, 0)
        p.fillRect(self.rect(), bg)
        if w.image is not None:
            img = w.image
            img.setDevicePixelRatio(self.devicePixelRatioF())
            p.drawImage(QPoint(0, 0), img)
        if w.show_hud:
            self._paint_hud(p)
        p.end()

    def _paint_hud(self, p: QPainter) -> None:
        w = self.window_
        rows, cols = w.grid
        line = (
            f"{cols}x{rows} cells of {w.table.cell_w}x{w.table.cell_h}  |  {w.last_ms:.1f} ms "
            f"(capture {w.last_capture_ms:.1f})  |  {w.capture.last_backend}  |  {w.fps} Hz"
        )
        p.setFont(QFont("Consolas", 9))
        metrics = p.fontMetrics()
        pad = 5
        box = QRect(6, 6, metrics.horizontalAdvance(line) + 2 * pad, metrics.height() + 2 * pad)
        p.fillRect(box, QColor(20, 20, 20, 210))
        p.setPen(QColor(230, 230, 230))
        p.drawText(box.left() + pad, box.top() + pad + metrics.ascent(), line)

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.LeftButton:
            self.window_.begin_drag(event.globalPosition().toPoint())

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        self.window_.update_cursor(event.globalPosition().toPoint(), self)

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        self.window_.toggle_freeze()


class OverlayWindow(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("ASCII overlay")
        self.setWindowFlags(Qt.Window | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_OpaquePaintEvent, True)
        self.setMouseTracking(True)

        self.settings = QSettings(APP_NAME, APP_NAME)
        self.params = MatchParams()
        self.params.gamma = float(self.settings.value("gamma", 1.0))
        self.params.exposure = float(self.settings.value("exposure", 1.0))
        self.black_ink = self.settings.value("black_ink", False, type=bool)  # display colours only
        self.params.negative = self.settings.value("negative", False, type=bool)
        self.params.hysteresis = float(self.settings.value("hysteresis", 0.04))
        self.params.tone_weight = float(self.settings.value("tone_weight", MatchParams.tone_weight))
        self.params.auto_tone = self.settings.value("auto_tone", True, type=bool)
        self.cell: tuple[int, int] = cell_for_height(int(self.settings.value("cell_height", 16)))
        self.charset: str = str(self.settings.value("charset", DEFAULT_CHARSET))
        if self.charset not in CHARSETS:
            self.charset = DEFAULT_CHARSET
        self.font_name: str = str(self.settings.value("font", DEFAULT_FONT_NAME))
        if self.font_name not in FONTS:
            self.font_name = next(iter(FONTS))
        self.fps = int(self.settings.value("fps", 20))
        if self.fps not in FPS_CHOICES:
            self.fps = 20
        self.show_hud = self.settings.value("hud", False, type=bool)

        self.table: GlyphTable = self._build_table()
        self.state = MatchState()
        self.capture = Capture()
        self.frozen = False
        self.image: QImage | None = None
        self.indices: np.ndarray | None = None
        self.last_frame: np.ndarray | None = None
        self.last_ms = 0.0
        self.last_capture_ms = 0.0
        self.grid = (0, 0)
        self._hotkey_ok = False
        self.ghost = False  # wanted click-through state; the window turns solid while the bar is hovered
        self._normal_geometry = None

        self.bar = TopBar(self)
        self.canvas = AsciiCanvas(self)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(BORDER, BORDER, BORDER, BORDER)
        lay.setSpacing(0)
        lay.addWidget(self.bar)
        lay.addWidget(self.canvas, 1)
        self.setMinimumWidth(self.bar.sizeHint().width() + 2 * BORDER)
        self.setMinimumHeight(self.bar.sizeHint().height() + 2 * BORDER + 64)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.timer.start(1000 // self.fps)

        geo = self.settings.value("geometry")
        if geo is not None:
            self.restoreGeometry(geo)
        else:
            self.resize(1000, 600)
        self.bar.refresh()

    # ------------------------------------------------------------------ lifecycle

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        hwnd = int(self.winId())
        if not win32.exclude_from_capture(hwnd, True):
            print("WARNING: SetWindowDisplayAffinity failed; the overlay would capture itself.", file=sys.stderr)
        if not self._hotkey_ok:
            self._hotkey_ok = win32.register_hotkey(hwnd, HOTKEY_SOLID_ID, win32.MOD_CONTROL | win32.MOD_ALT, VK_A)
            if not self._hotkey_ok:
                print("WARNING: global hotkey Ctrl+Alt+A could not be registered.", file=sys.stderr)

    def closeEvent(self, event) -> None:  # noqa: N802
        self.timer.stop()
        hwnd = int(self.winId())
        if self._hotkey_ok:
            win32.unregister_hotkey(hwnd, HOTKEY_SOLID_ID)
        s = self.settings
        s.setValue("geometry", self.saveGeometry())
        s.setValue("gamma", self.params.gamma)
        s.setValue("exposure", self.params.exposure)
        s.setValue("black_ink", self.black_ink)
        s.setValue("negative", self.params.negative)
        s.setValue("hysteresis", self.params.hysteresis)
        s.setValue("tone_weight", self.params.tone_weight)
        s.setValue("auto_tone", self.params.auto_tone)
        s.setValue("cell_height", self.cell[1])
        s.setValue("charset", self.charset)
        s.setValue("font", self.font_name)
        s.setValue("fps", self.fps)
        s.setValue("hud", self.show_hud)
        self.capture.close()
        super().closeEvent(event)

    def nativeEvent(self, event_type, message):  # noqa: N802
        # Global hotkey: the only way back once the window is click-through.
        if event_type in (b"windows_generic_MSG", "windows_generic_MSG"):
            import ctypes
            from ctypes import wintypes

            msg = ctypes.cast(int(message), ctypes.POINTER(wintypes.MSG)).contents
            if msg.message == win32.WM_HOTKEY and msg.wParam == HOTKEY_SOLID_ID:
                self.toggle_click_through()
                return True, 0
        return super().nativeEvent(event_type, message)

    # ------------------------------------------------------------------ pipeline

    def capture_rect(self) -> tuple[int, int, int, int]:
        """The canvas rectangle in physical screen pixels: (left, top, right, bottom)."""
        left, top, _right, _bottom = win32.client_rect_physical(int(self.winId()))
        dpr = self.devicePixelRatioF()
        off = self.canvas.mapTo(self, QPoint(0, 0))
        x = left + round(off.x() * dpr)
        y = top + round(off.y() * dpr)
        return x, y, x + round(self.canvas.width() * dpr), y + round(self.canvas.height() * dpr)

    def tick(self) -> None:
        if not self.isVisible():
            return
        if self.ghost:
            self._apply_ghost_hover(win32.cursor_pos())
        if self.frozen:
            return
        rect = self.capture_rect()
        w, h = rect[2] - rect[0], rect[3] - rect[1]
        cw, ch = self.table.cell_w, self.table.cell_h
        cols, rows = w // cw, h // ch
        if cols <= 0 or rows <= 0:
            return
        grid_rect = (rect[0], rect[1], rect[0] + cols * cw, rect[1] + rows * ch)

        t0 = time.perf_counter()
        frame = self.capture.grab(grid_rect)
        t1 = time.perf_counter()
        if frame is None:
            return
        if (
            self.last_frame is not None
            and self.last_frame.shape == frame.shape
            and self.grid == (rows, cols)
            and np.array_equal(self.last_frame, frame)
        ):
            return  # nothing changed under the lens
        self.last_frame = frame.copy()
        self.grid = (rows, cols)

        self.indices = frame_to_indices(frame, self.table, self.params, self.state)
        img = render(self.indices, self.table, self.black_ink)
        self.image = QImage(img.data, img.shape[1], img.shape[0], img.shape[1], QImage.Format_Grayscale8).copy()
        self.last_ms = (time.perf_counter() - t0) * 1000.0
        self.last_capture_ms = (t1 - t0) * 1000.0
        self.canvas.update()
        self.bar.stats.setText(self.stats_text())

    def stats_text(self) -> str:
        rows, cols = self.grid
        return f"{cols}x{rows} \u00b7 {self.table.count} \u00b7 {self.last_ms:.0f} ms"

    def force_refresh(self) -> None:
        """Forget the last frame and the last match: the next tick rebuilds everything."""
        self.last_frame = None
        self.indices = None  # they index the previous glyph table, which may have changed
        self.state.reset()
        self.bar.refresh()
        self.update()
        self.canvas.update()

    # ------------------------------------------------------------------ painting

    def paintEvent(self, event) -> None:  # noqa: N802
        p = QPainter(self)
        if self.frozen:
            color = COLOR_BORDER_FROZEN
        elif self.ghost:
            color = COLOR_BORDER_GHOST
        else:
            color = COLOR_BORDER
        p.fillRect(self.rect(), color)
        p.end()

    # ------------------------------------------------------------------ setters (bar + keys)

    def _build_table(self) -> GlyphTable:
        return get_table(*self.cell, FONTS[self.font_name], CHARSETS[self.charset])

    def set_cell(self, width: int, height: int) -> None:
        """Any cell size; the glyph table for it is built on first use and cached."""
        cell = (max(2, int(width)), max(MIN_CELL_HEIGHT, min(MAX_CELL_HEIGHT, int(height))))
        if cell == self.cell and self.table.cell_h == cell[1]:
            self.bar.refresh()
            return
        self.cell = cell
        self.table = self._build_table()
        self.force_refresh()

    def set_charset(self, name: str) -> None:
        if name not in CHARSETS:
            return
        self.charset = name
        self.table = self._build_table()
        self.force_refresh()

    def cycle_charset(self, step: int = 1) -> None:
        names = list(CHARSETS)
        self.set_charset(names[(names.index(self.charset) + step) % len(names)])

    def set_font(self, name: str) -> None:
        if name not in FONTS:
            return
        self.font_name = name
        self.table = self._build_table()
        self.force_refresh()

    def cycle_font(self, step: int = 1) -> None:
        names = list(FONTS)
        self.set_font(names[(names.index(self.font_name) + step) % len(names)])

    def set_cell_height(self, height: int) -> None:
        self.set_cell(*cell_for_height(height))

    def cycle_cell(self, step: int = 1) -> None:
        """Next / previous preset; from a custom size, the nearest preset in that direction."""
        heights = [h for _, h in CELL_SIZES]
        cur = self.cell[1]
        if step >= 0:
            bigger = [h for h in heights if h > cur]
            target = bigger[0] if bigger else heights[0]
        else:
            smaller = [h for h in heights if h < cur]
            target = smaller[-1] if smaller else heights[-1]
        self.set_cell(*CELL_SIZES[heights.index(target)])

    def set_auto_tone(self, enabled: bool) -> None:
        self.params.auto_tone = bool(enabled)
        self.force_refresh()

    def toggle_auto_tone(self) -> None:
        self.set_auto_tone(not self.params.auto_tone)

    def set_black_ink(self, enabled: bool) -> None:
        """Swap the display colours only: the chosen glyphs stay the same."""
        self.black_ink = bool(enabled)
        if self.indices is not None and int(self.indices.max()) < self.table.count:
            img = render(self.indices, self.table, self.black_ink)
            self.image = QImage(img.data, img.shape[1], img.shape[0], img.shape[1], QImage.Format_Grayscale8).copy()
        self.bar.refresh()
        self.canvas.update()

    def toggle_invert(self) -> None:
        self.set_black_ink(not self.black_ink)

    def set_negative(self, enabled: bool) -> None:
        """Which source pixels are ink: bright (screens) or dark (documents). Re-matches the frame."""
        self.params.negative = bool(enabled)
        self.force_refresh()

    def toggle_negative(self) -> None:
        self.set_negative(not self.params.negative)

    def set_gamma(self, value: float) -> None:
        self.params.gamma = float(value)
        self.force_refresh()

    def step_gamma(self, step: int) -> None:
        self.set_gamma(_step(GAMMA_STEPS, self.params.gamma, step))

    def set_exposure(self, value: float) -> None:
        self.params.exposure = float(value)
        self.force_refresh()

    def step_exposure(self, step: int) -> None:
        self.set_exposure(_step(EXPOSURE_STEPS, self.params.exposure, step))

    def set_fps(self, fps: int) -> None:
        self.fps = fps if fps in FPS_CHOICES else 20
        self.timer.setInterval(1000 // self.fps)
        self.bar.refresh()

    def cycle_fps(self) -> None:
        self.set_fps(FPS_CHOICES[(FPS_CHOICES.index(self.fps) + 1) % len(FPS_CHOICES)])

    def set_frozen(self, frozen: bool) -> None:
        self.frozen = bool(frozen)
        self.bar.refresh()
        self.update()

    def toggle_freeze(self) -> None:
        self.set_frozen(not self.frozen)

    # ------------------------------------------------------------------ click-through

    def solid_rect_physical(self) -> tuple[int, int, int, int]:
        """The part of the window that stays clickable in click-through mode: border + top bar."""
        left, top, right, _bottom = win32.client_rect_physical(int(self.winId()))
        dpr = self.devicePixelRatioF()
        bar_bottom = self.bar.mapTo(self, QPoint(0, self.bar.height())).y()
        return left, top, right, top + round(bar_bottom * dpr)

    def ghost_wants_transparent(self, cursor: tuple[int, int]) -> bool:
        """In click-through mode the window is transparent to input unless the cursor is over the bar."""
        if not self.ghost:
            return False
        l, t, r, b = self.solid_rect_physical()
        x, y = cursor
        return not (l <= x < r and t <= y < b)

    def _apply_ghost_hover(self, cursor: tuple[int, int]) -> None:
        hwnd = int(self.winId())
        want = self.ghost_wants_transparent(cursor)
        if win32.is_click_through(hwnd) != want:
            win32.set_click_through(hwnd, want)

    def set_click_through(self, enabled: bool) -> None:
        self.ghost = bool(enabled)
        self._apply_ghost_hover(win32.cursor_pos())
        self.bar.refresh()
        self.update()

    def toggle_click_through(self) -> None:
        self.set_click_through(not self.ghost)

    # ------------------------------------------------------------------ full screen

    def set_fullscreen(self, enabled: bool) -> None:
        if bool(enabled) == self.isFullScreen():
            self.bar.refresh()
            return
        if enabled:
            self._normal_geometry = self.saveGeometry()
            self.showFullScreen()
        else:
            self.showNormal()
            if self._normal_geometry is not None:
                self.restoreGeometry(self._normal_geometry)
        self.last_frame = None
        self.bar.refresh()

    def toggle_fullscreen(self) -> None:
        self.set_fullscreen(not self.isFullScreen())

    def toggle_hud(self) -> None:
        self.show_hud = not self.show_hud
        self.canvas.update()

    def copy_text(self) -> None:
        if self.indices is not None:
            QApplication.clipboard().setText(to_text(self.indices, self.table))

    def save_frame(self) -> None:
        if self.indices is None or self.image is None:
            return
        base = Path(QStandardPaths.writableLocation(QStandardPaths.PicturesLocation)) / APP_NAME
        base.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.image.save(str(base / f"ascii_{stamp}.png"))
        (base / f"ascii_{stamp}.txt").write_text(to_text(self.indices, self.table), encoding="utf-8")

    # ------------------------------------------------------------------ input

    def keyPressEvent(self, event) -> None:  # noqa: N802
        key, mods = event.key(), event.modifiers()
        shift = bool(mods & Qt.ShiftModifier)
        if key == Qt.Key_Escape:
            if self.isFullScreen():
                self.set_fullscreen(False)
            else:
                self.close()
        elif key == Qt.Key_F11:
            self.toggle_fullscreen()
        elif key == Qt.Key_I:
            self.toggle_invert()
        elif key == Qt.Key_N:
            self.toggle_negative()
        elif key == Qt.Key_C and mods & Qt.ControlModifier:
            self.copy_text()
        elif key == Qt.Key_C:
            self.cycle_cell(-1 if shift else 1)
        elif key == Qt.Key_K:
            self.cycle_charset(-1 if shift else 1)
        elif key == Qt.Key_O:
            self.cycle_font(-1 if shift else 1)
        elif key in (Qt.Key_Plus, Qt.Key_Equal):
            self.set_cell_height(self.cell[1] + 1)
        elif key in (Qt.Key_Minus, Qt.Key_Underscore):
            self.set_cell_height(self.cell[1] - 1)
        elif key == Qt.Key_G:
            self.step_gamma(-1 if shift else 1)
        elif key == Qt.Key_E:
            self.step_exposure(-1 if shift else 1)
        elif key == Qt.Key_A:
            self.toggle_auto_tone()
        elif key == Qt.Key_F:
            self.toggle_freeze()
        elif key == Qt.Key_T:
            self.toggle_click_through()
        elif key == Qt.Key_R:
            self.cycle_fps()
        elif key == Qt.Key_S:
            self.save_frame()
        elif key == Qt.Key_H:
            self.toggle_hud()
        else:
            super().keyPressEvent(event)

    def _edges_at(self, pos: QPoint) -> Qt.Edges:
        """Resize edges for a position in window coordinates."""
        edges = Qt.Edges()
        r = self.rect()
        if pos.x() <= RESIZE_MARGIN:
            edges |= Qt.LeftEdge
        if pos.x() >= r.width() - RESIZE_MARGIN:
            edges |= Qt.RightEdge
        if pos.y() <= RESIZE_MARGIN:
            edges |= Qt.TopEdge
        if pos.y() >= r.height() - RESIZE_MARGIN:
            edges |= Qt.BottomEdge
        return edges

    @staticmethod
    def _cursor_for(edges: Qt.Edges) -> Qt.CursorShape:
        horizontal = bool(edges & (Qt.LeftEdge | Qt.RightEdge))
        vertical = bool(edges & (Qt.TopEdge | Qt.BottomEdge))
        if horizontal and vertical:
            tl = bool(edges & Qt.LeftEdge) == bool(edges & Qt.TopEdge)
            return Qt.SizeFDiagCursor if tl else Qt.SizeBDiagCursor
        if horizontal:
            return Qt.SizeHorCursor
        if vertical:
            return Qt.SizeVerCursor
        return Qt.ArrowCursor

    def begin_drag(self, global_pos: QPoint) -> None:
        """Left press anywhere: resize when near an edge, else move the window."""
        edges = self._edges_at(self.mapFromGlobal(global_pos))
        handle = self.windowHandle()
        if handle is None:
            return
        if edges:
            handle.startSystemResize(edges)
        else:
            handle.startSystemMove()

    def update_cursor(self, global_pos: QPoint, widget: QWidget) -> None:
        widget.setCursor(self._cursor_for(self._edges_at(self.mapFromGlobal(global_pos))))

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.LeftButton:
            self.begin_drag(event.globalPosition().toPoint())

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        self.update_cursor(event.globalPosition().toPoint(), self)

    def contextMenuEvent(self, event) -> None:  # noqa: N802
        menu = QMenu(self)

        def add(text: str, slot, shortcut: str | None = None) -> None:
            act = QAction(text, menu)
            if shortcut:
                act.setShortcut(QKeySequence(shortcut))
            act.triggered.connect(slot)
            menu.addAction(act)

        add("White ink on black" if self.black_ink else "Black ink on white", self.toggle_invert, "I")
        add("Bright pixels are ink" if self.params.negative else "Negative: dark pixels are ink", self.toggle_negative, "N")
        add(f"Next preset cell size (now {self.table.cell_w}x{self.table.cell_h})", self.cycle_cell, "C")
        add("Character one pixel taller", lambda: self.set_cell_height(self.cell[1] + 1), "+")
        add("Character one pixel shorter", lambda: self.set_cell_height(self.cell[1] - 1), "-")
        add(f"Next character set (now {self.charset})", self.cycle_charset, "K")
        add(f"Next font (now {self.font_name})", self.cycle_font, "O")
        add("Literal ink ratio" if self.params.auto_tone else "Auto tone (black..white)", self.toggle_auto_tone, "A")
        add("Gamma +", lambda: self.step_gamma(1), "G")
        add("Gamma -", lambda: self.step_gamma(-1), "Shift+G")
        add("Exposure +", lambda: self.step_exposure(1), "E")
        add("Exposure -", lambda: self.step_exposure(-1), "Shift+E")
        add("Resume" if self.frozen else "Freeze", self.toggle_freeze, "F")
        add(f"Refresh rate (now {self.fps} Hz)", self.cycle_fps, "R")
        add(
            "Click-through off" if self.ghost else "Click-through (hover the bar or Ctrl+Alt+A to come back)",
            self.toggle_click_through,
            "T",
        )
        add("Exit full screen" if self.isFullScreen() else "Full screen", self.toggle_fullscreen, "F11")
        menu.addSeparator()
        add("Copy frame as text", self.copy_text, "Ctrl+C")
        add("Save PNG + text", self.save_frame, "S")
        add("Hide HUD" if self.show_hud else "Show HUD", self.toggle_hud, "H")
        menu.addSeparator()
        add("Quit", self.close, "Esc")
        # The window is solid while the menu is open (a right click reached us), keep it so.
        menu.exec(event.globalPos())

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self.last_frame = None


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(prog="ascii_overlay", description="Always-on-top ASCII lens for Windows.")
    parser.add_argument("--shot", metavar="PNG", help="save the overlay's own rendering to this file, then quit")
    parser.add_argument("--after", type=float, default=2.0, help="seconds to wait before --shot (default 2)")
    parser.add_argument("--geometry", metavar="WxH+X+Y", help="initial window geometry, e.g. 960x544+100+100")
    args, qt_args = parser.parse_known_args(argv if argv is not None else sys.argv[1:])

    win32.set_dpi_awareness()
    app = QApplication([sys.argv[0], *qt_args])
    app.setApplicationName(APP_NAME)
    window = OverlayWindow()
    if args.geometry:
        size, _, pos = args.geometry.partition("+")
        w, h = (int(v) for v in size.split("x"))
        window.resize(w, h)
        if pos:
            x, y = (int(v) for v in pos.split("+"))
            window.move(x, y)
    window.show()
    if args.shot:

        def snap() -> None:
            window.grab().save(args.shot)
            text = to_text(window.indices, window.table) if window.indices is not None else ""
            Path(args.shot).with_suffix(".txt").write_text(text, encoding="utf-8")
            print(f"shot saved: {args.shot}  ({window.grid[1]}x{window.grid[0]} cells, last frame {window.last_ms:.1f} ms)")
            window.close()

        QTimer.singleShot(int(args.after * 1000), snap)
    return app.exec()
