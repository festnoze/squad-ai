"""Low-level forward/backward primitives used by :mod:`nfl.nn.network`.

This module deliberately contains *no* graph logic — only the scalar/elementwise
building blocks: the activation functions, their derivatives, and a tiny resolver
that maps an activation name (as stored on a :class:`~nfl.neat.genome.NodeGene`)
to a ``(forward_fn, derivative_fn)`` pair.

All functions are fully vectorized over NumPy arrays so the :class:`Network`
can run a whole batch of samples through the same code path.

Derivative convention
----------------------
Each ``derivative_fn`` takes the **pre-activation** ``z`` (the weighted sum that
fed the node) and returns ``d(activation)/dz`` evaluated at ``z``. For sigmoid
and tanh this is the usual closed form; for relu it is the sub-gradient (0 for
``z <= 0`` is used here). Computing the derivative from ``z`` keeps the backward
pass independent of whether the forward activation was cached.
"""

from __future__ import annotations

from typing import Callable

import numpy as np

# An activation is a (forward, derivative-w.r.t.-preactivation) pair.
ActivationPair = tuple[Callable[[np.ndarray], np.ndarray], Callable[[np.ndarray], np.ndarray]]


# --- forward functions -----------------------------------------------------------
def identity_fwd(z: np.ndarray) -> np.ndarray:
    """f(z) = z."""
    return z


def sigmoid_fwd(z: np.ndarray) -> np.ndarray:
    """Numerically stable logistic sigmoid f(z) = 1 / (1 + e^-z)."""
    # Split on the sign of z to avoid overflow in exp for large |z|.
    out = np.empty_like(z, dtype=np.float64)
    pos = z >= 0
    neg = ~pos
    out[pos] = 1.0 / (1.0 + np.exp(-z[pos]))
    exp_z = np.exp(z[neg])
    out[neg] = exp_z / (1.0 + exp_z)
    return out


def tanh_fwd(z: np.ndarray) -> np.ndarray:
    """f(z) = tanh(z)."""
    return np.tanh(z)


def relu_fwd(z: np.ndarray) -> np.ndarray:
    """f(z) = max(0, z)."""
    return np.maximum(z, 0.0)


# --- derivative functions (w.r.t. the pre-activation z) --------------------------
def identity_grad(z: np.ndarray) -> np.ndarray:
    """f'(z) = 1."""
    return np.ones_like(z, dtype=np.float64)


def sigmoid_grad(z: np.ndarray) -> np.ndarray:
    """f'(z) = sigmoid(z) * (1 - sigmoid(z))."""
    s = sigmoid_fwd(z)
    return s * (1.0 - s)


def tanh_grad(z: np.ndarray) -> np.ndarray:
    """f'(z) = 1 - tanh(z)^2."""
    t = np.tanh(z)
    return 1.0 - t * t


def relu_grad(z: np.ndarray) -> np.ndarray:
    """Sub-gradient of relu: 1 where z > 0, else 0."""
    return (z > 0.0).astype(np.float64)


_ACTIVATIONS: dict[str, ActivationPair] = {
    "identity": (identity_fwd, identity_grad),
    "sigmoid": (sigmoid_fwd, sigmoid_grad),
    "tanh": (tanh_fwd, tanh_grad),
    "relu": (relu_fwd, relu_grad),
}


def resolve_activation(name: str) -> ActivationPair:
    """Return the ``(forward, derivative)`` pair for an activation ``name``.

    Raises
    ------
    KeyError
        If ``name`` is not one of ``identity``/``sigmoid``/``tanh``/``relu``.
    """
    try:
        return _ACTIVATIONS[name]
    except KeyError as exc:  # pragma: no cover - defensive
        raise KeyError(
            f"Unknown activation {name!r}; expected one of {sorted(_ACTIVATIONS)}"
        ) from exc
