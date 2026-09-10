"""The ``cross_asset`` sensor of CONTRACTS_V2 18.1 (package S1): the run's other instruments.

It gates ``underlying_id`` and ``twins``. Its only input is ``SensorInputs.peers`` (12.11), which is one
flat map from a peer's id to that peer's completed bars, with no label saying which peer is a twin, which
is the underlying and which is a cluster member. The split below is therefore read off the id itself,
which is the only distinguishing datum the declaration carries:

* a peer whose id prefix is one of section 2's five **prediction-market** providers is a market and a
  **cluster peer**; those five are the list ``tape.provider_index`` indexes, and the twelve venues
  amendment C1b added to ``PROVIDERS`` (17.1) are instruments, not prediction markets;
* such a peer whose provider differs from this market's is also a **twin** (the same event on another
  venue, which is what 18.1's column says a twin is);
* a peer whose prefix is not one of the five is an instrument and is this market's **underlying**; the
  first in canonical id order is the one read, so two underlyings never make the value depend on a
  dictionary's insertion order.

``constraint_residual_ppm`` and ``constraint_count`` have no input at all: ``SensorInputs`` carries no
``EventCluster`` and no ``Constraint``, and 7.9 forbids both records from reaching an observation
(ruling R209 bans even their structural key names). Both therefore read their sentinel, which is ``0``
for the signed residual and ``0`` for the count, and the gap is reported as a contract issue rather than
patched with a number this module would have to invent.
"""

from __future__ import annotations

from collections.abc import Mapping

from pmx.sensors.catalogue import SensorBlock, SensorInputsLike, SensorSpec, block_of
from pmx.types import PROVIDERS, Bar, bp_ratio, round_half_up

#: Section 2's five prediction-market providers: the list ``tape.provider_index`` indexes (its ``hi`` of
#: ``4`` is what fixes the count) and the only venues a twin can sit on.
MARKET_PROVIDERS: tuple[str, ...] = PROVIDERS[:5]


def _provider_of(market_id: str) -> str:
    return market_id.split("-", 1)[0]


def _last_close_bp(bars: tuple[Bar, ...]) -> int | None:
    return bars[-1].close_bp if bars else None


def sense(view: SensorInputsLike, *, now_ms: int, spec: SensorSpec) -> SensorBlock:
    """``cross_asset``'s six features (18.1)."""
    del now_ms
    peers: Mapping[str, tuple[Bar, ...]] = view.peers
    market_peers = {peer_id: bars for peer_id, bars in peers.items() if _provider_of(peer_id) in MARKET_PROVIDERS}
    underlyings = sorted(peer_id for peer_id in peers if _provider_of(peer_id) not in MARKET_PROVIDERS)

    last_price_bp = _last_close_bp(view.bars)
    peer_closes = [close for close in (_last_close_bp(bars) for bars in market_peers.values()) if close is not None]
    cluster_gap_bp: int | None = None
    if last_price_bp is not None and peer_closes:
        cluster_gap_bp = last_price_bp - round_half_up(sum(peer_closes), len(peer_closes))

    underlying_ret_1b_bp: int | None = None
    if underlyings:
        underlying_bars = peers[underlyings[0]]
        if len(underlying_bars) >= 2 and underlying_bars[-2].close_bp != 0:
            underlying_ret_1b_bp = bp_ratio(
                underlying_bars[-1].close_bp - underlying_bars[-2].close_bp, underlying_bars[-2].close_bp
            )

    values: list[int | None] = [
        cluster_gap_bp,
        # A count is always measured: no peer is zero peers, not a missing input.
        len(market_peers),
        None,
        None,
        sum(1 for peer_id in market_peers if _provider_of(peer_id) != view.meta.provider),
        underlying_ret_1b_bp,
    ]
    return block_of(spec, view.meta.id, values)
