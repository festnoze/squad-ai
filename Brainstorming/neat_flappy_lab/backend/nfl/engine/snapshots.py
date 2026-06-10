"""Serialization of engine state into WebSocket message payloads.

Two granularities, matching the protocol in PLAN.md:

* :func:`frame_message` — high-frequency, per game tick (live rendering + the
  selected bird's neuron activations).
* :func:`generation_message` — once per generation (curves, best-genome topology,
  leaderboard). The runner already produces the stats dict; this just tags it.
"""

from __future__ import annotations


def frame_message(
    render_state: dict, selected_activations: dict[int, float], gen: int
) -> dict:
    """Build a ``frame`` message from a world snapshot + selected activations."""
    birds = render_state.get("birds", [])
    alive_count = sum(1 for b in birds if b.get("alive"))
    return {
        "type": "frame",
        "gen": gen,
        "tick": render_state.get("tick", 0),
        "aliveCount": alive_count,
        "birds": birds,
        "pipes": render_state.get("pipes", []),
        "world": render_state.get("world"),
        # JSON object keys must be strings.
        "selectedActivations": {str(k): float(v) for k, v in selected_activations.items()},
    }


def generation_message(stats: dict) -> dict:
    """Tag a runner stats dict as a ``generation`` message."""
    return {"type": "generation", **stats}


def genome_message(bird_id: int, genome_dict: dict) -> dict:
    """Reply to a ``select`` request with a specific bird's network."""
    return {"type": "genome", "birdId": int(bird_id), "genome": genome_dict}
