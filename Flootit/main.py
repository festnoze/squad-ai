"""Flood-It Bot -- Autonomous solver and auto-clicker.

Usage::

    python main.py                        # default: lookahead solver, depth 3
    python main.py --solver greedy        # pure greedy
    python main.py --solver astar         # A* (small boards only)
    python main.py --depth 4             # deeper lookahead
    python main.py --dry-run             # solve without clicking
"""

from __future__ import annotations

import argparse
import time

import numpy as np

from config import (
    CLICK_DELAY_MS,
    LOOKAHEAD_DEPTH,
)
from region_selector import RegionSelector
from screen_capture import ScreenCapture
from color_quantizer import ColorQuantizer
from board import Board
from solver import AStarSolver, GreedySolver, LookaheadSolver
from auto_clicker import AutoClicker


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _get_region() -> tuple[int, int, int, int] | None:
    """Prompt the user to select the game region on screen."""
    print("Draw a rectangle around the Flood-It game board ...")
    selector = RegionSelector()
    region = selector.select()
    print(f"Region selected: {region}")
    return region


def _print_grid(grid: np.ndarray, palette: np.ndarray) -> None:
    """Pretty-print the quantized grid using ANSI colour blocks."""
    ansi_colors = [
        "\033[41m",  # red bg
        "\033[42m",  # green bg
        "\033[44m",  # blue bg
        "\033[43m",  # yellow bg
        "\033[45m",  # magenta bg
        "\033[46m",  # cyan bg
        "\033[47m",  # white bg
        "\033[100m", # dark grey bg
    ]
    reset = "\033[0m"

    rows, cols = grid.shape
    for r in range(rows):
        row_str = ""
        for c in range(cols):
            idx = int(grid[r, c])
            bg = ansi_colors[idx % len(ansi_colors)]
            row_str += f"{bg} {idx} {reset}"
        print(row_str)
    print()


def _make_solver(args) -> tuple:
    """Create the solver instance from CLI args."""
    if args.solver == "greedy":
        return GreedySolver(), "Greedy"
    elif args.solver == "astar":
        return AStarSolver(), "A*"
    else:
        return LookaheadSolver(depth=args.depth), f"Lookahead (depth={args.depth})"


# ------------------------------------------------------------------
# Single game round
# ------------------------------------------------------------------

def _analyze_board(
    capture: ScreenCapture,
) -> tuple[np.ndarray, np.ndarray, int, ColorQuantizer]:
    """Capture the screen, auto-detect grid size & colours, return the parsed board.

    Returns:
        (grid, palette, grid_size, quantizer)
    """
    image = capture.capture()
    print(f"Captured image: {image.shape[1]}x{image.shape[0]} px")

    # Detect grid size.
    grid_size = ScreenCapture.detect_grid_size(image)
    cell_w = image.shape[1] / grid_size
    cell_h = image.shape[0] / grid_size
    print(f"Auto-detected grid size: {grid_size}x{grid_size}")
    print(f"  Cell size: ~{cell_w:.1f}x{cell_h:.1f} px")

    # Detect number of colours.
    num_colors, pre_palette = ScreenCapture.detect_num_colors(image, grid_size)
    print(f"Detected {num_colors} distinct colours on the board:")
    for i, c in enumerate(pre_palette):
        print(f"  [{i}] RGB({c[0]}, {c[1]}, {c[2]})")

    # Extract grid & quantize.
    raw_colors = capture.extract_grid_colors(image, grid_size)
    quantizer = ColorQuantizer(num_colors=num_colors)
    quantizer.fit(raw_colors)
    grid = quantizer.quantize(raw_colors)
    palette = quantizer.palette

    print(
        f"Board: {grid_size}x{grid_size} ({grid_size * grid_size} cells), "
        f"{len(palette)} colours"
    )
    print("Parsed grid:")
    _print_grid(grid, palette)

    return grid, palette, grid_size, quantizer


def _play_one_game(
    capture: ScreenCapture,
    region: tuple[int, int, int, int],
    args,
    game_num: int,
) -> bool:
    """Play a single round: analyse, solve, click.

    Returns:
        True if the game was solved successfully.
    """
    print(f"\n{'='*50}")
    print(f"  GAME #{game_num}")
    print(f"{'='*50}\n")

    grid, palette, grid_size, quantizer = _analyze_board(capture)
    board = Board(grid, num_colors=len(palette))

    if board.is_solved():
        print("Board is already solved (or uniform). Skipping.")
        return True

    solver, solver_name = _make_solver(args)
    print(f"Solving with {solver_name} ...")
    t0 = time.perf_counter()
    moves = solver.solve(board)
    elapsed = time.perf_counter() - t0

    print(f"Solution found in {len(moves)} moves ({elapsed:.3f}s):")
    color_names = [f"C{i}" for i in range(len(palette))]
    print("  " + " -> ".join(color_names[m] for m in moves))
    print()

    if args.dry_run:
        print("Dry run -- not clicking.")
        return True

    print(f"Executing {len(moves)} moves (delay={args.delay}ms) ...")
    clicker = AutoClicker(
        region, grid, grid_size, capture, quantizer, delay_ms=args.delay
    )
    clicker.execute_solution(moves)

    # Verification.
    time.sleep(0.5)
    print("\nVerifying result ...")
    verify_image = capture.capture()
    verify_colors = capture.extract_grid_colors(verify_image, grid_size)
    verify_grid = quantizer.quantize(verify_colors)
    verify_board = Board(verify_grid, num_colors=len(palette))

    if verify_board.is_solved():
        print("SUCCESS -- Board is solved!")
        return True
    else:
        print("Board may not be fully solved (animation delay or misclick).")
        print("Remaining distinct colours:", verify_board.remaining_colors() + 1)
        return False


# ------------------------------------------------------------------
# Wait for new game
# ------------------------------------------------------------------

def _wait_for_new_game(
    capture: ScreenCapture,
    grid_size: int,
    poll_interval: float = 1.0,
) -> None:
    """Poll the screen until a new (unsolved) board appears.

    After a game is solved the board is uniform.  This function re-captures
    periodically and waits until it detects multiple colours again, meaning
    the player (or the game itself) started a new round.

    Args:
        capture: ScreenCapture bound to the game region.
        grid_size: Grid dimension to use for sampling.
        poll_interval: Seconds between polls.
    """
    print("\nWaiting for a new game (Ctrl+C to quit) ...")

    # First, wait until we see a solved/uniform state (game ending animation).
    # Then wait until we see a non-uniform state (new game).
    while True:
        time.sleep(poll_interval)
        image = capture.capture()
        num_colors, _ = ScreenCapture.detect_num_colors(image, grid_size)
        if num_colors >= 2:
            # Multiple colours detected -> new game started.
            # Wait a tiny bit more for the board to fully render.
            time.sleep(0.5)
            print("New game detected!")
            return


# ------------------------------------------------------------------
# Main
# ------------------------------------------------------------------

def main() -> None:
    """Main orchestration pipeline with game loop."""
    parser = argparse.ArgumentParser(description="Flood-It Bot")
    parser.add_argument(
        "--solver",
        choices=["greedy", "lookahead", "astar"],
        default="lookahead",
        help="Solver algorithm to use (default: lookahead).",
    )
    parser.add_argument(
        "--depth",
        type=int,
        default=LOOKAHEAD_DEPTH,
        help="Lookahead depth for the lookahead solver (default: %(default)s).",
    )
    parser.add_argument(
        "--delay",
        type=int,
        default=CLICK_DELAY_MS,
        help="Delay between clicks in ms (default: %(default)s).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Solve the board but do not click.",
    )
    parser.add_argument(
        "--loop",
        action="store_true",
        help="Keep playing: after solving, wait for a new game and repeat.",
    )
    args = parser.parse_args()

    # ------------------------------------------------------------------
    # 1. Region selection (once)
    # ------------------------------------------------------------------
    print("=== FLOOD-IT BOT ===\n")
    region = None
    while region is None:
        region = _get_region()
        if not region:
            time.sleep(6)
            continue
        capture = ScreenCapture(region)

    # ------------------------------------------------------------------
    # 2. Game loop
    # ------------------------------------------------------------------
    game_num = 1
    last_grid_size = 14  # Initial fallback; re-detected from capture before polling.

    try:
        while True:
            _play_one_game(capture, region, args, game_num)

            # if not args.loop:
            #     break

            # Re-detect grid_size for polling from last capture.
            image = capture.capture()
            last_grid_size = ScreenCapture.detect_grid_size(image)

            _wait_for_new_game(capture, last_grid_size)
            game_num += 1

    except KeyboardInterrupt:
        print("\n\nInterrupted by user. Goodbye!")

    print("\nDone.")


if __name__ == "__main__":
    main()
