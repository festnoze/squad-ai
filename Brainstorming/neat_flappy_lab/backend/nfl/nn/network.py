"""Evaluable, differentiable network built from a :class:`~nfl.neat.genome.Genome`.

A genome is a *direct encoding* of an acyclic (feed-forward) neural network. The
:class:`Network` here compiles that encoding into a structure that is cheap to
evaluate every game tick and — crucially for the hybrid (Lamarckian/Baldwinian)
modes — supports a hand-written backward pass so the connection weights can be
trained by gradient descent (imitation / MSE against a teacher).

Compilation strategy
--------------------
* Nodes are sorted into a **topological order** via Kahn's algorithm over the
  *enabled* connections only. The bias and input nodes (which have no incoming
  enabled connections) naturally land first.
* For each node we precompute its incoming ``(source_topo_index, weight)`` pairs.
  During forward we gather the already-computed source activations, multiply by
  the weight vector and sum — a node with zero incoming connections gets a
  pre-activation of ``0``.
* Forward and backward are vectorized over the batch dimension; a single sample
  is handled by promoting it to a ``(1, num_inputs)`` batch internally.

The weights live on the :class:`Network` (one float per enabled connection) so
that gradient-descent updates are local and can later be written back into a
genome via :meth:`Network.write_weights_to_genome`.
"""

from __future__ import annotations

import numpy as np

from ..neat.genome import Genome
from .autograd import resolve_activation


class Network:
    """A compiled, differentiable feed-forward view of a :class:`Genome`."""

    # ------------------------------------------------------------------ build ----
    def __init__(self) -> None:
        # Topological metadata (filled by from_genome).
        self._genome: Genome | None = None
        self._order: list[int] = []                 # node ids in topological order
        self._index_of: dict[int, int] = {}         # node id -> position in _order
        self._activation_names: list[str] = []      # per topo position
        self._fwd_fns: list = []                    # per topo position
        self._grad_fns: list = []                   # per topo position

        # Incoming structure, per topo position:
        #   _in_src[i]    -> np.ndarray[int] of source topo indices feeding node i
        #   _in_weight[i] -> np.ndarray[float] of weights, aligned with _in_src[i]
        #   _in_conn[i]   -> list[int] of source genome connection innovations,
        #                    aligned with _in_src[i] (for write-back)
        self._in_src: list[np.ndarray] = []
        self._in_weight: list[np.ndarray] = []
        self._in_conn: list[list[int]] = []

        # Role bookkeeping.
        self._bias_pos: int = -1
        self._input_pos: list[int] = []             # topo positions of inputs (genome order)
        self._output_pos: list[int] = []            # topo positions of outputs (genome order)
        self._num_inputs: int = 0
        self._num_outputs: int = 0

        # Last single-sample activations for visualization (node id -> float).
        self._last_activations: dict[int, float] = {}

    @classmethod
    def from_genome(cls, genome: Genome) -> "Network":
        """Build an evaluable, trainable :class:`Network` from ``genome``.

        Only **enabled** connections participate. Nodes are ordered via Kahn's
        algorithm; the per-node incoming ``(source, weight)`` lists and activation
        functions are precomputed for fast forward/backward passes.
        """
        net = cls()
        net._genome = genome

        enabled = genome.enabled_connections()

        # --- adjacency over enabled connections for Kahn's algorithm -------------
        all_node_ids = list(genome.nodes.keys())
        successors: dict[int, list[int]] = {nid: [] for nid in all_node_ids}
        in_degree: dict[int, int] = {nid: 0 for nid in all_node_ids}
        for conn in enabled:
            # Defensive: ignore connections referencing unknown nodes.
            if conn.in_node not in in_degree or conn.out_node not in in_degree:
                continue
            successors[conn.in_node].append(conn.out_node)
            in_degree[conn.out_node] += 1

        # --- Kahn's topological sort ---------------------------------------------
        # Seed with all zero-in-degree nodes. We push the bias + inputs first (in
        # genome order) so the visible ordering is stable and intuitive, then any
        # remaining source nodes.
        queue: list[int] = []
        seeded: set[int] = set()
        for nid in (genome.bias_id, *genome.input_ids):
            if nid in in_degree and in_degree[nid] == 0 and nid not in seeded:
                queue.append(nid)
                seeded.add(nid)
        for nid in all_node_ids:
            if in_degree[nid] == 0 and nid not in seeded:
                queue.append(nid)
                seeded.add(nid)

        order: list[int] = []
        remaining = dict(in_degree)
        head = 0
        while head < len(queue):
            nid = queue[head]
            head += 1
            order.append(nid)
            for succ in successors[nid]:
                remaining[succ] -= 1
                if remaining[succ] == 0:
                    queue.append(succ)

        if len(order) != len(all_node_ids):
            raise ValueError(
                "Genome graph is not acyclic (or contains unreachable cycles); "
                f"sorted {len(order)} of {len(all_node_ids)} nodes."
            )

        net._order = order
        net._index_of = {nid: i for i, nid in enumerate(order)}

        # --- per-node activation functions ---------------------------------------
        for nid in order:
            name = genome.nodes[nid].activation
            fwd, grad = resolve_activation(name)
            net._activation_names.append(name)
            net._fwd_fns.append(fwd)
            net._grad_fns.append(grad)

        # --- per-node incoming connection arrays ---------------------------------
        # Group enabled connections by their out_node.
        incoming: dict[int, list] = {nid: [] for nid in order}
        for conn in enabled:
            if conn.out_node in incoming and conn.in_node in net._index_of:
                incoming[conn.out_node].append(conn)

        for nid in order:
            conns = incoming[nid]
            if conns:
                src = np.array([net._index_of[c.in_node] for c in conns], dtype=np.intp)
                w = np.array([float(c.weight) for c in conns], dtype=np.float64)
                innovs = [c.innovation for c in conns]
            else:
                src = np.empty(0, dtype=np.intp)
                w = np.empty(0, dtype=np.float64)
                innovs = []
            net._in_src.append(src)
            net._in_weight.append(w)
            net._in_conn.append(innovs)

        # --- role positions -------------------------------------------------------
        net._bias_pos = net._index_of[genome.bias_id]
        net._input_pos = [net._index_of[nid] for nid in genome.input_ids]
        net._output_pos = [net._index_of[nid] for nid in genome.output_ids]
        net._num_inputs = len(genome.input_ids)
        net._num_outputs = len(genome.output_ids)

        return net

    # ---------------------------------------------------------------- forward ----
    def _forward_cache(self, X: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """Run a batched forward pass, returning (activations, pre_activations).

        Both returned arrays have shape ``(num_nodes, batch)`` indexed by topo
        position, so the backward pass can reuse the cached pre-activations.
        ``X`` must already be shaped ``(batch, num_inputs)``.
        """
        batch = X.shape[0]
        n_nodes = len(self._order)
        a = np.zeros((n_nodes, batch), dtype=np.float64)   # activations
        z = np.zeros((n_nodes, batch), dtype=np.float64)   # pre-activations

        # Seed bias and inputs. Their activation is "identity", so a == z there.
        a[self._bias_pos, :] = 1.0
        z[self._bias_pos, :] = 1.0
        for col, pos in enumerate(self._input_pos):
            a[pos, :] = X[:, col]
            z[pos, :] = X[:, col]

        # Evaluate the rest in topological order.
        input_positions = set(self._input_pos)
        for pos in range(n_nodes):
            if pos == self._bias_pos or pos in input_positions:
                continue
            src = self._in_src[pos]
            if src.size:
                # weighted sum over incoming edges -> (batch,)
                z[pos, :] = self._in_weight[pos] @ a[src, :]
            else:
                z[pos, :] = 0.0
            a[pos, :] = self._fwd_fns[pos](z[pos, :])

        return a, z

    def forward(self, x: np.ndarray) -> np.ndarray:
        """Evaluate the network on ``x``.

        Parameters
        ----------
        x:
            Either ``(num_inputs,)`` for a single sample or ``(batch, num_inputs)``
            for a batch. ``num_inputs`` is ``len(genome.input_ids)`` (sensors only;
            the bias is injected internally).

        Returns
        -------
        np.ndarray
            ``(num_outputs,)`` for a single sample, or ``(batch, num_outputs)`` for
            a batch, in ``genome.output_ids`` order.
        """
        x = np.asarray(x, dtype=np.float64)
        single = x.ndim == 1
        X = x.reshape(1, -1) if single else x
        if X.shape[1] != self._num_inputs:
            raise ValueError(
                f"forward expected {self._num_inputs} inputs, got {X.shape[1]}."
            )

        a, _ = self._forward_cache(X)

        if self._output_pos:
            out = a[self._output_pos, :].T  # (batch, num_outputs)
        else:
            out = np.zeros((X.shape[0], 0), dtype=np.float64)

        # Cache single-sample activations (first row) for visualization.
        self._last_activations = {
            nid: float(a[self._index_of[nid], 0]) for nid in self._order
        }

        return out[0] if single else out

    def activations(self) -> dict[int, float]:
        """Per-node activations (node id -> float) from the LAST forward pass.

        For a batched forward this holds the first row. Returns an empty dict if
        :meth:`forward` has not been called yet.
        """
        return dict(self._last_activations)

    # --------------------------------------------------------------- training ----
    def train_step(self, X: np.ndarray, Y: np.ndarray, lr: float) -> float:
        """One MSE gradient-descent step; returns the loss BEFORE the update.

        Parameters
        ----------
        X:
            ``(batch, num_inputs)`` inputs.
        Y:
            ``(batch, num_outputs)`` teacher targets.
        lr:
            Learning rate. Weights are updated in place: ``w -= lr * dL/dw``, with
            ``dL/dw`` averaged over the batch.

        Notes
        -----
        Loss is the mean-squared error ``mean((forward(X) - Y) ** 2)`` taken over
        both batch and output dimensions (matching ``np.mean``). The backward pass
        is implemented by hand (see :mod:`nfl.nn.autograd` for the activation
        derivatives); gradients flow in reverse topological order.
        """
        X = np.asarray(X, dtype=np.float64)
        Y = np.asarray(Y, dtype=np.float64)
        if X.ndim != 2 or X.shape[1] != self._num_inputs:
            raise ValueError(
                f"train_step X must be (batch, {self._num_inputs}); got {X.shape}."
            )
        if Y.ndim != 2 or Y.shape[1] != self._num_outputs:
            raise ValueError(
                f"train_step Y must be (batch, {self._num_outputs}); got {Y.shape}."
            )
        if X.shape[0] != Y.shape[0]:
            raise ValueError("train_step X and Y must share the batch dimension.")

        batch = X.shape[0]
        n_nodes = len(self._order)

        # --- forward with cache ---------------------------------------------------
        a, z = self._forward_cache(X)

        # Also refresh the visualization cache from the first row.
        self._last_activations = {
            nid: float(a[self._index_of[nid], 0]) for nid in self._order
        }

        # Predictions in genome output order -> (batch, num_outputs).
        if self._output_pos:
            pred = a[self._output_pos, :].T
        else:
            pred = np.zeros((batch, 0), dtype=np.float64)

        # --- loss (before update) -------------------------------------------------
        diff = pred - Y  # (batch, num_outputs)
        # Mean over batch * num_outputs to match np.mean(diff**2).
        denom = max(diff.size, 1)
        loss = float(np.sum(diff * diff) / denom)

        # --- backward -------------------------------------------------------------
        # grad_a[pos] = dL/d(activation of node pos), shape (batch,).
        grad_a = np.zeros((n_nodes, batch), dtype=np.float64)

        # dL/d(pred_j) = 2 * (pred_j - Y_j) / (batch * num_outputs).
        if self._output_pos:
            seed = (2.0 / denom) * diff  # (batch, num_outputs)
            for j, pos in enumerate(self._output_pos):
                grad_a[pos, :] += seed[:, j]

        # Accumulators for weight gradients, one array per node (aligned with
        # _in_weight / _in_src), summed over the batch.
        grad_w: list[np.ndarray] = [
            np.zeros_like(self._in_weight[pos]) for pos in range(n_nodes)
        ]

        input_positions = set(self._input_pos)

        # Reverse topological order so every consumer is processed before its source.
        for pos in range(n_nodes - 1, -1, -1):
            if pos == self._bias_pos or pos in input_positions:
                # Bias/inputs have no incoming weights and are never updated; their
                # upstream gradient is irrelevant.
                continue
            src = self._in_src[pos]
            # dL/dz = dL/da * f'(z)   -> (batch,)
            grad_z = grad_a[pos, :] * self._grad_fns[pos](z[pos, :])
            if src.size:
                # dL/dw_k = sum_batch grad_z * a_src_k
                #   a[src, :] is (num_in, batch); grad_z is (batch,).
                grad_w[pos] = a[src, :] @ grad_z  # (num_in,)
                # Propagate to sources: dL/da_src += w_k * grad_z
                # outer product (num_in, 1) * (1, batch) -> (num_in, batch)
                contrib = np.outer(self._in_weight[pos], grad_z)
                np.add.at(grad_a, src, contrib)

        # --- update weights in place ---------------------------------------------
        for pos in range(n_nodes):
            if self._in_weight[pos].size:
                self._in_weight[pos] -= lr * grad_w[pos]

        return loss

    # -------------------------------------------------------------- write-back ----
    def write_weights_to_genome(self, genome: Genome) -> None:
        """Copy this network's (possibly GD-updated) weights into ``genome``.

        Connections are matched by innovation number first (the source genome's
        connection ids are remembered at build time); any unmatched edge falls
        back to matching on ``(in_node, out_node)``. Used by ``write_back``
        (Lamarckian) mode.
        """
        for pos, nid in enumerate(self._order):
            src = self._in_src[pos]
            if not src.size:
                continue
            weights = self._in_weight[pos]
            innovs = self._in_conn[pos]
            for k in range(src.size):
                innov = innovs[k]
                conn = genome.connections.get(innov)
                if conn is None or conn.in_node != self._order[src[k]] or conn.out_node != nid:
                    # Fall back to structural match by (in_node, out_node).
                    in_node = self._order[src[k]]
                    conn = genome.connection_between(in_node, nid)
                if conn is not None:
                    conn.weight = float(weights[k])
