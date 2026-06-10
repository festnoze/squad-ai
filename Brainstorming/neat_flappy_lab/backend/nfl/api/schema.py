"""Config schema helpers exposed to the frontend.

The frontend fetches the JSON schema of :class:`~nfl.config.SimConfig` to
auto-generate its controls (labels, bounds, defaults). Keeping this in one place
means a new backend parameter shows up in the UI without any frontend change.
"""

from __future__ import annotations

from ..config import SimConfig

# Fields whose change requires a full reset (they alter genome/structure or
# population identity). Everything else can be applied between generations.
STRUCTURAL_FIELDS = frozenset(
    {
        "pop_size",
        "active_sensors",
        "initial_hidden",
        "max_nodes",
        "max_connections",
        "seed",
        # Re-splitting the camps mid-run would clobber both lineages.
        "gd_ratio",
    }
)


def config_schema_dict() -> dict:
    """JSON schema of the full config model."""
    return SimConfig.model_json_schema()


def config_defaults_dict() -> dict:
    """Default config values, JSON-serializable (enums as their values)."""
    return SimConfig().model_dump(mode="json")


def is_structural_change(old: SimConfig, new: SimConfig) -> bool:
    """True if going from ``old`` to ``new`` requires rebuilding the run."""
    old_d = old.model_dump()
    new_d = new.model_dump()
    return any(old_d[f] != new_d[f] for f in STRUCTURAL_FIELDS)
