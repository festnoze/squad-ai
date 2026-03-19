"""Unit tests for the solver algorithms."""

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from board import Board
from solver import AStarSolver, GreedySolver, LookaheadSolver


def _apply_moves(board: Board, moves: list[int]) -> Board:
    """Apply a list of moves to a copy and return the resulting board."""
    b = board.copy()
    for m in moves:
        b.apply_move(m)
    return b


class TestGreedySolver:
    def test_already_solved(self):
        grid = np.zeros((3, 3), dtype=int)
        b = Board(grid, num_colors=2)
        moves = GreedySolver().solve(b)
        assert moves == []

    def test_simple_solve(self):
        grid = np.array([
            [0, 1],
            [0, 1],
        ])
        b = Board(grid, num_colors=2)
        moves = GreedySolver().solve(b)
        result = _apply_moves(b, moves)
        assert result.is_solved()

    def test_three_color(self):
        grid = np.array([
            [0, 1, 2],
            [0, 1, 2],
            [0, 1, 2],
        ])
        b = Board(grid, num_colors=3)
        moves = GreedySolver().solve(b)
        result = _apply_moves(b, moves)
        assert result.is_solved()
        assert len(moves) == 2

    def test_random_board(self):
        rng = np.random.RandomState(42)
        grid = rng.randint(0, 4, size=(6, 6))
        b = Board(grid, num_colors=4)
        moves = GreedySolver().solve(b)
        result = _apply_moves(b, moves)
        assert result.is_solved()


class TestLookaheadSolver:
    def test_already_solved(self):
        grid = np.ones((3, 3), dtype=int)
        b = Board(grid, num_colors=2)
        moves = LookaheadSolver(depth=3).solve(b)
        assert moves == []

    def test_depth_1_equals_greedy(self):
        rng = np.random.RandomState(7)
        grid = rng.randint(0, 3, size=(4, 4))
        b = Board(grid, num_colors=3)
        greedy_moves = GreedySolver().solve(b)
        lookahead_moves = LookaheadSolver(depth=1).solve(b)
        # Depth-1 applies one move per window = same as greedy.
        assert lookahead_moves == greedy_moves

    def test_solves_correctly_depth2(self):
        rng = np.random.RandomState(123)
        grid = rng.randint(0, 6, size=(8, 8))
        b = Board(grid, num_colors=6)
        moves = LookaheadSolver(depth=2).solve(b)
        result = _apply_moves(b, moves)
        assert result.is_solved()

    def test_solves_correctly_depth3(self):
        rng = np.random.RandomState(99)
        grid = rng.randint(0, 4, size=(6, 6))
        b = Board(grid, num_colors=4)
        moves = LookaheadSolver(depth=3).solve(b)
        result = _apply_moves(b, moves)
        assert result.is_solved()

    def test_solves_correctly_depth4(self):
        rng = np.random.RandomState(42)
        grid = rng.randint(0, 6, size=(8, 8))
        b = Board(grid, num_colors=6)
        moves = LookaheadSolver(depth=4).solve(b)
        result = _apply_moves(b, moves)
        assert result.is_solved()

    def test_deeper_beats_or_ties_shallow(self):
        rng = np.random.RandomState(55)
        grid = rng.randint(0, 4, size=(6, 6))
        b = Board(grid, num_colors=4)
        moves_d2 = LookaheadSolver(depth=2).solve(b)
        moves_d4 = LookaheadSolver(depth=4).solve(b)
        # Deeper lookahead should generally produce fewer or equal moves.
        assert len(moves_d4) <= len(moves_d2)
        assert _apply_moves(b, moves_d4).is_solved()

    def test_applies_full_sequence(self):
        """Verify the solver applies multi-move windows, not just one."""
        grid = np.array([
            [0, 1, 2],
            [0, 1, 2],
            [0, 1, 2],
        ])
        b = Board(grid, num_colors=3)
        moves = LookaheadSolver(depth=3).solve(b)
        result = _apply_moves(b, moves)
        assert result.is_solved()
        assert len(moves) == 2  # optimal: [1, 2]


class TestAStarSolver:
    def test_already_solved(self):
        grid = np.zeros((2, 2), dtype=int)
        b = Board(grid, num_colors=2)
        moves = AStarSolver().solve(b)
        assert moves == []

    def test_small_board_optimal(self):
        grid = np.array([
            [0, 1],
            [0, 1],
        ])
        b = Board(grid, num_colors=2)
        moves = AStarSolver().solve(b)
        assert len(moves) == 1
        assert moves == [1]

    def test_small_board_3_colors(self):
        grid = np.array([
            [0, 1, 2],
            [0, 1, 2],
            [0, 1, 2],
        ])
        b = Board(grid, num_colors=3)
        moves = AStarSolver().solve(b)
        result = _apply_moves(b, moves)
        assert result.is_solved()
        # Optimal should be 2 moves (1 then 2).
        assert len(moves) == 2

    def test_fallback_on_large_board(self):
        rng = np.random.RandomState(42)
        grid = rng.randint(0, 6, size=(10, 10))
        b = Board(grid, num_colors=6)
        # With a tiny budget the A* should fall back.
        moves = AStarSolver(max_states=100).solve(b)
        result = _apply_moves(b, moves)
        assert result.is_solved()


# ---------------------------------------------------------------------------
# Full 14x14 resolution tests (real game size)
# ---------------------------------------------------------------------------


class TestFullResolution14x14:
    """End-to-end solve of 14x14 boards with 6 colours -- real game conditions."""

    SEEDS = [1, 42, 77, 123, 256]

    def test_greedy_solves_14x14(self):
        for seed in self.SEEDS:
            rng = np.random.RandomState(seed)
            grid = rng.randint(0, 6, size=(14, 14))
            b = Board(grid, num_colors=6)
            moves = GreedySolver().solve(b)
            result = _apply_moves(b, moves)
            assert result.is_solved(), f"Greedy failed on seed {seed}"
            print(f"  Greedy   seed={seed}: solved in {len(moves)} moves")

    def test_lookahead_d3_solves_14x14(self):
        for seed in self.SEEDS:
            rng = np.random.RandomState(seed)
            grid = rng.randint(0, 6, size=(14, 14))
            b = Board(grid, num_colors=6)
            moves = LookaheadSolver(depth=3).solve(b)
            result = _apply_moves(b, moves)
            assert result.is_solved(), f"Lookahead d=3 failed on seed {seed}"
            print(f"  Lookahead(3) seed={seed}: solved in {len(moves)} moves")

    def test_lookahead_d4_solves_14x14(self):
        for seed in self.SEEDS:
            rng = np.random.RandomState(seed)
            grid = rng.randint(0, 6, size=(14, 14))
            b = Board(grid, num_colors=6)
            moves = LookaheadSolver(depth=4).solve(b)
            result = _apply_moves(b, moves)
            assert result.is_solved(), f"Lookahead d=4 failed on seed {seed}"
            print(f"  Lookahead(4) seed={seed}: solved in {len(moves)} moves")

    def test_deeper_is_better_14x14(self):
        """On real-size boards, deeper lookahead should use fewer moves."""
        total_greedy = 0
        total_d3 = 0
        total_d4 = 0
        for seed in self.SEEDS:
            rng = np.random.RandomState(seed)
            grid = rng.randint(0, 6, size=(14, 14))
            b = Board(grid, num_colors=6)
            total_greedy += len(GreedySolver().solve(b))
            total_d3 += len(LookaheadSolver(depth=3).solve(b))
            total_d4 += len(LookaheadSolver(depth=4).solve(b))
        print(f"\n  Totals over {len(self.SEEDS)} boards:")
        print(f"    Greedy:       {total_greedy} moves")
        print(f"    Lookahead(3): {total_d3} moves")
        print(f"    Lookahead(4): {total_d4} moves")
        assert total_d3 <= total_greedy, "Depth 3 should beat greedy overall"
        assert total_d4 <= total_d3, "Depth 4 should beat depth 3 overall"
