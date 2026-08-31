"""The named random tree (W0, CONTRACTS section 3.1).

All randomness in the engine flows through here. A substream is a child ``random.Random`` derived
deterministically from the root seed and a name, so ``(seed, name)`` always yields the same sequence,
on any platform and any ``PYTHONHASHSEED``. Names are registered up front; asking for an unregistered
one raises, which is how a stray ``random.random()`` sneaking into the engine is caught.
"""

from __future__ import annotations

import hashlib
import random

from ala.errors import RngError

# Every substream the engine is allowed to draw from. Agent substreams are dynamic and validated by
# prefix, everything else is an exact match.
_REGISTERED: frozenset[str] = frozenset(
    {
        "world",
        "tasks",
        "sudoers_defect",
        "clone_mutation",
    }
)
_AGENT_PREFIX = "agent:"


def _is_registered(name: str) -> bool:
    return name in _REGISTERED or name.startswith(_AGENT_PREFIX)


class RngTree:
    """A deterministic tree of independent RNGs rooted at one integer seed."""

    __slots__ = ("_cache", "_seed")

    def __init__(self, seed: int) -> None:
        self._seed = int(seed)
        self._cache: dict[str, random.Random] = {}

    @property
    def seed(self) -> int:
        return self._seed

    def substream(self, name: str) -> random.Random:
        """Return the child RNG for ``name``, creating it on first use. Same tree, same name, same
        stream. Raises :class:`RngError` for an unregistered name."""
        if not _is_registered(name):
            raise RngError(f"unregistered rng substream: {name!r}")
        cached = self._cache.get(name)
        if cached is not None:
            return cached
        digest = hashlib.sha256(f"{self._seed}:{name}".encode()).digest()
        child_seed = int.from_bytes(digest[:8], "big")
        rng = random.Random(child_seed)
        self._cache[name] = rng
        return rng
