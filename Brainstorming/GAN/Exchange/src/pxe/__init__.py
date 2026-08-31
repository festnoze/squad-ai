"""Prediction Exchange (pxe).

An arena where LLM agents trade binary contracts on a shared central limit order
book. The simulation engine is pure, synchronous and deterministic; only the
agent gateway is asynchronous.

Read ``docs/CONTRACTS.md`` before writing any module: it is the single source of
truth for module boundaries, public APIs, the determinism contract and the
event sourcing contract.
"""

from pxe.types import ACTION_VERSION, ENGINE_VERSION, OBS_VERSION

__all__ = ["__version__", "ENGINE_VERSION", "OBS_VERSION", "ACTION_VERSION"]

__version__ = ENGINE_VERSION
