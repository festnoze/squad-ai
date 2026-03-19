"""Fullscreen transparent overlay for selecting the game board region on screen."""

import ctypes
import json
import tkinter as tk
from pathlib import Path


# Enable per-monitor DPI awareness on Windows so pixel coordinates are accurate.
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    pass  # Non-Windows or already set


class RegionSelector:
    """Draw a rectangle on a fullscreen transparent overlay to select a screen region.

    Usage::

        selector = RegionSelector()
        left, top, width, height = selector.select()
    """

    def __init__(self) -> None:
        self._region: tuple[int, int, int, int] | None = None
        self._start_x: int = 0
        self._start_y: int = 0
        self._rect_id: int | None = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def select(self) -> tuple[int, int, int, int] | None:
        """Open the overlay, let the user draw a rectangle, and return the region.

        Blocks until the user finishes the selection.

        Returns:
            A tuple of (left, top, width, height) in screen pixels.
        """
        self._build_overlay()
        self._root.mainloop()
        return self._region

    @staticmethod
    def save_region(region: tuple[int, int, int, int], path: str | Path) -> None:
        """Persist a region to a JSON file.

        Args:
            region: (left, top, width, height) tuple.
            path: File path for the JSON output.
        """
        data = {
            "left": region[0],
            "top": region[1],
            "width": region[2],
            "height": region[3],
        }
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2)

    @staticmethod
    def load_region(path: str | Path) -> tuple[int, int, int, int]:
        """Load a previously saved region from a JSON file.

        Args:
            path: File path to read.

        Returns:
            A tuple of (left, top, width, height).

        Raises:
            FileNotFoundError: If the file does not exist.
            KeyError: If the JSON is missing required keys.
        """
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        return (data["left"], data["top"], data["width"], data["height"])

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_overlay(self) -> None:
        """Create the fullscreen transparent tkinter window."""
        self._root = tk.Tk()
        self._root.title("Select Game Region")
        self._root.attributes("-fullscreen", True)
        self._root.attributes("-topmost", True)
        self._root.attributes("-alpha", 0.3)
        self._root.configure(cursor="crosshair")

        # Canvas fills the entire screen.
        self._canvas = tk.Canvas(
            self._root,
            bg="grey",
            highlightthickness=0,
        )
        self._canvas.pack(fill=tk.BOTH, expand=True)

        # Bind mouse events.
        self._canvas.bind("<ButtonPress-1>", self._on_press)
        self._canvas.bind("<B1-Motion>", self._on_drag)
        self._canvas.bind("<ButtonRelease-1>", self._on_release)

        # Allow Escape to cancel.
        self._root.bind("<Escape>", self._on_escape)

    def _on_press(self, event: tk.Event) -> None:
        """Record the starting point of the rectangle."""
        self._start_x = event.x
        self._start_y = event.y
        # Create an initial rectangle (zero size).
        self._rect_id = self._canvas.create_rectangle(
            self._start_x,
            self._start_y,
            self._start_x,
            self._start_y,
            outline="red",
            width=2,
        )

    def _on_drag(self, event: tk.Event) -> None:
        """Update the rectangle as the mouse moves."""
        if self._rect_id is not None:
            self._canvas.coords(
                self._rect_id,
                self._start_x,
                self._start_y,
                event.x,
                event.y,
            )

    def _on_release(self, event: tk.Event) -> None:
        """Finalise the region and close the overlay."""
        end_x = event.x
        end_y = event.y

        # Normalise so that (left, top) is always the upper-left corner.
        left = min(self._start_x, end_x)
        top = min(self._start_y, end_y)
        width = abs(end_x - self._start_x)
        height = abs(end_y - self._start_y)

        if width > 0 and height > 0:
            self._region = (left, top, width, height)

        self._root.destroy()

    def _on_escape(self, event: tk.Event) -> None:
        """Cancel the selection."""
        self._region = None
        self._root.destroy()
