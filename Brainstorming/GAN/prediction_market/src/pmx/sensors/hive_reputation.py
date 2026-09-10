"""The ``hive_reputation`` sensor of CONTRACTS_V2 18.1 (package S1): who has been right.

It gates ``HiveView.reputations`` and it is the **one observation-level sensor** of the shipped catalogue
(ruling R286): ``per_market`` is ``False``, so its block is one per observation and its ``market_id`` is
``None``. Every other sensor, ``memory`` and ``hive_insights`` included, is per market, because a rule
evaluated per ``(market, bar)`` needs one block per open market with the observation-level values
repeated. The arbitration settled that against the code comment that said otherwise and in favour of the
fixture, and ``CATALOGUE_HASH`` did not move for it.

A reputation is a signed ``skill_micro``, so "positive" and "negative" are strict: a peer with no measured
skill yet counts in neither column and in the total.
"""

from __future__ import annotations

from pmx.sensors.catalogue import SensorBlock, SensorInputsLike, SensorSpec, block_of


def sense(view: SensorInputsLike, *, now_ms: int, spec: SensorSpec) -> SensorBlock:
    """``hive_reputation``'s three features (18.1). ``block_of`` drops the market id for this row."""
    del now_ms
    hive = view.hive
    if hive is None:
        return block_of(spec, None, [None] * len(spec.features))
    reputations = hive.reputations
    values: list[int | None] = [
        len(reputations),
        sum(1 for entry in reputations if entry.skill_micro > 0),
        sum(1 for entry in reputations if entry.skill_micro < 0),
    ]
    return block_of(spec, None, values)
