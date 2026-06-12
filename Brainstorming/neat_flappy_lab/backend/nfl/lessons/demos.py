"""Deterministic didactic demos for the React curriculum.

The production NEAT/Flappy engine is intentionally stateful and visual. These
helpers are the opposite: small, repeatable traces that make the core ideas easy
to inspect step by step from the frontend.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np


def _round(value: float, digits: int = 6) -> float:
    return float(round(float(value), digits))


def _linspace_points(xs: np.ndarray, ys: np.ndarray) -> list[dict[str, float]]:
    return [{"x": _round(x), "y": _round(y)} for x, y in zip(xs, ys)]


def linear_regression_demo(steps: int = 80, lr: float = 0.08, seed: int = 4) -> dict[str, Any]:
    """Fit y = w*x + b with plain gradient descent.

    Returns both the noisy samples and the whole optimization trace so the UI can
    scrub through the loss landscape.
    """

    steps = int(np.clip(steps, 5, 300))
    lr = float(np.clip(lr, 0.001, 0.4))
    rng = np.random.default_rng(seed)
    xs = np.linspace(-1.6, 1.6, 28)
    ys = 1.75 * xs - 0.35 + rng.normal(0.0, 0.18, size=xs.shape)

    w = -1.15
    b = 0.85
    trace: list[dict[str, float]] = []
    for step in range(steps + 1):
        preds = w * xs + b
        err = preds - ys
        loss = float(np.mean(err * err))
        trace.append(
            {
                "step": step,
                "w": _round(w),
                "b": _round(b),
                "loss": _round(loss),
            }
        )
        dw = float(2.0 * np.mean(err * xs))
        db = float(2.0 * np.mean(err))
        w -= lr * dw
        b -= lr * db

    line_x = np.array([-1.8, 1.8])
    start = trace[0]
    final = trace[-1]
    return {
        "title": "Regression lineaire par descente de gradient",
        "formula": "y = w*x + b",
        "samples": _linspace_points(xs, ys),
        "initialLine": _linspace_points(line_x, start["w"] * line_x + start["b"]),
        "finalLine": _linspace_points(line_x, final["w"] * line_x + final["b"]),
        "trace": trace,
        "explanation": [
            "Chaque point est une observation bruitee.",
            "La pente w et le biais b sont corriges dans la direction qui reduit la MSE.",
            "La courbe de loss montre ce que signifie converger sans changer de modele.",
        ],
    }


@dataclass
class TinyNetwork:
    w1: np.ndarray
    b1: np.ndarray
    w2: np.ndarray
    b2: float

    @classmethod
    def create(cls, hidden: int, seed: int) -> "TinyNetwork":
        rng = np.random.default_rng(seed)
        return cls(
            w1=rng.normal(0, 0.7, size=(hidden,)),
            b1=rng.normal(0, 0.15, size=(hidden,)),
            w2=rng.normal(0, 0.5, size=(hidden,)),
            b2=0.0,
        )

    def forward(self, xs: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        z1 = xs[:, None] * self.w1[None, :] + self.b1[None, :]
        h = np.tanh(z1)
        y = h @ self.w2 + self.b2
        return h, y


def quadratic_network_demo(
    steps: int = 160,
    lr: float = 0.035,
    hidden: int = 6,
    seed: int = 7,
) -> dict[str, Any]:
    """Train a tiny 1-hidden-layer network to approximate a quadratic curve."""

    steps = int(np.clip(steps, 20, 500))
    lr = float(np.clip(lr, 0.001, 0.2))
    hidden = int(np.clip(hidden, 3, 12))
    rng = np.random.default_rng(seed)
    xs = np.linspace(-1.3, 1.3, 44)
    ys = 0.85 * xs * xs - 0.25 * xs - 0.55 + rng.normal(0.0, 0.035, size=xs.shape)
    net = TinyNetwork.create(hidden, seed)

    trace: list[dict[str, Any]] = []
    snapshot_steps = {0, 1, 2, 5, 10, 20, 40, 80, steps}
    snapshot_steps.update(range(0, steps + 1, max(10, steps // 8)))

    for step in range(steps + 1):
        h, pred = net.forward(xs)
        err = pred - ys
        loss = float(np.mean(err * err))

        if step in snapshot_steps:
            probe = np.array([-1.0, -0.25, 0.5, 1.0])
            probe_h, probe_y = net.forward(probe)
            grid = np.linspace(-1.4, 1.4, 60)
            _, grid_pred = net.forward(grid)
            trace.append(
                {
                    "step": step,
                    "loss": _round(loss),
                    "prediction": _linspace_points(grid, grid_pred),
                    "probe": [
                        {
                            "x": _round(x),
                            "y": _round(y),
                            "hidden": [_round(v) for v in row],
                        }
                        for x, y, row in zip(probe, probe_y, probe_h)
                    ],
                    "weights": {
                        "w1": [_round(v) for v in net.w1],
                        "b1": [_round(v) for v in net.b1],
                        "w2": [_round(v) for v in net.w2],
                        "b2": _round(net.b2),
                    },
                }
            )

        grad_y = (2.0 / xs.size) * err
        grad_w2 = h.T @ grad_y
        grad_b2 = float(np.sum(grad_y))
        grad_h = grad_y[:, None] * net.w2[None, :]
        grad_z1 = grad_h * (1.0 - h * h)
        grad_w1 = np.sum(grad_z1 * xs[:, None], axis=0)
        grad_b1 = np.sum(grad_z1, axis=0)

        net.w2 -= lr * grad_w2
        net.b2 -= lr * grad_b2
        net.w1 -= lr * grad_w1
        net.b1 -= lr * grad_b1

    return {
        "title": "Reseau de neurones qui approxime une fonction quadratique",
        "formula": "1 entree -> tanh caches -> sortie lineaire",
        "samples": _linspace_points(xs, ys),
        "trace": trace,
        "explanation": [
            "Le modele n'ajoute pas une formule quadratique a la main.",
            "Les neurones caches creent des courbures locales; la sortie les combine.",
            "La descente de gradient ajuste seulement les poids, pas la topologie.",
        ],
    }


def _xor_score(weights: np.ndarray) -> float:
    x = np.array([[0.0, 0.0], [0.0, 1.0], [1.0, 0.0], [1.0, 1.0]])
    target = np.array([0.0, 1.0, 1.0, 0.0])
    hidden = np.tanh(x @ weights[:4].reshape(2, 2) + weights[4:6])
    out = 1.0 / (1.0 + np.exp(-(hidden @ weights[6:8] + weights[8])))
    mse = float(np.mean((out - target) ** 2))
    return max(0.0, 4.0 - 12.0 * mse)


def neat_intro_demo(generations: int = 32, seed: int = 11) -> dict[str, Any]:
    """Toy NEAT-like trace on XOR.

    This is not the full Flappy engine; it is a compact teaching trace that keeps
    the moving parts visible: fitness, species, topology growth and innovation ids.
    """

    generations = int(np.clip(generations, 8, 80))
    rng = np.random.default_rng(seed)
    population = rng.normal(0, 0.8, size=(36, 9))
    complexity = np.ones(36) * 5.0
    trace: list[dict[str, Any]] = []
    innovation = 7

    for gen in range(generations + 1):
        scores = np.array([_xor_score(ind) for ind in population])
        order = np.argsort(scores)[::-1]
        species = max(1, int(2 + np.std(complexity) + gen / 11))
        mean_complexity = float(np.mean(complexity))
        trace.append(
            {
                "gen": gen,
                "fitnessMax": _round(scores[order[0]]),
                "fitnessMean": _round(float(np.mean(scores))),
                "species": species,
                "complexity": _round(mean_complexity),
                "innovations": int(innovation),
                "nodes": int(5 + np.floor(mean_complexity / 4)),
                "connections": int(round(mean_complexity + gen * 0.35)),
            }
        )
        if gen == generations:
            break

        elites = population[order[:8]]
        new_pop = [elites[0], elites[1]]
        new_complexity = [complexity[order[0]], complexity[order[1]]]
        while len(new_pop) < len(population):
            p1, p2 = elites[rng.integers(0, len(elites), size=2)]
            mask = rng.random(p1.shape) < 0.5
            child = np.where(mask, p1, p2)
            child = child + rng.normal(0, 0.18, size=child.shape)
            if rng.random() < 0.18:
                child[rng.integers(0, child.size)] += rng.normal(0, 1.1)
                innovation += 1
            new_pop.append(child)
            parent_complexity = float(np.mean(complexity[order[:8]]))
            bump = 1.0 if rng.random() < 0.16 else 0.0
            new_complexity.append(min(28.0, parent_complexity + bump + rng.normal(0, 0.35)))
        population = np.array(new_pop)
        complexity = np.array(new_complexity)

    final_weights = population[np.argmax([_xor_score(ind) for ind in population])]
    return {
        "title": "NEAT sur XOR: selection + mutations structurelles",
        "task": "XOR",
        "trace": trace,
        "bestGenome": {
            "nodes": [
                {"id": 0, "type": "input", "label": "x1"},
                {"id": 1, "type": "input", "label": "x2"},
                {"id": 2, "type": "hidden", "label": "h1"},
                {"id": 3, "type": "hidden", "label": "h2"},
                {"id": 4, "type": "output", "label": "xor"},
            ],
            "connections": [
                {"in": 0, "out": 2, "weight": _round(final_weights[0]), "innovation": 1},
                {"in": 1, "out": 2, "weight": _round(final_weights[1]), "innovation": 2},
                {"in": 0, "out": 3, "weight": _round(final_weights[2]), "innovation": 3},
                {"in": 1, "out": 3, "weight": _round(final_weights[3]), "innovation": 4},
                {"in": 2, "out": 4, "weight": _round(final_weights[6]), "innovation": 5},
                {"in": 3, "out": 4, "weight": _round(final_weights[7]), "innovation": 6},
            ],
        },
        "explanation": [
            "NEAT cherche avec une population, pas avec une seule trajectoire de gradient.",
            "Les innovations donnent une identite aux connexions pour croiser deux genomes.",
            "La speciation protege les topologies nouvelles le temps qu'elles deviennent utiles.",
        ],
    }
