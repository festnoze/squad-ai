"""Lifetime gradient descent by imitation of the elite.

In a control task the fitness (distance survived) is **not** differentiable, so
gradient descent has no natural signal. We manufacture one: during its "life"
each agent runs a few GD steps to imitate the *actions* of the previous
generation's champions on states drawn from the population's own experience.

The loss is plain MSE between the learner's output and the (averaged) teacher
output on the same observations — fully differentiable and handled by
:meth:`nfl.nn.network.Network.train_step`. Whether the learned weights are then
written back into the genome (Lamarckian) or discarded after scoring
(Baldwinian) is decided by the caller (the runner), not here.
"""

from __future__ import annotations

from collections.abc import Callable

import numpy as np

from ..config import SimConfig
from ..neat.genome import Genome
from ..nn.network import Network

TeacherFn = Callable[[np.ndarray], np.ndarray]


def build_teacher(teacher_genomes: list[Genome]) -> TeacherFn | None:
    """Return a function mapping a batch of states to averaged teacher actions.

    The teacher is the ensemble of the previous generation's top-K genomes; its
    output on a batch ``X`` of shape ``(batch, num_inputs)`` is the mean of each
    teacher network's output, shape ``(batch, num_outputs)``. Returns ``None`` if
    there are no teachers yet (e.g. generation 0).
    """
    if not teacher_genomes:
        return None
    nets = [Network.from_genome(g) for g in teacher_genomes]

    def teacher_fn(X: np.ndarray) -> np.ndarray:
        outs = []
        for net in nets:
            y = net.forward(X)              # (batch, num_outputs)
            outs.append(np.atleast_2d(y))
        return np.mean(np.stack(outs, axis=0), axis=0)

    return teacher_fn


def imitate(
    network: Network,
    teacher_fn: TeacherFn,
    states: np.ndarray | None,
    config: SimConfig,
    rng: np.random.Generator,
) -> float:
    """Run ``config.gd_steps`` imitation GD steps on ``network`` in place.

    Each step samples a minibatch of ``config.gd_batch_size`` observations from
    ``states``, computes the teacher's targets on them, and takes one MSE
    gradient step. Returns the final step's loss (0.0 if there is nothing to do).
    """
    if states is None or len(states) == 0 or config.gd_steps <= 0:
        return 0.0

    n = len(states)
    batch = min(config.gd_batch_size, n)
    loss = 0.0
    for _ in range(config.gd_steps):
        idx = rng.integers(0, n, size=batch)
        X = states[idx]
        Y = teacher_fn(X)
        loss = network.train_step(X, Y, config.gd_lr)
    return loss
