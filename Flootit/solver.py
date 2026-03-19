"""Flood-It solver algorithms: Greedy, Lookahead, and A*.

This module provides three solver classes of increasing sophistication
for finding a sequence of moves that solves a Flood-It board.

Usage example::

    from board import Board
    from solver import GreedySolver, LookaheadSolver, AStarSolver
    import numpy as np

    grid = np.random.randint(0, 6, size=(14, 14))
    b = Board(grid, num_colors=6)
    moves = LookaheadSolver(depth=2).solve(b)
"""

from __future__ import annotations

import heapq
from typing import Optional

from board import Board
from config import LOOKAHEAD_DEPTH


# ---------------------------------------------------------------------------
# Greedy solver
# ---------------------------------------------------------------------------


class GreedySolver:
    """Greedy solver that picks the colour absorbing the most cells each turn.

    At every step the solver evaluates each candidate colour (skipping the
    colour the flooded region already has) and selects the one that maximises
    the flooded-region size after a single move.
    """

    def solve(self, board: Board) -> list[int]:
        """Solve the board using a pure greedy strategy.

        Args:
            board: The initial Board instance.  It is **not** mutated;
                   an internal copy is used.

        Returns:
            A list of colour indices representing the move sequence.
        """
        b = board.copy()
        moves: list[int] = []

        while not b.is_solved():
            current_color = int(b.grid[0, 0])
            best_color: int = -1
            best_size: int = -1

            for color in range(b.num_colors):
                if color == current_color:
                    continue
                trial = b.copy()
                size = trial.apply_move(color)
                if size > best_size:
                    best_size = size
                    best_color = color

            # Safety: if no improving move was found (shouldn't happen on a
            # non-solved board), fall back to the first different colour.
            if best_color == -1:
                best_color = (current_color + 1) % b.num_colors

            b.apply_move(best_color)
            moves.append(best_color)

        return moves


# ---------------------------------------------------------------------------
# Lookahead solver
# ---------------------------------------------------------------------------


class LookaheadSolver:
    """Solver that explores all colour sequences up to a configurable depth
    and applies the **entire best sequence** at once before re-evaluating.

    At each iteration the solver builds a search tree of depth *d*, scoring
    every leaf by the flooded-region size.  The full sequence of *d* moves
    leading to the best leaf is applied in one batch, then the process
    repeats on the updated board.

    This yields significantly better solutions than applying only the first
    move of the best sequence, because later moves in the window are
    informed by the same lookahead context.
    """

    def __init__(self, depth: int = LOOKAHEAD_DEPTH) -> None:
        """Initialise the solver with a given lookahead depth.

        Args:
            depth: How many moves to look ahead (default from config).
                   Typical values: 3 or 4.  Higher is better but slower
                   (branching factor ~5, so depth 4 evaluates ~625 states
                   per window).
        """
        self.depth: int = depth

    def solve(self, board: Board) -> list[int]:
        """Solve the board by repeatedly finding and applying the best
        *depth*-length sequence.

        Args:
            board: The initial Board instance.  It is **not** mutated.

        Returns:
            A list of colour indices representing the move sequence.
        """
        b = board.copy()
        moves: list[int] = []

        while not b.is_solved():
            _best_score, best_seq = self._evaluate(b, self.depth)
            if not best_seq:
                break
            for color in best_seq:
                if b.is_solved():
                    break
                b.apply_move(color)
                moves.append(color)

        return moves

    def _evaluate(self, board: Board, depth: int) -> tuple[int, list[int]]:
        """Recursively evaluate all move sequences up to *depth* plies.

        Args:
            board: Current board state (not mutated).
            depth: Remaining levels of lookahead.

        Returns:
            A tuple ``(best_score, best_sequence)`` where *best_score* is
            the maximum flooded-region size achievable and *best_sequence*
            is the full list of colour moves that achieves it.
        """
        if depth == 0 or board.is_solved():
            return len(board.get_flooded_region()), []

        current_color = int(board.grid[0, 0])
        best_score: int = -1
        best_seq: list[int] = []

        for color in range(board.num_colors):
            if color == current_color:
                continue

            trial = board.copy()
            trial.apply_move(color)

            if trial.is_solved():
                return trial.rows * trial.cols, [color]

            sub_score, sub_seq = self._evaluate(trial, depth - 1)

            if sub_score > best_score:
                best_score = sub_score
                best_seq = [color] + sub_seq

        return best_score, best_seq


# ---------------------------------------------------------------------------
# A* solver
# ---------------------------------------------------------------------------


class AStarSolver:
    """A* search solver for Flood-It.

    Uses an admissible heuristic (number of distinct colours outside the
    flooded region) and a transposition table to avoid revisiting states.
    Falls back to :class:`LookaheadSolver` if the search space exceeds
    *max_states*.
    """

    def __init__(self, max_states: int = 500_000) -> None:
        """Initialise the solver with a state-count budget.

        Args:
            max_states: Maximum number of states to explore before bailing
                        out to the LookaheadSolver fallback.
        """
        self.max_states: int = max_states

    # ------------------------------------------------------------------
    # Heuristic
    # ------------------------------------------------------------------

    @staticmethod
    def _heuristic(board: Board) -> int:
        """Admissible heuristic: number of distinct colours outside the flooded region.

        Each remaining colour needs at least one move to incorporate, so this
        is a lower bound on the number of moves to solve the board.

        Args:
            board: The board state to evaluate.

        Returns:
            A non-negative integer lower-bound on remaining moves.
        """
        return board.remaining_colors()

    # ------------------------------------------------------------------
    # Solve
    # ------------------------------------------------------------------

    def solve(self, board: Board) -> list[int]:
        """Solve the board using A* search with an admissible heuristic.

        The search explores states in best-first order according to
        f(n) = g(n) + h(n) where g is the number of moves so far and h is
        the remaining-colours heuristic.

        A transposition table keyed on board hash avoids expanding the same
        state twice.  If the state budget is exhausted the solver falls back
        to :class:`LookaheadSolver`.

        Args:
            board: The initial Board instance.  It is **not** mutated.

        Returns:
            A list of colour indices representing the move sequence.
        """
        # Trivial case: already solved.
        if board.is_solved():
            return []

        # Priority queue entries: (f, tie_breaker, g, moves_list, board_copy)
        # The tie_breaker ensures deterministic ordering when f values collide
        # and avoids comparing Board objects.
        initial = board.copy()
        h0 = self._heuristic(initial)
        counter: int = 0  # monotonic tie-breaker
        open_heap: list[tuple[int, int, int, list[int], Board]] = [
            (h0, counter, 0, [], initial)
        ]

        # Transposition table: board_hash -> best g seen
        visited: dict[int, int] = {hash(initial): 0}
        states_explored: int = 0

        while open_heap:
            _f, _tie, g, moves, current = heapq.heappop(open_heap)
            states_explored += 1

            # Budget exhausted -- fall back.
            if states_explored > self.max_states:
                return self._fallback(current, moves)

            current_color = int(current.grid[0, 0])

            for color in range(current.num_colors):
                if color == current_color:
                    continue

                child = current.copy()
                child.apply_move(color)
                new_moves = moves + [color]

                if child.is_solved():
                    return new_moves

                child_hash = hash(child)
                new_g = g + 1

                # Skip if we've already reached this state in fewer moves.
                prev_g: Optional[int] = visited.get(child_hash)
                if prev_g is not None and prev_g <= new_g:
                    continue
                visited[child_hash] = new_g

                h = self._heuristic(child)
                f = new_g + h
                counter += 1
                heapq.heappush(open_heap, (f, counter, new_g, new_moves, child))

        # Open set exhausted without solution (should not happen on a valid board).
        # Fall back as a last resort.
        return self._fallback(board, [])

    # ------------------------------------------------------------------
    # Fallback
    # ------------------------------------------------------------------

    @staticmethod
    def _fallback(board: Board, moves_so_far: list[int]) -> list[int]:
        """Continue solving with :class:`LookaheadSolver` when A* exceeds budget.

        Args:
            board: The board state at the point A* bailed out.
            moves_so_far: Moves already accumulated by A*.

        Returns:
            Combined move list (A* prefix + LookaheadSolver suffix).
        """
        remaining_moves = LookaheadSolver().solve(board)
        return moves_so_far + remaining_moves
