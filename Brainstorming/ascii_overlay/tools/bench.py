"""Time the full pipeline on a synthetic 1280x720 frame for every cell size.

Usage (venv active): python tools/bench.py
"""

from __future__ import annotations

import time

import numpy as np

from ascii_overlay.glyphs import CELL_SIZES, get_table
from ascii_overlay.matcher import MatchParams, MatchState, frame_to_indices, render


def main() -> None:
    rng = np.random.default_rng(1)
    base = rng.integers(0, 256, size=(720, 1280, 4), dtype=np.uint8)
    # Add structure: gradients and stripes, closer to a desktop than white noise.
    yy, xx = np.mgrid[0:720, 0:1280]
    base[..., :3] = (base[..., :3] * 0.3 + ((xx + yy) % 64 * 4)[..., None] * 0.7).astype(np.uint8)
    params = MatchParams()
    for cw, ch in CELL_SIZES:
        table = get_table(cw, ch)
        state = MatchState()
        frame = base[: (720 // ch) * ch, : (1280 // cw) * cw]
        idx = frame_to_indices(frame, table, params, state)
        t0 = time.perf_counter()
        n = 10
        for _ in range(n):
            idx = frame_to_indices(frame, table, params, state)
            render(idx, table)
        ms = (time.perf_counter() - t0) / n * 1000.0
        rows, cols = idx.shape
        print(f"cell {cw:2d}x{ch:2d}: {cols}x{rows} = {rows * cols:5d} cells, {table.count} glyphs -> {ms:6.1f} ms/frame")


if __name__ == "__main__":
    main()
