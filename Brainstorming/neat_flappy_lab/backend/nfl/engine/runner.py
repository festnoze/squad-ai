"""Runner — orchestrates one generation end to end.

Ties the pieces together: lifetime learning (optional GD by imitation),
evaluation in the Flappy world, fitness assignment, teacher/state bookkeeping
for the next generation, statistics, and reproduction.

The hybridization regimes differ in how lifetime GD interacts with the genome:

* ``evolution_only`` — no GD; evaluate the genomes' birth networks.
* ``write_back``     — GD on each network, **write the learned weights back into
  the genome** (so offspring inherit them), then evaluate.
* ``evaluate_only``  — GD on each network, evaluate with the learned weights, but
  leave the genome (birth weights) untouched for reproduction.
* ``confrontation``  — the population is split into a NEAT camp (no GD, breeds
  within itself) and a GD camp (GD only, weights persisted, no breeding); both
  camps play in the same world so their champions are directly comparable.

An optional ``on_frame`` callback receives a per-tick world snapshot plus the
selected bird's live activations, so the API layer can stream the game.
"""

from __future__ import annotations

from collections.abc import Callable

import numpy as np

from ..config import Mode, SimConfig, TeacherScope
from ..learning.imitation import build_teacher, imitate
from ..neat.population import Population
from ..nn.network import Network

# Subsample cap for the imitation state buffer (keeps GD cheap & memory bounded).
_STATE_BUFFER_CAP = 2000

FrameCallback = Callable[[dict, dict], None]


class Runner:
    """Drives the NEAT (+ optional GD) loop over the Flappy environment."""

    def __init__(self, config: SimConfig) -> None:
        # Import here to avoid a hard module-load dependency cycle with sim.
        from ..sim.flappy import FlappyEnv

        self.config = config
        self.rng = np.random.default_rng(config.seed)
        self.population = Population(config, self.rng)
        self.env = FlappyEnv(config, self.rng)

        self.teacher_genomes: list = []          # imitation teachers (top-K)
        self.state_buffer: np.ndarray | None = None  # observations for imitation
        self.selected_bird: int = 0              # index whose network we surface

        if config.mode == Mode.confrontation:
            self.population.assign_camps(config.gd_ratio)

    # ------------------------------------------------------------------- camps ---
    def _ensure_camps(self) -> None:
        """Lazily split the population when confrontation mode is switched on live.

        ``mode`` is a soft (hot-swappable) parameter, so a run started in another
        mode may enter confrontation mid-flight; in that case the split happens
        here, freezing the GD camp's topologies from this generation onward.
        """
        genomes = self.population.genomes
        if any(g.camp == "gd" for g in genomes):
            return
        self.population.assign_camps(self.config.gd_ratio)

    def _camp_labels(self) -> list[str]:
        """One label per bird, telling the UI how each one is being trained."""
        mode = self.config.mode
        if mode == Mode.confrontation:
            return [g.camp for g in self.population.genomes]
        if mode == Mode.evolution_only:
            label = "neat"
        elif mode == Mode.gradient_only:
            label = "gd"
        else:
            label = "hybrid"
        return [label] * len(self.population.genomes)

    # --------------------------------------------------------- lifetime learning --
    def _networks_for_evaluation(self) -> list[Network]:
        """Build the networks that will play this generation.

        For the GD modes, each network is trained by imitation first; ``write_back``
        also copies the learned weights into its genome. In confrontation mode only
        the GD camp trains (and always persists — GD is its sole way to improve).
        """
        cfg = self.config
        genomes = self.population.genomes

        teacher_fn = None
        if cfg.mode != Mode.evolution_only and cfg.gd_steps > 0:
            teacher_fn = build_teacher(self.teacher_genomes)

        # Persist learned weights into the genome for write_back (Lamarckian) and
        # for the no-reproduction regimes (gradient_only / the GD camp), where GD
        # must stick because nothing else ever changes the weights.
        persist = cfg.mode in (Mode.write_back, Mode.gradient_only, Mode.confrontation)
        confrontation = cfg.mode == Mode.confrontation

        networks: list[Network] = []
        for genome in genomes:
            net = Network.from_genome(genome)
            if teacher_fn is not None and (not confrontation or genome.camp == "gd"):
                imitate(net, teacher_fn, self.state_buffer, cfg, self.rng)
                if persist:
                    net.write_weights_to_genome(genome)
            networks.append(net)
        return networks

    # ------------------------------------------------------------- evaluation -----
    def _evaluate(
        self,
        networks: list[Network],
        camps: list[str],
        on_frame: FrameCallback | None,
    ) -> tuple[np.ndarray, np.ndarray | None]:
        """Play one episode with all birds; return (fitness, recorded states)."""
        env = self.env
        n = len(networks)
        obs = env.reset(n)
        recorded: list[np.ndarray] = []

        done = False
        while not done:
            alive = env.alive
            actions = np.zeros(n, dtype=np.float64)
            for i in range(n):
                if alive[i]:
                    actions[i] = float(networks[i].forward(obs[i])[0])

            result = env.step(actions)
            obs = result.observations

            # Record the states living birds actually saw (for imitation next gen).
            living = result.alive
            if living.any():
                recorded.append(obs[living])

            if on_frame is not None:
                # Read the selected bird FRESH each tick so changing the selection
                # mid-episode updates the streamed activations live.
                sel = self.selected_bird if 0 <= self.selected_bird < n else 0
                sel_act = networks[sel].activations()
                state = env.render_state()
                for bird, camp in zip(state["birds"], camps):
                    bird["camp"] = camp
                on_frame(state, sel_act)

            done = result.done

        states = np.concatenate(recorded, axis=0) if recorded else None
        return env.fitness.copy(), states

    # ----------------------------------------------------------------- teachers ---
    def _update_teachers(
        self, evaluated: list, order: np.ndarray, camps: list[str]
    ) -> None:
        """Pick next generation's imitation teachers.

        Default: top-K overall. In confrontation mode with ``camp`` scope, the GD
        camp only ever imitates its own champions, so the duel stays pure.
        """
        cfg = self.config
        ranked = [int(i) for i in order]
        if cfg.mode == Mode.confrontation and cfg.gd_teacher_scope == TeacherScope.camp:
            ranked = [i for i in ranked if camps[i] == "gd"]
        self.teacher_genomes = [evaluated[i].copy() for i in ranked[: cfg.teacher_k]]

    # ------------------------------------------------------------- generation -----
    def step_generation(self, on_frame: FrameCallback | None = None) -> dict:
        """Run exactly one generation; return its statistics snapshot."""
        cfg = self.config
        gen_index = self.population.generation

        if cfg.mode == Mode.confrontation:
            self._ensure_camps()
        camps = self._camp_labels()

        networks = self._networks_for_evaluation()
        fitness, states = self._evaluate(networks, camps, on_frame)

        for genome, fit in zip(self.population.genomes, fitness):
            genome.fitness = float(fit)

        # Snapshot the evaluated generation before reproduction rewrites genomes.
        evaluated = list(self.population.genomes)
        order = np.argsort(fitness)[::-1]

        # Teachers + state buffer for next generation's lifetime learning.
        self._update_teachers(evaluated, order, camps)
        if states is not None and len(states) > 0:
            if len(states) > _STATE_BUFFER_CAP:
                idx = self.rng.integers(0, len(states), size=_STATE_BUFFER_CAP)
                states = states[idx]
            self.state_buffer = states

        if cfg.mode == Mode.gradient_only:
            # Pure GD: keep the frozen-topology genomes, just advance the counter.
            self.population.advance_without_reproduction()
        elif cfg.mode == Mode.confrontation:
            self.population.evolve_confrontation()
        else:
            self.population.evolve()  # speciates `evaluated`, then builds the next gen

        return self._stats(gen_index, evaluated, fitness, order, camps)

    def _stats(
        self,
        gen_index: int,
        evaluated: list,
        fitness: np.ndarray,
        order: np.ndarray,
        camps: list[str],
    ) -> dict:
        """Build the per-generation statistics / message payload."""
        best = evaluated[int(order[0])]
        complexity = float(np.mean([g.complexity for g in evaluated]))
        leaderboard = [
            {
                "birdId": int(i),
                "fitness": float(fitness[int(i)]),
                "camp": camps[int(i)],
            }
            for i in order[: min(10, len(order))]
        ]

        # Per-camp aggregates — the heart of the NEAT-vs-GD confrontation view.
        camp_stats: dict[str, dict] = {}
        camps_arr = np.array(camps)
        for camp in sorted(set(camps)):
            mask = camps_arr == camp
            camp_fit = fitness[mask]
            best_local = int(np.flatnonzero(mask)[int(np.argmax(camp_fit))])
            camp_stats[camp] = {
                "count": int(mask.sum()),
                "fitnessMax": float(camp_fit.max()),
                "fitnessMean": float(camp_fit.mean()),
                "bestBirdId": best_local,
            }

        return {
            "gen": gen_index,
            "fitnessMax": float(fitness.max()),
            "fitnessMean": float(fitness.mean()),
            "species": len(self.population.species),
            "complexity": complexity,
            "bestGenome": best.to_dict(),
            "bestFitness": float(best.fitness),
            "leaderboard": leaderboard,
            "camps": camp_stats,
            "winnerCamp": camps[int(order[0])],
        }

    # ----------------------------------------------------------------- control ----
    def select_bird(self, bird_id: int) -> None:
        """Choose which bird's network the frame stream surfaces."""
        self.selected_bird = int(bird_id)
