"""Fee, borrow and carry schedules as data (CONTRACTS_V2 8.8 and 17.4), and the integer price model.

Why this module exists at all: a fee is a venue fact with a source and a date, not a constant somebody
tuned until a backtest looked good. Every row below carries the page it was read from and the day it was
read, so a claim can be re-derived from the same numbers, and a row is never a formula: the four models of
:data:`FEE_MODELS` are the whole arithmetic and a new venue tier is a new row.

Why the integer price model lives here: section 17.1's ``notional_micro``, ``cash_out_cents``,
``cash_in_cents``, ``mark_value_cents``, ``price_micro`` and ``split_position_milli``, the six caps and
:data:`INSTRUMENT_KINDS` are declared in ``pmx.types`` (section 17.9, landed by gate G2) and re-exported
here explicitly, so every fee body below is written in the contract's own names and E2's tests read one
spelling of each. Every schedule row is a contract print and every scalar constant is read from
``pmx.types``, so the two cannot disagree.

One rounding, at the end, against the agent (ruling R146): ``cash_out_cents`` rounds up, ``cash_in_cents``
rounds down, a mark is ``floor`` for a long and ``-ceil`` for a short, and every fee rounds up. The engine
never creates a cent by rounding, which is what makes the accounting invariant of 8.9 an exact identity.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from pmx.errors import InvalidConfigError

# The price model of section 17.1 is declared once, in ``pmx.types`` (D1, landed by gate G2), and re-exported
# here because every fee body below is written in its terms and E2's tests import them from this module.
from pmx.types import BINARY_POINT_VALUE_MICRO as BINARY_POINT_VALUE_MICRO
from pmx.types import BINARY_TICK_SIZE_MICRO as BINARY_TICK_SIZE_MICRO
from pmx.types import BP_ONE, RE_FEE_SCHEDULE_ID
from pmx.types import CASH_EVENT_KINDS as CASH_EVENT_KINDS
from pmx.types import CONTINUOUS_KINDS as CONTINUOUS_KINDS
from pmx.types import DATA_CASH_EVENT_KINDS as DATA_CASH_EVENT_KINDS
from pmx.types import INSTRUMENT_KINDS as INSTRUMENT_KINDS
from pmx.types import INT63_MAX as INT63_MAX
from pmx.types import MICRO as MICRO
from pmx.types import MILLI as MILLI
from pmx.types import NOTIONAL_CENTS_MAX as NOTIONAL_CENTS_MAX
from pmx.types import NOTIONAL_DENOMINATOR as NOTIONAL_DENOMINATOR
from pmx.types import POINT_VALUE_MICRO_MAX as POINT_VALUE_MICRO_MAX
from pmx.types import PRICE_TICKS_MAX as PRICE_TICKS_MAX
from pmx.types import SIZE_MILLI_MAX as SIZE_MILLI_MAX
from pmx.types import TICK_SIZE_MICRO_MAX as TICK_SIZE_MICRO_MAX
from pmx.types import cash_in_cents as cash_in_cents
from pmx.types import cash_out_cents as cash_out_cents
from pmx.types import mark_value_cents as mark_value_cents
from pmx.types import notional_micro as notional_micro
from pmx.types import price_micro as price_micro
from pmx.types import split_position_milli as split_position_milli

if TYPE_CHECKING:  # pragma: no cover - import-time typing only
    from collections.abc import Mapping

__all__ = [
    "BINARY_POINT_VALUE_MICRO",
    "BINARY_TICK_SIZE_MICRO",
    "CARRY_SCHEDULES",
    "CASH_EVENT_KINDS",
    "CONTINUOUS_KINDS",
    "DATA_CASH_EVENT_KINDS",
    "CARRY_ROLES",
    "FEE_MODELS",
    "FEE_ROLES",
    "FEE_SCHEDULES",
    "INSTRUMENT_KINDS",
    "INT63_MAX",
    "KALSHI_REDUCED_FEE_SERIES",
    "MICRO",
    "MILLI",
    "NOTIONAL_CENTS_MAX",
    "NOTIONAL_DENOMINATOR",
    "POINT_VALUE_MICRO_MAX",
    "PRICE_TICKS_MAX",
    "SIZE_MILLI_MAX",
    "TICK_SIZE_MICRO_MAX",
    "CarrySchedule",
    "FeeSchedule",
    "carry_schedule",
    "cash_in_cents",
    "cash_out_cents",
    "fee_cents",
    "fee_schedule",
    "mark_value_cents",
    "notional_micro",
    "price_micro",
    "split_position_milli",
]


def _ceil_div(numerator: int, denominator: int) -> int:
    """``ceil(numerator / denominator)`` in integers, for a positive denominator: every fee rounds up, once."""
    return -((-numerator) // denominator)


# --------------------------------------------------------------------------------------------------
# 8.8 and 17.4: the schedule record and the four fee models
# --------------------------------------------------------------------------------------------------
#: The four fee models (section 17.4). ``pq_permille`` is section 8.8's binary rule, unchanged.
FEE_MODELS: tuple[str, ...] = ("pq_permille", "notional_bp", "per_contract", "zero")

#: The roles a fill can carry: a market order is a taker, a resting limit order that fills is a maker.
FEE_ROLES: tuple[str, ...] = ("taker", "maker")

#: The two roles a :class:`CarrySchedule` can play (section 17.4).
CARRY_ROLES: tuple[str, ...] = ("borrow", "carry")


@dataclass(frozen=True, slots=True)
class FeeSchedule:
    """One venue's fee rule as data, with the page it was read from and the day it was read (17.4).

    ``kind`` and ``model`` are amendment C1b's (ruling R155) and default to the binary row, so every
    schedule written against section 8.8 keeps its meaning: ``pq_permille`` with a taker and a maker
    permille is the Kalshi rule and every binary schedule uses it.
    """

    schedule_id: str
    provider: str
    kind: str = "binary"
    model: str = "pq_permille"
    taker_permille: int = 0
    maker_permille: int = 0
    taker_bp: int = 0
    maker_bp: int = 0
    sale_bp: int = 0
    per_contract_cents: int = 0
    exchange_cents: int = 0
    min_half_spread_ticks: int = 0
    rounding: str = "ceil"
    source_url: str = ""
    as_of_date: str = ""
    note: str = ""

    def __post_init__(self) -> None:
        """Refuse a schedule the contract cannot price, at construction rather than at the first fill."""
        if RE_FEE_SCHEDULE_ID.fullmatch(self.schedule_id) is None:
            raise InvalidConfigError("fee schedule id is not section 2's format", schedule_id=self.schedule_id)
        if self.kind not in INSTRUMENT_KINDS:
            raise InvalidConfigError("fee schedule kind is not an instrument kind", kind=self.kind)
        if self.model not in FEE_MODELS:
            raise InvalidConfigError("fee schedule model is not one of FEE_MODELS", model=self.model)
        if self.rounding != "ceil":
            raise InvalidConfigError("every fee rounds up to the next cent (8.8)", rounding=self.rounding)
        numbers = (
            ("taker_permille", self.taker_permille),
            ("maker_permille", self.maker_permille),
            ("taker_bp", self.taker_bp),
            ("maker_bp", self.maker_bp),
            ("sale_bp", self.sale_bp),
            ("per_contract_cents", self.per_contract_cents),
            ("exchange_cents", self.exchange_cents),
            ("min_half_spread_ticks", self.min_half_spread_ticks),
        )
        for name, value in numbers:
            if value < 0:
                raise InvalidConfigError("a fee rate is never negative", field=name, value=value)

    def to_dict(self) -> dict[str, object]:
        """The canonical-json-able record, for a manifest's ``schedules`` block and for a claim."""
        return {
            "schedule_id": self.schedule_id,
            "provider": self.provider,
            "kind": self.kind,
            "model": self.model,
            "taker_permille": self.taker_permille,
            "maker_permille": self.maker_permille,
            "taker_bp": self.taker_bp,
            "maker_bp": self.maker_bp,
            "sale_bp": self.sale_bp,
            "per_contract_cents": self.per_contract_cents,
            "exchange_cents": self.exchange_cents,
            "min_half_spread_ticks": self.min_half_spread_ticks,
            "rounding": self.rounding,
            "source_url": self.source_url,
            "as_of_date": self.as_of_date,
            "note": self.note,
        }


@dataclass(frozen=True, slots=True)
class CarrySchedule:
    """A borrow rate for an equity short or a carry rate for an fx swap (section 17.4).

    ``rate_ppm_per_day`` is signed for ``carry`` (a long pays when it is negative) and non-negative for
    ``borrow``. The engine turns it into the ``borrow_fee`` and ``carry`` cash events of 17.3.
    """

    schedule_id: str
    provider: str
    kind: str
    role: str
    rate_ppm_per_day: int
    source_url: str = ""
    as_of_date: str = ""
    note: str = ""

    def __post_init__(self) -> None:
        if RE_FEE_SCHEDULE_ID.fullmatch(self.schedule_id) is None:
            raise InvalidConfigError("carry schedule id is not section 2's format", schedule_id=self.schedule_id)
        if self.kind not in INSTRUMENT_KINDS:
            raise InvalidConfigError("carry schedule kind is not an instrument kind", kind=self.kind)
        if self.role not in CARRY_ROLES:
            raise InvalidConfigError("carry schedule role is borrow or carry", role=self.role)
        if self.role == "borrow" and self.rate_ppm_per_day < 0:
            raise InvalidConfigError("a borrow rate is never negative", rate=self.rate_ppm_per_day)

    def to_dict(self) -> dict[str, object]:
        return {
            "schedule_id": self.schedule_id,
            "provider": self.provider,
            "kind": self.kind,
            "role": self.role,
            "rate_ppm_per_day": self.rate_ppm_per_day,
            "source_url": self.source_url,
            "as_of_date": self.as_of_date,
            "note": self.note,
        }


def fee_cents(
    schedule: FeeSchedule,
    *,
    size: int,
    price_bp: int,
    role: str,
    side: str = "buy",
    tick_size_micro: int = BINARY_TICK_SIZE_MICRO,
    point_value_micro: int = BINARY_POINT_VALUE_MICRO,
) -> int:
    """The fee of one fill, in cents, always rounded up (sections 8.8 and 17.4).

    Args:
        schedule: The venue's schedule, resolved from the instrument's ``fee_schedule_id``.
        size: Whole contracts under ``pq_permille``; ``size_milli`` under every other model, because a
            ``// MILLI`` there would turn a one milli-coin fill into a fee on nothing (ruling R173).
        price_bp: The fill price in the instrument's ticks (basis points on a binary).
        role: ``taker`` for a market order, ``maker`` for a resting limit fill.
        side: ``buy`` or ``sell``; only ``notional_bp`` reads it, for the sale fee.
        tick_size_micro: The instrument's tick scale; the binary default keeps 8.8's call verbatim.
        point_value_micro: The instrument's point value.

    Returns:
        The fee in cents, ``0`` for a zero-size fill and for the ``zero`` model.

    Raises:
        InvalidConfigError: On an unknown role, side or model.
    """
    if role not in FEE_ROLES:
        raise InvalidConfigError("a fill role is taker or maker", role=role)
    if side not in ("buy", "sell"):
        raise InvalidConfigError("a fill side is buy or sell", side=side)
    if size <= 0:
        return 0
    if schedule.model == "zero":
        return 0
    if schedule.model == "pq_permille":
        multiplier = schedule.taker_permille if role == "taker" else schedule.maker_permille
        numerator = multiplier * size * price_bp * (BP_ONE - price_bp)
        if numerator <= 0:
            return 0
        return _ceil_div(numerator, 1_000_000_000)
    if schedule.model == "notional_bp":
        rate_bp = schedule.taker_bp if role == "taker" else schedule.maker_bp
        if side == "sell":
            rate_bp += schedule.sale_bp
        if rate_bp <= 0:
            return 0
        product = notional_micro(size, price_bp, tick_size_micro, point_value_micro) * rate_bp
        return _ceil_div(product, NOTIONAL_DENOMINATOR * BP_ONE)
    if schedule.model == "per_contract":
        per_side = schedule.per_contract_cents + schedule.exchange_cents
        if per_side <= 0:
            return 0
        return _ceil_div(size * per_side, MILLI)
    raise InvalidConfigError("fee schedule model is not one of FEE_MODELS", model=schedule.model)


# --------------------------------------------------------------------------------------------------
# The shipped schedules: data, not code (8.8's five binary rows and 17.4's continuous ones)
# --------------------------------------------------------------------------------------------------
#: The Kalshi series that carry the reduced taker rate. Empty until the fee PDF is read: the schedule
#: page returned 429 to the contract author on 2026-09-07 and this engine opens no socket, so the row
#: below keeps the contract's number and its date, and the series list stays empty rather than guessed.
KALSHI_REDUCED_FEE_SERIES: tuple[str, ...] = ()

_KALSHI_FEE_PDF = "https://kalshi.com/docs/kalshi-fee-schedule.pdf"

_SCHEDULE_ROWS: tuple[FeeSchedule, ...] = (
    FeeSchedule(
        schedule_id="kalshi-general-2026-09",
        provider="kalshi",
        kind="binary",
        model="pq_permille",
        taker_permille=70,
        maker_permille=0,
        source_url=_KALSHI_FEE_PDF,
        as_of_date="2026-09-07",
        note="round_up(0.07 * C * P * (1 - P)) USD, the general rate",
    ),
    FeeSchedule(
        schedule_id="kalshi-reduced-2026-09",
        provider="kalshi",
        kind="binary",
        model="pq_permille",
        taker_permille=35,
        maker_permille=0,
        source_url=_KALSHI_FEE_PDF,
        as_of_date="2026-09-07",
        note="the reduced rate; KALSHI_REDUCED_FEE_SERIES lists the series it applies to",
    ),
    FeeSchedule(
        schedule_id="polymarket-zero-2026-09",
        provider="polymarket",
        kind="binary",
        model="zero",
        source_url="https://docs.polymarket.com/",
        as_of_date="2026-09-07",
        note="standard markets carry no trading fee",
    ),
    FeeSchedule(
        schedule_id="manifold-zero-2026-09",
        provider="manifold",
        kind="binary",
        model="zero",
        source_url="https://manifoldmarkets.notion.site/",
        as_of_date="2026-09-07",
        note="play money, no trading fee",
    ),
    FeeSchedule(
        schedule_id="demo-zero",
        provider="demo",
        kind="binary",
        model="zero",
        note="the migrated v1 pack: no venue, no fee",
    ),
    FeeSchedule(
        schedule_id="binance-spot-2026-09",
        provider="binance",
        kind="spot_crypto",
        model="notional_bp",
        taker_bp=10,
        maker_bp=10,
        source_url="https://www.binance.com/en/fee/schedule",
        as_of_date="2026-09-08",
    ),
    FeeSchedule(
        schedule_id="binance-perp-2026-09",
        provider="binance",
        kind="perp",
        model="notional_bp",
        taker_bp=5,
        maker_bp=2,
        source_url="https://www.binance.com/en/fee/futureFee",
        as_of_date="2026-09-08",
    ),
    FeeSchedule(
        schedule_id="bybit-perp-2026-09",
        provider="bybit",
        kind="perp",
        model="notional_bp",
        taker_bp=5,
        maker_bp=2,
        source_url="https://www.bybit.com/en/help-center/article/Trading-Fee-Structure",
        as_of_date="2026-09-08",
    ),
    FeeSchedule(
        schedule_id="kraken-spot-2026-09",
        provider="kraken",
        kind="spot_crypto",
        model="notional_bp",
        taker_bp=26,
        maker_bp=16,
        source_url="https://www.kraken.com/features/fee-schedule",
        as_of_date="2026-09-08",
    ),
    FeeSchedule(
        schedule_id="coinbase-spot-2026-09",
        provider="coinbase",
        kind="spot_crypto",
        model="notional_bp",
        taker_bp=60,
        maker_bp=40,
        source_url="https://www.coinbase.com/advanced-fees",
        as_of_date="2026-09-08",
    ),
    FeeSchedule(
        schedule_id="xnys-zero-2026-09",
        provider="xnys",
        kind="equity",
        model="notional_bp",
        min_half_spread_ticks=1,
        source_url="https://www.sec.gov/divisions/marketreg/mrfreqreq.shtml",
        as_of_date="2026-09-08",
        note="commission-free; sale_bp carries the SEC section 31 rate when it is read",
    ),
    FeeSchedule(
        schedule_id="xnas-zero-2026-09",
        provider="xnas",
        kind="equity",
        model="notional_bp",
        min_half_spread_ticks=1,
        source_url="https://www.sec.gov/divisions/marketreg/mrfreqreq.shtml",
        as_of_date="2026-09-08",
        note="commission-free; sale_bp carries the SEC section 31 rate when it is read",
    ),
    FeeSchedule(
        schedule_id="arcx-zero-2026-09",
        provider="arcx",
        kind="equity",
        model="notional_bp",
        min_half_spread_ticks=1,
        source_url="https://www.sec.gov/divisions/marketreg/mrfreqreq.shtml",
        as_of_date="2026-09-08",
        note="commission-free; sale_bp carries the SEC section 31 rate when it is read",
    ),
    FeeSchedule(
        schedule_id="cme-es-2026-09",
        provider="xcme",
        kind="future",
        model="per_contract",
        per_contract_cents=125,
        exchange_cents=128,
        source_url="https://www.cmegroup.com/company/clearing-fees.html",
        as_of_date="2026-09-08",
        note="round turn halved per side",
    ),
    FeeSchedule(
        schedule_id="otcfx-spread-2026-09",
        provider="otcfx",
        kind="fx",
        model="zero",
        min_half_spread_ticks=5,
        source_url="https://www.bis.org/statistics/rpfx22.htm",
        as_of_date="2026-09-08",
        note="no commission; the cost is the half pip of the half-spread floor",
    ),
)

#: Every shipped fee schedule by id (section 17.4). An instrument's ``fee_schedule_id`` names one.
FEE_SCHEDULES: Mapping[str, FeeSchedule] = {row.schedule_id: row for row in _SCHEDULE_ROWS}

_CARRY_ROWS: tuple[CarrySchedule, ...] = tuple(
    CarrySchedule(
        schedule_id=f"{venue}-borrowgc-2026-09",
        provider=venue,
        kind="equity",
        role="borrow",
        rate_ppm_per_day=8,
        source_url="",
        as_of_date="2026-09-08",
        note=(
            "the general collateral floor of CONTRACTS_V2 17.4, about 0.3 percent a year; no public "
            "per-name borrow rate is free, so the number is the contract's and carries no page, and a "
            "hard-to-borrow list is a later row"
        ),
    )
    for venue in ("arcx", "xnas", "xnys")
)

#: Borrow and carry schedules by id. No carry schedule ships: an fx instrument's ``carry_schedule_id`` is
#: ``None`` unless a dataset declares the rate differential, which is off by default (ruling R177).
CARRY_SCHEDULES: Mapping[str, CarrySchedule] = {row.schedule_id: row for row in _CARRY_ROWS}


def fee_schedule(schedule_id: str, *, schedules: Mapping[str, FeeSchedule] | None = None) -> FeeSchedule:
    """Resolve a fee schedule id, preferring the run's own mapping over the shipped rows.

    Raises:
        InvalidConfigError: If no schedule carries that id. A market whose ``fee_schedule_id`` names
            nothing is a build error, and pricing it at zero would silently make a claim look better.
    """
    if schedules is not None:
        found = schedules.get(schedule_id)
        if found is not None:
            return found
    shipped = FEE_SCHEDULES.get(schedule_id)
    if shipped is None:
        raise InvalidConfigError("unknown fee schedule id", schedule_id=schedule_id)
    return shipped


def carry_schedule(schedule_id: str, *, schedules: Mapping[str, CarrySchedule] | None = None) -> CarrySchedule:
    """Resolve a borrow or carry schedule id, preferring the run's own mapping over the shipped rows.

    Raises:
        InvalidConfigError: If no schedule carries that id.
    """
    if schedules is not None:
        found = schedules.get(schedule_id)
        if found is not None:
            return found
    shipped = CARRY_SCHEDULES.get(schedule_id)
    if shipped is None:
        raise InvalidConfigError("unknown carry schedule id", schedule_id=schedule_id)
    return shipped
