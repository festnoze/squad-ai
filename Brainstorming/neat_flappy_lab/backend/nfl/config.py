"""Central configuration contract for neat_flappy_lab.

Every tunable lives here as a Pydantic field with a default, bounds and a
description. The frontend fetches the JSON schema of :class:`SimConfig` (via
``GET /config/schema``) to auto-generate its controls, and every ``config``
message from the WebSocket is validated/coerced against this model. Nothing in
the engine should hard-code a hyperparameter: read it from a ``SimConfig``.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class Mode(str, Enum):
    """Training method / hybridization regime.

    Two pure baselines, two hybrids, and a head-to-head confrontation:

    * ``evolution_only`` — pure neuroevolution (NEAT): selection, crossover,
      mutation, speciation. No gradient descent.
    * ``gradient_only`` — pure gradient descent: a FIXED-topology population is
      trained by imitation GD only. No selection / crossover / mutation /
      speciation — weights just descend the loss. Illustrates the limit of local
      search without evolutionary exploration.
    * ``write_back`` (Lamarckian) — NEAT + GD; learned weights re-enter the genome.
    * ``evaluate_only`` (Baldwinian) — NEAT + GD; GD scores fitness, birth genome
      is inherited.
    * ``confrontation`` — the population is SPLIT by ``gd_ratio`` into two camps
      competing in the same world: a NEAT camp (pure neuroevolution, breeds only
      within itself) and a GD camp (frozen topologies that learn only by
      imitation gradient descent, weights persisting across generations). The
      winning bird is therefore fully NEAT-evolved or fully GD-trained — never a
      mix — which makes the two approaches directly comparable.
    """

    evolution_only = "evolution_only"
    gradient_only = "gradient_only"
    write_back = "write_back"
    evaluate_only = "evaluate_only"
    confrontation = "confrontation"


class TeacherScope(str, Enum):
    """Where the GD camp's imitation teachers come from (confrontation mode).

    * ``camp`` — the GD camp only imitates its own top-K: both camps progress in
      full isolation, the purest confrontation.
    * ``global`` — teachers are the top-K of the WHOLE population: the GD camp
      may distill behaviours discovered by NEAT (knowledge transfer made visible).
    """

    camp = "camp"
    global_ = "global"


class StreamMode(str, Enum):
    watch = "watch"  # stream per-tick frames of the current generation
    fast = "fast"    # skip frame streaming; only per-generation summaries


class Activation(str, Enum):
    sigmoid = "sigmoid"
    tanh = "tanh"
    relu = "relu"


class Sensor(str, Enum):
    """Selectable inputs. The active subset sets the input-layer size."""

    dy_gap = "dy_gap"      # vertical distance to next gap center
    dx_pipe = "dx_pipe"    # horizontal distance to next pipe
    vy = "vy"              # bird vertical velocity
    dy_gap2 = "dy_gap2"    # vertical distance to the gap AFTER next (optional)
    y_abs = "y_abs"        # absolute bird height (optional)


DEFAULT_SENSORS = [Sensor.dy_gap, Sensor.dx_pipe, Sensor.vy]


class SimConfig(BaseModel):
    """The single source of truth for a run. Sent partially as a `config` patch."""

    # --- Population & simulation -------------------------------------------------
    mode: Mode = Field(Mode.evolution_only, description="Hybridization regime.")
    pop_size: int = Field(120, ge=2, le=1000, description="Number of birds per generation.")
    sim_speed: float = Field(1.0, ge=0.1, le=50.0, description="Simulation speed multiplier.")
    seed: int = Field(0, ge=0, le=2**31 - 1, description="RNG seed (reproducible runs).")
    max_ticks_per_gen: int = Field(
        3000, ge=100, le=100_000, description="Hard cap on ticks before a generation ends."
    )
    stream_mode: StreamMode = Field(StreamMode.watch, description="Frame streaming granularity.")

    # --- Network size ------------------------------------------------------------
    active_sensors: list[Sensor] = Field(
        default_factory=lambda: list(DEFAULT_SENSORS),
        description="Active input sensors (sets input-layer size). A bias is always added.",
    )
    initial_hidden: int = Field(
        0, ge=0, le=20, description="Hidden nodes at birth (0 = minimal NEAT topology)."
    )
    max_nodes: int = Field(30, ge=2, le=500, description="Complexity cap on total nodes.")
    max_connections: int = Field(
        100, ge=1, le=5000, description="Complexity cap on total connections."
    )
    activation: Activation = Field(
        Activation.sigmoid, description="Activation for hidden/output nodes."
    )

    # --- NEAT --------------------------------------------------------------------
    add_connection_rate: float = Field(0.05, ge=0.0, le=1.0, description="P(add-connection mutation).")
    add_node_rate: float = Field(0.03, ge=0.0, le=1.0, description="P(add-node mutation).")
    weight_perturb_rate: float = Field(0.8, ge=0.0, le=1.0, description="P(perturb a weight).")
    weight_replace_rate: float = Field(0.1, ge=0.0, le=1.0, description="P(replace a weight).")
    weight_sigma: float = Field(0.5, ge=0.0, le=5.0, description="Std-dev of weight perturbation.")
    toggle_enable_rate: float = Field(0.01, ge=0.0, le=1.0, description="P(toggle a connection).")
    compat_threshold: float = Field(3.0, ge=0.1, le=20.0, description="Speciation distance threshold δ_t.")
    c1: float = Field(1.0, ge=0.0, le=10.0, description="Excess-genes coefficient.")
    c2: float = Field(1.0, ge=0.0, le=10.0, description="Disjoint-genes coefficient.")
    c3: float = Field(0.4, ge=0.0, le=10.0, description="Mean weight-difference coefficient.")
    elitism_per_species: int = Field(1, ge=0, le=50, description="Champions copied unchanged per species.")
    survival_threshold: float = Field(
        0.3, ge=0.05, le=1.0, description="Top fraction of a species allowed to reproduce."
    )
    target_species: int = Field(
        8, ge=0, le=100, description="If >0, auto-adjust δ_t to hit this species count (0 = off)."
    )

    # --- Hybridization / gradient descent ---------------------------------------
    gd_steps: int = Field(8, ge=0, le=200, description="GD steps per agent per generation.")
    gd_lr: float = Field(0.05, ge=0.0, le=2.0, description="GD learning rate.")
    teacher_k: int = Field(3, ge=1, le=50, description="Top-K of previous gen used as imitation teachers.")
    gd_batch_size: int = Field(32, ge=1, le=2048, description="Batch size sampled from the teacher buffer.")

    # --- Confrontation (NEAT camp vs GD camp) ------------------------------------
    gd_ratio: float = Field(
        0.5,
        ge=0.0,
        le=1.0,
        description=(
            "Confrontation mode: fraction of the population assigned to the GD camp "
            "(the rest evolves by NEAT). Applied at reset."
        ),
    )
    gd_teacher_scope: TeacherScope = Field(
        TeacherScope.camp,
        description=(
            "Confrontation mode: 'camp' = GD birds imitate their own champions only "
            "(pure duel); 'global' = they imitate the overall champions (may copy NEAT)."
        ),
    )

    def num_inputs(self) -> int:
        """Input-layer size = active sensors + 1 bias."""
        return len(self.active_sensors) + 1


# Module-level defaults for code paths that just want sane values.
DEFAULTS = SimConfig()
