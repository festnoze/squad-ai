"""Vectorized Flappy-Bird-style world for population-based neuroevolution.

A whole *population* of birds plays in the **same** world at once so that every
genome is judged against an identical pipe stream (fair comparison). All birds
share a fixed horizontal position ``BIRD_X``; the pipes scroll left at a constant
speed and new pipes spawn endlessly as old ones leave the screen.

Each tick a bird's controlling network reads a normalized observation vector --
one value per *active* sensor, in :attr:`SimConfig.active_sensors` order -- and
emits a single scalar. The convention (enforced by the caller) is *flap when the
output > 0.5*. Observations are returned as a ``numpy`` array normalized to
roughly ``[-1, 1]`` so they feed straight into a neural net. A bias term is
**not** part of the observation; the network supplies its own.

Screen convention: ``y`` grows downward, so an upward flap uses a *negative*
velocity.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from ..config import Sensor, SimConfig

# --- Physics / world constants (tuned for playability in a ~600x400 world) ---
WORLD_W: float = 600.0       # world width (px)
WORLD_H: float = 400.0       # world height (px)
BIRD_X: float = 120.0        # fixed horizontal position of every bird (px)
GRAVITY: float = 0.58        # downward acceleration per tick (px/tick^2)
FLAP_VELOCITY: float = -7.2  # vy set on flap (negative = upward)
PIPE_SPEED: float = 3.8      # leftward scroll speed of pipes (px/tick)
PIPE_GAP: float = 98.0       # vertical opening height of a pipe (px)
PIPE_SPACING: float = 185.0  # horizontal distance between consecutive pipes (px)
PIPE_WIDTH: float = 60.0     # horizontal thickness of a pipe (px)
BIRD_RADIUS: float = 12.0    # bird collision radius (px)

# Reward shaping. The fitness landscape must be SMOOTH for evolution to climb:
# a tiny survival bonus, a continuous alignment bonus (rewards being vertically
# centered on the next gap even before clearing it — gives partial credit and a
# gradient toward navigation), and a large bonus for actually clearing a pipe so
# navigation skill dominates selection.
ALIVE_REWARD: float = 0.04   # small per-tick survival bonus
ALIGN_REWARD: float = 0.12   # per-tick bonus scaled by alignment with the next gap
PASS_REWARD: float = 5.0     # bonus when a pipe is cleared (navigation is the goal)

# Vertical margin kept from the world edges when sampling a gap center.
_GAP_MARGIN: float = 60.0


@dataclass
class Pipe:
    """A single pipe obstacle.

    ``x`` is the left edge of the pipe column; the solid parts are everything
    *except* the vertical gap. The gap spans ``[gap_y - gap_h/2, gap_y + gap_h/2]``.
    """

    x: float          # left edge (px); pipe occupies [x, x + PIPE_WIDTH]
    gap_y: float      # vertical center of the opening (px)
    gap_h: float = PIPE_GAP  # opening height (px)
    passed: bool = False     # has the population's x already cleared this pipe?


@dataclass
class StepResult:
    """Outcome of a single :meth:`FlappyEnv.step` call.

    Attributes:
        observations: ``(n_agents, num_sensors)`` float array. One row per bird,
            one column per active sensor (in config order). Dead birds' rows are
            zeros.
        alive: ``(n_agents,)`` bool mask, the alive state *after* this step.
        rewards: ``(n_agents,)`` float, reward gained by each bird *this* step.
        done: ``True`` when every bird is dead or ``max_ticks_per_gen`` is hit.
    """

    observations: np.ndarray
    alive: np.ndarray
    rewards: np.ndarray
    done: bool


class FlappyEnv:
    """Population-level Flappy world simulated with numpy-vectorized birds.

    One instance hosts ``n_agents`` birds that all experience the identical pipe
    stream generated deterministically from the provided ``rng`` at :meth:`reset`.
    """

    def __init__(self, config: SimConfig, rng: np.random.Generator) -> None:
        """Store config/rng. Call :meth:`reset` before stepping."""
        self.config = config
        self.rng = rng

        self._n: int = 0
        self._y: np.ndarray = np.empty(0, dtype=np.float64)
        self._vy: np.ndarray = np.empty(0, dtype=np.float64)
        self._alive: np.ndarray = np.empty(0, dtype=bool)
        self._fitness: np.ndarray = np.empty(0, dtype=np.float64)
        self.pipes: list[Pipe] = []
        self.tick: int = 0

    # ------------------------------------------------------------------ helpers
    @property
    def num_sensors(self) -> int:
        """Number of active sensors == observation columns (bias excluded)."""
        return len(self.config.active_sensors)

    def _sample_gap_y(self) -> float:
        """Draw a gap center within safe vertical margins."""
        lo = _GAP_MARGIN + PIPE_GAP / 2.0
        hi = WORLD_H - _GAP_MARGIN - PIPE_GAP / 2.0
        if hi <= lo:  # degenerate world; fall back to center
            return WORLD_H / 2.0
        return float(self.rng.uniform(lo, hi))

    def _next_pipe_idx_array(self) -> np.ndarray | None:
        """Index of the "next" pipe (right edge ahead of BIRD_X), or None."""
        for i, p in enumerate(self.pipes):
            if p.x + PIPE_WIDTH >= BIRD_X:
                return i
        return None

    def _observe(self) -> np.ndarray:
        """Build the ``(n, num_sensors)`` normalized observation array.

        The "next" pipe is the first pipe whose right edge is still ahead of the
        birds. ``dy_gap`` is measured per-bird (depends on each bird's ``y``);
        the rest are either per-bird or pipe-only. Dead birds get zero rows.
        """
        n = self._n
        obs = np.zeros((n, self.num_sensors), dtype=np.float64)
        if n == 0:
            return obs

        idx = self._next_pipe_idx_array()
        if idx is None:
            next_pipe = None
            after_pipe = None
        else:
            next_pipe = self.pipes[idx]
            after_pipe = self.pipes[idx + 1] if idx + 1 < len(self.pipes) else None

        # Per-sensor normalized columns.
        for col, sensor in enumerate(self.config.active_sensors):
            if sensor is Sensor.dy_gap:
                gap_y = next_pipe.gap_y if next_pipe is not None else WORLD_H / 2.0
                obs[:, col] = (gap_y - self._y) / WORLD_H
            elif sensor is Sensor.dx_pipe:
                dx = (next_pipe.x - BIRD_X) if next_pipe is not None else WORLD_W
                obs[:, col] = dx / WORLD_W
            elif sensor is Sensor.vy:
                # Velocity rarely exceeds ~|terminal|; WORLD_H/20 is a sane scale.
                obs[:, col] = self._vy / (WORLD_H / 20.0)
            elif sensor is Sensor.dy_gap2:
                gap_y2 = after_pipe.gap_y if after_pipe is not None else WORLD_H / 2.0
                obs[:, col] = (gap_y2 - self._y) / WORLD_H
            elif sensor is Sensor.y_abs:
                # Map [0, WORLD_H] -> [-1, 1].
                obs[:, col] = (self._y / WORLD_H) * 2.0 - 1.0

        # Zero out dead birds.
        obs[~self._alive] = 0.0
        return obs

    # -------------------------------------------------------------------- reset
    def reset(self, n_agents: int) -> np.ndarray:
        """Spawn ``n_agents`` birds and a fresh deterministic pipe stream.

        Birds start at center height with ``vy=0``, all alive and zero fitness.
        Returns the initial ``(n_agents, num_sensors)`` observation array.
        """
        self._n = int(n_agents)
        self._y = np.full(self._n, WORLD_H / 2.0, dtype=np.float64)
        self._vy = np.zeros(self._n, dtype=np.float64)
        self._alive = np.ones(self._n, dtype=bool)
        self._fitness = np.zeros(self._n, dtype=np.float64)
        self.tick = 0

        # Pre-generate enough pipes to cover the screen plus a buffer ahead.
        self.pipes = []
        first_x = WORLD_W + PIPE_WIDTH  # first pipe starts just off the right edge
        n_initial = int(np.ceil((WORLD_W + 2 * PIPE_SPACING) / PIPE_SPACING)) + 2
        for k in range(n_initial):
            self.pipes.append(
                Pipe(x=first_x + k * PIPE_SPACING, gap_y=self._sample_gap_y())
            )

        return self._observe()

    # --------------------------------------------------------------------- step
    def step(self, actions: np.ndarray) -> StepResult:
        """Advance the world one tick.

        Args:
            actions: ``(n_agents,)`` array; a bird flaps where ``actions > 0.5``.
                Dead birds' actions are ignored.

        Returns:
            A :class:`StepResult` with post-step observations, alive mask,
            per-bird reward gained this tick, and a ``done`` flag.
        """
        n = self._n
        rewards = np.zeros(n, dtype=np.float64)
        if n == 0:
            return StepResult(self._observe(), self._alive.copy(), rewards, True)

        actions = np.asarray(actions, dtype=np.float64).reshape(-1)
        was_alive = self._alive.copy()

        # --- Apply flaps then gravity to living birds --------------------------
        flap = (actions > 0.5) & self._alive
        self._vy[flap] = FLAP_VELOCITY
        self._vy[self._alive] += GRAVITY
        self._y[self._alive] += self._vy[self._alive]

        # --- Scroll pipes and recycle off-screen ones into the stream ----------
        for p in self.pipes:
            p.x -= PIPE_SPEED
        # Drop pipes fully off the left edge; append fresh ones on the right to
        # keep the stream endless and evenly spaced.
        while self.pipes and self.pipes[0].x + PIPE_WIDTH < 0.0:
            self.pipes.pop(0)
        rightmost = max((p.x for p in self.pipes), default=WORLD_W)
        while rightmost < WORLD_W + 2 * PIPE_SPACING:
            rightmost += PIPE_SPACING
            self.pipes.append(Pipe(x=rightmost, gap_y=self._sample_gap_y()))

        # --- Pass detection: award when a pipe's right edge crosses BIRD_X -----
        for p in self.pipes:
            if not p.passed and (p.x + PIPE_WIDTH) < BIRD_X:
                p.passed = True
                rewards[was_alive] += PASS_REWARD

        # --- Collision detection (vectorized over birds) -----------------------
        # Out of vertical bounds.
        out_of_bounds = (self._y - BIRD_RADIUS < 0.0) | (self._y + BIRD_RADIUS > WORLD_H)

        # Overlap with any pipe's solid part. A bird (circle approximated as a
        # box of half-size BIRD_RADIUS at BIRD_X) hits a pipe if it horizontally
        # overlaps the column AND its y is outside the gap.
        hit_pipe = np.zeros(n, dtype=bool)
        for p in self.pipes:
            x_overlap = (BIRD_X + BIRD_RADIUS > p.x) and (BIRD_X - BIRD_RADIUS < p.x + PIPE_WIDTH)
            if not x_overlap:
                continue
            gap_top = p.gap_y - p.gap_h / 2.0
            gap_bot = p.gap_y + p.gap_h / 2.0
            in_gap = (self._y - BIRD_RADIUS >= gap_top) & (self._y + BIRD_RADIUS <= gap_bot)
            hit_pipe |= ~in_gap

        newly_dead = self._alive & (out_of_bounds | hit_pipe)
        self._alive[newly_dead] = False

        # --- Survival + alignment reward for birds still alive -----------------
        # Continuous shaping: full ALIGN_REWARD when centered on the next gap,
        # fading to 0 when half a world away. Gives partial credit + a smooth
        # gradient toward navigation, so evolution converges instead of relying
        # on a few lucky genomes.
        idx = self._next_pipe_idx_array()
        gap_y = self.pipes[idx].gap_y if idx is not None else WORLD_H / 2.0
        align = 1.0 - np.clip(np.abs(self._y - gap_y) / (WORLD_H * 0.5), 0.0, 1.0)
        shaped = ALIVE_REWARD + ALIGN_REWARD * align
        rewards[self._alive] += shaped[self._alive]

        # Dead-this-tick birds keep nothing extra; ensure dead birds get 0.
        rewards[~was_alive] = 0.0

        # --- Accumulate fitness / advance time ---------------------------------
        self._fitness += rewards
        self.tick += 1

        done = (not self._alive.any()) or (self.tick >= self.config.max_ticks_per_gen)
        return StepResult(self._observe(), self._alive.copy(), rewards, bool(done))

    # ---------------------------------------------------------------- accessors
    @property
    def fitness(self) -> np.ndarray:
        """``(n_agents,)`` cumulative fitness."""
        return self._fitness

    @property
    def alive(self) -> np.ndarray:
        """``(n_agents,)`` current alive mask."""
        return self._alive

    # ------------------------------------------------------------------- render
    def render_state(self) -> dict:
        """JSON-serializable snapshot of the world for the frontend.

        Only on-screen pipes are included. Coordinates are world pixels.
        """
        birds = [
            {
                "id": int(i),
                "x": float(BIRD_X),
                "y": float(self._y[i]),
                "vy": float(self._vy[i]),
                "alive": bool(self._alive[i]),
                "fitness": float(self._fitness[i]),
            }
            for i in range(self._n)
        ]
        pipes = [
            {"x": float(p.x), "gapY": float(p.gap_y), "gapH": float(p.gap_h)}
            for p in self.pipes
            if (p.x + PIPE_WIDTH) >= 0.0 and p.x <= WORLD_W
        ]
        return {
            "birds": birds,
            "pipes": pipes,
            "tick": int(self.tick),
            "world": {"w": WORLD_W, "h": WORLD_H},
        }
