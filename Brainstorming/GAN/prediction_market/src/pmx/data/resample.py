"""Irregular provider prints to the regular bar grid the engine consumes (CONTRACTS_V2 section 5.2).

Why a grid at all: an agent that decides on a tape of irregular prints decides on a different tape than the
one the fill model reads, and "the price at t" stops being a single number. A grid makes the two readings
the same object, and it makes "nothing traded" a value (``volume_milli = 0``) instead of an absence, which
is what section 8.6 needs in order to refuse a fill rather than invent one at a stale price.

Every number here is an integer: prices in basis points, sizes in thousandths of a contract, time in epoch
milliseconds. The one rounding is ``round_half_up`` on the volume weighted mean, pinned by the contract as
the bar's ``vwap_bp``, so two builds of the same tape write the same bytes. Nothing in this module reads a
clock or a random number: a bar is a pure function of the prints that fall inside it.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from pmx.errors import InvalidConfigError, SchemaError
from pmx.types import (
    INTERVALS_MIN,
    MS_PER_DAY,
    PRICE_MAX_BP,
    PRICE_MIN_BP,
    Bar,
    Trade,
    bar_of,
    interval_ms,
    round_half_up,
)

__all__ = [
    "EMPTY_QUOTE",
    "Quote",
    "bars_from_trades",
    "median_daily_volume_milli",
    "median_daily_volume_milli_of",
    "traded_bars",
    "volume_milli_total",
]


@dataclass(frozen=True, slots=True)
class Quote:
    """What a provider's candlestick adds to a bar that its prints cannot: the book and the open interest.

    All three fields are optional because only some providers publish them (Kalshi does, Manifold does
    not), and ``market.v2.json`` accepts ``null`` for each.
    """

    yes_bid_bp: int | None = None
    yes_ask_bp: int | None = None
    open_interest: int | None = None


#: The quote of a bar the provider said nothing about.
EMPTY_QUOTE = Quote()


def _trade_sort_key(trade: Trade) -> tuple[int, int, int, str]:
    """The canonical order of section 3. Sorting by it is idempotent on an importer's already sorted tape
    and makes ``open`` and ``close`` deterministic when two prints share a millisecond."""
    return (trade.t_ms, trade.price_bp, trade.size_milli, trade.side)


def _check_price(name: str, value: int) -> int:
    if not PRICE_MIN_BP <= value <= PRICE_MAX_BP:
        raise InvalidConfigError(f"{name} outside the tradable range", value=value, lo=PRICE_MIN_BP, hi=PRICE_MAX_BP)
    return value


def bars_from_trades(
    trades: Sequence[Trade],
    *,
    interval_min: int,
    start_ms: int,
    end_ms: int,
    first_price_bp: int,
    quotes: Mapping[int, Quote] | None = None,
) -> tuple[Bar, ...]:
    """Resample ``trades`` onto the ``interval_min`` grid from ``start_ms`` to ``end_ms``, both inclusive.

    ``start_ms`` and ``end_ms`` are the caller's ``bar_of(created_at_ms)`` and ``bar_of(resolved_at_ms)``;
    they are re-aligned here so a caller that passes the raw instants gets the same grid. Every bar of the
    range is emitted, in ascending ``t_ms``, with no gap and no duplicate, which is the density the loader
    demands of a market file.

    A bar that holds prints takes ``open`` from its first print, ``close`` from its last, ``high``/``low``
    from the extremes, ``vwap_bp = round_half_up(sum(price_bp * size_milli), sum(size_milli))``,
    ``volume_milli`` the sum of the sizes and ``n_trades`` the count. A bar that holds none repeats the
    carried close as ``open == high == low == close == vwap`` with ``volume_milli = 0`` and
    ``n_trades = 0``; before the first print the carried close is ``first_price_bp`` (the provider's
    opening quote when it published one, else its first print).

    Raises ``InvalidConfigError`` on an unknown interval, an inverted range or an out-of-range price, and
    ``SchemaError`` on a print that falls outside the grid: dropping it would silently lose volume, and
    growing the grid would break the density rule the market's ``created_at_ms`` fixes.
    """
    if interval_min not in INTERVALS_MIN:
        raise InvalidConfigError("interval_min is not a grid of the contract", interval_min=interval_min)
    step_ms = interval_ms(interval_min)
    first_bar_ms = bar_of(start_ms, interval_min)
    last_bar_ms = bar_of(end_ms, interval_min)
    if last_bar_ms < first_bar_ms:
        raise InvalidConfigError("end_ms is before start_ms", start_ms=start_ms, end_ms=end_ms)
    _check_price("first_price_bp", first_price_bp)

    ordered = sorted(trades, key=_trade_sort_key)
    for trade in ordered:
        _check_price("trade.price_bp", trade.price_bp)
        if trade.size_milli < 1:
            raise InvalidConfigError("trade.size_milli is below one thousandth", size_milli=trade.size_milli)
        if not first_bar_ms <= trade.t_ms < last_bar_ms + step_ms:
            raise SchemaError(
                "a print falls outside the market's bar grid",
                t_ms=trade.t_ms,
                first_bar_ms=first_bar_ms,
                last_bar_ms=last_bar_ms,
            )

    grouped: dict[int, list[Trade]] = {}
    for trade in ordered:
        grouped.setdefault(bar_of(trade.t_ms, interval_min), []).append(trade)

    book = quotes or {}
    bars: list[Bar] = []
    carried_bp = first_price_bp
    t_ms = first_bar_ms
    while t_ms <= last_bar_ms:
        quote = book.get(t_ms, EMPTY_QUOTE)
        if quote.yes_bid_bp is not None:
            _check_price("quote.yes_bid_bp", quote.yes_bid_bp)
        if quote.yes_ask_bp is not None:
            _check_price("quote.yes_ask_bp", quote.yes_ask_bp)
        if quote.yes_bid_bp is not None and quote.yes_ask_bp is not None and quote.yes_bid_bp > quote.yes_ask_bp:
            raise SchemaError(
                "a quote's bid is above its ask",
                t_ms=t_ms,
                yes_bid_bp=quote.yes_bid_bp,
                yes_ask_bp=quote.yes_ask_bp,
            )
        if quote.open_interest is not None and quote.open_interest < 0:
            raise InvalidConfigError("open_interest is negative", open_interest=quote.open_interest)

        inside = grouped.get(t_ms, [])
        if inside:
            prices = [trade.price_bp for trade in inside]
            volume_milli = sum(trade.size_milli for trade in inside)
            notional = sum(trade.price_bp * trade.size_milli for trade in inside)
            bar = Bar(
                t_ms=t_ms,
                open_bp=prices[0],
                high_bp=max(prices),
                low_bp=min(prices),
                close_bp=prices[-1],
                vwap_bp=round_half_up(notional, volume_milli),
                volume_milli=volume_milli,
                n_trades=len(inside),
                yes_bid_bp=quote.yes_bid_bp,
                yes_ask_bp=quote.yes_ask_bp,
                open_interest=quote.open_interest,
            )
            carried_bp = bar.close_bp
        else:
            bar = Bar(
                t_ms=t_ms,
                open_bp=carried_bp,
                high_bp=carried_bp,
                low_bp=carried_bp,
                close_bp=carried_bp,
                vwap_bp=carried_bp,
                volume_milli=0,
                n_trades=0,
                yes_bid_bp=quote.yes_bid_bp,
                yes_ask_bp=quote.yes_ask_bp,
                open_interest=quote.open_interest,
            )
        bars.append(bar)
        t_ms += step_ms
    return tuple(bars)


def traded_bars(bars: Sequence[Bar]) -> int:
    """Bars that saw at least one print. Feeds ``quality.traded_bars`` and the density filter of 7.4."""
    return sum(1 for bar in bars if bar.n_trades > 0)


def volume_milli_total(bars: Sequence[Bar]) -> int:
    """Total traded volume of the tape in thousandths. Feeds ``quality.volume_milli_total``."""
    return sum(bar.volume_milli for bar in bars)


def median_daily_volume_milli_of(samples: Sequence[tuple[int, int]]) -> int:
    """Median of the per-day traded volume, in thousandths, over ``(t_ms, volume_milli)`` samples.

    The ``illiquid`` hardness tag of section 7.5 is a decile of this number across a provider slice, so it
    is defined per day and not per bar: an hourly dataset must not read as twenty four times more liquid
    than the daily one built from the same prints. Days with no print count as zero, because they are days
    on which the market could not be traded. The median of an even count is the lower of the two middle
    values, which keeps the result an integer without inventing a rounding rule nothing else shares.

    This spelling takes pairs rather than bars because the dataset builder holds market payloads as plain
    JSON objects, and the definition of "median daily volume" must not exist twice.
    """
    if not samples:
        return 0
    per_day: dict[int, int] = {}
    for t_ms, volume_milli in samples:
        day_ms = (t_ms // MS_PER_DAY) * MS_PER_DAY
        per_day[day_ms] = per_day.get(day_ms, 0) + volume_milli
    daily = sorted(per_day.values())
    return daily[(len(daily) - 1) // 2]


def median_daily_volume_milli(bars: Sequence[Bar]) -> int:
    """``median_daily_volume_milli_of`` over a market's bars."""
    return median_daily_volume_milli_of([(bar.t_ms, bar.volume_milli) for bar in bars])
