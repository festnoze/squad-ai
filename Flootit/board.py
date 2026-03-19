"""Board data model and flood-fill logic for the Flood-It game.

This module provides the Board class which represents the game state
as a 2D grid of color indices and implements all flood-fill operations
needed by the solver algorithms.
"""

from __future__ import annotations

from collections import deque
from typing import Optional

import numpy as np



class Board:
    """Represents a Flood-It board as a 2D grid of integer color indices.

    The board uses BFS-based flood fill starting from the top-left corner (0, 0).
    Colors are represented as integers in the range [0, num_colors).

    Attributes:
        grid: 2D numpy array of shape (rows, cols) with dtype int,
              where each cell holds a color index in [0, num_colors).
        num_colors: Total number of distinct colors available in the game.
        rows: Number of rows in the grid.
        cols: Number of columns in the grid.
    """

    __slots__ = ("grid", "num_colors", "rows", "cols", "_hash")

    def __init__(self, grid: np.ndarray, num_colors: int = 6) -> None:
        """Initialise the board with a grid and color count.

        Args:
            grid: 2D numpy array of int color indices (values in 0..num_colors-1).
            num_colors: Number of discrete colours in the game (default from config).

        Raises:
            ValueError: If the grid is not 2-dimensional or contains values outside
                        the valid colour range.
        """
        if grid.ndim != 2:
            raise ValueError(f"Grid must be 2-dimensional, got {grid.ndim}D array.")
        if grid.size > 0:
            min_val, max_val = int(grid.min()), int(grid.max())
            if min_val < 0 or max_val >= num_colors:
                raise ValueError(
                    f"Grid values must be in [0, {num_colors}), "
                    f"got range [{min_val}, {max_val}]."
                )
        self.grid: np.ndarray = grid.astype(int, copy=True)
        self.num_colors: int = num_colors
        self.rows: int = grid.shape[0]
        self.cols: int = grid.shape[1]
        self._hash: Optional[int] = None

    # ------------------------------------------------------------------
    # Copying
    # ------------------------------------------------------------------

    def copy(self) -> Board:
        """Return a deep copy of this board.

        Returns:
            A new Board instance with an independent copy of the grid.
        """
        new = Board.__new__(Board)
        new.grid = self.grid.copy()
        new.num_colors = self.num_colors
        new.rows = self.rows
        new.cols = self.cols
        new._hash = None
        return new

    # ------------------------------------------------------------------
    # Flood-fill helpers
    # ------------------------------------------------------------------

    def get_flooded_region(self) -> set[tuple[int, int]]:
        """BFS from (0, 0) to find all connected cells sharing the same colour.

        The flooded region is the maximal connected component of cells that
        share the colour of (0, 0), using 4-directional adjacency.

        Returns:
            A set of (row, col) tuples belonging to the flooded region.
        """
        if self.grid.size == 0:
            return set()

        origin_color: int = int(self.grid[0, 0])
        visited: set[tuple[int, int]] = {(0, 0)}
        queue: deque[tuple[int, int]] = deque([(0, 0)])

        while queue:
            r, c = queue.popleft()
            for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                nr, nc = r + dr, c + dc
                if 0 <= nr < self.rows and 0 <= nc < self.cols and (nr, nc) not in visited:
                    if int(self.grid[nr, nc]) == origin_color:
                        visited.add((nr, nc))
                        queue.append((nr, nc))

        return visited

    def get_frontier(
        self, flooded: set[tuple[int, int]]
    ) -> dict[int, set[tuple[int, int]]]:
        """Find cells adjacent to the flooded region, grouped by colour.

        Args:
            flooded: The current flooded region (set of (row, col) tuples).

        Returns:
            A dict mapping each adjacent colour index to the set of (row, col)
            cells of that colour that border the flooded region.
        """
        frontier: dict[int, set[tuple[int, int]]] = {}
        for r, c in flooded:
            for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                nr, nc = r + dr, c + dc
                if (
                    0 <= nr < self.rows
                    and 0 <= nc < self.cols
                    and (nr, nc) not in flooded
                ):
                    color = int(self.grid[nr, nc])
                    if color not in frontier:
                        frontier[color] = set()
                    frontier[color].add((nr, nc))
        return frontier

    # ------------------------------------------------------------------
    # Move application
    # ------------------------------------------------------------------

    def apply_move(self, color: int) -> int:
        """Apply a flood-fill move: change the flooded region to *color* and expand.

        The entire current flooded region is repainted to the given colour.
        Then the region expands via BFS to absorb all newly-connected cells
        of that colour.  The grid is mutated in place.

        If *color* equals the current colour of (0, 0) the method still
        performs the expansion check (which is a no-op), ensuring correctness
        for edge cases.

        Args:
            color: The colour index to flood with (0..num_colors-1).

        Returns:
            The size of the flooded region after the move.

        Raises:
            ValueError: If *color* is outside the valid range.
        """
        if color < 0 or color >= self.num_colors:
            raise ValueError(
                f"Color must be in [0, {self.num_colors}), got {color}."
            )

        # Invalidate cached hash since the grid is about to change.
        self._hash = None

        current_color: int = int(self.grid[0, 0])

        # Fast path: if same colour, nothing changes.
        if color == current_color:
            return len(self.get_flooded_region())

        # Step 1: find current flooded region.
        flooded: set[tuple[int, int]] = self.get_flooded_region()

        # Step 2: repaint the flooded region to the new colour.
        for r, c in flooded:
            self.grid[r, c] = color

        # Step 3: BFS-expand into adjacent cells that now match *color*.
        queue: deque[tuple[int, int]] = deque()

        # Seed the queue with frontier cells of the target colour.
        # Iterate over a snapshot since we mutate `flooded` inside the loop.
        for r, c in list(flooded):
            for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                nr, nc = r + dr, c + dc
                if (
                    0 <= nr < self.rows
                    and 0 <= nc < self.cols
                    and (nr, nc) not in flooded
                    and int(self.grid[nr, nc]) == color
                ):
                    flooded.add((nr, nc))
                    queue.append((nr, nc))

        while queue:
            r, c = queue.popleft()
            for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                nr, nc = r + dr, c + dc
                if (
                    0 <= nr < self.rows
                    and 0 <= nc < self.cols
                    and (nr, nc) not in flooded
                    and int(self.grid[nr, nc]) == color
                ):
                    flooded.add((nr, nc))
                    queue.append((nr, nc))

        return len(flooded)

    # ------------------------------------------------------------------
    # State queries
    # ------------------------------------------------------------------

    def is_solved(self) -> bool:
        """Check whether the board is solved (all cells are the same colour).

        Returns:
            True if every cell in the grid has the same colour index.
        """
        if self.grid.size == 0:
            return True
        first: int = int(self.grid[0, 0])
        return bool(np.all(self.grid == first))

    def remaining_colors(self) -> int:
        """Count distinct colours that are NOT part of the flooded region.

        Returns:
            Number of unique colour indices found outside the flooded region.
        """
        if self.grid.size == 0:
            return 0

        flooded = self.get_flooded_region()
        total_cells = self.rows * self.cols

        # If the entire board is flooded there are no remaining colours.
        if len(flooded) == total_cells:
            return 0

        # Build a boolean mask of non-flooded cells.
        mask = np.ones((self.rows, self.cols), dtype=bool)
        for r, c in flooded:
            mask[r, c] = False

        outside_colors = set(int(v) for v in self.grid[mask])
        return len(outside_colors)

    # ------------------------------------------------------------------
    # Hashing / equality (for transposition tables)
    # ------------------------------------------------------------------

    def __hash__(self) -> int:
        """Return a stable hash derived from the grid contents.

        The hash is cached and invalidated when apply_move mutates the grid.
        """
        if self._hash is None:
            self._hash = hash(self.grid.tobytes())
        return self._hash

    def __eq__(self, other: object) -> bool:
        """Two boards are equal iff their grids are element-wise identical."""
        if not isinstance(other, Board):
            return NotImplemented
        if self.rows != other.rows or self.cols != other.cols:
            return False
        return bool(np.array_equal(self.grid, other.grid))

    def __repr__(self) -> str:
        return f"Board(shape={self.grid.shape}, num_colors={self.num_colors})"
