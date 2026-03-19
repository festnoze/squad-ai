"""Unit tests for the ColorQuantizer."""

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from color_quantizer import ColorQuantizer


def _make_grid(palette: np.ndarray, indices: np.ndarray) -> np.ndarray:
    """Build a (H, W, 3) RGB grid from a palette and index map."""
    h, w = indices.shape
    grid = np.zeros((h, w, 3), dtype=np.uint8)
    for r in range(h):
        for c in range(w):
            grid[r, c] = palette[indices[r, c]]
    return grid


class TestFit:
    def test_detects_exact_palette(self):
        palette = np.array([
            [255, 0, 0],
            [0, 255, 0],
            [0, 0, 255],
        ], dtype=np.uint8)
        indices = np.array([[0, 1, 2], [2, 0, 1]])
        raw = _make_grid(palette, indices)

        q = ColorQuantizer(num_colors=3)
        q.fit(raw)

        assert q.palette.shape == (3, 3)

    def test_fewer_colors_than_expected(self):
        palette = np.array([[100, 100, 100], [200, 200, 200]], dtype=np.uint8)
        indices = np.array([[0, 1], [1, 0]])
        raw = _make_grid(palette, indices)

        q = ColorQuantizer(num_colors=6)
        q.fit(raw)

        assert len(q.palette) == 2

    def test_palette_not_available_before_fit(self):
        q = ColorQuantizer()
        with pytest.raises(RuntimeError, match="fit"):
            _ = q.palette


class TestQuantize:
    def test_roundtrip(self):
        palette = np.array([
            [255, 0, 0],
            [0, 255, 0],
            [0, 0, 255],
            [255, 255, 0],
        ], dtype=np.uint8)
        indices = np.array([
            [0, 1, 2, 3],
            [3, 2, 1, 0],
        ])
        raw = _make_grid(palette, indices)

        q = ColorQuantizer(num_colors=4)
        q.fit(raw)
        result = q.quantize(raw)

        # Each cell should map back to a consistent index.
        assert result.shape == (2, 4)
        # Top-left and bottom-right should have the same index (both are colour 0).
        assert result[0, 0] == result[1, 3]
        # All cells with the same input colour should map to the same output index.
        for r in range(2):
            for c in range(4):
                assert result[r, c] == result[0, indices[r, c]]

    def test_noisy_colors(self):
        palette = np.array([
            [255, 0, 0],
            [0, 255, 0],
        ], dtype=np.uint8)
        # Add some noise.
        noisy = np.array([
            [[250, 5, 3], [3, 250, 8]],
            [[8, 248, 2], [252, 2, 5]],
        ], dtype=np.uint8)

        q = ColorQuantizer(num_colors=2)
        q.fit(noisy)
        result = q.quantize(noisy)

        assert result.shape == (2, 2)
        # Diagonals should share the same colour index.
        assert result[0, 0] == result[1, 1]
        assert result[0, 1] == result[1, 0]
        assert result[0, 0] != result[0, 1]


class TestColorDistance:
    def test_same_color(self):
        c = np.array([100, 150, 200])
        assert ColorQuantizer._color_distance(c, c) == 0.0

    def test_known_distance(self):
        c1 = np.array([0, 0, 0])
        c2 = np.array([3, 4, 0])
        assert abs(ColorQuantizer._color_distance(c1, c2) - 5.0) < 1e-9
