"""Unit tests for the Board class and flood-fill logic."""

import sys
from pathlib import Path

import numpy as np
import pytest

# Ensure project root is on the path.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from board import Board


class TestBoardInit:
    def test_valid_grid(self):
        grid = np.array([[0, 1], [2, 0]])
        b = Board(grid, num_colors=3)
        assert b.rows == 2
        assert b.cols == 2
        assert b.num_colors == 3

    def test_rejects_3d_grid(self):
        with pytest.raises(ValueError, match="2-dimensional"):
            Board(np.zeros((2, 2, 2)), num_colors=3)

    def test_rejects_out_of_range(self):
        with pytest.raises(ValueError, match="range"):
            Board(np.array([[0, 5]]), num_colors=3)


class TestFloodedRegion:
    def test_single_cell(self):
        b = Board(np.array([[0]]), num_colors=1)
        assert b.get_flooded_region() == {(0, 0)}

    def test_uniform_grid(self):
        grid = np.zeros((3, 3), dtype=int)
        b = Board(grid, num_colors=1)
        assert len(b.get_flooded_region()) == 9

    def test_partial_flood(self):
        grid = np.array([
            [0, 0, 1],
            [0, 1, 1],
            [1, 1, 1],
        ])
        b = Board(grid, num_colors=2)
        flooded = b.get_flooded_region()
        assert flooded == {(0, 0), (0, 1), (1, 0)}

    def test_corner_only(self):
        grid = np.array([
            [0, 1],
            [1, 1],
        ])
        b = Board(grid, num_colors=2)
        assert b.get_flooded_region() == {(0, 0)}


class TestFrontier:
    def test_simple_frontier(self):
        grid = np.array([
            [0, 1],
            [2, 1],
        ])
        b = Board(grid, num_colors=3)
        flooded = b.get_flooded_region()
        frontier = b.get_frontier(flooded)
        assert 1 in frontier
        assert 2 in frontier
        assert (0, 1) in frontier[1]
        assert (1, 0) in frontier[2]


class TestApplyMove:
    def test_apply_different_color(self):
        grid = np.array([
            [0, 0, 1],
            [0, 1, 1],
            [1, 1, 1],
        ])
        b = Board(grid, num_colors=2)
        size = b.apply_move(1)
        # After changing top-left region to 1, entire board is colour 1.
        assert size == 9
        assert b.is_solved()

    def test_apply_same_color_noop(self):
        grid = np.array([
            [0, 1],
            [1, 1],
        ])
        b = Board(grid, num_colors=2)
        size = b.apply_move(0)
        assert size == 1  # No expansion

    def test_multi_step_solve(self):
        grid = np.array([
            [0, 1, 2],
            [0, 1, 2],
            [0, 1, 2],
        ])
        b = Board(grid, num_colors=3)
        b.apply_move(1)
        assert not b.is_solved()
        b.apply_move(2)
        assert b.is_solved()


class TestIsSolved:
    def test_solved(self):
        grid = np.ones((4, 4), dtype=int)
        assert Board(grid, num_colors=2).is_solved()

    def test_not_solved(self):
        grid = np.array([[0, 1], [1, 0]])
        assert not Board(grid, num_colors=2).is_solved()

    def test_empty_grid(self):
        grid = np.zeros((0, 0), dtype=int)
        assert Board(grid, num_colors=1).is_solved()


class TestRemainingColors:
    def test_solved_board(self):
        grid = np.zeros((3, 3), dtype=int)
        assert Board(grid, num_colors=2).remaining_colors() == 0

    def test_two_remaining(self):
        grid = np.array([
            [0, 1, 2],
            [0, 1, 2],
            [0, 1, 2],
        ])
        b = Board(grid, num_colors=3)
        assert b.remaining_colors() == 2


class TestHashAndEquality:
    def test_equal_boards_hash(self):
        g = np.array([[0, 1], [1, 0]])
        b1 = Board(g, num_colors=2)
        b2 = Board(g.copy(), num_colors=2)
        assert b1 == b2
        assert hash(b1) == hash(b2)

    def test_different_boards(self):
        b1 = Board(np.array([[0, 1]]), num_colors=2)
        b2 = Board(np.array([[1, 0]]), num_colors=2)
        assert b1 != b2

    def test_copy_independence(self):
        b1 = Board(np.array([[0, 1], [1, 0]]), num_colors=2)
        b2 = b1.copy()
        b2.apply_move(1)
        assert b1 != b2
