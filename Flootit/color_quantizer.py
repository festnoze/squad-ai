"""Colour clustering and palette detection for the Flood-It grid."""

import numpy as np

from config import COLOR_DISTANCE_THRESHOLD


class ColorQuantizer:
    """Detect a discrete colour palette from raw grid colours and map each cell
    to the nearest palette entry.

    The clustering algorithm is a simple greedy approach:

    1. Take the first pixel colour as the first centroid.
    2. For every subsequent pixel, if its Euclidean RGB distance to *all*
       existing centroids exceeds ``COLOR_DISTANCE_THRESHOLD``, add it as a
       new centroid.
    3. Stop once ``num_colors`` centroids have been collected or all pixels
       have been inspected.

    Args:
        num_colors: The expected number of discrete colours in the game board.
    """

    def __init__(self, num_colors: int = 6) -> None:
        self._num_colors = num_colors
        self._palette: np.ndarray | None = None

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def palette(self) -> np.ndarray:
        """The detected colour palette as an array of shape (num_colors, 3).

        Raises:
            RuntimeError: If :meth:`fit` has not been called yet.
        """
        if self._palette is None:
            raise RuntimeError("Palette not available. Call fit() first.")
        return self._palette

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def fit(self, raw_colors: np.ndarray) -> None:
        """Determine the colour palette from the grid's raw colour data.

        Args:
            raw_colors: An array of shape (grid_size, grid_size, 3) containing
                the RGB colour sampled from each cell centre.
        """
        flat = raw_colors.reshape(-1, 3).astype(np.float64)

        centroids: list[np.ndarray] = []

        for pixel in flat:
            if len(centroids) >= self._num_colors:
                break

            if not centroids:
                centroids.append(pixel.copy())
                continue

            # Check distance to every existing centroid.
            distances = np.array(
                [self._color_distance(pixel, c) for c in centroids]
            )
            if np.all(distances > COLOR_DISTANCE_THRESHOLD):
                centroids.append(pixel.copy())

        # If fewer centroids than expected were found, that's still valid --
        # some boards might use fewer colours.
        self._palette = np.array(centroids, dtype=np.uint8)

    def quantize(self, raw_colors: np.ndarray) -> np.ndarray:
        """Map every cell's RGB colour to the index of the nearest palette entry.

        Args:
            raw_colors: An array of shape (grid_size, grid_size, 3).

        Returns:
            An integer array of shape (grid_size, grid_size) where each value
            is the palette index (0 .. num_colors-1) of the closest colour.

        Raises:
            RuntimeError: If :meth:`fit` has not been called yet.
        """
        if self._palette is None:
            raise RuntimeError("Palette not available. Call fit() first.")

        grid_h, grid_w, _ = raw_colors.shape
        flat = raw_colors.reshape(-1, 3).astype(np.float64)

        # Compute distances from every pixel to every centroid using
        # broadcasting: flat is (N, 3), palette is (K, 3).
        palette_f = self._palette.astype(np.float64)
        # Expand dims: (N, 1, 3) - (1, K, 3) -> (N, K, 3)
        diff = flat[:, np.newaxis, :] - palette_f[np.newaxis, :, :]
        distances = np.sqrt(np.sum(diff ** 2, axis=2))  # (N, K)

        indices = np.argmin(distances, axis=1)  # (N,)
        return indices.reshape(grid_h, grid_w)

    # ------------------------------------------------------------------
    # Static helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _color_distance(c1: np.ndarray, c2: np.ndarray) -> float:
        """Compute the Euclidean distance between two RGB colours.

        Args:
            c1: First colour as an array-like of 3 floats/ints.
            c2: Second colour as an array-like of 3 floats/ints.

        Returns:
            The Euclidean distance in RGB space.
        """
        diff = np.asarray(c1, dtype=np.float64) - np.asarray(c2, dtype=np.float64)
        return float(np.sqrt(np.sum(diff ** 2)))
