"""Prove that WDA_EXCLUDEFROMCAPTURE hides a window from screen capture on this machine.

Creates a solid magenta top-level window, captures its own rectangle with the
GDI backend (mss / BitBlt) and, when available, the Desktop Duplication backend
(dxcam), and reports whether the magenta is absent from each capture. A capture
that still contains the magenta means the backend sees the window itself and
the overlay would render its own output recursively.

Usage (venv active):
    python tools/probe_exclusion.py
Exit code 0 when every backend passes, 1 otherwise.
"""

from __future__ import annotations

import ctypes
import sys
import time
from ctypes import wintypes

import numpy as np

WDA_EXCLUDEFROMCAPTURE = 0x00000011
MAGENTA = (255, 0, 255)


def set_dpi_awareness() -> None:
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        pass


def physical_client_rect(hwnd: int) -> tuple[int, int, int, int]:
    """Client rectangle in physical screen pixels: (left, top, right, bottom)."""
    user32 = ctypes.windll.user32
    rect = wintypes.RECT()
    user32.GetClientRect(hwnd, ctypes.byref(rect))
    pt = wintypes.POINT(0, 0)
    user32.ClientToScreen(hwnd, ctypes.byref(pt))
    return pt.x, pt.y, pt.x + rect.right, pt.y + rect.bottom


def magenta_fraction(rgb: np.ndarray) -> float:
    r, g, b = rgb[..., 0].astype(int), rgb[..., 1].astype(int), rgb[..., 2].astype(int)
    hit = (r > 200) & (g < 60) & (b > 200)
    return float(hit.mean())


def capture_mss(rect):
    import mss

    l, t, r, b = rect
    with mss.mss() as sct:
        shot = sct.grab({"left": l, "top": t, "width": r - l, "height": b - t})
        return np.frombuffer(shot.rgb, dtype=np.uint8).reshape(shot.height, shot.width, 3)


def capture_dxcam(rect):
    try:
        import dxcam
    except Exception as exc:  # pragma: no cover - optional backend
        return None, f"dxcam unavailable: {exc}"
    cam = dxcam.create(output_color="RGB")
    try:
        frame = None
        deadline = time.time() + 2.0
        while frame is None and time.time() < deadline:
            frame = cam.grab(region=rect)
        if frame is None:
            return None, "dxcam returned no frame"
        return frame, ""
    finally:
        cam.release()


def main() -> int:
    set_dpi_awareness()
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication, QWidget

    app = QApplication(sys.argv)
    w = QWidget()
    w.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
    w.setStyleSheet("background: rgb(255, 0, 255);")
    w.resize(320, 200)
    w.move(200, 200)
    w.show()
    hwnd = int(w.winId())
    app.processEvents()
    time.sleep(0.4)
    app.processEvents()

    rect = physical_client_rect(hwnd)
    print(f"window client rect (physical px): {rect}")

    # Control: the window must be visible to capture before exclusion.
    before = magenta_fraction(capture_mss(rect))
    print(f"mss before exclusion: magenta fraction = {before:.3f}")

    ok = ctypes.windll.user32.SetWindowDisplayAffinity(hwnd, WDA_EXCLUDEFROMCAPTURE)
    print(f"SetWindowDisplayAffinity -> {bool(ok)}")
    if not ok:
        print(f"GetLastError = {ctypes.GetLastError()}")
        return 1
    app.processEvents()
    time.sleep(0.4)
    app.processEvents()

    failures = 0
    after = magenta_fraction(capture_mss(rect))
    print(f"mss after exclusion:  magenta fraction = {after:.3f} -> {'PASS' if after < 0.01 else 'FAIL'}")
    failures += after >= 0.01

    frame, err = capture_dxcam(rect)
    if frame is None:
        print(f"dxcam: skipped ({err})")
    else:
        dx = magenta_fraction(frame)
        print(f"dxcam after exclusion: magenta fraction = {dx:.3f} -> {'PASS' if dx < 0.01 else 'FAIL'}")
        failures += dx >= 0.01

    if before < 0.5:
        print("WARNING: control capture did not see the window; the test is not conclusive.")
        failures += 1

    w.close()
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
