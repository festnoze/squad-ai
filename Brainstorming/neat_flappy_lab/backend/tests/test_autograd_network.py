"""Tests for the differentiable Network: gradients, shapes, training, write-back.

The gradient check is the centerpiece: we verify that the weight update applied
by ``train_step`` matches both an analytic gradient (on a hand-built tiny net)
and a central finite-difference estimate (on a small net rebuilt from the genome).
"""

from __future__ import annotations

import numpy as np

from nfl.config import Sensor, SimConfig
from nfl.neat.genome import (
    ConnectionGene,
    Genome,
    InnovationTracker,
    NodeGene,
    NodeType,
    create_initial_genome,
)
from nfl.nn.autograd import sigmoid_fwd
from nfl.nn.network import Network


def _tiny_genome(w_bias: float, w_in: float) -> Genome:
    """Hand-built net: bias(0) + input(1) -> output(2), sigmoid output.

    output_z = w_bias * 1 + w_in * x ; output_a = sigmoid(output_z).
    """
    g = Genome()
    g.bias_id = 0
    g.add_node(NodeGene(id=0, type=NodeType.BIAS, activation="identity"))
    g.add_node(NodeGene(id=1, type=NodeType.INPUT, activation="identity"))
    g.add_node(NodeGene(id=2, type=NodeType.OUTPUT, activation="sigmoid"))
    g.input_ids = [1]
    g.output_ids = [2]
    g.add_connection(ConnectionGene(in_node=0, out_node=2, weight=w_bias, enabled=True, innovation=0))
    g.add_connection(ConnectionGene(in_node=1, out_node=2, weight=w_in, enabled=True, innovation=1))
    return g


def _conn_weight(net: Network, innovation: int) -> float:
    """Read the live network weight for a given connection innovation."""
    for pos in range(len(net._order)):
        innovs = net._in_conn[pos]
        for k, inno in enumerate(innovs):
            if inno == innovation:
                return float(net._in_weight[pos][k])
    raise KeyError(innovation)


def _loss(net: Network, X: np.ndarray, Y: np.ndarray) -> float:
    pred = net.forward(X)
    pred = pred.reshape(X.shape[0], -1)
    diff = pred - Y
    return float(np.mean(diff * diff))


# --------------------------------------------------------------------------- #
# Gradient check
# --------------------------------------------------------------------------- #
def test_gradient_check_analytic_and_finite_difference():
    """Compare train_step's applied delta to analytic and FD gradients to ~1e-5."""
    rng = np.random.default_rng(0)

    w_bias, w_in = 0.3, -0.7
    X = np.array([[0.5], [1.5], [-2.0], [0.1]], dtype=np.float64)  # (batch, 1 input)
    Y = np.array([[0.2], [0.9], [0.1], [0.6]], dtype=np.float64)   # (batch, 1 output)
    batch = X.shape[0]

    # --- analytic gradient (closed form for this tiny sigmoid net) -------------
    # z = w_bias + w_in*x ; a = sigmoid(z) ; L = mean((a - y)^2) over batch*1.
    z = w_bias + w_in * X[:, 0]
    a = sigmoid_fwd(z)
    y = Y[:, 0]
    # dL/da = 2(a - y)/batch ; da/dz = a(1-a)
    dL_dz = (2.0 / batch) * (a - y) * (a * (1.0 - a))
    grad_w_bias = float(np.sum(dL_dz * 1.0))      # bias activation = 1
    grad_w_in = float(np.sum(dL_dz * X[:, 0]))    # input activation = x

    # --- finite-difference gradient on the genome ------------------------------
    eps = 1e-6

    # bias weight FD
    loss_plus_b = _loss(Network.from_genome(_tiny_genome(w_bias + eps, w_in)), X, Y)
    loss_minus_b = _loss(Network.from_genome(_tiny_genome(w_bias - eps, w_in)), X, Y)
    fd_grad_bias = (loss_plus_b - loss_minus_b) / (2 * eps)

    # input weight FD
    loss_plus_i = _loss(Network.from_genome(_tiny_genome(w_bias, w_in + eps)), X, Y)
    loss_minus_i = _loss(Network.from_genome(_tiny_genome(w_bias, w_in - eps)), X, Y)
    fd_grad_in = (loss_plus_i - loss_minus_i) / (2 * eps)

    # --- gradient implied by train_step ---------------------------------------
    # train_step updates w -= lr * grad, so applied_grad = (w_before - w_after)/lr.
    lr = 1.0
    net = Network.from_genome(_tiny_genome(w_bias, w_in))
    wb_before = _conn_weight(net, 0)
    wi_before = _conn_weight(net, 1)
    net.train_step(X, Y, lr)
    wb_after = _conn_weight(net, 0)
    wi_after = _conn_weight(net, 1)
    ts_grad_bias = (wb_before - wb_after) / lr
    ts_grad_in = (wi_before - wi_after) / lr

    # --- agreement to ~1e-5 ----------------------------------------------------
    err_bias_analytic = abs(ts_grad_bias - grad_w_bias)
    err_in_analytic = abs(ts_grad_in - grad_w_in)
    err_bias_fd = abs(ts_grad_bias - fd_grad_bias)
    err_in_fd = abs(ts_grad_in - fd_grad_in)

    assert err_bias_analytic < 1e-5
    assert err_in_analytic < 1e-5
    assert err_bias_fd < 1e-5
    assert err_in_fd < 1e-5

    # Expose the largest error so the test runner / report can surface it.
    max_err = max(err_bias_analytic, err_in_analytic, err_bias_fd, err_in_fd)
    print(f"\n[gradient-check] max finite-difference/analytic error = {max_err:.3e}")
    assert max_err < 1e-5


# --------------------------------------------------------------------------- #
# Shapes
# --------------------------------------------------------------------------- #
def test_forward_accepts_single_and_batch_shapes():
    g = _tiny_genome(0.1, 0.2)
    net = Network.from_genome(g)

    # single sample: (num_inputs,) -> (num_outputs,)
    single = net.forward(np.array([0.5]))
    assert single.shape == (1,)

    # batch: (batch, num_inputs) -> (batch, num_outputs)
    batch = net.forward(np.array([[0.5], [1.0], [-1.0]]))
    assert batch.shape == (3, 1)


def test_forward_multi_input_output_shapes():
    rng = np.random.default_rng(0)
    config = SimConfig(active_sensors=[Sensor.dy_gap, Sensor.dx_pipe, Sensor.vy])
    tracker = InnovationTracker(1 + 3 + 1)
    g = create_initial_genome(
        num_inputs=3,
        num_outputs=1,
        activation="sigmoid",
        tracker=tracker,
        rng=rng,
        initial_hidden=0,
        weight_sigma=1.0,
    )
    net = Network.from_genome(g)
    assert net.forward(np.zeros(3)).shape == (1,)
    assert net.forward(np.zeros((5, 3))).shape == (5, 1)


# --------------------------------------------------------------------------- #
# Training reduces loss
# --------------------------------------------------------------------------- #
def test_train_step_monotonically_decreases_loss():
    rng = np.random.default_rng(0)
    g = _tiny_genome(0.0, 0.0)
    net = Network.from_genome(g)

    X = rng.normal(size=(16, 1))
    # Fixed regression target derived from a known linear-ish mapping.
    Y = sigmoid_fwd(1.5 * X[:, 0] - 0.5).reshape(-1, 1)

    prev = _loss(net, X, Y)
    losses = [prev]
    for _ in range(50):
        net.train_step(X, Y, lr=0.5)
        cur = _loss(net, X, Y)
        losses.append(cur)
        # strictly non-increasing with a small lr on a convex-ish target
        assert cur <= prev + 1e-9
        prev = cur

    assert losses[-1] < losses[0]


def test_train_step_reduces_loss_on_random_network():
    rng = np.random.default_rng(1)
    config = SimConfig(active_sensors=[Sensor.dy_gap, Sensor.dx_pipe, Sensor.vy])
    tracker = InnovationTracker(1 + 3 + 1)
    g = create_initial_genome(
        num_inputs=3,
        num_outputs=1,
        activation="sigmoid",
        tracker=tracker,
        rng=rng,
        initial_hidden=2,
        weight_sigma=1.0,
    )
    net = Network.from_genome(g)
    X = rng.normal(size=(32, 3))
    Y = rng.uniform(0.0, 1.0, size=(32, 1))

    before = _loss(net, X, Y)
    for _ in range(30):
        net.train_step(X, Y, lr=0.2)
    after = _loss(net, X, Y)
    assert after < before


# --------------------------------------------------------------------------- #
# Write-back
# --------------------------------------------------------------------------- #
def test_write_weights_to_genome_copies_learned_weights():
    rng = np.random.default_rng(0)
    g = _tiny_genome(0.0, 0.0)
    weights_before = {inv: c.weight for inv, c in g.connections.items()}

    net = Network.from_genome(g)
    X = rng.normal(size=(16, 1))
    Y = sigmoid_fwd(2.0 * X[:, 0]).reshape(-1, 1)
    for _ in range(20):
        net.train_step(X, Y, lr=0.5)

    net.write_weights_to_genome(g)

    # at least one genome weight changed after training + write-back
    changed = any(g.connections[inv].weight != weights_before[inv] for inv in g.connections)
    assert changed

    # written weights match the live network weights
    for inv in g.connections:
        assert abs(g.connections[inv].weight - _conn_weight(net, inv)) < 1e-12
