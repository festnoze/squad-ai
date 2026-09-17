"""Screen capture of a physical-pixel rectangle, as (h, w, 4) BGRA uint8.

Two backends behind one interface:
  - dxcam (DXGI Desktop Duplication): about 5 ms for 1280x720 on this machine,
    but bound to one output (monitor).
  - mss (GDI BitBlt): about 16 ms for the same region, sees the whole virtual
    desktop, always available.
Both are blind to a window flagged WDA_EXCLUDEFROMCAPTURE (verified by
tools/probe_exclusion.py), which is what lets the overlay read what lies under it.

The rectangle is clamped to the virtual screen; pixels outside it come back black.
"""

from __future__ import annotations

import numpy as np

Rect = tuple[int, int, int, int]  # left, top, right, bottom in physical pixels


class MssBackend:
    name = "mss"

    def __init__(self) -> None:
        import mss

        self._sct = mss.MSS()
        m = self._sct.monitors[0]  # the whole virtual screen
        self.bounds: Rect = (m["left"], m["top"], m["left"] + m["width"], m["top"] + m["height"])

    def grab(self, rect: Rect) -> np.ndarray:
        l, t, r, b = rect
        shot = self._sct.grab({"left": l, "top": t, "width": r - l, "height": b - t})
        return np.frombuffer(shot.bgra, dtype=np.uint8).reshape(shot.height, shot.width, 4)

    def close(self) -> None:
        self._sct.close()


class DxcamBackend:
    name = "dxcam"

    def __init__(self) -> None:
        import dxcam

        # Raw BGRA: dxcam's colour conversion needs OpenCV, which we do not want.
        self._cam = dxcam.create(output_color="BGRA")
        w, h = self._cam.width, self._cam.height
        self.bounds: Rect = (0, 0, w, h)  # dxcam regions are relative to the primary output

    def grab(self, rect: Rect) -> np.ndarray | None:
        frame = self._cam.grab(region=rect)
        if frame is None:
            return None
        return frame

    def close(self) -> None:
        try:
            self._cam.release()
        except Exception:
            pass


def _inside(inner: Rect, outer: Rect) -> bool:
    return inner[0] >= outer[0] and inner[1] >= outer[1] and inner[2] <= outer[2] and inner[3] <= outer[3]


class Capture:
    """Picks the fastest backend able to see the rectangle, clamps, pads with black."""

    def __init__(self, prefer_dxcam: bool = True) -> None:
        self.mss = MssBackend()
        self.dxcam: DxcamBackend | None = None
        if prefer_dxcam:
            try:
                self.dxcam = DxcamBackend()
            except Exception:
                self.dxcam = None
        self.last_backend = self.mss.name

    def grab(self, rect: Rect) -> np.ndarray | None:
        l, t, r, b = rect
        w, h = r - l, b - t
        if w <= 0 or h <= 0:
            return None
        vl, vt, vr, vb = self.mss.bounds
        cl, ct, cr, cb = max(l, vl), max(t, vt), min(r, vr), min(b, vb)
        if cr <= cl or cb <= ct:
            return np.zeros((h, w, 4), dtype=np.uint8)
        clamped: Rect = (cl, ct, cr, cb)

        backend = self.mss
        if self.dxcam is not None and _inside(clamped, self.dxcam.bounds):
            backend = self.dxcam
        self.last_backend = backend.name
        try:
            part = backend.grab(clamped)
        except Exception:
            if backend is self.dxcam:
                self.dxcam.close()
                self.dxcam = None
                self.last_backend = self.mss.name
                part = self.mss.grab(clamped)
            else:
                raise
        if part is None:
            return None
        if clamped == rect:
            return part
        full = np.zeros((h, w, 4), dtype=np.uint8)
        full[ct - t : cb - t, cl - l : cr - l] = part
        return full

    def close(self) -> None:
        if self.dxcam is not None:
            self.dxcam.close()
        self.mss.close()
