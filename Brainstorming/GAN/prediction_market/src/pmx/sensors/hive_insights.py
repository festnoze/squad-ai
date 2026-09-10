"""The ``hive_insights`` sensor of CONTRACTS_V2 18.1 (package S1): the readable half of the hive.

It gates ``HiveView.insights``, ``lessons``, ``resolutions``, ``forecasts`` and ``prev_bar_forecasts``;
``HiveView.reputations`` is the other half and belongs to ``hive_reputation`` (ruling R233 splits the one
view between the two sensors, and ``Observation.hive`` is present when either is bought and carries only
the bought half).

``HiveView.insights`` and ``InsightView`` are amendment C1c's and land in ``pmx.types`` with A1 and A3 in
lot 6 (18.8's first row). Until then the four insight features read an absent tuple, which is a missing
input and takes the sentinel, and the two features that read fields ``HiveView`` already carries
(``lessons``, ``forecasts`` and ``prev_bar_forecasts``) are measured today. The reads are attribute reads
with a default rather than an import of a name that does not exist, so the day A3 lands ``insights`` this
block starts measuring it with no edit here.
"""

from __future__ import annotations

from collections.abc import Sequence

from pmx.sensors.catalogue import SensorBlock, SensorInputsLike, SensorSpec, block_of
from pmx.types import HiveView


def _int_attr(entry: object, name: str) -> int:
    """One integer field of an insight entry, ``0`` when the entry does not carry it."""
    value = getattr(entry, name, 0)
    return value if isinstance(value, int) and not isinstance(value, bool) else 0


def firing_insights(hive: HiveView | None) -> tuple[object, ...]:
    """``HiveView.insights``: the promoted, undemoted insights whose rule fires at ``now_ms`` on this
    market, already narrowed to what the agent's diet can read by the runner (ruling R279).

    The tuple is empty on a tree whose ``HiveView`` has no ``insights`` field yet.
    """
    if hive is None:
        return ()
    entries = getattr(hive, "insights", ())
    if not isinstance(entries, Sequence) or isinstance(entries, str | bytes):
        return ()
    return tuple(entries)


def sense(view: SensorInputsLike, *, now_ms: int, spec: SensorSpec) -> SensorBlock:
    """``hive_insights``'s six features (18.1)."""
    hive = view.hive
    if hive is None:
        return block_of(spec, view.meta.id, [None] * len(spec.features))
    market_id = view.meta.id
    insights = firing_insights(hive)
    lifts = [(_int_attr(entry, "direction"), _int_attr(entry, "lift_bp")) for entry in insights]
    values: list[int | None] = [
        len(insights),
        max((_int_attr(entry, "lower_bp") for entry in insights), default=None),
        sum(lift for direction, lift in lifts if direction > 0) if insights else None,
        sum(lift for direction, lift in lifts if direction < 0) if insights else None,
        sum(
            1
            for lesson in hive.lessons
            if lesson.visible_from_ms <= now_ms and (not lesson.market_ids or market_id in lesson.market_ids)
        ),
        sum(
            1
            for forecast in (*hive.forecasts, *hive.prev_bar_forecasts)
            if forecast.market_id == market_id and forecast.bar_ms <= now_ms
        ),
    ]
    return block_of(spec, market_id, values)
