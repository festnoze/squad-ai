"""The one place that joins the three metric families (CONTRACTS section 7.17, A15).

This is a separate module and not ``projection.py``, because it imports
:mod:`pxe.metrics.performance`, :mod:`pxe.metrics.calibration` and
:mod:`pxe.metrics.behavioral`, all three of which import
:mod:`pxe.metrics.projection`: putting it there would make the metrics package
import itself. It is not ``__init__.py`` either, because a shared ``__init__.py``
holds a docstring and nothing else (section 1).

It is also the **only** module of A15 allowed to import ``calibration`` (A16) and
``behavioral`` (A17), which is what keeps the dependency arrow of section 13
readable: ``projection`` and ``performance`` know nothing about the other two.

:func:`write_metrics` is the one writer of ``runs/<match_id>/metrics.json``
(section 4.6) and :func:`read_metrics` its exact inverse, which is what
``GET /api/matches/{id}/metrics`` serves. The file is written with
:func:`~pxe.events.stable_json` and the contractual ``open()`` arguments of
section 4.2, so it is byte stable across platforms even though it is not part of
the journal hash.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pxe.errors import InvalidConfigError
from pxe.events import JOURNAL_ENCODING, JOURNAL_NEWLINE, stable_json
from pxe.metrics.behavioral import BehavioralDescriptors, compute_descriptors
from pxe.metrics.calibration import CalibrationMetrics, compute_calibration
from pxe.metrics.performance import PerformanceMetrics, compute_performance
from pxe.metrics.projection import MatchProjection

__all__ = ["MatchMetrics", "compute_all", "write_metrics", "read_metrics"]

#: Schema marker written into ``metrics.json``. It is not a version of the
#: engine: the file is a projection and may be regenerated from the journal at
#: any time, but a reader still has to refuse a shape it does not know.
_METRICS_FORMAT = "pxe.metrics/1"


@dataclass(frozen=True)
class MatchMetrics:
    """Every metric of one match, joined and ready to serve or to store.

    Attributes:
        match_id: The match these metrics describe.
        performance: One block per ranked seat, sorted by ``agent_id``.
        calibration: One block per ranked seat, sorted by ``agent_id``.
        descriptors: One block per ranked seat, sorted by ``agent_id``.
        mm_pnl_cents: The FR-5.8.5 cost of liquidity, excluded from ranking.
        fees_collected_cents: Final balance of the ``FEES`` vault.
    """

    match_id: str
    performance: tuple[PerformanceMetrics, ...]  # sorted by agent_id
    calibration: tuple[CalibrationMetrics, ...]  # sorted by agent_id
    descriptors: tuple[BehavioralDescriptors, ...]  # sorted by agent_id
    mm_pnl_cents: int
    fees_collected_cents: int


def compute_all(projection: MatchProjection) -> MatchMetrics:
    """Compute performance, calibration and behavioral descriptors in one call.

    The three families are computed from the same projection and never from each
    other: that is AC-P4, and it is structural here rather than a convention,
    because ``compute_performance`` cannot see a prediction and
    ``compute_calibration`` cannot see a trade.

    Args:
        projection: The folded journal.

    Returns:
        The joined metrics, every block in canonical agent order.
    """
    return MatchMetrics(
        match_id=projection.match_id,
        performance=compute_performance(projection),
        calibration=compute_calibration(projection),
        descriptors=compute_descriptors(projection),
        mm_pnl_cents=projection.mm_pnl_cents,
        fees_collected_cents=projection.fees_collected_cents,
    )


def write_metrics(path: Path, metrics: MatchMetrics) -> None:
    r"""Write ``runs/<match_id>/metrics.json``, the one writer (section 4.6).

    Uses :func:`~pxe.events.stable_json` and the usual ``open()`` arguments, that
    is ``encoding="utf-8", newline="\n"``, so the bytes are identical on Windows
    and on Linux (section 4.2).

    Args:
        path: Destination file. Parent directories are created.
        metrics: The metrics to serialise.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding=JOURNAL_ENCODING, newline=JOURNAL_NEWLINE) as handle:
        handle.write(stable_json(_to_dict(metrics)) + JOURNAL_NEWLINE)


def read_metrics(path: Path) -> MatchMetrics:
    """Read back what :func:`write_metrics` wrote.

    This is what ``GET /api/matches/{id}/metrics`` serves. The API never
    recomputes engine logic, so without this function that endpoint has no
    source.

    Args:
        path: The ``metrics.json`` file.

    Returns:
        The reconstructed metrics.

    Raises:
        InvalidConfigError: If the file is not a ``metrics.json`` of this format,
            or if a block is missing a field. A silently defaulted metric is
            worse than a refusal: it would be published as a measurement.
    """
    with open(path, encoding=JOURNAL_ENCODING, newline=JOURNAL_NEWLINE) as handle:
        raw = json.load(handle)
    if not isinstance(raw, dict) or raw.get("format") != _METRICS_FORMAT:
        raise InvalidConfigError("not a pxe metrics.json", path=str(path), format=str(raw.get("format"))[:40])
    return MatchMetrics(
        match_id=_str(raw, "match_id", path),
        performance=tuple(_performance_from(row, path) for row in _rows(raw, "performance", path)),
        calibration=tuple(_calibration_from(row, path) for row in _rows(raw, "calibration", path)),
        descriptors=tuple(_descriptors_from(row, path) for row in _rows(raw, "descriptors", path)),
        mm_pnl_cents=_int(raw, "mm_pnl_cents", path),
        fees_collected_cents=_int(raw, "fees_collected_cents", path),
    )


# --------------------------------------------------------------------------
# Serialisation helpers. Private.
# --------------------------------------------------------------------------
def _to_dict(metrics: MatchMetrics) -> dict[str, Any]:
    """Return the JSON friendly mapping of one :class:`MatchMetrics`."""
    return {
        "format": _METRICS_FORMAT,
        "match_id": metrics.match_id,
        "performance": [
            {
                "agent_id": row.agent_id,
                "pnl_cents": row.pnl_cents,
                "pnl_bps": row.pnl_bps,
                "sharpe_milli": row.sharpe_milli,
                "max_drawdown_cents": row.max_drawdown_cents,
                "max_drawdown_bps": row.max_drawdown_bps,
                "volume_qty": row.volume_qty,
                "trade_count": row.trade_count,
                "maker_trade_count": row.maker_trade_count,
                "fees_paid_cents": row.fees_paid_cents,
            }
            for row in metrics.performance
        ],
        "calibration": [
            {
                "agent_id": row.agent_id,
                "brier_ppm": row.brier_ppm,
                "n_terms": row.n_terms,
                "n_carried": row.n_carried,
            }
            for row in metrics.calibration
        ],
        "descriptors": [
            {
                "agent_id": row.agent_id,
                "maker_ratio_ppm": row.maker_ratio_ppm,
                "reaction_latency_milli": row.reaction_latency_milli,
                "holding_horizon_milli": row.holding_horizon_milli,
                "herfindahl_ppm": row.herfindahl_ppm,
                "leverage_ppm": row.leverage_ppm,
                "message_intensity_ppm": row.message_intensity_ppm,
            }
            for row in metrics.descriptors
        ],
        "mm_pnl_cents": metrics.mm_pnl_cents,
        "fees_collected_cents": metrics.fees_collected_cents,
    }


def _rows(raw: Mapping[str, Any], key: str, path: Path) -> Sequence[Mapping[str, Any]]:
    """Return one block list of a ``metrics.json``, refusing anything else."""
    value = raw.get(key)
    if not isinstance(value, list) or any(not isinstance(row, dict) for row in value):
        raise InvalidConfigError("metrics.json block is not a list of objects", path=str(path), block=key)
    return value


def _int(row: Mapping[str, Any], key: str, path: Path) -> int:
    """Return an integer field, refusing a missing one or a float."""
    value = row.get(key)
    if not isinstance(value, int) or isinstance(value, bool):
        raise InvalidConfigError("metrics.json field is not an integer", path=str(path), field=key)
    return value


def _str(row: Mapping[str, Any], key: str, path: Path) -> str:
    """Return a string field, refusing a missing one."""
    value = row.get(key)
    if not isinstance(value, str):
        raise InvalidConfigError("metrics.json field is not a string", path=str(path), field=key)
    return value


def _performance_from(row: Mapping[str, Any], path: Path) -> PerformanceMetrics:
    """Rebuild one :class:`~pxe.metrics.performance.PerformanceMetrics`."""
    return PerformanceMetrics(
        agent_id=_str(row, "agent_id", path),
        pnl_cents=_int(row, "pnl_cents", path),
        pnl_bps=_int(row, "pnl_bps", path),
        sharpe_milli=_int(row, "sharpe_milli", path),
        max_drawdown_cents=_int(row, "max_drawdown_cents", path),
        max_drawdown_bps=_int(row, "max_drawdown_bps", path),
        volume_qty=_int(row, "volume_qty", path),
        trade_count=_int(row, "trade_count", path),
        maker_trade_count=_int(row, "maker_trade_count", path),
        fees_paid_cents=_int(row, "fees_paid_cents", path),
    )


def _calibration_from(row: Mapping[str, Any], path: Path) -> CalibrationMetrics:
    """Rebuild one :class:`~pxe.metrics.calibration.CalibrationMetrics`."""
    return CalibrationMetrics(
        agent_id=_str(row, "agent_id", path),
        brier_ppm=_int(row, "brier_ppm", path),
        n_terms=_int(row, "n_terms", path),
        n_carried=_int(row, "n_carried", path),
    )


def _descriptors_from(row: Mapping[str, Any], path: Path) -> BehavioralDescriptors:
    """Rebuild one :class:`~pxe.metrics.behavioral.BehavioralDescriptors`."""
    return BehavioralDescriptors(
        agent_id=_str(row, "agent_id", path),
        maker_ratio_ppm=_int(row, "maker_ratio_ppm", path),
        reaction_latency_milli=_int(row, "reaction_latency_milli", path),
        holding_horizon_milli=_int(row, "holding_horizon_milli", path),
        herfindahl_ppm=_int(row, "herfindahl_ppm", path),
        leverage_ppm=_int(row, "leverage_ppm", path),
        message_intensity_ppm=_int(row, "message_intensity_ppm", path),
    )
