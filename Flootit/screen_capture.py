"""Screen capture and grid parsing engine using mss."""

from __future__ import annotations

import numpy as np
import mss

from config import COLOR_DISTANCE_THRESHOLD


class ScreenCapture:
    """Capture a screen region and extract the colour grid from a Flood-It board.

    Args:
        region: A tuple of (left, top, width, height) describing the area to
            capture, in screen pixels.
    """

    def __init__(self, region: tuple[int, int, int, int]) -> None:
        self._left, self._top, self._width, self._height = region

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def capture(self) -> np.ndarray:
        """Capture the configured screen region and return an RGB numpy array.

        Returns:
            A numpy array of shape (height, width, 3) with dtype uint8 in RGB
            order.
        """
        monitor = {
            "left": self._left,
            "top": self._top,
            "width": self._width,
            "height": self._height,
        }
        with mss.mss() as sct:
            screenshot = sct.grab(monitor)
            rgb = np.frombuffer(screenshot.rgb, dtype=np.uint8)
            rgb = rgb.reshape((self._height, self._width, 3))
        return rgb

    def extract_grid_colors(
        self,
        image: np.ndarray,
        grid_size: int = 14,
    ) -> np.ndarray:
        """Sample the centre colour of each cell in the grid.

        For every cell a small 5x5 patch around the centre pixel is averaged
        to reduce noise from grid lines or anti-aliasing.

        Args:
            image: An RGB image array of shape (H, W, 3).
            grid_size: Number of rows (and columns) in the grid.

        Returns:
            A numpy array of shape (grid_size, grid_size, 3) with the average
            RGB colour of each cell centre.
        """
        h, w, _ = image.shape
        cell_h = h / grid_size
        cell_w = w / grid_size
        patch_r = 2  # radius of sampling patch (5x5)

        colors = np.zeros((grid_size, grid_size, 3), dtype=np.float64)

        for row in range(grid_size):
            cy = int(row * cell_h + cell_h / 2)
            for col in range(grid_size):
                cx = int(col * cell_w + cell_w / 2)

                y_lo = max(cy - patch_r, 0)
                y_hi = min(cy + patch_r + 1, h)
                x_lo = max(cx - patch_r, 0)
                x_hi = min(cx + patch_r + 1, w)

                patch = image[y_lo:y_hi, x_lo:x_hi]
                colors[row, col] = patch.mean(axis=(0, 1))

        return colors.astype(np.uint8)

    # ------------------------------------------------------------------
    # Grid size detection via autocorrelation of gradient
    # ------------------------------------------------------------------

    @staticmethod
    def detect_grid_size(image: np.ndarray) -> int:
        """Auto-detect the grid dimensions using gradient autocorrelation.

        The approach:
        1. Compute the per-pixel gradient magnitude (edge detection).
        2. Project edges onto horizontal axis (sum rows) and vertical axis
           (sum columns) to get 1D periodic signals.
        3. Compute the autocorrelation of each projection.
        4. Find the first significant peak = cell size in pixels.
        5. grid_size = image_dimension / cell_size.

        This works even when adjacent cells share the same colour, because
        most Flood-It games have thin grid lines or at least enough
        colour boundaries to produce a periodic signal.

        Falls back to 14 if detection fails.

        Args:
            image: An RGB image array of shape (H, W, 3).

        Returns:
            The detected grid size (number of rows/columns).
        """
        h, w, _ = image.shape
        gray = image.astype(np.float64).mean(axis=2)

        # Gradient magnitude (Sobel-like via simple differences).
        grad_x = np.abs(np.diff(gray, axis=1))  # (H, W-1)
        grad_y = np.abs(np.diff(gray, axis=0))  # (H-1, W)

        # Horizontal projection: sum gradient_x over all rows -> shape (W-1,)
        h_proj = grad_x.sum(axis=0)
        # Vertical projection: sum gradient_y over all columns -> shape (H-1,)
        v_proj = grad_y.sum(axis=1)

        cell_w = ScreenCapture._find_period(h_proj, w)
        cell_h = ScreenCapture._find_period(v_proj, h)

        if cell_w is None and cell_h is None:
            return 14

        estimates: list[int] = []
        if cell_w is not None:
            estimates.append(round(w / cell_w))
        if cell_h is not None:
            estimates.append(round(h / cell_h))

        grid_size = int(np.median(estimates))

        if 4 <= grid_size <= 40:
            return grid_size
        return DEFAULT_GRID_SIZE

    @staticmethod
    def _find_period(signal: np.ndarray, total_length: int) -> float | None:
        """Find the dominant period in a 1D signal via autocorrelation.

        Args:
            signal: 1D array (e.g. gradient projection).
            total_length: Full image dimension (width or height).

        Returns:
            The period in pixels, or None if no clear period is found.
        """
        # Normalise signal to zero-mean.
        sig = signal - signal.mean()
        n = len(sig)
        if n < 10:
            return None

        # Autocorrelation via FFT (fast).
        fft = np.fft.rfft(sig, n=2 * n)
        acorr = np.fft.irfft(fft * np.conj(fft))[:n]
        acorr = acorr / acorr[0]  # normalise so lag-0 = 1.0

        # Minimum cell size in pixels (cells smaller than 5px are unreasonable).
        min_lag = max(5, total_length // 40)
        # Maximum cell size (cells bigger than half the image are unreasonable).
        max_lag = total_length // 3

        # Find all local maxima in the valid range.
        best_lag = None
        best_val = 0.0
        for i in range(min_lag, min(max_lag, n - 1)):
            if acorr[i] > acorr[i - 1] and acorr[i] > acorr[i + 1]:
                if acorr[i] > best_val:
                    best_val = acorr[i]
                    best_lag = i
                    # Take the FIRST strong peak (smallest period = cell size),
                    # not the global maximum (which could be a harmonic).
                    if best_val > 0.15:
                        break

        if best_lag is not None and best_val > 0.05:
            return float(best_lag)
        return None

    # ------------------------------------------------------------------
    # Colour counting
    # ------------------------------------------------------------------

    @staticmethod
    def detect_num_colors(
        image: np.ndarray,
        grid_size: int,
        distance_threshold: float = COLOR_DISTANCE_THRESHOLD,
    ) -> tuple[int, np.ndarray]:
        """Detect the number of distinct colours on the board.

        Samples the centre of every cell, then clusters by Euclidean
        distance in RGB space.

        Args:
            image: An RGB image array of shape (H, W, 3).
            grid_size: The grid dimension (already detected).
            distance_threshold: Minimum RGB distance to consider two
                colours as distinct.

        Returns:
            A tuple (num_colors, palette) where palette is an (N, 3) uint8
            array of the detected colour centroids.
        """
        h, w, _ = image.shape
        cell_h = h / grid_size
        cell_w = w / grid_size
        patch_r = 2

        # Sample every cell centre.
        samples: list[np.ndarray] = []
        for row in range(grid_size):
            cy = int(row * cell_h + cell_h / 2)
            for col in range(grid_size):
                cx = int(col * cell_w + cell_w / 2)
                y_lo = max(cy - patch_r, 0)
                y_hi = min(cy + patch_r + 1, h)
                x_lo = max(cx - patch_r, 0)
                x_hi = min(cx + patch_r + 1, w)
                patch = image[y_lo:y_hi, x_lo:x_hi]
                samples.append(patch.mean(axis=(0, 1)))

        # Greedy clustering.
        centroids: list[np.ndarray] = []
        for pixel in samples:
            pixel_f = pixel.astype(np.float64)
            if not centroids:
                centroids.append(pixel_f)
                continue
            dists = [
                float(np.sqrt(np.sum((pixel_f - c) ** 2))) for c in centroids
            ]
            if min(dists) > distance_threshold:
                centroids.append(pixel_f)

        palette = np.array(centroids, dtype=np.uint8)
        return len(centroids), palette
