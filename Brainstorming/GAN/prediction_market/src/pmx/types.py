"""The unit system, the identifier formats, the canonical orderings and every v2 dataclass.

This module is the reason twenty-seven packages can be written in parallel: every number the contract
pins is a named constant here, every conversion between units is one function here, and every structure
that crosses a package boundary is one frozen dataclass here. A package that needs a scale, a cap, a
regex or a shape reads it from ``pmx.types`` rather than restating it, so a change of unit is a change of
one line and not a hunt through twenty-seven files (CONTRACTS_V2 sections 1 to 5, 7.2 to 7.4, 8.1, 8.3
and 8.4).

Three rules of the contract are enforced by the shapes below rather than by discipline:

* **Integers only.** Money is cents, price is basis points of one currency unit, probability is parts per
  million, Brier is micro-units, time is UTC epoch milliseconds. There is no float in a score, a fill, a
  balance or a journal, so every rounding is written out (``cost_cents`` rounds against the buyer,
  ``proceeds_cents`` against the seller) and no cent is ever created by a rounding mode.
* **No clock and no identity source.** Nothing here reads the wall clock, a UUID or module-level
  randomness; an instant arrives as an argument and an id is derived from data.
* **Leak-free by construction.** ``Market`` carries ``final_price_bp``, never ``last_price_bp``:
  ``MarketView.last_price_bp`` is the as-of price of the bar being decided, and giving the two the same
  name is exactly the leak that no named test would have caught (section 7.2).
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_HALF_UP, Decimal, localcontext
from enum import StrEnum
from pathlib import Path

from pmx.errors import InvalidConfigError, SchemaError

# Re-exported (section 6.1) so that the engine version tuple
# ``(pmx.__version__, CONTRACT_VERSION, RNG_ALGORITHM_VERSION)`` reads from one module. The constant
# itself belongs to ``pmx.rng``, which owns the pinned arithmetic it versions; nothing here redefines it.
from pmx.rng import RNG_ALGORITHM_VERSION as RNG_ALGORITHM_VERSION

# Re-exported for the same reason (ruling R86): ``SEED_SPACE`` is the seed range ``pmx.rng`` itself
# accepts, so the module that owns the pinned arithmetic owns the constant, and this module (which
# every config validates against) reads it from there rather than restating it.
from pmx.rng import SEED_SPACE as SEED_SPACE

# --------------------------------------------------------------------------------------------------
# 1.2 Units and scales
# --------------------------------------------------------------------------------------------------
#: Parts per million: the one probability scale. There is no float probability anywhere in pmx.
PPM_ONE = 1_000_000
#: Basis points of one currency unit: the one price scale. A YES contract settles at BP_ONE or at 0.
BP_ONE = 10_000
#: A tradable price is never 0 and never 1: those are settlement values, not quotes.
PRICE_MIN_BP = 1
PRICE_MAX_BP = 9_999
SETTLE_YES_BP = 10_000
SETTLE_NO_BP = 0
#: Cents per currency unit: a YES contract pays 100 cents on YES.
CENTS_PER_UNIT = 100
#: The log score is clamped before the logarithm, so a confident wrong call is finite and comparable.
LOG_CLAMP_LO_PPM = 10_000
LOG_CLAMP_HI_PPM = 990_000

# --------------------------------------------------------------------------------------------------
# 17.1 The integer price model across kinds (amendment C1b, rulings R144 to R148; landed by gate G2)
# --------------------------------------------------------------------------------------------------
#: Millionths: the scale of ``tick_size_micro`` and ``point_value_micro``.
MICRO = 1_000_000
#: Thousandths of one unit of position, the one quantity unit of the price model. Re-exported by
#: ``pmx.engine.liquidity`` (ruling R86's rule: declared once, in the lowest layer everyone imports).
MILLI = 1_000
#: ``MILLI * MICRO * MICRO // CENTS_PER_UNIT``, exactly ``10 ** 13``: the one divisor of a cash movement.
NOTIONAL_DENOMINATOR = MILLI * MICRO * MICRO // CENTS_PER_UNIT
#: One basis point of a one-unit payout, which is what keeps ``price_ticks == price_bp`` on a binary
#: (ruling R145: ``100`` and not the PRD's ``10_000``, which would price forty contracts at 2 530 USD).
BINARY_TICK_SIZE_MICRO = 100
#: One unit of binary position pays one currency unit at a price of 1.0.
BINARY_POINT_VALUE_MICRO = 1_000_000
#: The five caps that make every STORED integer fit ``INT63_MAX`` (ruling R147). The four-factor product
#: itself is exact in Python and is never written.
PRICE_TICKS_MAX = 10**12
SIZE_MILLI_MAX = 10**12
TICK_SIZE_MICRO_MAX = 10**9
POINT_VALUE_MICRO_MAX = 10**12
#: One fill or one cash event may not exceed this notional; ``Execution`` refuses ``bad_size`` beyond it.
NOTIONAL_CENTS_MAX = 10**15
INT63_MAX = 2**63 - 1
#: Section 16.2 (ruling R107): an action decided on bar ``t`` executes at the open of the instrument's
#: next bar. A contract constant and never a ``RunConfig`` field: a run that could turn the latency off
#: would be a run whose fills the tape never had to honour.
DECISION_LATENCY_BARS = 1
#: The calendar of every binary and every crypto instrument: one session ``[0, INT63_MAX)``, synthesised
#: by the loader and never a file (section 17.2, ruling R185).
CONTINUOUS_CALENDAR_ID = "continuous"
#: How many applied data cash events a ``MarketView`` shows (section 8.3, ruling R183).
CASH_EVENTS_VIEW_MAX = 30
#: The five pinball levels (section 17.5, ruling R159), fixed for every kind and every horizon.
QUANTILE_LEVELS_PPM = (100_000, 250_000, 500_000, 750_000, 900_000)
#: The random walk: the efficient-market statement for a price series (ruling R158). Its directional
#: Brier is the constant below on an up, a down and a flat realisation alike, so its skill is zero by
#: construction.
RANDOM_WALK_UP_PPM = 500_000
RANDOM_WALK_BRIER_MICRO = 250_000
#: Section 10.4's reputation window: the last fifty settled markets of an ``(agent, category)``. Declared
#: here rather than in ``pmx.agents.hive`` because the runner (wave 2) needs it before the hive (wave 3)
#: exists, and because every number a test can pin lives in this module (gate G2 ruling).
REPUTATION_WINDOW_MARKETS = 50

# --------------------------------------------------------------------------------------------------
# 5.1 Time
# --------------------------------------------------------------------------------------------------
MS_PER_SECOND = 1_000
MS_PER_MINUTE = 60_000
MS_PER_HOUR = 3_600_000
MS_PER_DAY = 86_400_000
#: The two grids a dataset may be built on. One dataset carries one of them (section 5.3).
INTERVALS_MIN = (60, 1_440)
#: Six hours: a news item is readable this long after it was published (section 5.5).
SAFETY_LAG_MS_DEFAULT = 21_600_000

# --------------------------------------------------------------------------------------------------
# 2 Enumerations
# --------------------------------------------------------------------------------------------------
#: The seventeen providers of section 17.8 (ruling R165): the five binary venues, the four crypto venues,
#: the equity and futures venues as lower-case ISO 10383 MIC codes, and ``otcfx`` for the FX book. A
#: provider is the venue whose fee schedule applies, which is why an instrument id starts with one.
PROVIDERS = (
    "kalshi",
    "manifold",
    "polymarket",
    "metaculus",
    "demo",
    "binance",
    "kraken",
    "coinbase",
    "bybit",
    "xnys",
    "xnas",
    "arcx",
    "xcme",
    "xnym",
    "xcec",
    "xcbt",
    "otcfx",
)
#: The twelve vendors of section 17.8: the data source a tape was read from. A binary's vendor is its
#: provider; ``yahoo`` is unofficial and every claim on a ``yahoo`` tape carries the vendor caveat.
VENDORS = (
    "kalshi",
    "manifold",
    "polymarket",
    "metaculus",
    "demo",
    "binance",
    "kraken",
    "coinbase",
    "bybit",
    "yahoo",
    "frankfurter",
    "ecb",
)
#: The six instrument kinds, a closed enumeration (section 17.1, ruling R144). A binary contract is one
#: kind among six and nothing already written for it changes value.
INSTRUMENT_KINDS = ("binary", "spot_crypto", "perp", "fx", "equity", "future")
#: Every kind that has no resolution and is closed by a forced flat at its last bar (17.2, 17.3).
CONTINUOUS_KINDS = INSTRUMENT_KINDS[1:]
#: The seven cash event kinds in **application order** (section 17.3, rulings R177 and R193): the events
#: of one bar apply kind first, so a funding never applies after a roll of the same bar and a forced flat
#: is last on its bar.
CASH_EVENT_KINDS = ("funding", "dividend", "split", "roll", "borrow_fee", "carry", "forced_flat")
#: What an instrument file may carry; the other three are the engine's own (ruling R177).
DATA_CASH_EVENT_KINDS = CASH_EVENT_KINDS[:4]
CASH_EVENT_ORIGINS = ("data", "engine")
#: The order of this tuple **is** the lexicon order: ``specialist.category``, ``newsbayes.lexicon_id``
#: and ``data/lexicons/<category>.v1.json`` all index it (section 2).
CATEGORIES = (
    "politics",
    "economics",
    "finance",
    "crypto",
    "sports",
    "science",
    "tech",
    "entertainment",
    "weather",
    "health",
    "world",
    "other",
)
LEXICON_COUNT = len(CATEGORIES)
#: The quote currencies of section 17.1, whose minor unit is the cash unit. ``mana`` is Manifold's play
#: money; the three added by amendment C1b are the quote currencies of the crypto, FX and equity venues.
CURRENCIES = ("usd", "mana", "usdt", "eur", "jpy")
SOURCES = ("imported", "reconstructed")
#: ``yes``, ``no`` or ``unknown`` on a binary; ``buy``, ``sell`` or ``unknown`` on a continuous instrument
#: (the taker's side). The loader enforces the pair per kind (ruling R173).
TRADE_SIDES = ("yes", "no", "unknown", "buy", "sell")
BINARY_TRADE_SIDES = TRADE_SIDES[:3]
CONTINUOUS_TRADE_SIDES = ("buy", "sell", "unknown")
#: The eight news sources of section 17.8: the five of section 2 and amendment C1b's ``edgar``, ``fred``
#: and ``cboe`` (ruling R165; ``news.v1.json`` gains them at gate G3b, so a build that names one of the
#: three passes ``BuildConfig`` today and fails the schema until then).
NEWS_SOURCES = (
    "wikipedia_current_events",
    "wikipedia_asof",
    "wayback",
    "gdelt",
    "manifold_comment",
    "edgar",
    "fred",
    "cboe",
)
NEWS_KINDS = ("headline", "background", "frontpage", "article", "comment", "filing", "release")
#: ``source`` fixes ``kind`` and the ``news_id`` prefix; the loader checks both (sections 2 and 7.3).
NEWS_KIND_BY_SOURCE = {
    "wikipedia_current_events": "headline",
    "wikipedia_asof": "background",
    "wayback": "frontpage",
    "gdelt": "article",
    "manifold_comment": "comment",
    "edgar": "filing",
    "fred": "release",
    "cboe": "release",
}
NEWS_CODE_BY_SOURCE = {
    "wikipedia_current_events": "wce",
    "wikipedia_asof": "wasof",
    "wayback": "wb",
    "gdelt": "gd",
    "manifold_comment": "mfc",
    "edgar": "edg",
    "fred": "fred",
    "cboe": "cboe",
}
#: Stored, never used to drop a market, never shown to an agent (section 7.5).
HARDNESS_TAGS = ("trivial", "upset", "whipsaw", "illiquid")
#: A market belongs to exactly one of the first three; ``all`` is the run-config spelling for "no filter".
FOLDS = ("train", "validation", "sealed", "all")
ACTION_KINDS = ("hold", "target", "limit", "abstain")
RESEARCH_KINDS = ("news", "history", "wiki_asof")
#: Days to ``close_at_ms``: ``>= 30 -> 30d``, ``[7, 30) -> 7d``, ``[2, 7) -> 2d``, ``< 2 -> 0d``. The last
#: bucket is ``< 2`` and not ``[0, 2)`` because a market stays open between its close and its resolution,
#: where ``days_to_close`` is negative, and ``0d`` absorbs those settlement-lag bars (sections 10.3, 12.1).
HORIZON_BUCKETS = ("30d", "7d", "2d", "0d")
#: Reliability bins: ``bin = min(CALIBRATION_BINS - 1, prob_ppm // 100_000)`` (section 12.2).
CALIBRATION_BINS = 10
#: The journal envelope's phase order, and the order ``verify_journal`` compares against (section 9.1).
#: ``generation`` sits between ``close`` and ``post`` because an evolution journal is ``pre``
#: (``evolution_started``), then ``generation`` (every generation event), then ``post``
#: (``evolution_ended``), all at ``bar_ms = 0``. A journal never mixes ``generation`` with the bar phases.
PHASE_ORDER = (
    "pre",
    "open",
    "observe",
    "decide",
    "execute",
    "settle",
    "learn",
    "hive",
    "close",
    "generation",
    "post",
)

# --------------------------------------------------------------------------------------------------
# 2 Identifier formats. Every regex of the contract's table is one constant here, and the loader, the
# runner and the API validate against these and never against a literal of their own.
# --------------------------------------------------------------------------------------------------
_PROVIDER_ALT = "|".join(PROVIDERS)
RE_PROVIDER = re.compile(rf"^({_PROVIDER_ALT})$")
RE_MARKET_ID = re.compile(rf"^({_PROVIDER_ALT})-[A-Za-z0-9._-]{{1,96}}$")
RE_CATEGORY = re.compile(rf"^({'|'.join(CATEGORIES)})$")
RE_AGENT_ID = re.compile(r"^[a-z][a-z0-9_]{0,31}(-[0-9a-f]{8})?$")
RE_FAMILY = re.compile(r"^[a-z][a-z0-9_]{0,23}$")
RE_GENOME_HASH = re.compile(r"^[0-9a-f]{64}$")
RE_DATASET_NAME = re.compile(r"^[a-z][a-z0-9_-]{0,31}$")
RE_DATASET_HASH = re.compile(r"^[0-9a-f]{64}$")
RE_RUN_BACKTEST_ID = re.compile(r"^r-[0-9a-f]{8}-[0-9]{1,19}-[0-9a-f]{8}$")
RE_RUN_EVOLUTION_ID = re.compile(r"^e-[0-9a-f]{8}-[0-9]{1,19}-[0-9a-f]{8}$")
_KIND_ALT = "|".join(INSTRUMENT_KINDS)
#: ``c-<dataset_hash[:8]>-<kind>-<provider>-h<horizon_bars>-<genome_hash[:16]>`` (section 17.8, ruling
#: R162). The v2 form ``c-<hash8>-<provider>-<genome16>`` is still accepted by ``journal.v2.json`` so a
#: journal written before the amendment validates, and is never written again; ``RE_CLAIM_ID_V2`` names it
#: for the one reader that must still recognise it.
RE_CLAIM_ID = re.compile(rf"^c-[0-9a-f]{{8}}-({_KIND_ALT})-({_PROVIDER_ALT})-h[0-9]{{1,5}}-[0-9a-f]{{16}}$")
RE_CLAIM_ID_V2 = re.compile(rf"^c-[0-9a-f]{{8}}-({_PROVIDER_ALT})-[0-9a-f]{{16}}$")
RE_NEWS_ID = re.compile(r"^(wce|wasof|wb|gd|mfc|edg|fred|cboe)-[0-9]{8}-[0-9]{4}$")
RE_VENDOR = re.compile(rf"^({'|'.join(VENDORS)})$")
RE_KIND = re.compile(rf"^({_KIND_ALT})$")
#: A session calendar id (section 17.8); ``continuous`` matches and is the one id never read from a file.
RE_CALENDAR_ID = re.compile(r"^[a-z][a-z0-9_]{0,31}$")
RE_CASH_EVENT_ID = re.compile(r"^ce-[0-9a-f]{16}$")
#: A ``HorizonBucket.bucket`` string: one of the four binary buckets or the ``h<bars>`` of section 17.5
#: (ruling R188). ``HORIZON_BUCKETS`` stays the four binary strings, because horizons are per-run config.
RE_HORIZON_BUCKET = re.compile(r"^(30d|7d|2d|0d|h[0-9]{1,5})$")
RE_ORDER_ID = re.compile(r"^o-[0-9]{8}$")
RE_HIVE_ENTRY_ID = re.compile(r"^h-[0-9]{8}$")
RE_LEXICON_ID = re.compile(r"^[a-z]+\.v[0-9]+$")
RE_FEE_SCHEDULE_ID = re.compile(r"^([a-z]+-[a-z0-9]+-[0-9]{4}-[0-9]{2}|demo-zero)$")
RE_LIVE_FORECAST_ID = re.compile(
    rf"^lf-[0-9]{{8}}-[a-z][a-z0-9_]{{0,31}}(-[0-9a-f]{{8}})?-({_PROVIDER_ALT})-[A-Za-z0-9._-]{{1,96}}$"
)
RE_TAG = re.compile(r"^[a-z0-9_-]{1,32}$")
RE_ISO_DATE = re.compile(r"^([0-9]{4})-([0-9]{2})-([0-9]{2})$")
RE_SHA256 = re.compile(r"^[0-9a-f]{64}$")

# --------------------------------------------------------------------------------------------------
# 6.2 and 8.1 Caps a config may not exceed, and the seed space
# --------------------------------------------------------------------------------------------------
#: ``SEED_SPACE`` is imported from ``pmx.rng`` at the head of this module (ruling R86); seeds are
#: persisted in sqlite BigInteger columns, and one spelling of the range is the whole point.
BARS_WINDOW_MAX = 720
TRADES_WINDOW_MAX = 1_000
NEWS_PER_MARKET_MAX = 50
NEWS_GLOBAL_MAX = 200
HIVE_LESSONS_MAX = 50
HIVE_FORECASTS_MAX = 2_000
MARKETS_PER_OBS_MAX = 200
NOTES_MAX_CHARS = 500
LESSON_MAX_CHARS = 300
LESSONS_PER_BAR_MAX = 5
RATIONALE_MAX_CHARS = 2_000
TTL_BARS_MAX = 90
#: 8 MiB of canonical JSON. The observation builder raises rather than truncating silently: a silent
#: truncation would give two agents different worlds for the same bar (section 8.1).
OBSERVATION_MAX_BYTES = 8_388_608
#: A research request costs units from a per-agent per-run budget; E1 grants and E5 journals the same table.
RESEARCH_UNIT_COST = {"news": 1, "history": 2, "wiki_asof": 3}
RESEARCH_PENALTY_UNITS = 5
#: A link below this score is not stored as a link at all (section 7.6).
LINK_THRESHOLD_PERMILLE = 150
#: What a market's tape is made of, which decides which quality filter of 7.4 it can answer.
#: ``prints`` is a per-trade tape and answers ``n_trades``; ``bars_only`` is a tape whose size arrives
#: per bar and nowhere else, so its ``n_trades`` is ``0`` however much it traded and ``traded_bars`` is
#: the only honest count of activity it can offer. Kalshi settled markets are the real case: the
#: exchange publishes per-bar volume and open interest and keeps no settled print tape at all.
TAPE_KIND_PRINTS = "prints"
TAPE_KIND_BARS_ONLY = "bars_only"
TAPE_KINDS = (TAPE_KIND_BARS_ONLY, TAPE_KIND_PRINTS)
#: The two provenance flags a market's ``wiki_subjects`` entry can carry. ``stated`` is a subject the
#: provider itself published (a Wikipedia link in a Manifold description, a curated series map entry);
#: ``derived`` is one this repository computed from the question or the title. The distinction is what
#: keeps the ``wikipedia_asof`` schedule on the subject a human would have chosen when there is one.
SUBJECT_STATED = "stated"
SUBJECT_DERIVED = "derived"
SUBJECT_PROVENANCES = (SUBJECT_DERIVED, SUBJECT_STATED)
#: The MAP-Elites grid: 4 turnover bins x 4 contrarian bins x 3 abstention bins (section 12.5).
ARCHIVE_CELLS = 48
#: A claim needs this many sealed-fold markets, and this many *traded* markets for its PnL part (12.6).
CLAIM_MIN_MARKETS = 60

# --------------------------------------------------------------------------------------------------
# 4.2 File conventions. Reading passes the same two, and a line carrying a carriage return is rejected
# rather than normalised: the development platform is Windows, where the default text mode would leave
# the in-memory hash right and the bytes on disk wrong.
# --------------------------------------------------------------------------------------------------
#: ``pmx.journal`` imports and re-exports both (ruling R86). Section 14 lists them against D7, but
#: ``pmx.data.schema`` and ``pmx.data.loader`` sit *below* the journal in the import order and cannot
#: reach it, so the definition lives in the lowest layer that everyone can import.
JOURNAL_ENCODING = "utf-8"
JOURNAL_NEWLINE = "\n"


# --------------------------------------------------------------------------------------------------
# 1.2 Conversions. Every one is integer; ``round()`` (banker's rounding) is banned everywhere, and ``//``
# on a signed ratio is banned because it rounds toward minus infinity and overstates every loss.
# --------------------------------------------------------------------------------------------------
def ppm_from_bp(price_bp: int) -> int:
    """A price in basis points as a probability in parts per million."""
    return price_bp * 100


def bp_from_ppm(prob_ppm: int) -> int:
    """A probability in ppm as a tradable price, clamped: a tradable price is never 0 and never 1."""
    return clamp_price_bp(prob_ppm // 100)


def clamp_price_bp(bp: int) -> int:
    return max(PRICE_MIN_BP, min(PRICE_MAX_BP, bp))


def clamp_ppm(ppm: int) -> int:
    return max(0, min(PPM_ONE, ppm))


def bp_from_v1_cents(cents: int) -> int:
    """v1 stored the YES price in whole cents; v2 stores basis points. Migration only (section 7.10)."""
    return cents * 100


def brier_micro(prob_ppm: int, outcome: int) -> int:
    """The Brier score of one forecast in micro-units: ``(p - y)^2`` scaled by ``PPM_ONE``.

    It truncates by at most one micro-unit, and the numerator fits in 64 bits with room to spare.
    """
    delta = prob_ppm - outcome * PPM_ONE
    return (delta * delta) // PPM_ONE


def cost_cents(size: int, price_bp: int) -> int:
    """What a buyer pays for ``size`` contracts at ``price_bp``, rounded **up** (against the buyer)."""
    return -((-size * price_bp) // CENTS_PER_UNIT)


def proceeds_cents(size: int, price_bp: int) -> int:
    """What a seller receives for ``size`` contracts at ``price_bp``, rounded **down** (against the
    seller). With ``cost_cents`` this is why the engine never creates a cent by rounding."""
    return (size * price_bp) // CENTS_PER_UNIT


def round_half_up(numerator: int, denominator: int) -> int:
    """Half up, for a non-negative quantity. The caller returns 0 rather than passing a zero denominator."""
    if denominator <= 0:
        raise ValueError("round_half_up needs a positive denominator; return 0 before calling it")
    return (2 * numerator + denominator) // (2 * denominator)


def round_half_up_decimal(value: Decimal) -> int:
    """Half up over a provider's decimal string. Never a float: Manifold's ``probAfter`` is text, and
    reading it as a float would make the same tape hash differently on two machines (section 7.2)."""
    return int(value.to_integral_value(rounding=ROUND_HALF_UP))


def bp_ratio(numerator: int, denominator: int) -> int:
    """A signed ratio in basis points, half away from zero, so a loss and the mirror gain report the
    same magnitude."""
    if denominator == 0:
        raise ValueError("bp_ratio needs a non-zero denominator; return 0 before calling it")
    scaled = numerator * BP_ONE
    quotient, remainder = divmod(abs(scaled), abs(denominator))
    quotient += 1 if 2 * remainder >= abs(denominator) else 0
    negative = (scaled < 0) != (denominator < 0)
    return -quotient if negative else quotient


def milli_ratio(numerator: int, denominator: int) -> int:
    """``bp_ratio`` in milli-units: the Sharpe-like ratios of section 12.3."""
    if denominator == 0:
        raise ValueError("milli_ratio needs a non-zero denominator; return 0 before calling it")
    scaled = numerator * 1_000
    quotient, remainder = divmod(abs(scaled), abs(denominator))
    quotient += 1 if 2 * remainder >= abs(denominator) else 0
    negative = (scaled < 0) != (denominator < 0)
    return -quotient if negative else quotient


def neg_ln_micronats(prob_ppm: int) -> int:
    """``-ln(p)`` in micro-nats for a probability already clamped to ``[1 percent, 99 percent]``.

    ``math.log`` reaches the platform libm and is not bit identical across glibc, msvcrt and macOS, so it
    never touches a score. ``Decimal.ln`` is correctly rounded by the decimal specification, so this
    result is the same integer on every platform (section 1.3).
    """
    with localcontext() as ctx:
        ctx.prec = 40
        value = -(Decimal(prob_ppm) / Decimal(PPM_ONE)).ln() * Decimal(PPM_ONE)
        return int(value.to_integral_value(rounding=ROUND_HALF_UP))


# --------------------------------------------------------------------------------------------------
# 17.1 The price model: three integers and one exact product, divided once, rounded against the agent
# (rulings R145 to R147). ``cost_cents(size, p) == cash_out_cents(size * MILLI, p, 100, 1_000_000)`` for
# every legal binary size and price, which is the property that lets a bp price keep its value.
# --------------------------------------------------------------------------------------------------
def _ceil_div(numerator: int, denominator: int) -> int:
    """``ceil(numerator / denominator)`` in integers, for a positive denominator: "round up, against
    the agent" spelled once rather than as four sign puzzles."""
    return -((-numerator) // denominator)


def notional_micro(size_milli: int, price_ticks: int, tick_size_micro: int, point_value_micro: int) -> int:
    """The exact four-factor product of section 17.1. Never stored, never rounded: at the caps it reaches
    ``10 ** 45``, which is why the contract says "exact" and not "64-bit"."""
    return size_milli * price_ticks * tick_size_micro * point_value_micro


def cash_out_cents(size_milli: int, price_ticks: int, tick_size_micro: int, point_value_micro: int) -> int:
    """What the agent pays: the notional divided once, rounded **up** (against the agent)."""
    product = notional_micro(size_milli, price_ticks, tick_size_micro, point_value_micro)
    return _ceil_div(product, NOTIONAL_DENOMINATOR)


def cash_in_cents(size_milli: int, price_ticks: int, tick_size_micro: int, point_value_micro: int) -> int:
    """What the agent receives: the notional divided once, rounded **down** (against the agent)."""
    return notional_micro(size_milli, price_ticks, tick_size_micro, point_value_micro) // NOTIONAL_DENOMINATOR


def mark_value_cents(position_milli: int, mark_ticks: int, tick_size_micro: int, point_value_micro: int) -> int:
    """The signed marked value of a position: ``floor`` for a long, ``-ceil`` of the liability for a short.

    The conservative side in both directions (ruling R146), which is why ``positions_value_cents`` is
    signed and why a short that has run away can take equity below zero (ruling R154).
    """
    product = notional_micro(abs(position_milli), mark_ticks, tick_size_micro, point_value_micro)
    if position_milli >= 0:
        return product // NOTIONAL_DENOMINATOR
    return -_ceil_div(product, NOTIONAL_DENOMINATOR)


def price_micro(price_ticks: int, tick_size_micro: int) -> int:
    """The price in micro quote units (section 17.1)."""
    return price_ticks * tick_size_micro


def split_position_milli(position_milli: int, numerator: int, denominator: int) -> int:
    """The position a split leaves (17.3, ruling R153): ``sign(q) * round_half_up(abs(q) * numerator,
    denominator)``. The rounding is at most half a milli-unit and is stated here so that nobody "fixes"
    it into cash in lieu, which this engine does not model."""
    if numerator < 1 or denominator < 1:
        raise InvalidConfigError(
            "a split ratio is two positive integers", numerator=numerator, denominator=denominator
        )
    magnitude = round_half_up(abs(position_milli) * numerator, denominator)
    return magnitude if position_milli >= 0 else -magnitude


def default_horizons_bars(interval_min: int) -> tuple[int, ...]:
    """Section 17.5's default horizons in bars of the instrument's own sequence (ruling R188).

    One bar, one day and one week, duplicates removed and ascending: ``(1, 7)`` on a daily grid,
    ``(1, 24, 168)`` on an hourly one. ``RunConfig`` resolves an empty ``horizons_bars`` to this before
    hashing, so a config that spells the default and one that omits it are one run.
    """
    span = interval_ms(interval_min)
    return tuple(sorted({1, max(1, MS_PER_DAY // span), max(1, 7 * MS_PER_DAY // span)}))


def cash_event_id(market_id: str, kind: str, t_ms: int, detail: Mapping[str, int | str]) -> str:
    """``"ce-" + sha256(canonical_json([market_id, kind, t_ms, detail]))[:16]`` (section 17.8).

    The one spelling for an importer's data event and for the engine's own (ruling R176: an engine event
    hashes the last instant of the bar it applies at). ``canonical_sha256`` belongs to ``pmx.journal`` and
    is imported inside the function for the reason ``market_set_hash`` does.
    """
    from pmx.journal import canonical_sha256

    return "ce-" + canonical_sha256([market_id, kind, t_ms, dict(detail)])[:16]


# --------------------------------------------------------------------------------------------------
# 5.1 and 5.2 The bar grid and the one date parser
# --------------------------------------------------------------------------------------------------
def interval_ms(interval_min: int) -> int:
    return interval_min * MS_PER_MINUTE


def bar_of(t_ms: int, interval_min: int) -> int:
    """The open time of the bar containing ``t_ms``. A bar covers ``[t_ms, t_ms + interval_ms)``."""
    step = interval_ms(interval_min)
    return (t_ms // step) * step


def day_start_ms(t_ms: int) -> int:
    return (t_ms // MS_PER_DAY) * MS_PER_DAY


_EPOCH_ORDINAL = date(1970, 1, 1).toordinal()


def ms_from_iso_date(text: str) -> int:
    """``yyyy-mm-dd`` at 00:00:00Z, as an integer, without touching a clock or a float.

    The engine never parses a date string; the data layer does, here and only here, for the three fields
    that are dates by contract (``freeze_date``, ``asof_day``, ``as_of_date``) (section 5.1).
    """
    match = RE_ISO_DATE.fullmatch(text)
    if match is None:
        raise SchemaError("not an ISO date (yyyy-mm-dd)", value=text)
    year, month, day = (int(part) for part in match.groups())
    try:
        ordinal = date(year, month, day).toordinal()
    except ValueError as exc:  # 2016-02-30 and friends
        raise SchemaError("not a calendar date", value=text) from exc
    return (ordinal - _EPOCH_ORDINAL) * MS_PER_DAY


def iso_date_from_ms(t_ms: int) -> str:
    """The ``yyyy-mm-dd`` of the UTC day containing ``t_ms``: the convenience spelling that sits beside
    the integer in a manifest and in the UI, never the one the engine reads."""
    return date.fromordinal(t_ms // MS_PER_DAY + _EPOCH_ORDINAL).isoformat()


def day_key(t_ms: int) -> str:
    """``yyyymmdd``, the day key of a news file (section 7.1)."""
    return iso_date_from_ms(t_ms).replace("-", "")


# --------------------------------------------------------------------------------------------------
# 3 Canonical ordering. These helpers are the only spelling: iterating a set, or a dict built from one,
# is forbidden wherever the order can reach an event, a fill, a score or a file.
# --------------------------------------------------------------------------------------------------
def sorted_market_ids(market_ids: Iterable[str]) -> tuple[str, ...]:
    """Market ids ascending by code point, deduplicated."""
    return tuple(sorted(set(market_ids)))


def sorted_agent_ids(agent_ids: Iterable[str]) -> tuple[str, ...]:
    """Agent ids ascending by code point, deduplicated."""
    return tuple(sorted(set(agent_ids)))


def sort_markets(markets: Sequence[Market]) -> tuple[Market, ...]:
    """Markets of a dataset or a run: ``(resolved_at_ms, id)`` ascending."""
    return tuple(sorted(markets, key=lambda m: (m.resolved_at_ms, m.id)))


def sort_market_metas(metas: Sequence[MarketMeta]) -> tuple[MarketMeta, ...]:
    """The same order over the leak-free projection."""
    return tuple(sorted(metas, key=lambda m: (m.resolved_at_ms, m.id)))


def news_rank_key(*, match_score_permille: int, published_at_ms: int, news_id: str) -> tuple[int, int, str]:
    """The one news order of section 3: best link first, then oldest, then id.

    Ruling R87 gives that order a single arithmetic and two typed entry points, because the two shapes a
    news item takes in this codebase carry the score differently and neither can be made to satisfy the
    other: a ``NewsItem`` of the dataset holds one score per linked market (``match_scores_permille``),
    while the ``NewsView`` an agent sees holds the scalar ``match_score_permille`` section 3 names. The
    key ends in ``news_id``, so the order is total and two calls agree.
    """
    return (-match_score_permille, published_at_ms, news_id)


def rank_news(views: Sequence[NewsView]) -> tuple[NewsView, ...]:
    """A digest's order over the views an agent is handed (sections 3 and 8.3).

    This is the spelling section 3 names, over the scalar ``match_score_permille`` of ``NewsView``; the
    projection into views has already resolved which market a score belongs to.
    """
    return tuple(
        sorted(
            views,
            key=lambda view: news_rank_key(
                match_score_permille=view.match_score_permille,
                published_at_ms=view.published_at_ms,
                news_id=view.news_id,
            ),
        )
    )


def rank_news_items(items: Sequence[NewsItem], *, market_id: str | None = None) -> tuple[NewsItem, ...]:
    """The same order over dataset ``NewsItem`` objects (ruling R87).

    ``market_id`` is what a per-market digest ranks by, because a ``NewsItem`` carries one score per linked
    market and a rank only exists relative to a market (``NewsItem.score_for``); without it the item's best
    link is used, which is what a global digest needs. E1 ranks the items with this function and then
    projects the survivors into ``NewsView``, so the digest an agent receives is already in the order
    :func:`rank_news` would put it in.
    """

    def key(item: NewsItem) -> tuple[int, int, str]:
        if market_id is None:
            score = max(item.match_scores_permille) if item.match_scores_permille else 0
        else:
            score = item.score_for(market_id)
        return news_rank_key(
            match_score_permille=score,
            published_at_ms=item.published_at_ms,
            news_id=item.news_id,
        )

    return tuple(sorted(items, key=key))


def sha256_hex(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def market_set_hash(market_ids: Iterable[str]) -> str:
    """``sha256(canonical_json(sorted market ids))``: what ``RunConfig.market_ids_hash`` carries.

    The name differs from the field so nothing shadows anything (section 8.1). ``canonical_sha256`` is
    the one spelling of "SHA-256 over canonical bytes" (section 4.3, ruling R88) and is imported inside the
    function because it belongs to ``pmx.journal`` (section 4.1, D7): importing it at module level would
    make ``pmx.types`` un-importable from the journal itself.
    """
    from pmx.journal import canonical_sha256

    return canonical_sha256(list(sorted_market_ids(market_ids)))


# --------------------------------------------------------------------------------------------------
# 7.2 The market and its tape
# --------------------------------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class Bar:
    """One bar of a market's tape, identified by its **open** time, covering ``[t_ms, t_ms + interval)``.

    A bar with no trade repeats the previous close as ``open == high == low == close == vwap`` with a
    zero volume, so the grid is dense and ``bar_at`` is always defined for a listed market (section 5.2).
    """

    t_ms: int
    open_bp: int
    high_bp: int
    low_bp: int
    close_bp: int
    vwap_bp: int
    volume_milli: int
    n_trades: int
    yes_bid_bp: int | None
    yes_ask_bp: int | None
    open_interest: int | None

    def to_dict(self) -> dict[str, object]:
        return {
            "t_ms": self.t_ms,
            "open_bp": self.open_bp,
            "high_bp": self.high_bp,
            "low_bp": self.low_bp,
            "close_bp": self.close_bp,
            "vwap_bp": self.vwap_bp,
            "volume_milli": self.volume_milli,
            "n_trades": self.n_trades,
            "yes_bid_bp": self.yes_bid_bp,
            "yes_ask_bp": self.yes_ask_bp,
            "open_interest": self.open_interest,
        }


@dataclass(frozen=True, slots=True)
class Trade:
    """One print: the taker's side, the price it printed at, and its size in thousandths."""

    t_ms: int
    price_bp: int
    size_milli: int
    side: str

    def to_dict(self) -> dict[str, object]:
        return {
            "t_ms": self.t_ms,
            "price_bp": self.price_bp,
            "size_milli": self.size_milli,
            "side": self.side,
        }


def _bar_at(bars: Sequence[Bar], t_ms: int, interval_min: int) -> Bar | None:
    """The one implementation of ``Instrument.bar_at`` (7.2, ruling R173), shared by every kind.

    The index is arithmetic because a dataset's bars are dense on the grid; the bisection fallback is for
    a session instrument, whose bars are dense on its calendar and not on the grid, and for a market an
    importer built and the builder has not resampled yet.
    """
    if not bars:
        return None
    target = bar_of(t_ms, interval_min)
    index = (target - bars[0].t_ms) // interval_ms(interval_min)
    if 0 <= index < len(bars) and bars[index].t_ms == target:
        return bars[index]
    lo, hi = 0, len(bars)
    while lo < hi:
        mid = (lo + hi) // 2
        if bars[mid].t_ms < target:
            lo = mid + 1
        else:
            hi = mid
    if lo < len(bars) and bars[lo].t_ms == target:
        return bars[lo]
    return None


def _bars_before(bars: Sequence[Bar], now_ms: int, limit: int, interval_min: int) -> tuple[Bar, ...]:
    """The one implementation of ``Instrument.bars_before`` (5.4): the last ``limit`` bars with
    ``b.t_ms + interval_ms <= now_ms``, oldest first, ``()`` when none is completed."""
    if limit <= 0:
        return ()
    span = interval_ms(interval_min)
    lo, hi = 0, len(bars)
    while lo < hi:
        mid = (lo + hi) // 2
        if bars[mid].t_ms + span <= now_ms:
            lo = mid + 1
        else:
            hi = mid
    return tuple(bars[max(0, lo - limit) : lo])


@dataclass(frozen=True, slots=True)
class MarketQuality:
    """What the quality filters of section 7.4 read. Never shown to an agent (section 7.9)."""

    n_trades: int
    unique_bettors: int | None
    life_days: int
    volume_milli_total: int
    traded_bars: int
    #: ``prints`` or ``bars_only`` (:data:`TAPE_KINDS`). It says which of the two activity counts above
    #: is a fact about this market and which is a zero the provider forced: a ``bars_only`` market has
    #: ``n_trades == 0`` because no settled print tape is published, not because nobody traded, so the
    #: ``min_trades`` filter of 7.4 reads ``traded_bars`` for it instead. The default is ``prints``,
    #: which is what every provider with a print tape has always meant.
    tape_kind: str = TAPE_KIND_PRINTS

    def __post_init__(self) -> None:
        if self.tape_kind not in TAPE_KINDS:
            raise InvalidConfigError("unknown tape_kind", tape_kind=self.tape_kind)

    def to_dict(self) -> dict[str, object]:
        """The ``market.v2`` ``quality`` block.

        ``tape_kind`` is written only when it is **not** ``prints``. The flag marks the exception, which
        is the tape that publishes no print at all, and its absence is defined by the schema as the
        ordinary case; so a market file whose venue has a print tape keeps exactly the bytes it had
        before the flag existed, and no dataset hash moves for a fact that did not change.
        """
        block: dict[str, object] = {
            "n_trades": self.n_trades,
            "unique_bettors": self.unique_bettors,
            "life_days": self.life_days,
            "volume_milli_total": self.volume_milli_total,
            "traded_bars": self.traded_bars,
        }
        if self.tape_kind != TAPE_KIND_PRINTS:
            block["tape_kind"] = self.tape_kind
        return block


@dataclass(frozen=True, slots=True)
class Market:
    """One resolved binary market with its full tape (section 7.2).

    ``final_price_bp`` is the close of the last bar of the tape, next to settlement. It is never shown to
    an agent and it is deliberately **not** called ``last_price_bp``: that name belongs to the as-of
    ``MarketView`` of the bar being decided, and one name for both was a leak with money attached.
    """

    schema_version: str
    id: str
    provider: str
    provider_id: str
    url: str
    question: str
    description: str
    category: str
    tags: tuple[str, ...]
    wiki_subjects: tuple[str, ...]
    currency: str
    source: str
    created_at_ms: int
    close_at_ms: int
    resolved_at_ms: int
    resolution: int
    resolution_source: str
    event_key: str | None
    interval_min: int
    bars: tuple[Bar, ...]
    trades: tuple[Trade, ...]
    first_price_bp: int
    final_price_bp: int
    hardness_tags: tuple[str, ...]
    quality: MarketQuality
    fee_schedule_id: str
    notes: str
    #: One flag per entry of ``wiki_subjects``, in the same order: ``stated`` for a subject the provider
    #: published and ``derived`` for one this repository computed from the question or the title
    #: (:data:`SUBJECT_PROVENANCES`). It is a parallel list for the reason ``match_scores_permille`` is
    #: one beside ``match_ids``: the subjects themselves are compared verbatim against an item's
    #: ``wiki_links`` (section 7.6) and must stay exactly the article titles. An empty list beside a
    #: non-empty ``wiki_subjects`` reads as "every subject is stated", which is what every market written
    #: before the flag existed meant.
    wiki_subject_provenance: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        """Freeze the six sequence fields into tuples and default the subject provenance.

        The declared type is a tuple, because a market is a hashable immutable record and half the engine
        slices its bars. An importer that hands a list gets it frozen here rather than silently carrying a
        mutable tape into a run whose journal must hash the same twice.
        """
        for name in ("tags", "wiki_subjects", "bars", "trades", "hardness_tags", "wiki_subject_provenance"):
            value = getattr(self, name)
            if not isinstance(value, tuple):
                object.__setattr__(self, name, tuple(value))
        if not self.wiki_subject_provenance and self.wiki_subjects:
            object.__setattr__(
                self, "wiki_subject_provenance", (SUBJECT_STATED,) * len(self.wiki_subjects)
            )
        if len(self.wiki_subject_provenance) != len(self.wiki_subjects):
            raise InvalidConfigError(
                "wiki_subject_provenance must carry one flag per wiki_subject",
                market_id=self.id,
                n_subjects=len(self.wiki_subjects),
                n_flags=len(self.wiki_subject_provenance),
            )
        unknown = [flag for flag in self.wiki_subject_provenance if flag not in SUBJECT_PROVENANCES]
        if unknown:
            raise InvalidConfigError(
                "unknown wiki subject provenance", market_id=self.id, provenance=unknown
            )

    @property
    def interval_ms(self) -> int:
        return interval_ms(self.interval_min)

    @property
    def kind(self) -> str:
        """A ``Market`` is the binary instrument (section 17.1, ruling R144)."""
        return INSTRUMENT_KINDS[0]

    @property
    def instrument(self) -> Instrument:
        """The ``Instrument`` base as a **view** of this market (17.1, ruling R144).

        Nothing moves out of ``Market``: the mapping is the table of section 17.1 (``kind = "binary"``,
        ``vendor = provider``, ``symbol = provider_id``, ``tick_size_micro = 100``, ``point_value_micro =
        1_000_000``, ``session_calendar_id = "continuous"``, no borrow or carry schedule, ``listed_at_ms =
        created_at_ms``, ``delisted_at_ms = resolved_at_ms``, ``short_allowed = True`` for the NO leg), and
        no code path reads ``tick_size_micro`` off a ``Market`` field that does not exist. The bars and
        trades are the same tuples, so the view costs one small object.
        """
        return Instrument(
            id=self.id,
            provider=self.provider,
            vendor=self.provider,
            symbol=self.provider_id,
            kind=INSTRUMENT_KINDS[0],
            currency=self.currency,
            tick_size_micro=BINARY_TICK_SIZE_MICRO,
            point_value_micro=BINARY_POINT_VALUE_MICRO,
            session_calendar_id=CONTINUOUS_CALENDAR_ID,
            fee_schedule_id=self.fee_schedule_id,
            borrow_schedule_id=None,
            carry_schedule_id=None,
            listed_at_ms=self.created_at_ms,
            delisted_at_ms=self.resolved_at_ms,
            short_allowed=True,
            interval_min=self.interval_min,
            bars=self.bars,
            trades=self.trades,
        )

    def bar_at(self, t_ms: int) -> Bar | None:
        """The bar whose ``t_ms`` equals ``bar_of(t_ms, self.interval_min)``, or ``None`` when the market
        is not listed at that instant.

        The index is arithmetic because a dataset's bars are dense on the grid; the linear fallback is
        for a market an importer built and the builder has not resampled yet.
        """
        return _bar_at(self.bars, t_ms, self.interval_min)

    def bars_before(self, now_ms: int, limit: int) -> tuple[Bar, ...]:
        """The last ``limit`` **completed** bars at ``now_ms``, oldest first, ``()`` when none is complete.

        A bar is completed when ``b.t_ms + interval_ms <= now_ms``: an agent deciding at the open of bar
        ``t`` has never seen bar ``t`` (section 5.4).
        """
        return _bars_before(self.bars, now_ms, limit, self.interval_min)

    def to_dict(self) -> dict[str, object]:
        """The ``market.v2.json`` shape, exactly: what ``markets/<id>.json`` holds.

        ``wiki_subject_provenance`` is written only when at least one subject is ``derived``, for the
        reason ``quality.tape_kind`` is written only when the tape is not made of prints: the list marks
        what a reader would otherwise assume wrongly, and a market whose every subject the provider
        itself stated keeps the bytes it had before the flag existed.
        """
        document: dict[str, object] = {
            "schema_version": self.schema_version,
            "id": self.id,
            "provider": self.provider,
            "provider_id": self.provider_id,
            "url": self.url,
            "question": self.question,
            "description": self.description,
            "category": self.category,
            "tags": list(self.tags),
            "wiki_subjects": list(self.wiki_subjects),
            "currency": self.currency,
            "source": self.source,
            "created_at_ms": self.created_at_ms,
            "close_at_ms": self.close_at_ms,
            "resolved_at_ms": self.resolved_at_ms,
            "resolution": self.resolution,
            "resolution_source": self.resolution_source,
            "event_key": self.event_key,
            "interval_min": self.interval_min,
            "bars": [bar.to_dict() for bar in self.bars],
            "trades": [trade.to_dict() for trade in self.trades],
            "first_price_bp": self.first_price_bp,
            "final_price_bp": self.final_price_bp,
            "hardness_tags": list(self.hardness_tags),
            "quality": self.quality.to_dict(),
            "fee_schedule_id": self.fee_schedule_id,
            "notes": self.notes,
        }
        if any(flag == SUBJECT_DERIVED for flag in self.wiki_subject_provenance):
            document["wiki_subject_provenance"] = list(self.wiki_subject_provenance)
        return document


# --------------------------------------------------------------------------------------------------
# 17.1 to 17.3 The instrument base, the continuous instrument, the session calendar and the cash event
# (amendment C1b, landed by gate G2). ``Market`` is the binary instrument and reaches the base through
# ``Market.instrument``; a continuous instrument **is** an ``Instrument`` and its ``instrument`` view is
# itself, so every consumer reads one shape through one name.
# --------------------------------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class Session:
    """One trading session of a sealed calendar, ``[open_ms, close_ms)`` (section 17.2)."""

    open_ms: int
    close_ms: int

    def to_dict(self) -> dict[str, object]:
        return {"open_ms": self.open_ms, "close_ms": self.close_ms}


@dataclass(frozen=True, slots=True)
class SessionCalendar:
    """A **dated** session calendar (``session_calendar.v1.json``, section 17.2, ruling R149).

    Explicit sessions for the window rather than a weekly template, because daylight saving makes a UTC
    template wrong for half the year. The ``sessions`` list is the normative object; ``holidays`` is
    informative. ``in_session``, ``next_bar_ms`` and the generator live in ``pmx.data.sessions`` (D1,
    ruling R174), the one implementation of session membership (architecture rule 11).
    """

    calendar_id: str
    description: str
    source_url: str
    as_of_date: str
    window: DatasetWindow
    sessions: tuple[Session, ...]
    holidays: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if RE_CALENDAR_ID.fullmatch(self.calendar_id) is None:
            raise InvalidConfigError("calendar id is not section 17.8's format", calendar_id=self.calendar_id)
        if not isinstance(self.sessions, tuple):
            object.__setattr__(self, "sessions", tuple(self.sessions))
        if not isinstance(self.holidays, tuple):
            object.__setattr__(self, "holidays", tuple(self.holidays))
        previous_close: int | None = None
        for session in self.sessions:
            if session.open_ms >= session.close_ms:
                raise InvalidConfigError("a session opens before it closes", calendar_id=self.calendar_id)
            if previous_close is not None and session.open_ms < previous_close:
                raise InvalidConfigError(
                    "sessions must be sorted by open_ms and non-overlapping", calendar_id=self.calendar_id
                )
            previous_close = session.close_ms

    @property
    def is_continuous(self) -> bool:
        """The synthesised ``continuous`` calendar (ruling R185): one session covering everything."""
        return self.calendar_id == CONTINUOUS_CALENDAR_ID

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": "session_calendar.v1",
            "calendar_id": self.calendar_id,
            "description": self.description,
            "source_url": self.source_url,
            "as_of_date": self.as_of_date,
            "window": self.window.to_dict(),
            "sessions": [session.to_dict() for session in self.sessions],
            "holidays": list(self.holidays),
        }


def continuous_calendar() -> SessionCalendar:
    """The ``continuous`` calendar of ruling R185: one session ``[0, INT63_MAX)``, synthesised and never a
    file. It is the calendar of every binary and every crypto instrument, and it reduces every session
    rule of 17.2 to 7.2's dense grid."""
    return SessionCalendar(
        calendar_id=CONTINUOUS_CALENDAR_ID,
        description="Synthesised: trades around the clock (CONTRACTS_V2 17.2, ruling R185).",
        source_url="",
        as_of_date="1970-01-01",
        window=DatasetWindow(start_ms=0, end_ms=INT63_MAX),
        sessions=(Session(open_ms=0, close_ms=INT63_MAX),),
        holidays=(),
    )


@dataclass(frozen=True, slots=True)
class CashEvent:
    """One dated cash flow that is not a fill (section 17.3, ruling R151), applied by execution in the
    settle phase and journaled once as ``cash_event_applied``.

    ``t_ms`` is the venue's instant: the open of the first bar priced in the new regime for a dividend, a
    split and a roll (ruling R175), the funding time for a funding, and the last instant of the applying
    bar for an engine event (ruling R176). ``origin`` is ``data`` for the first four kinds of
    ``CASH_EVENT_KINDS`` and ``engine`` for ``borrow_fee``, ``carry`` and ``forced_flat`` (ruling R177).
    """

    cash_event_id: str
    market_id: str
    kind: str
    t_ms: int
    origin: str
    source_url: str
    detail: Mapping[str, int | str]

    def __post_init__(self) -> None:
        if self.kind not in CASH_EVENT_KINDS:
            raise InvalidConfigError("unknown cash event kind", kind=self.kind, market_id=self.market_id)
        if self.origin not in CASH_EVENT_ORIGINS:
            raise InvalidConfigError("unknown cash event origin", origin=self.origin, market_id=self.market_id)
        expected = "data" if self.kind in DATA_CASH_EVENT_KINDS else "engine"
        if self.origin != expected:
            raise InvalidConfigError(
                "a cash event's origin follows its kind (ruling R177)",
                kind=self.kind,
                origin=self.origin,
                expected=expected,
            )
        if not isinstance(self.detail, dict):
            object.__setattr__(self, "detail", dict(self.detail))

    @classmethod
    def build(
        cls, *, market_id: str, kind: str, t_ms: int, detail: Mapping[str, int | str], source_url: str = ""
    ) -> CashEvent:
        """A cash event with the contract's id, hashing exactly ``[market_id, kind, t_ms, detail]``."""
        origin = "data" if kind in DATA_CASH_EVENT_KINDS else "engine"
        return cls(
            cash_event_id=cash_event_id(market_id, kind, t_ms, detail),
            market_id=market_id,
            kind=kind,
            t_ms=t_ms,
            origin=origin,
            source_url=source_url,
            detail=dict(detail),
        )

    def to_dict(self) -> dict[str, object]:
        """The ``cash_event.v1.json`` shape: what an instrument file's ``cash_events`` entry holds."""
        return {
            "schema_version": "cash_event.v1",
            "cash_event_id": self.cash_event_id,
            "market_id": self.market_id,
            "kind": self.kind,
            "t_ms": self.t_ms,
            "origin": self.origin,
            "source_url": self.source_url,
            "detail": {key: self.detail[key] for key in sorted(self.detail)},
        }


@dataclass(frozen=True, slots=True)
class Instrument:
    """The common base every kind satisfies (section 17.1, ruling R144).

    The field the events, views and signatures call ``market_id`` is ``id`` here for every kind: it is
    the id namespace, not a claim about the kind. ``bars`` and ``trades`` are the one in-memory ``Bar``
    and ``Trade`` for every kind (ruling R173): on a continuous instrument their ``_bp`` fields carry the
    instrument's ticks. ``bar_at`` and ``bars_before`` are declared here because the engine calls them by
    name on every kind.
    """

    id: str
    provider: str
    vendor: str
    symbol: str
    kind: str
    currency: str
    tick_size_micro: int
    point_value_micro: int
    session_calendar_id: str
    fee_schedule_id: str
    borrow_schedule_id: str | None
    carry_schedule_id: str | None
    listed_at_ms: int
    delisted_at_ms: int | None
    short_allowed: bool
    interval_min: int
    bars: tuple[Bar, ...]
    trades: tuple[Trade, ...]

    @property
    def interval_ms(self) -> int:
        return interval_ms(self.interval_min)

    @property
    def is_binary(self) -> bool:
        return self.kind == INSTRUMENT_KINDS[0]

    @property
    def instrument(self) -> Instrument:
        """The base view of an instrument is the instrument itself, so ``record.instrument`` is one
        spelling for a ``Market`` and a ``ContinuousInstrument`` alike."""
        return self

    def bar_at(self, t_ms: int) -> Bar | None:
        """The bar whose ``t_ms == bar_of(t_ms, interval_min)``, or ``None`` (7.2, ruling R173)."""
        return _bar_at(self.bars, t_ms, self.interval_min)

    def bars_before(self, now_ms: int, limit: int) -> tuple[Bar, ...]:
        """The last ``limit`` completed bars at ``now_ms``, oldest first (section 5.4)."""
        return _bars_before(self.bars, now_ms, limit, self.interval_min)


#: The categories a continuous instrument may carry (``instrument.v1.json``, section 17.1).
INSTRUMENT_CATEGORIES = ("crypto", "finance", "economics", "other")
ROLL_SOURCES = ("venue", "vendor")


@dataclass(frozen=True, slots=True)
class ContinuousInstrument(Instrument):
    """A continuous instrument (``instrument.v1.json``, ``instruments/<id>.json``): every kind but
    ``binary``, which is a ``Market`` and never one of these (section 17.1).

    It has no resolution: it is judged by its realised price path, and a position still open at its
    last bar is closed by the engine's forced flat (17.3). ``first_price_bp`` mirrors ``first_price_ticks``
    so that the one code path of ruling R148 (``_bp`` carries ticks) reads a first price off every kind.
    """

    schema_version: str
    url: str
    description: str
    category: str
    tags: tuple[str, ...]
    twins: tuple[str, ...]
    underlying_id: str | None
    roll_source: str | None
    first_price_ticks: int
    quality: MarketQuality
    cash_events: tuple[CashEvent, ...]
    source: str
    notes: str

    def __post_init__(self) -> None:
        """Freeze the sequence fields and refuse what the kind table of 17.1 forbids."""
        for name in ("tags", "twins", "bars", "trades", "cash_events"):
            value = getattr(self, name)
            if not isinstance(value, tuple):
                object.__setattr__(self, name, tuple(value))
        if self.kind not in CONTINUOUS_KINDS:
            raise InvalidConfigError("a continuous instrument is never a binary", market_id=self.id, kind=self.kind)
        if self.kind == "spot_crypto" and self.short_allowed:
            raise InvalidConfigError("spot_crypto has no short side: the short is the perp twin", market_id=self.id)
        if self.kind in ("perp", "fx", "future") and not self.short_allowed:
            raise InvalidConfigError("perp, fx and future are natively shortable", market_id=self.id, kind=self.kind)
        if self.kind == "equity" and self.short_allowed != (self.borrow_schedule_id is not None):
            raise InvalidConfigError(
                "an equity is shortable iff it names a borrow schedule (ruling R154)", market_id=self.id
            )
        if self.kind != "equity" and self.borrow_schedule_id is not None:
            raise InvalidConfigError("only an equity names a borrow schedule", market_id=self.id, kind=self.kind)
        if self.kind != "fx" and self.carry_schedule_id is not None:
            raise InvalidConfigError("only an fx instrument names a carry schedule", market_id=self.id)
        if (self.kind == "perp") != (self.underlying_id is not None):
            raise InvalidConfigError("exactly a perp names an underlying", market_id=self.id, kind=self.kind)
        if (self.kind == "future") != (self.roll_source is not None):
            raise InvalidConfigError("exactly a future has a roll source", market_id=self.id, kind=self.kind)

    @property
    def first_price_bp(self) -> int:
        return self.first_price_ticks

    @property
    def created_at_ms(self) -> int:
        """``listed_at_ms`` under the binary name, for the one reader of a listing instant (17.1)."""
        return self.listed_at_ms

    def clipped(self, end_ms: int) -> ContinuousInstrument:
        """The record with every bar, trade and cash event at or after ``end_ms`` removed (ruling R182).

        ``Dataset.market`` hands out a continuous instrument clipped at ``validation_end_ms``, so no
        consumer outside the claim path ever holds the sealed months of a price path; ``quality`` stays
        the whole-window statistic, because the filters of 7.4 need the whole life.
        """
        delisted = self.delisted_at_ms if self.delisted_at_ms is None or self.delisted_at_ms < end_ms else None
        return ContinuousInstrument(
            id=self.id,
            provider=self.provider,
            vendor=self.vendor,
            symbol=self.symbol,
            kind=self.kind,
            currency=self.currency,
            tick_size_micro=self.tick_size_micro,
            point_value_micro=self.point_value_micro,
            session_calendar_id=self.session_calendar_id,
            fee_schedule_id=self.fee_schedule_id,
            borrow_schedule_id=self.borrow_schedule_id,
            carry_schedule_id=self.carry_schedule_id,
            listed_at_ms=self.listed_at_ms,
            delisted_at_ms=delisted,
            short_allowed=self.short_allowed,
            interval_min=self.interval_min,
            bars=tuple(bar for bar in self.bars if bar.t_ms < end_ms),
            trades=tuple(trade for trade in self.trades if trade.t_ms < end_ms),
            schema_version=self.schema_version,
            url=self.url,
            description=self.description,
            category=self.category,
            tags=self.tags,
            twins=self.twins,
            underlying_id=self.underlying_id,
            roll_source=self.roll_source,
            first_price_ticks=self.first_price_ticks,
            quality=self.quality,
            cash_events=tuple(event for event in self.cash_events if event.t_ms < end_ms),
            source=self.source,
            notes=self.notes,
        )

    def to_dict(self) -> dict[str, object]:
        """The ``instrument.v1.json`` shape, exactly, with the ``_ticks`` spelling of the file (R173)."""
        return {
            "schema_version": self.schema_version,
            "id": self.id,
            "provider": self.provider,
            "vendor": self.vendor,
            "symbol": self.symbol,
            "kind": self.kind,
            "currency": self.currency,
            "tick_size_micro": self.tick_size_micro,
            "point_value_micro": self.point_value_micro,
            "session_calendar_id": self.session_calendar_id,
            "fee_schedule_id": self.fee_schedule_id,
            "borrow_schedule_id": self.borrow_schedule_id,
            "carry_schedule_id": self.carry_schedule_id,
            "listed_at_ms": self.listed_at_ms,
            "delisted_at_ms": self.delisted_at_ms,
            "short_allowed": self.short_allowed,
            "interval_min": self.interval_min,
            "url": self.url,
            "description": self.description,
            "category": self.category,
            "tags": list(self.tags),
            "twins": list(self.twins),
            "underlying_id": self.underlying_id,
            "roll_source": self.roll_source,
            "first_price_ticks": self.first_price_ticks,
            "bars": [bar_file_dict(bar) for bar in self.bars],
            "trades": [trade_file_dict(trade) for trade in self.trades],
            "quality": {
                "n_trades": self.quality.n_trades,
                "life_days": self.quality.life_days,
                "volume_milli_total": self.quality.volume_milli_total,
                "traded_bars": self.quality.traded_bars,
                "tape_kind": self.quality.tape_kind,
            },
            "cash_events": [event.to_dict() for event in self.cash_events],
            "source": self.source,
            "notes": self.notes,
        }


def bar_file_dict(bar: Bar) -> dict[str, object]:
    """One bar in the **file** shape of ``instrument.v1.json`` (``_ticks`` fields, ruling R173)."""
    return {
        "t_ms": bar.t_ms,
        "open_ticks": bar.open_bp,
        "high_ticks": bar.high_bp,
        "low_ticks": bar.low_bp,
        "close_ticks": bar.close_bp,
        "vwap_ticks": bar.vwap_bp,
        "volume_milli": bar.volume_milli,
        "n_trades": bar.n_trades,
        "bid_ticks": bar.yes_bid_bp,
        "ask_ticks": bar.yes_ask_bp,
        "open_interest_milli": bar.open_interest,
    }


def trade_file_dict(trade: Trade) -> dict[str, object]:
    """One trade in the file shape of ``instrument.v1.json``."""
    return {"t_ms": trade.t_ms, "price_ticks": trade.price_bp, "size_milli": trade.size_milli, "side": trade.side}


@dataclass(frozen=True, slots=True)
class MarketMeta:
    """The leak-free projection of a market that the metrics and the optimizer pass around instead of the
    market itself: no bars, no trades, no prices, no quality (section 7.2).

    It does carry ``resolution`` and ``fold``, which is why section 7.9 forbids it inside an observation:
    ``MarketMeta`` is for the scorer and the selector, never for an agent. On a continuous instrument
    (ruling R186) ``created_at_ms = listed_at_ms``, ``resolved_at_ms = delisted_at_ms`` when set else the
    dataset's window end, ``close_at_ms = resolved_at_ms``, ``resolution = -1``, ``event_key = None``,
    ``hardness_tags = ()``, ``fold = "all"`` and ``n_bars`` the file's bar count, so section 3's order,
    ``block_key`` and ``Folds`` read one sequence for every kind.
    """

    id: str
    provider: str
    category: str
    tags: tuple[str, ...]
    event_key: str | None
    created_at_ms: int
    close_at_ms: int
    resolved_at_ms: int
    resolution: int
    interval_min: int
    n_bars: int
    hardness_tags: tuple[str, ...]
    fee_schedule_id: str
    fold: str
    kind: str = "binary"

    def __post_init__(self) -> None:
        if self.kind not in INSTRUMENT_KINDS:
            raise InvalidConfigError("unknown instrument kind", market_id=self.id, kind=self.kind)

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "provider": self.provider,
            "category": self.category,
            "tags": list(self.tags),
            "event_key": self.event_key,
            "created_at_ms": self.created_at_ms,
            "close_at_ms": self.close_at_ms,
            "resolved_at_ms": self.resolved_at_ms,
            "resolution": self.resolution,
            "interval_min": self.interval_min,
            "n_bars": self.n_bars,
            "hardness_tags": list(self.hardness_tags),
            "fee_schedule_id": self.fee_schedule_id,
            "fold": self.fold,
            "kind": self.kind,
        }


def meta_of(
    market: Market | ContinuousInstrument, *, fold: str, window_end_ms: int | None = None
) -> MarketMeta:
    """Project a market or a continuous instrument onto its leak-free metadata (7.2, ruling R186).

    One spelling, so no package writes its own. ``window_end_ms`` is the dataset's ``window.end_ms`` and
    stands in for ``resolved_at_ms`` on a continuous instrument that is still listed at the freeze; a
    binary ignores it. ``fold`` is the caller's on a binary and always ``"all"`` on a continuous
    instrument, which belongs to every fold whose months it has bars in (17.6).
    """
    if isinstance(market, Market):
        return MarketMeta(
            id=market.id,
            provider=market.provider,
            category=market.category,
            tags=market.tags,
            event_key=market.event_key,
            created_at_ms=market.created_at_ms,
            close_at_ms=market.close_at_ms,
            resolved_at_ms=market.resolved_at_ms,
            resolution=market.resolution,
            interval_min=market.interval_min,
            n_bars=len(market.bars),
            hardness_tags=market.hardness_tags,
            fee_schedule_id=market.fee_schedule_id,
            fold=fold,
        )
    if market.delisted_at_ms is not None:
        end_ms = market.delisted_at_ms
    elif window_end_ms is not None:
        end_ms = window_end_ms
    else:
        raise InvalidConfigError(
            "a continuous instrument still listed at the freeze needs the dataset's window end",
            market_id=market.id,
        )
    return MarketMeta(
        id=market.id,
        provider=market.provider,
        category=market.category,
        tags=market.tags,
        event_key=None,
        created_at_ms=market.listed_at_ms,
        close_at_ms=end_ms,
        resolved_at_ms=end_ms,
        resolution=-1,
        interval_min=market.interval_min,
        n_bars=len(market.bars),
        hardness_tags=(),
        fee_schedule_id=market.fee_schedule_id,
        fold="all",
        kind=market.kind,
    )


@dataclass(frozen=True, slots=True)
class OpenMarket:
    """A market with no outcome yet: what the live jobs of L1 trade against (section 7.12).

    It never enters a dataset, which is why it has no ``resolution``, no ``resolved_at_ms`` and no
    ``final_price_bp``: there is nothing to leak, because nothing has happened yet. ``bars`` is truncated
    at ``now_ms`` to completed bars only, and ``last_price_bp`` is the as-of price of section 5.4.
    """

    id: str
    provider: str
    provider_id: str
    url: str
    question: str
    description: str
    category: str
    tags: tuple[str, ...]
    wiki_subjects: tuple[str, ...]
    currency: str
    created_at_ms: int
    close_at_ms: int
    interval_min: int
    bars: tuple[Bar, ...]
    first_price_bp: int
    last_price_bp: int
    quality: MarketQuality
    fee_schedule_id: str

    def __post_init__(self) -> None:
        """The same freezing as ``Market``: an importer may hand a list, the record keeps a tuple."""
        for name in ("tags", "wiki_subjects", "bars"):
            value = getattr(self, name)
            if not isinstance(value, tuple):
                object.__setattr__(self, name, tuple(value))

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "provider": self.provider,
            "provider_id": self.provider_id,
            "url": self.url,
            "question": self.question,
            "description": self.description,
            "category": self.category,
            "tags": list(self.tags),
            "wiki_subjects": list(self.wiki_subjects),
            "currency": self.currency,
            "created_at_ms": self.created_at_ms,
            "close_at_ms": self.close_at_ms,
            "interval_min": self.interval_min,
            "bars": [bar.to_dict() for bar in self.bars],
            "first_price_bp": self.first_price_bp,
            "last_price_bp": self.last_price_bp,
            "quality": self.quality.to_dict(),
            "fee_schedule_id": self.fee_schedule_id,
        }


# --------------------------------------------------------------------------------------------------
# 7.5 Hardness tags. Section 7.5 assigns the computation to the builder (D6) and section 7.10 requires
# it of the migration (D1); the shared implementation lives here so the two cannot drift.
# --------------------------------------------------------------------------------------------------
#: ``upset`` reads the last thirty **days** of life, not the last thirty bars: on an hourly dataset the
#: second reading is thirty hours and tags a different set of markets (section 7.5, ruling R89).
UPSET_WINDOW_MS = 30 * MS_PER_DAY


def hardness_tags_from_closes(
    *,
    bar_times_ms: Sequence[int],
    closes_bp: Sequence[int],
    resolution: int,
    resolved_at_ms: int,
    illiquid: bool = False,
) -> tuple[str, ...]:
    """The one implementation of section 7.5, over the two parallel sequences a caller always has.

    Ruling R89 collapses the two implementations this wave produced (one here over ``Bar`` objects, one in
    ``pmx.data.builder`` over the builder's ``MarketFacts``) into this helper, which both now call: a
    market must not get two answers depending on who asked.

    ``trivial`` is the corrected reading of decision D-4: a market whose closes never left ``[500, 9500]``
    is the *hard* case, so ``trivial`` is the mirror (every close under 500, or every close over 9500,
    from the first bar: the outcome was never in doubt). ``upset`` compares the mean close of the last
    ``UPSET_WINDOW_MS`` of life (the whole life when it is shorter) against the outcome. ``whipsaw`` counts
    crossings of ``5000`` by consecutive closes. ``illiquid`` is the one tag that is relative to a dataset
    rather than to a market, so the caller that knows the provider slice decides it and passes it in.
    """
    tags: list[str] = []
    closes = list(closes_bp)
    if closes and (all(close < 500 for close in closes) or all(close > 9_500 for close in closes)):
        tags.append("trivial")
    tail = [
        close
        for t_ms, close in zip(bar_times_ms, closes, strict=True)
        if t_ms >= resolved_at_ms - UPSET_WINDOW_MS
    ] or closes
    if tail:
        mean_bp = round_half_up(sum(tail), len(tail))
        if (mean_bp > 5_000 and resolution == 0) or (mean_bp < 5_000 and resolution == 1):
            tags.append("upset")
    crossings = sum(
        1
        for previous, current in zip(closes, closes[1:], strict=False)
        if (previous < 5_000 <= current) or (current < 5_000 <= previous)
    )
    if crossings > 4:
        tags.append("whipsaw")
    if illiquid:
        tags.append("illiquid")
    return tuple(sorted(tags))


def hardness_tags_of(
    bars: Sequence[Bar], *, resolution: int, resolved_at_ms: int, illiquid: bool = False
) -> tuple[str, ...]:
    """:func:`hardness_tags_from_closes` over a market's own bars, sorted as the schema requires."""
    return hardness_tags_from_closes(
        bar_times_ms=[bar.t_ms for bar in bars],
        closes_bp=[bar.close_bp for bar in bars],
        resolution=resolution,
        resolved_at_ms=resolved_at_ms,
        illiquid=illiquid,
    )


# --------------------------------------------------------------------------------------------------
# 7.3 The news item
# --------------------------------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class NewsItem:
    """One dated item of the news of the time (section 7.3).

    ``visible_from_ms`` is ``published_at_ms + safety_lag_ms`` and is stamped at **build** time, so the
    safety lag cannot be skipped by a consumer: the observation builder reads this field and nothing else.
    ``fetched_at_ms`` is a wall clock, which is legal here and nowhere else, because a dataset is built,
    not run.
    """

    schema_version: str
    news_id: str
    source: str
    kind: str
    published_at_ms: int
    revid: int | None
    asof_day: str | None
    visible_from_ms: int
    fetched_at_ms: int
    url: str
    headline: str
    text: str
    section: str | None
    wiki_links: tuple[str, ...]
    source_urls: tuple[str, ...]
    match_ids: tuple[str, ...]
    match_scores_permille: tuple[int, ...]
    lang: str
    author_key: str | None

    def score_for(self, market_id: str) -> int:
        """The link score this item carries for ``market_id``, or 0 when it is not linked to it."""
        for candidate, score in zip(self.match_ids, self.match_scores_permille, strict=False):
            if candidate == market_id:
                return score
        return 0

    def to_dict(self) -> dict[str, object]:
        """The ``news.v1.json`` shape, exactly: one line of ``news/<yyyymmdd>.jsonl``."""
        return {
            "schema_version": self.schema_version,
            "news_id": self.news_id,
            "source": self.source,
            "kind": self.kind,
            "published_at_ms": self.published_at_ms,
            "revid": self.revid,
            "asof_day": self.asof_day,
            "visible_from_ms": self.visible_from_ms,
            "fetched_at_ms": self.fetched_at_ms,
            "url": self.url,
            "headline": self.headline,
            "text": self.text,
            "section": self.section,
            "wiki_links": list(self.wiki_links),
            "source_urls": list(self.source_urls),
            "match_ids": list(self.match_ids),
            "match_scores_permille": list(self.match_scores_permille),
            "lang": self.lang,
            "author_key": self.author_key,
        }


# --------------------------------------------------------------------------------------------------
# 7.8 The manifest
# --------------------------------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class DatasetWindow:
    start_ms: int
    end_ms: int

    def to_dict(self) -> dict[str, object]:
        return {"start_ms": self.start_ms, "end_ms": self.end_ms}


@dataclass(frozen=True, slots=True)
class DatasetFilters:
    """``config`` is ``BuildConfig.to_dict()`` verbatim; ``removed`` carries **exactly** the ten filter
    keys of section 7.4, every one always present and 0 when the filter removed nothing, so the dataset
    panel and the gate's shortfall report read a fixed shape."""

    config: Mapping[str, object]
    removed: Mapping[str, int]

    def to_dict(self) -> dict[str, object]:
        return {
            "config": {key: self.config[key] for key in sorted(self.config)},
            "removed": {key: self.removed[key] for key in sorted(self.removed)},
        }


REMOVED_FILTER_KEYS = (
    "window",
    "opened_early",
    "binary",
    "min_trades",
    "min_life",
    "density",
    "self_resolved",
    "kalshi_shards",
    "resolution",
    "no_leak",
)


@dataclass(frozen=True, slots=True)
class DatasetCounts:
    markets: int
    per_provider: Mapping[str, int]
    per_category: Mapping[str, int]
    resolution_yes: int
    resolution_no: int
    hardness_tags: Mapping[str, int]
    #: The bottom-decile boundary of median daily volume, per provider slice, in milli-contracts. Section
    #: 7.5 requires the ``illiquid`` tag to be "reported with the decile boundary" and ruling R98 gives
    #: that report a typed field instead of a sentence in ``notes``. A provider whose surviving slice was
    #: too small for a tenth percentile is **absent** from the map rather than carrying a sentinel, so
    #: every value here is a real boundary a reviewer can re-derive from the markets.
    illiquid_boundary_milli: Mapping[str, int] = field(default_factory=dict)
    #: How many kept markets came in on the bars-only tape (:data:`TAPE_KIND_BARS_ONLY`), which is the
    #: only path a provider with no settled print tape has through the ``min_trades`` filter of 7.4. A
    #: dataset that reports zero here took every one of its markets on prints.
    n_bars_only: int = 0
    #: How many kept markets landed on the ``other`` category because nothing named a better one: the
    #: series-to-category map of a provider whose listing rows carry no category. It is reported because
    #: the leaderboard, the specialist family and the category priors all read ``per_category``, and a
    #: flat ``other`` slice is a measurement failure rather than a fact about the markets.
    n_category_fallback: int = 0
    #: Per provider, the twelve month buckets of the window (section 7.7) counted **after** every filter
    #: of 7.4 and **before** ``limit_per_provider`` was applied. It is what makes the cap auditable: the
    #: dataset shows what was sampled, this shows what there was to sample from.
    precap_per_provider_month: Mapping[str, tuple[int, ...]] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        counts: dict[str, object] = {
            "markets": self.markets,
            "per_provider": {key: self.per_provider[key] for key in sorted(self.per_provider)},
            "per_category": {key: self.per_category[key] for key in sorted(self.per_category)},
            "resolution_yes": self.resolution_yes,
            "resolution_no": self.resolution_no,
            "hardness_tags": {key: self.hardness_tags[key] for key in sorted(self.hardness_tags)},
            "illiquid_boundary_milli": {
                key: self.illiquid_boundary_milli[key] for key in sorted(self.illiquid_boundary_milli)
            },
        }
        # The three counts below are written only when they carry a number, for the reason
        # ``quality.tape_kind`` is: a build that took no bars-only market, mapped every category and
        # capped nothing has nothing to say here, and saying it as three zeros would move the bytes of
        # every manifest that predates them.
        if self.n_bars_only:
            counts["n_bars_only"] = self.n_bars_only
        if self.n_category_fallback:
            counts["n_category_fallback"] = self.n_category_fallback
        if self.precap_per_provider_month:
            counts["precap_per_provider_month"] = {
                key: list(self.precap_per_provider_month[key])
                for key in sorted(self.precap_per_provider_month)
            }
        return counts


@dataclass(frozen=True, slots=True)
class NewsSourceCount:
    source: str
    n_items: int
    fetched_at_ms_min: int
    fetched_at_ms_max: int

    def to_dict(self) -> dict[str, object]:
        return {
            "source": self.source,
            "n_items": self.n_items,
            "fetched_at_ms_min": self.fetched_at_ms_min,
            "fetched_at_ms_max": self.fetched_at_ms_max,
        }


@dataclass(frozen=True, slots=True)
class DatasetNews:
    sources: tuple[NewsSourceCount, ...]
    n_items: int
    n_linked: int

    def to_dict(self) -> dict[str, object]:
        return {
            "sources": [source.to_dict() for source in self.sources],
            "n_items": self.n_items,
            "n_linked": self.n_linked,
        }


@dataclass(frozen=True, slots=True)
class DatasetSplit:
    """The thirteen month edges and the three fold counts (section 7.7). A market belongs to exactly one
    fold, by ``resolved_at_ms``."""

    month_edges_ms: tuple[int, ...]
    train_end_ms: int
    validation_end_ms: int
    n_train: int
    n_validation: int
    n_sealed: int
    #: Amendment C1b (17.6, 17.9): a continuous instrument belongs to every fold whose months it has bars
    #: in, so these count instruments per fold rather than partition them. Written only when non-zero, so a
    #: binary manifest keeps its bytes.
    n_instruments_train: int = 0
    n_instruments_validation: int = 0
    n_instruments_sealed: int = 0

    def fold_of(self, resolved_at_ms: int) -> str:
        if resolved_at_ms < self.train_end_ms:
            return "train"
        if resolved_at_ms < self.validation_end_ms:
            return "validation"
        return "sealed"

    def to_dict(self) -> dict[str, object]:
        block: dict[str, object] = {
            "month_edges_ms": list(self.month_edges_ms),
            "train_end_ms": self.train_end_ms,
            "validation_end_ms": self.validation_end_ms,
            "n_train": self.n_train,
            "n_validation": self.n_validation,
            "n_sealed": self.n_sealed,
        }
        for name in ("n_instruments_train", "n_instruments_validation", "n_instruments_sealed"):
            value = getattr(self, name)
            if value:
                block[name] = value
        return block


def month_edges_for(window_start_ms: int) -> tuple[int, ...]:
    """The thirteen edges of section 7.7: offsets of 0, 30, 60, 91, ... 365 days from the window start."""
    return tuple(window_start_ms + ((k * 365) // 12) * MS_PER_DAY for k in range(13))


@dataclass(frozen=True, slots=True)
class DatasetFile:
    path: str
    sha256: str
    bytes: int

    def to_dict(self) -> dict[str, object]:
        return {"path": self.path, "sha256": self.sha256, "bytes": self.bytes}


@dataclass(frozen=True, slots=True)
class BuiltBy:
    pmx_version: str
    contract_version: str
    rng_algorithm_version: str

    def to_dict(self) -> dict[str, object]:
        return {
            "pmx_version": self.pmx_version,
            "contract_version": self.contract_version,
            "rng_algorithm_version": self.rng_algorithm_version,
        }


@dataclass(frozen=True, slots=True)
class DatasetManifest:
    """``dataset.v1.json`` as a structure (section 7.8).

    ``manifest.json`` is excluded from ``dataset_hash`` because it carries the hash; its own integrity is
    the ``sealed`` flag plus the recomputation ``verify_dataset`` performs.
    """

    schema_version: str
    name: str
    freeze_date: str
    freeze_ms: int
    window: DatasetWindow
    interval_min: int
    providers: tuple[str, ...]
    safety_lag_ms: int
    filters: DatasetFilters
    counts: DatasetCounts
    news: DatasetNews
    split: DatasetSplit
    files: tuple[DatasetFile, ...]
    dataset_hash: str
    built_by: BuiltBy
    sealed: bool
    notes: str
    #: Amendment C1b's three optional blocks (7.8, 17.9, rulings R149 and R166): the kinds the dataset
    #: carries, the instrument counts (``per_kind``, ``per_provider``, ``per_vendor``, ``n_cash_events``,
    #: ``n_calendars``) and the schedules it used (``fee``, ``borrow``, ``carry`` id lists). Absent from a
    #: binary-only manifest and written only when set, so no manifest of 2026-09-08 moves a byte.
    kinds: tuple[str, ...] = ()
    instruments: Mapping[str, object] | None = None
    schedules: Mapping[str, tuple[str, ...]] | None = None
    #: Amendment C1's two optional blocks (16.1 and 16.3, rulings R117 and R135), carried through as opaque
    #: mappings so that a reseal never silently deletes them; their typed consumers land in waves 7 and 8.
    clusters: Mapping[str, object] | None = None
    impact: Mapping[str, object] | None = None

    @property
    def is_demo_pack(self) -> bool:
        """The one dataset the window and freeze rules of section 5.6 do not apply to: an unsealed pack
        whose only provider is ``demo`` (section 7.1). No other dataset gets the exemption."""
        return not self.sealed and self.providers == ("demo",)

    def to_dict(self) -> dict[str, object]:
        document: dict[str, object] = {
            "schema_version": self.schema_version,
            "name": self.name,
            "freeze_date": self.freeze_date,
            "freeze_ms": self.freeze_ms,
            "window": self.window.to_dict(),
            "interval_min": self.interval_min,
            "providers": list(self.providers),
            "safety_lag_ms": self.safety_lag_ms,
            "filters": self.filters.to_dict(),
            "counts": self.counts.to_dict(),
            "news": self.news.to_dict(),
            "split": self.split.to_dict(),
            "files": [entry.to_dict() for entry in self.files],
            "dataset_hash": self.dataset_hash,
            "built_by": self.built_by.to_dict(),
            "sealed": self.sealed,
            "notes": self.notes,
        }
        if self.kinds:
            document["kinds"] = list(self.kinds)
        if self.instruments is not None:
            document["instruments"] = {key: self.instruments[key] for key in sorted(self.instruments)}
        if self.schedules is not None:
            document["schedules"] = {key: list(self.schedules[key]) for key in sorted(self.schedules)}
        if self.clusters is not None:
            document["clusters"] = dict(self.clusters)
        if self.impact is not None:
            document["impact"] = dict(self.impact)
        return document


@dataclass(frozen=True, slots=True)
class Dataset:
    """What ``load_dataset`` returns and ``run_backtest`` receives (section 7.2).

    Only the manifest and the leak-free metas are held in memory: a market's tape is loaded and validated
    on demand, because a year of hourly bars over three hundred markets is not something to hold at once.
    The cache is per ``Dataset`` instance and keyed by market id, so two calls return the same object and
    a run reads a file once.
    """

    manifest: DatasetManifest
    metas: tuple[MarketMeta, ...]
    path: Path
    #: The fields below are keyword-only extensions of the contract's three (rule 2): the loader injects
    #: how to read a market, a calendar and the news, so ``Dataset`` itself opens no file and a test can
    #: build one over in-memory markets. ``market_loader`` returns the **whole** record; the clip of ruling
    #: R182 is applied here, once, in :meth:`market`.
    market_loader: Callable[[str], Market | ContinuousInstrument] | None = field(default=None, kw_only=True)
    news_loader: Callable[[], tuple[NewsItem, ...]] | None = field(default=None, kw_only=True)
    background_loader: Callable[[str], tuple[NewsItem, ...]] | None = field(default=None, kw_only=True)
    calendar_loader: Callable[[str], SessionCalendar] | None = field(default=None, kw_only=True)
    _markets: dict[str, Market | ContinuousInstrument] = field(
        default_factory=dict, compare=False, repr=False, kw_only=True
    )
    _whole: dict[str, Market | ContinuousInstrument] = field(
        default_factory=dict, compare=False, repr=False, kw_only=True
    )
    _calendars: dict[str, SessionCalendar] = field(default_factory=dict, compare=False, repr=False, kw_only=True)
    _news: list[NewsItem] = field(default_factory=list, compare=False, repr=False, kw_only=True)
    _news_loaded: list[bool] = field(default_factory=list, compare=False, repr=False, kw_only=True)

    def meta(self, market_id: str) -> MarketMeta:
        for meta in self.metas:
            if meta.id == market_id:
                return meta
        raise SchemaError("unknown market id", market_id=market_id, dataset=self.manifest.name)

    def _load_whole(self, market_id: str) -> Market | ContinuousInstrument:
        cached = self._whole.get(market_id)
        if cached is not None:
            return cached
        if self.market_loader is None:
            raise SchemaError("this dataset carries no market loader", market_id=market_id)
        record = self.market_loader(market_id)
        self._whole[market_id] = record
        return record

    def market(self, market_id: str) -> Market | ContinuousInstrument:
        """The instrument's full tape, loaded and validated on first use.

        A ``Market`` for a binary; a ``ContinuousInstrument`` for every other kind, **clipped** at
        ``manifest.split.validation_end_ms`` (bars, trades and cash events), so no consumer outside the
        claim path ever holds the sealed months of a price path (17.2, ruling R182). A binary's sealed
        guarantee is structural, because a sealed id is never handed out.
        """
        cached = self._markets.get(market_id)
        if cached is not None:
            return cached
        record = self._load_whole(market_id)
        if isinstance(record, ContinuousInstrument):
            record = record.clipped(self.manifest.split.validation_end_ms)
        self._markets[market_id] = record
        return record

    def calendar(self, calendar_id: str) -> SessionCalendar:
        """The sealed session calendar, or the synthesised ``continuous`` one (17.2, ruling R185).

        ``continuous`` is one session ``[0, INT63_MAX)`` and is never read from a file, so a dataset with
        no ``calendars/`` directory (the demo pack, the 2026-09-08 build) answers for every binary.
        """
        cached = self._calendars.get(calendar_id)
        if cached is not None:
            return cached
        if calendar_id == CONTINUOUS_CALENDAR_ID:
            calendar = continuous_calendar()
        elif self.calendar_loader is None:
            raise SchemaError("this dataset carries no calendar loader", calendar_id=calendar_id)
        else:
            calendar = self.calendar_loader(calendar_id)
        self._calendars[calendar_id] = calendar
        return calendar

    def calendar_ids(self) -> tuple[str, ...]:
        """The calendar ids the dataset's instruments name, ``continuous`` included, sorted."""
        ids = {CONTINUOUS_CALENDAR_ID}
        for meta in self.metas:
            if meta.kind != INSTRUMENT_KINDS[0]:
                ids.add(self.market(meta.id).instrument.session_calendar_id)
        return tuple(sorted(ids))

    def sealed_market(self, market_id: str) -> Market | ContinuousInstrument:
        """The **unclipped** record, sealed months included (17.2, ruling R182).

        Named only here, where it is declared, and in ``optimizer/folds.py`` and ``optimizer/claims.py``
        (architecture rule 3 scans every other file for the name), so the sealed months of a price path
        are reachable from the claim path and nowhere else.
        """
        return self._load_whole(market_id)

    def _all_news(self) -> tuple[NewsItem, ...]:
        if not self._news_loaded:
            if self.news_loader is not None:
                self._news.extend(self.news_loader())
            self._news_loaded.append(True)
        return tuple(self._news)

    def news_for(self, market_id: str, now_ms: int) -> tuple[NewsItem, ...]:
        """Items linked to ``market_id`` and visible at ``now_ms``, in dataset order.

        The as-of test is ``visible_from_ms <= now_ms`` and nothing else: the safety lag was applied at
        build time (section 5.5), so a consumer cannot skip it and a consumer cannot double it either.
        """
        return tuple(
            item
            for item in self._all_news()
            if item.visible_from_ms <= now_ms and market_id in item.match_ids
        )

    def news_global(self, now_ms: int) -> tuple[NewsItem, ...]:
        """Every item visible at ``now_ms``, linked or not: the global digest's raw material."""
        return tuple(item for item in self._all_news() if item.visible_from_ms <= now_ms)

    def background_for(self, market_id: str, now_ms: int) -> tuple[NewsItem, ...]:
        """The point-in-time background snapshots of ``market_id`` visible at ``now_ms``, oldest first.

        A keyword-free addition to the contract's three methods (rule 2, reported): the snapshots under
        ``wiki_asof/<market_id>/`` are not part of the news digest, they are the payload of a granted
        ``wiki_asof`` research request (section 8.4), so they need their own accessor rather than
        widening ``news_for``.
        """
        if self.background_loader is None:
            return ()
        return tuple(
            item for item in self.background_loader(market_id) if item.visible_from_ms <= now_ms
        )


# --------------------------------------------------------------------------------------------------
# 7.4 The build config
# --------------------------------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class BuildConfig:
    """Every window and quality filter of section 7.4, and every one of them reported in the manifest.

    ``limit_per_provider`` renders as ``0`` in ``to_dict`` (and therefore in the manifest) because
    ``dataset.v1.json`` allows an integer, a boolean, a string or an array in ``filters.config`` and not
    a null: ``None`` and ``0`` both mean "no limit" to the builder.
    """

    freeze_date: str
    providers: tuple[str, ...]
    interval_min: int = 1_440
    window_days: int = 365
    opened_early_days: int = 90
    min_trades: int = 50
    min_unique_bettors: int = 30
    min_life_days: int = 7
    #: The bars-only branch of the ``min_trades`` filter (section 7.4). A market whose tape carries its
    #: size per bar and publishes no prints answers ``n_trades == 0`` whatever it traded, so it passes
    #: the filter on ``quality.traded_bars >= min_traded_bars`` instead. Twenty traded bars on the daily
    #: grid is three weeks of activity, which is the same order of evidence fifty prints are.
    min_traded_bars: int = 20
    min_traded_bars_per_day_permille: int = 250
    exclude_self_resolved: bool = True
    exclude_kalshi_shards: bool = True
    #: The Kalshi series a build asks the provider for, empty meaning every series that is
    #: not excluded. Ruling R100 makes it a build-time filter rather than a caller argument
    #: only: Kalshi honours ``series_ticker`` on both settled listings and honours nothing
    #: else, so a twelve-month window is unreachable without it. It enters the manifest with
    #: the other filters, which is what makes a dataset's universe auditable.
    kalshi_series_allow_list: tuple[str, ...] = ()
    safety_lag_ms: int = SAFETY_LAG_MS_DEFAULT
    news_sources: tuple[str, ...] = ("wikipedia_current_events", "manifold_comment")
    limit_per_provider: int | None = None
    #: Amendment C1b (7.4, 17.2, ruling R144): which instrument kinds the build imports. A continuous
    #: kind's instruments are filtered by ``min_life_days`` and ``density`` on their own calendars and by
    #: nothing else in 7.4's table.
    kinds: tuple[str, ...] = ("binary",)

    def __post_init__(self) -> None:
        if RE_ISO_DATE.fullmatch(self.freeze_date) is None:
            raise InvalidConfigError("freeze_date must be yyyy-mm-dd", freeze_date=self.freeze_date)
        if not self.providers:
            raise InvalidConfigError("a build needs at least one provider")
        unknown = [name for name in self.providers if name not in PROVIDERS]
        if unknown:
            raise InvalidConfigError("unknown provider", providers=unknown)
        if not self.kinds:
            raise InvalidConfigError("a build imports at least one kind")
        unknown_kinds = [name for name in self.kinds if name not in INSTRUMENT_KINDS]
        if unknown_kinds:
            raise InvalidConfigError("unknown instrument kind", kinds=unknown_kinds)
        if len(set(self.kinds)) != len(self.kinds):
            raise InvalidConfigError("kinds must be unique", kinds=list(self.kinds))
        if tuple(sorted(set(self.providers))) != self.providers:
            raise InvalidConfigError("providers must be sorted and unique", providers=list(self.providers))
        if self.interval_min not in INTERVALS_MIN:
            raise InvalidConfigError("interval_min must be 60 or 1440", interval_min=self.interval_min)
        for name in ("window_days", "min_life_days"):
            if getattr(self, name) < 1:
                raise InvalidConfigError(f"{name} must be at least 1", value=getattr(self, name))
        negatives = ("opened_early_days", "min_trades", "min_unique_bettors", "min_traded_bars", "safety_lag_ms")
        for name in negatives:
            if getattr(self, name) < 0:
                raise InvalidConfigError(f"{name} must not be negative", value=getattr(self, name))
        if not 0 <= self.min_traded_bars_per_day_permille <= 1_000:
            raise InvalidConfigError(
                "min_traded_bars_per_day_permille is a permille",
                value=self.min_traded_bars_per_day_permille,
            )
        unknown_sources = [name for name in self.news_sources if name not in NEWS_SOURCES]
        if unknown_sources:
            raise InvalidConfigError("unknown news source", news_sources=unknown_sources)
        if self.limit_per_provider is not None and self.limit_per_provider < 0:
            raise InvalidConfigError("limit_per_provider must not be negative", value=self.limit_per_provider)

    @property
    def freeze_ms(self) -> int:
        return ms_from_iso_date(self.freeze_date)

    def to_dict(self) -> dict[str, object]:
        return {
            "freeze_date": self.freeze_date,
            "providers": list(self.providers),
            "interval_min": self.interval_min,
            "window_days": self.window_days,
            "opened_early_days": self.opened_early_days,
            "min_trades": self.min_trades,
            "min_unique_bettors": self.min_unique_bettors,
            "min_life_days": self.min_life_days,
            "min_traded_bars": self.min_traded_bars,
            "min_traded_bars_per_day_permille": self.min_traded_bars_per_day_permille,
            "exclude_self_resolved": self.exclude_self_resolved,
            "kalshi_series_allow_list": list(self.kalshi_series_allow_list),
            "exclude_kalshi_shards": self.exclude_kalshi_shards,
            "safety_lag_ms": self.safety_lag_ms,
            "news_sources": list(self.news_sources),
            "limit_per_provider": 0 if self.limit_per_provider is None else self.limit_per_provider,
            "kinds": list(self.kinds),
        }


# --------------------------------------------------------------------------------------------------
# 8.1 The run config
# --------------------------------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class RunConfig:
    """Everything a backtest needs that is not the dataset, the roster or the RNG tree (section 8.1).

    ``fold`` and ``market_ids_hash`` are in the config, and therefore in ``config_hash`` and in the run
    id, because a generation runs the same population, the same seed and the same config on the training
    and on the validation fold: without them the two runs share a run id, overwrite each other's journal,
    and a validation number can be presented as a training number with nothing in the artefacts to tell
    them apart. ``memory_from_run_id`` and ``hive_from_run_id`` are in it for the same reason: memory
    carried between runs is a channel into an observation, so it must move the run id.
    """

    seed: int
    interval_min: int = 1_440
    t0_ms: int | None = None
    t1_ms: int | None = None
    bankroll_cents: int = 100_000
    volume_cap_permille: int = 100
    slippage_bp_per_pct: int = 10
    ruin_floor_cents: int = 1_000
    bars_window: int = 90
    trades_window: int = 200
    news_per_market: int = 20
    news_global: int = 50
    hive_lessons: int = 20
    hive_forecasts: int = 200
    markets_per_obs_max: int = 200
    research_budget_units: int = 10
    research_budget_by_agent: tuple[tuple[str, int], ...] = ()
    amnesic: bool = False
    no_hive: bool = False
    live_coop: bool = False
    memory_frozen: bool = False
    memory_from_run_id: str | None = None
    hive_from_run_id: str | None = None
    contamination_hash: str | None = None
    fold: str = "all"
    market_ids_hash: str = ""
    #: Amendment C1's two fields (16.1, ruling R112): the liquidity model the run faced and the hash of
    #: its parameters. Both enter ``config_hash`` and the run id: two runs that differ only in the tape
    #: they had to trade against must not share a directory, a journal or a claim.
    liquidity: str = "historical"
    liquidity_params_hash: str = ""
    #: Amendment C1b's two fields (17.2, 17.5, rulings R144 and R157): the horizons a run scores, in bars
    #: of the instrument's own sequence, and the kinds it carries (``()`` meaning every kind the dataset
    #: has). ``()`` horizons means ``default_horizons_bars(interval_min)`` and ``__post_init__`` resolves
    #: it **here**, before ``to_dict`` and therefore before ``config_hash`` (17.5, ruling R188): a config
    #: that spells the default and one that omits it are one run and must not be two run ids.
    horizons_bars: tuple[int, ...] = ()
    kinds: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not 0 <= self.seed < SEED_SPACE:
            raise InvalidConfigError("seed outside SEED_SPACE", seed=self.seed)
        if self.interval_min not in INTERVALS_MIN:
            raise InvalidConfigError("interval_min must be 60 or 1440", interval_min=self.interval_min)
        if not isinstance(self.horizons_bars, tuple):
            object.__setattr__(self, "horizons_bars", tuple(self.horizons_bars))
        if not isinstance(self.kinds, tuple):
            object.__setattr__(self, "kinds", tuple(self.kinds))
        if any(not isinstance(h, int) or isinstance(h, bool) or h < 1 or h > 99_999 for h in self.horizons_bars):
            raise InvalidConfigError("horizons_bars are integers in 1..99999", horizons_bars=list(self.horizons_bars))
        if tuple(sorted(set(self.horizons_bars))) != self.horizons_bars:
            raise InvalidConfigError("horizons_bars must be sorted and unique", value=list(self.horizons_bars))
        if not self.horizons_bars:
            object.__setattr__(self, "horizons_bars", default_horizons_bars(self.interval_min))
        unknown_kinds = [kind for kind in self.kinds if kind not in INSTRUMENT_KINDS]
        if unknown_kinds:
            raise InvalidConfigError("unknown kind in config.kinds", kinds=unknown_kinds)
        if tuple(sorted(set(self.kinds))) != self.kinds:
            raise InvalidConfigError("kinds must be sorted and unique", kinds=list(self.kinds))
        if self.liquidity_params_hash != "" and RE_SHA256.fullmatch(self.liquidity_params_hash) is None:
            raise InvalidConfigError("liquidity_params_hash must be 64 hex or empty", hash=self.liquidity_params_hash)
        if self.t0_ms is not None and self.t0_ms < 0:
            raise InvalidConfigError("t0_ms must not be negative", t0_ms=self.t0_ms)
        if self.t0_ms is not None and self.t1_ms is not None and self.t1_ms <= self.t0_ms:
            raise InvalidConfigError("t1_ms must be after t0_ms", t0_ms=self.t0_ms, t1_ms=self.t1_ms)
        if self.bankroll_cents <= 0:
            raise InvalidConfigError("bankroll_cents must be positive", bankroll_cents=self.bankroll_cents)
        if not 0 <= self.volume_cap_permille <= 1_000:
            raise InvalidConfigError("volume_cap_permille is a permille", value=self.volume_cap_permille)
        if self.slippage_bp_per_pct < 0:
            raise InvalidConfigError("slippage_bp_per_pct must not be negative", value=self.slippage_bp_per_pct)
        if self.ruin_floor_cents < 0:
            raise InvalidConfigError("ruin_floor_cents must not be negative", value=self.ruin_floor_cents)
        caps = (
            ("bars_window", self.bars_window, BARS_WINDOW_MAX),
            ("trades_window", self.trades_window, TRADES_WINDOW_MAX),
            ("news_per_market", self.news_per_market, NEWS_PER_MARKET_MAX),
            ("news_global", self.news_global, NEWS_GLOBAL_MAX),
            ("hive_lessons", self.hive_lessons, HIVE_LESSONS_MAX),
            ("hive_forecasts", self.hive_forecasts, HIVE_FORECASTS_MAX),
            ("markets_per_obs_max", self.markets_per_obs_max, MARKETS_PER_OBS_MAX),
        )
        for name, value, cap in caps:
            if value < 0 or value > cap:
                raise InvalidConfigError(f"{name} outside [0, {cap}]", value=value)
        if self.markets_per_obs_max < 1:
            raise InvalidConfigError("markets_per_obs_max must be at least 1", value=self.markets_per_obs_max)
        if self.research_budget_units < 0:
            raise InvalidConfigError("research_budget_units must not be negative", value=self.research_budget_units)
        agent_ids = [agent_id for agent_id, _ in self.research_budget_by_agent]
        if agent_ids != sorted(set(agent_ids)):
            raise InvalidConfigError("research_budget_by_agent must be sorted and unique", agents=agent_ids)
        for agent_id, units in self.research_budget_by_agent:
            if RE_AGENT_ID.fullmatch(agent_id) is None:
                raise InvalidConfigError("bad agent id in research_budget_by_agent", agent_id=agent_id)
            if units < 0:
                raise InvalidConfigError("research budget must not be negative", agent_id=agent_id, units=units)
        if self.fold not in FOLDS:
            raise InvalidConfigError("fold must be one of FOLDS", fold=self.fold)
        if self.contamination_hash is not None and RE_SHA256.fullmatch(self.contamination_hash) is None:
            raise InvalidConfigError("contamination_hash must be 64 hex", value=self.contamination_hash)
        if self.market_ids_hash != "" and RE_SHA256.fullmatch(self.market_ids_hash) is None:
            raise InvalidConfigError("market_ids_hash must be 64 hex or empty", value=self.market_ids_hash)

    def research_budget_for(self, agent_id: str) -> int:
        """The per-agent override when there is one, the scalar otherwise (section 8.1)."""
        for candidate, units in self.research_budget_by_agent:
            if candidate == agent_id:
                return units
        return self.research_budget_units

    @property
    def interval_ms(self) -> int:
        return interval_ms(self.interval_min)

    def to_dict(self) -> dict[str, object]:
        """Every value is an int, a bool, a str, None, or a list of ``[str, int]`` pairs, so
        ``canonical_json`` accepts it and ``config_hash`` is stable."""
        return {
            "seed": self.seed,
            "interval_min": self.interval_min,
            "t0_ms": self.t0_ms,
            "t1_ms": self.t1_ms,
            "bankroll_cents": self.bankroll_cents,
            "volume_cap_permille": self.volume_cap_permille,
            "slippage_bp_per_pct": self.slippage_bp_per_pct,
            "ruin_floor_cents": self.ruin_floor_cents,
            "bars_window": self.bars_window,
            "trades_window": self.trades_window,
            "news_per_market": self.news_per_market,
            "news_global": self.news_global,
            "hive_lessons": self.hive_lessons,
            "hive_forecasts": self.hive_forecasts,
            "markets_per_obs_max": self.markets_per_obs_max,
            "research_budget_units": self.research_budget_units,
            "research_budget_by_agent": [[agent_id, units] for agent_id, units in self.research_budget_by_agent],
            "amnesic": self.amnesic,
            "no_hive": self.no_hive,
            "live_coop": self.live_coop,
            "memory_frozen": self.memory_frozen,
            "memory_from_run_id": self.memory_from_run_id,
            "hive_from_run_id": self.hive_from_run_id,
            "contamination_hash": self.contamination_hash,
            "fold": self.fold,
            "market_ids_hash": self.market_ids_hash,
            "liquidity": self.liquidity,
            "liquidity_params_hash": self.liquidity_params_hash,
            "horizons_bars": list(self.horizons_bars),
            "kinds": list(self.kinds),
        }


# --------------------------------------------------------------------------------------------------
# 8.3 The observation and its views. Nothing here carries a field of section 7.9: no resolution, no
# resolved_at_ms, no final_price_bp, no hardness tag, no quality, no bar count, no t1_ms.
# --------------------------------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class NewsView:
    """One news item as an agent sees it: 600 characters of body, never the 4000 the dataset keeps."""

    news_id: str
    source: str
    kind: str
    published_at_ms: int
    headline: str
    text: str
    section: str | None
    url: str
    match_score_permille: int

    def to_dict(self) -> dict[str, object]:
        return {
            "news_id": self.news_id,
            "source": self.source,
            "kind": self.kind,
            "published_at_ms": self.published_at_ms,
            "headline": self.headline,
            "text": self.text,
            "section": self.section,
            "url": self.url,
            "match_score_permille": self.match_score_permille,
        }


@dataclass(frozen=True, slots=True)
class OpenOrderView:
    order_id: str
    side: str
    price_bp: int
    remaining_size: int
    expires_at_ms: int

    def to_dict(self) -> dict[str, object]:
        return {
            "order_id": self.order_id,
            "side": self.side,
            "price_bp": self.price_bp,
            "remaining_size": self.remaining_size,
            "expires_at_ms": self.expires_at_ms,
        }


@dataclass(frozen=True, slots=True)
class PositionView:
    """The agent's leg on one market: positive is YES contracts held, negative is NO."""

    position: int
    avg_cost_bp: int
    unrealised_cents: int
    open_orders: tuple[OpenOrderView, ...] = ()

    def to_dict(self) -> dict[str, object]:
        return {
            "position": self.position,
            "avg_cost_bp": self.avg_cost_bp,
            "unrealised_cents": self.unrealised_cents,
            "open_orders": [order.to_dict() for order in self.open_orders],
        }


@dataclass(frozen=True, slots=True)
class PortfolioView:
    """``reserved_cents`` is inside ``cash_cents`` (it is cash, earmarked), so equity never adds it twice."""

    cash_cents: int
    reserved_cents: int
    equity_cents: int
    fees_paid_cents: int
    peak_equity_cents: int
    drawdown_bp: int
    n_open_positions: int
    n_open_orders: int
    research_units_remaining: int

    def to_dict(self) -> dict[str, object]:
        return {
            "cash_cents": self.cash_cents,
            "reserved_cents": self.reserved_cents,
            "equity_cents": self.equity_cents,
            "fees_paid_cents": self.fees_paid_cents,
            "peak_equity_cents": self.peak_equity_cents,
            "drawdown_bp": self.drawdown_bp,
            "n_open_positions": self.n_open_positions,
            "n_open_orders": self.n_open_orders,
            "research_units_remaining": self.research_units_remaining,
        }


@dataclass(frozen=True, slots=True)
class MarketView:
    """One open market as an agent sees it at the open of the bar being decided.

    ``last_price_bp`` is the close of the **last completed** bar, or ``first_price_bp`` when no bar is
    complete yet (the market's first bar). It is not the close of the bar being decided: the agent
    decides on completed information and its market orders fill against this bar's own vwap, which it has
    not seen. That is the honest shape of "trade at the next price" (section 5.4).
    """

    market_id: str
    provider: str
    url: str
    question: str
    description: str
    category: str
    tags: tuple[str, ...]
    currency: str
    created_at_ms: int
    close_at_ms: int
    tradable: bool
    bars: tuple[Bar, ...]
    first_price_bp: int
    last_price_bp: int
    best_bid_bp: int | None
    best_ask_bp: int | None
    volume_milli_7d: int
    volume_milli_to_date: int
    n_trades_to_date: int
    trades: tuple[Trade, ...]
    news: tuple[NewsView, ...]
    position: PositionView
    fee_schedule_id: str
    #: Amendment C1b's eight defaulted fields (8.3, ruling R188), filled by E1. ``to_dict()`` renders them
    #: always, so a binary observation gains eight keys at their defaults. ``close_at_ms`` is ``0`` and
    #: ``tradable`` is ``open(i, t)`` on a continuous instrument, because both would otherwise announce
    #: ``last_bar(i)`` (ruling R181); ``hours_to_next_bar`` is the venue's published schedule, which is
    #: not a datum about the future (7.9).
    kind: str = "binary"
    tick_size_micro: int = BINARY_TICK_SIZE_MICRO
    point_value_micro: int = BINARY_POINT_VALUE_MICRO
    session_calendar_id: str = CONTINUOUS_CALENDAR_ID
    hours_to_next_bar: int = 0
    underlying_id: str | None = None
    twins: tuple[str, ...] = ()
    cash_events: tuple[CashEventView, ...] = ()

    def to_dict(self) -> dict[str, object]:
        return {
            "market_id": self.market_id,
            "provider": self.provider,
            "url": self.url,
            "question": self.question,
            "description": self.description,
            "category": self.category,
            "tags": list(self.tags),
            "currency": self.currency,
            "created_at_ms": self.created_at_ms,
            "close_at_ms": self.close_at_ms,
            "tradable": self.tradable,
            "bars": [bar.to_dict() for bar in self.bars],
            "first_price_bp": self.first_price_bp,
            "last_price_bp": self.last_price_bp,
            "best_bid_bp": self.best_bid_bp,
            "best_ask_bp": self.best_ask_bp,
            "volume_milli_7d": self.volume_milli_7d,
            "volume_milli_to_date": self.volume_milli_to_date,
            "n_trades_to_date": self.n_trades_to_date,
            "trades": [trade.to_dict() for trade in self.trades],
            "news": [item.to_dict() for item in self.news],
            "position": self.position.to_dict(),
            "fee_schedule_id": self.fee_schedule_id,
            "kind": self.kind,
            "tick_size_micro": self.tick_size_micro,
            "point_value_micro": self.point_value_micro,
            "session_calendar_id": self.session_calendar_id,
            "hours_to_next_bar": self.hours_to_next_bar,
            "underlying_id": self.underlying_id,
            "twins": list(self.twins),
            "cash_events": [event.to_dict() for event in self.cash_events],
        }


@dataclass(frozen=True, slots=True)
class CashEventView:
    """One **applied** data cash event as an agent may see it (8.3, ruling R183).

    Visible exactly as a bar is: once its application bar has completed it is the venue's published past;
    before that it never reaches an observation, so an announced dividend is hidden until the cum-date
    close. Never an engine kind: those are the agent's own charges and reach it through its portfolio.
    """

    kind: str
    t_ms: int
    applied_at_ms: int
    detail: Mapping[str, int | str]

    def to_dict(self) -> dict[str, object]:
        return {
            "kind": self.kind,
            "t_ms": self.t_ms,
            "applied_at_ms": self.applied_at_ms,
            "detail": {key: self.detail[key] for key in sorted(self.detail)},
        }


@dataclass(frozen=True, slots=True)
class CalibrationBinView:
    """One reliability bin of an agent's own memory, or of the projection (sections 8.3 and 12.2).

    ``n_yes_x2`` is amendment C1b's (17.5, ruling R194): twice the yes count, so that a flat realisation
    on a continuous slice adds ``1`` and an up adds ``2``. It is ``2 * n_yes`` on a binary slice, and every
    ratio a consumer computes reads ``n_yes_x2`` over ``2 * n`` through ``pmx.metrics.calibration``.
    """

    category: str
    horizon_bucket: str
    bin: int
    n: int
    n_yes: int
    n_yes_x2: int = 0

    def to_dict(self) -> dict[str, object]:
        return {
            "category": self.category,
            "horizon_bucket": self.horizon_bucket,
            "bin": self.bin,
            "n": self.n,
            "n_yes": self.n_yes,
            "n_yes_x2": self.n_yes_x2,
        }


@dataclass(frozen=True, slots=True)
class PriorView:
    """``key`` is a category or ``tag:<tag>``: the base rate the agent has actually observed."""

    key: str
    n: int
    n_yes: int

    def to_dict(self) -> dict[str, object]:
        return {"key": self.key, "n": self.n, "n_yes": self.n_yes}


@dataclass(frozen=True, slots=True)
class FeatureStatView:
    family: str
    key: str
    n: int
    sum_milli: int
    sum_sq_milli: int

    def to_dict(self) -> dict[str, object]:
        return {
            "family": self.family,
            "key": self.key,
            "n": self.n,
            "sum_milli": self.sum_milli,
            "sum_sq_milli": self.sum_sq_milli,
        }


@dataclass(frozen=True, slots=True)
class LessonView:
    written_at_ms: int
    text: str
    market_ids: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "written_at_ms": self.written_at_ms,
            "text": self.text,
            "market_ids": list(self.market_ids),
        }


@dataclass(frozen=True, slots=True)
class NoteView:
    written_at_ms: int
    market_id: str | None
    text: str

    def to_dict(self) -> dict[str, object]:
        return {"written_at_ms": self.written_at_ms, "market_id": self.market_id, "text": self.text}


@dataclass(frozen=True, slots=True)
class MemoryView:
    """A snapshot of the agent's own memory, filtered to records written at or before ``now_ms``.

    Memory was the one channel into an observation with no as-of filter at all, which is why every record
    carries ``written_at_ms`` and the poisoned-future test injects a record stamped after ``now_ms``.
    """

    calibration: tuple[CalibrationBinView, ...] = ()
    priors: tuple[PriorView, ...] = ()
    features: tuple[FeatureStatView, ...] = ()
    lessons: tuple[LessonView, ...] = ()
    notes: tuple[NoteView, ...] = ()

    def to_dict(self) -> dict[str, object]:
        return {
            "calibration": [item.to_dict() for item in self.calibration],
            "priors": [item.to_dict() for item in self.priors],
            "features": [item.to_dict() for item in self.features],
            "lessons": [item.to_dict() for item in self.lessons],
            "notes": [item.to_dict() for item in self.notes],
        }


@dataclass(frozen=True, slots=True)
class HiveLessonView:
    entry_id: str
    author_id: str
    author_skill_micro: int
    text: str
    market_ids: tuple[str, ...]
    visible_from_ms: int

    def to_dict(self) -> dict[str, object]:
        return {
            "entry_id": self.entry_id,
            "author_id": self.author_id,
            "author_skill_micro": self.author_skill_micro,
            "text": self.text,
            "market_ids": list(self.market_ids),
            "visible_from_ms": self.visible_from_ms,
        }


@dataclass(frozen=True, slots=True)
class ReputationView:
    agent_id: str
    category: str
    n: int
    skill_micro: int
    pnl_cents: int

    def to_dict(self) -> dict[str, object]:
        return {
            "agent_id": self.agent_id,
            "category": self.category,
            "n": self.n,
            "skill_micro": self.skill_micro,
            "pnl_cents": self.pnl_cents,
        }


@dataclass(frozen=True, slots=True)
class ResolutionView:
    """A settled market as the hive publishes it: an outcome an agent may read only after settlement."""

    market_id: str
    outcome: int
    life_mean_price_bp: int
    resolved_at_ms: int

    def to_dict(self) -> dict[str, object]:
        return {
            "market_id": self.market_id,
            "outcome": self.outcome,
            "life_mean_price_bp": self.life_mean_price_bp,
            "resolved_at_ms": self.resolved_at_ms,
        }


@dataclass(frozen=True, slots=True)
class ForecastView:
    agent_id: str
    market_id: str
    bar_ms: int
    prob_ppm: int

    def to_dict(self) -> dict[str, object]:
        return {
            "agent_id": self.agent_id,
            "market_id": self.market_id,
            "bar_ms": self.bar_ms,
            "prob_ppm": self.prob_ppm,
        }


@dataclass(frozen=True, slots=True)
class HiveView:
    """What one agent may read of the hive at ``now_ms``.

    ``prev_bar_forecasts`` is named for what it is: every observation is built in the ``observe`` phase,
    before any agent decides, so a same-bar forecast does not exist. Every entry satisfies
    ``bar_ms == now_ms - interval_ms`` and the tuple is empty unless ``live_coop`` (section 8.3).
    """

    lessons: tuple[HiveLessonView, ...] = ()
    reputations: tuple[ReputationView, ...] = ()
    resolutions: tuple[ResolutionView, ...] = ()
    forecasts: tuple[ForecastView, ...] = ()
    prev_bar_forecasts: tuple[ForecastView, ...] = ()

    def to_dict(self) -> dict[str, object]:
        return {
            "lessons": [item.to_dict() for item in self.lessons],
            "reputations": [item.to_dict() for item in self.reputations],
            "resolutions": [item.to_dict() for item in self.resolutions],
            "forecasts": [item.to_dict() for item in self.forecasts],
            "prev_bar_forecasts": [item.to_dict() for item in self.prev_bar_forecasts],
        }


@dataclass(frozen=True, slots=True)
class ResearchGrant:
    """A research result granted at the previous bar, so its content is as of ``now_ms - interval_ms``
    and is filtered by the same as-of rules as everything else (section 5.4)."""

    kind: str
    market_id: str | None
    granted_at_ms: int
    news: tuple[NewsView, ...] = ()
    trades: tuple[Trade, ...] = ()

    @property
    def payload(self) -> tuple[NewsView, ...] | tuple[Trade, ...]:
        """The contract calls the result a ``payload``; it is stored as two typed tuples so that no
        consumer has to narrow a union at run time, and read back here for the one caller that wants it
        polymorphically."""
        return self.trades if self.kind == "history" else self.news

    def to_dict(self) -> dict[str, object]:
        return {
            "kind": self.kind,
            "market_id": self.market_id,
            "granted_at_ms": self.granted_at_ms,
            "news": [item.to_dict() for item in self.news],
            "trades": [trade.to_dict() for trade in self.trades],
        }


@dataclass(frozen=True, slots=True)
class ResearchView:
    units_remaining: int
    granted: tuple[ResearchGrant, ...] = ()

    def to_dict(self) -> dict[str, object]:
        return {
            "units_remaining": self.units_remaining,
            "granted": [grant.to_dict() for grant in self.granted],
        }


@dataclass(frozen=True, slots=True)
class Limits:
    """The caps the agent is being judged under, stated to it, so a reply that exceeds them is the
    agent's mistake and not a surprise."""

    bars_window: int
    news_per_market: int
    news_global: int
    hive_lessons: int
    hive_forecasts: int
    markets_per_obs_max: int
    notes_max_chars: int
    lessons_per_bar_max: int
    lesson_max_chars: int
    research_units_total: int

    def to_dict(self) -> dict[str, object]:
        return {
            "bars_window": self.bars_window,
            "news_per_market": self.news_per_market,
            "news_global": self.news_global,
            "hive_lessons": self.hive_lessons,
            "hive_forecasts": self.hive_forecasts,
            "markets_per_obs_max": self.markets_per_obs_max,
            "notes_max_chars": self.notes_max_chars,
            "lessons_per_bar_max": self.lessons_per_bar_max,
            "lesson_max_chars": self.lesson_max_chars,
            "research_units_total": self.research_units_total,
        }


def limits_from_config(config: RunConfig, *, research_units_total: int) -> Limits:
    """The one spelling of "the limits of this run", so E1 and A5 cannot disagree about them."""
    return Limits(
        bars_window=config.bars_window,
        news_per_market=config.news_per_market,
        news_global=config.news_global,
        hive_lessons=config.hive_lessons,
        hive_forecasts=config.hive_forecasts,
        markets_per_obs_max=config.markets_per_obs_max,
        notes_max_chars=NOTES_MAX_CHARS,
        lessons_per_bar_max=LESSONS_PER_BAR_MAX,
        lesson_max_chars=LESSON_MAX_CHARS,
        research_units_total=research_units_total,
    )


@dataclass(frozen=True, slots=True)
class Observation:
    """Everything one agent may know at one bar, and nothing else (section 8.3).

    The builder applies the as-of rules by **filtering**, never by trusting the agent, and this structure
    is what a leak test reads: the recursive key set of ``to_dict()`` may not contain
    ``resolved_at_ms``, ``n_bars``, ``bars_remaining``, ``bar_index``, ``t1_ms``, ``resolution``,
    ``resolution_source``, ``hardness_tags``, ``quality``, ``fold`` or ``final_price_bp``.
    """

    obs_version: str
    agent_id: str
    now_ms: int
    interval_min: int
    markets: tuple[MarketView, ...]
    news: tuple[NewsView, ...]
    portfolio: PortfolioView
    memory: MemoryView
    hive: HiveView
    research: ResearchView
    limits: Limits

    def to_dict(self) -> dict[str, object]:
        return {
            "obs_version": self.obs_version,
            "agent_id": self.agent_id,
            "now_ms": self.now_ms,
            "interval_min": self.interval_min,
            "markets": [view.to_dict() for view in self.markets],
            "news": [item.to_dict() for item in self.news],
            "portfolio": self.portfolio.to_dict(),
            "memory": self.memory.to_dict(),
            "hive": self.hive.to_dict(),
            "research": self.research.to_dict(),
            "limits": self.limits.to_dict(),
        }


# --------------------------------------------------------------------------------------------------
# 8.4 The actions
# --------------------------------------------------------------------------------------------------
class RejectReason(StrEnum):
    """Why an action, an order or a reply was refused. One enum, so the projection and the UI can count
    refusals by reason without a per-package spelling (section 8.4)."""

    UNKNOWN_MARKET = "unknown_market"
    DUPLICATE = "duplicate"
    BAD_PROB = "bad_prob"
    BAD_KIND = "bad_kind"
    MISSING_FIELD = "missing_field"
    BAD_PRICE = "bad_price"
    BAD_SIZE = "bad_size"
    BAD_TTL = "bad_ttl"
    NOTES_TOO_LONG = "notes_too_long"
    TOO_MANY_LESSONS = "too_many_lessons"
    LESSON_TOO_LONG = "lesson_too_long"
    BAD_RESEARCH = "bad_research"
    SCHEMA_INVALID = "schema_invalid"
    NOT_TRADABLE = "not_tradable"
    INSUFFICIENT_CASH = "insufficient_cash"
    ZERO_SIZE = "zero_size"
    RUINED = "ruined"
    BUDGET_EXCEEDED = "budget_exceeded"
    AGENT_TIMEOUT = "agent_timeout"
    PROVIDER_ERROR = "provider_error"
    MALFORMED_RESPONSE = "malformed_response"
    #: Amendment C1b (17.5, ruling R157): a horizon outside ``config.horizons_bars``, and a non-monotone
    #: or wrong-length quantile tuple.
    BAD_HORIZON = "bad_horizon"
    BAD_QUANTILES = "bad_quantiles"


@dataclass(frozen=True, slots=True)
class MarketAction:
    """One agent's move on one market for one bar.

    ``prob_ppm`` is always required, whatever the ``kind``: the forecast is the thing being scored, and a
    ``hold`` that carried no probability would let an agent trade without ever being judged. A ``hold``
    never produces an order and never produces an ``order_placed`` event, and a ``target`` equal to the
    current position produces no order either (never a size-zero order).
    """

    market_id: str
    prob_ppm: int
    kind: str
    target_position: int | None = None
    side: str | None = None
    price_bp: int | None = None
    size: int | None = None
    ttl_bars: int | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "market_id": self.market_id,
            "prob_ppm": self.prob_ppm,
            "kind": self.kind,
            "target_position": self.target_position,
            "side": self.side,
            "price_bp": self.price_bp,
            "size": self.size,
            "ttl_bars": self.ttl_bars,
        }


@dataclass(frozen=True, slots=True)
class ResearchRequest:
    """A request granted at the **next** bar, costing ``RESEARCH_UNIT_COST[kind]`` units."""

    kind: str
    market_id: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {"kind": self.kind, "market_id": self.market_id}


@dataclass(frozen=True, slots=True)
class Lesson:
    """A lesson an agent wrote this bar, with the markets that are its evidence."""

    text: str
    market_ids: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, object]:
        return {"text": self.text, "market_ids": list(self.market_ids)}


@dataclass(frozen=True, slots=True)
class HorizonForecast:
    """One agent's statement on one continuous instrument at one horizon (17.5, ruling R157).

    ``up_probability_ppm`` is ``P(price at the horizon > the reference price)`` and ``quantiles_ticks``
    the five prices at ``QUANTILE_LEVELS_PPM``, non-decreasing, or ``None`` for an agent that states a
    direction only. The runner validates the horizon against the config and the tuple's shape; this
    record only freezes what it is handed.
    """

    market_id: str
    horizon_bars: int
    up_probability_ppm: int
    quantiles_ticks: tuple[int, ...] | None = None

    def __post_init__(self) -> None:
        if self.quantiles_ticks is not None and not isinstance(self.quantiles_ticks, tuple):
            object.__setattr__(self, "quantiles_ticks", tuple(self.quantiles_ticks))

    def to_dict(self) -> dict[str, object]:
        return {
            "market_id": self.market_id,
            "horizon_bars": self.horizon_bars,
            "up_probability_ppm": self.up_probability_ppm,
            "quantiles_ticks": None if self.quantiles_ticks is None else list(self.quantiles_ticks),
        }


@dataclass(frozen=True, slots=True)
class Actions:
    """One agent's whole reply for one bar (``actions.v2.json``).

    ``rationale`` is LLM-only and goes to ``llm_trace.jsonl``, never to the journal: what the model said
    about its reasoning is not something a replay needs, and it is not reproducible.
    ``horizon_forecasts`` is amendment C1b's (17.5): one per ``(market_id, horizon_bars)`` on the open
    continuous instruments; a scripted binary family sends ``()``.
    """

    actions_version: str
    markets: tuple[MarketAction, ...] = ()
    research: ResearchRequest | None = None
    notes: str = ""
    lessons: tuple[Lesson, ...] = ()
    rationale: str | None = None
    horizon_forecasts: tuple[HorizonForecast, ...] = ()

    def to_dict(self) -> dict[str, object]:
        return {
            "actions_version": self.actions_version,
            "markets": [action.to_dict() for action in self.markets],
            "research": None if self.research is None else self.research.to_dict(),
            "notes": self.notes,
            "lessons": [lesson.to_dict() for lesson in self.lessons],
            "rationale": self.rationale,
            "horizon_forecasts": [forecast.to_dict() for forecast in self.horizon_forecasts],
        }
