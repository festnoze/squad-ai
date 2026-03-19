"""Mouse automation to click grid cells of a target colour in Flood-It."""

from __future__ import annotations

import time

import numpy as np
import pyautogui

from config import CLICK_DELAY_MS

# Safety: allow aborting by moving the mouse to a screen corner.
pyautogui.FAILSAFE = True

MAX_NO_CHANGE_RETRIES = 3
MAX_MISMATCH_RETRIES = 2


class AutoClicker:
    """Click directly on grid cells and verify the board state after each move.

    After every click the clicker re-captures the screen, re-quantizes it,
    and compares the actual board state with the expected one.  If the board
    did not change (e.g. animation lag, misclick), the click is retried.

    Args:
        region: (left, top, width, height) of the game grid in screen pixels.
        grid: 2D numpy array of quantized colour indices (rows x cols).
        grid_size: Number of rows/columns in the grid.
        capture: ScreenCapture instance for re-reading the screen.
        quantizer: ColorQuantizer instance (already fitted) for re-quantizing.
        delay_ms: Pause between consecutive clicks, in milliseconds.
    """

    def __init__(
        self,
        region: tuple[int, int, int, int],
        grid: np.ndarray,
        grid_size: int,
        capture,
        quantizer,
        delay_ms: int = CLICK_DELAY_MS,
    ) -> None:
        self._left, self._top, self._width, self._height = region
        self._grid = grid.copy()
        self._grid_size = grid_size
        self._capture = capture
        self._quantizer = quantizer
        self._delay = delay_ms / 1000.0
        self._cell_w = self._width / grid_size
        self._cell_h = self._height / grid_size

    def _cell_screen_pos(self, row: int, col: int) -> tuple[int, int]:
        """Return the absolute screen (x, y) of a cell's centre."""
        x = self._left + int(col * self._cell_w + self._cell_w / 2)
        y = self._top + int(row * self._cell_h + self._cell_h / 2)
        return x, y

    def _find_cell_with_color(self, color: int) -> tuple[int, int] | None:
        """Find a grid cell that contains the given colour index.

        Returns:
            (row, col) of a matching cell, or None if no cell has that colour.
        """
        rows, cols = self._grid.shape
        for r in range(rows):
            for c in range(cols):
                if int(self._grid[r, c]) == color:
                    return r, c
        return None

    def _recapture_grid(self) -> np.ndarray:
        """Re-capture the screen and return the quantized grid."""
        image = self._capture.capture()
        raw_colors = self._capture.extract_grid_colors(image, self._grid_size)
        return self._quantizer.quantize(raw_colors)

    def _click_and_verify(
        self,
        color: int,
        board: "Board",
        move_label: str,
    ) -> tuple[bool, np.ndarray | None]:
        """Click a cell of *color*, verify the board changed to the expected state.

        Handles "no change" retries internally (up to MAX_NO_CHANGE_RETRIES).

        Returns:
            (success, actual_grid) -- *success* is True when the post-click
            board matches the expected state.  *actual_grid* is the last
            captured grid (useful for re-analysis on mismatch).
        """
        cell = self._find_cell_with_color(color)
        if cell is None:
            print(f"    {move_label}: no cell with colour {color} found on grid")
            return False, None
        row, col = cell
        x, y = self._cell_screen_pos(row, col)

        expected_board = board.copy()
        expected_board.apply_move(color)

        for attempt in range(1, MAX_NO_CHANGE_RETRIES + 1):
            pyautogui.click(x, y)
            time.sleep(self._delay)

            actual_grid = self._recapture_grid()

            if np.array_equal(actual_grid, self._grid):
                # Board did not change -- retry the click.
                print(
                    f"    [no-change retry {attempt}/{MAX_NO_CHANGE_RETRIES}] "
                    f"colour {color}, retrying ..."
                )
                time.sleep(self._delay)
                continue

            # Board changed -- check if it matches expected.
            if np.array_equal(actual_grid, expected_board.grid):
                return True, actual_grid

            # Board changed but doesn't match expected.
            return False, actual_grid

        # All no-change retries exhausted.
        return False, None

    def execute_solution(
        self,
        moves: list[int],
        on_move: callable | None = None,
    ) -> None:
        """Execute a full solution sequence, verifying state after each click.

        After each click the board is re-captured from screen.  If the board
        did not change, the click is retried.  If the board changed but does
        not match the expected state, a mismatch retry is performed: wait
        longer for animations, re-capture, re-analyse the board, and try
        clicking again.  Only after ``MAX_MISMATCH_RETRIES`` consecutive
        mismatches the execution is aborted.

        Args:
            moves: Ordered list of colour indices to click.
            on_move: Optional callback ``(move_index, color_index) -> None``
                     invoked after each successful click.
        """
        from board import Board

        board = Board(self._grid, num_colors=int(self._grid.max()) + 1)

        for idx, color in enumerate(moves):
            move_label = f"Move {idx + 1}/{len(moves)}"

            success, actual_grid = self._click_and_verify(
                color, board, move_label,
            )

            if success:
                print(f"  {move_label}: colour {color} -- OK")
                board.apply_move(color)
                self._grid = board.grid.copy()
                if on_move is not None:
                    on_move(idx, color)
                continue

            # ----------------------------------------------------------
            # Mismatch or no-change failure -- retry with re-analysis
            # ----------------------------------------------------------
            resolved = False
            for retry in range(1, MAX_MISMATCH_RETRIES + 1):
                # Wait longer for animations to settle.
                time.sleep(self._delay * 3)
                actual_grid = self._recapture_grid()

                # Maybe the animation just finished and it now matches.
                expected_board = board.copy()
                expected_board.apply_move(color)
                if np.array_equal(actual_grid, expected_board.grid):
                    print(
                        f"  {move_label}: colour {color} -- OK "
                        f"(matched after mismatch retry {retry})"
                    )
                    board.apply_move(color)
                    self._grid = board.grid.copy()
                    resolved = True
                    break

                # Still mismatched -- re-analyse from actual screen state
                # and attempt the click again with a fresh cell lookup.
                print(
                    f"    [mismatch retry {retry}/{MAX_MISMATCH_RETRIES}] "
                    f"Re-analysing board and retrying colour {color} ..."
                )
                self._grid = actual_grid.copy()
                num_c = max(int(actual_grid.max()) + 1, board.num_colors)
                board = Board(actual_grid, num_colors=num_c)

                # Recompute expected state from the actual board.
                success, actual_grid = self._click_and_verify(
                    color, board, move_label,
                )
                if success:
                    print(
                        f"  {move_label}: colour {color} -- OK "
                        f"(succeeded on mismatch retry {retry})"
                    )
                    board.apply_move(color)
                    self._grid = board.grid.copy()
                    resolved = True
                    break

            if not resolved:
                print(
                    f"\n  ABORT {move_label}: colour {color}"
                    f"\n  Board state does not match expected result "
                    f"after {MAX_MISMATCH_RETRIES} retries."
                    f"\n  Stopping."
                )
                return

            if on_move is not None:
                on_move(idx, color)
