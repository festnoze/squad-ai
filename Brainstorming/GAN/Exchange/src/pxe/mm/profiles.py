"""The three FR-5.8.6 liquidity presets, and the T2.6 cost of liquidity study.

Two responsibilities, both about *profiles* rather than about quoting:

* :func:`mm_config_for` resolves a preset name to the
  :class:`~pxe.types.MMConfig` of :data:`pxe.types.LIQUIDITY_PROFILES`. The
  table lives in :mod:`pxe.types` and not here, because ``MatchConfig.mm``
  defaults to the standard preset and :mod:`pxe.types` may import nothing.
* the cost of liquidity study (PRD T2.6, FR-5.8.5) reduces a set of finished
  match journals to one row per profile, which is what ``pxe mm study --profile
  <p> --matches 200`` publishes into ``docs/MM_LIQUIDITY_COST.md``.

The study reads **journals and nothing else**. That is not a convenience: the
market maker PnL is the published cost of liquidity (FR-5.8.5) and decision 16
requires it to be recomputable from the journal alone, and a study that reached
into a live :class:`~pxe.exchange.accounts.AccountBook` would both break that
property and violate A07's import ban (CONTRACTS section 13, decision 28).
Every number below is therefore derived from ``mm_quoted``, ``trade_executed``
and ``settlement_applied`` events, which means the same function scores a
scripted match, an LLM match and a replayed journal identically.

This module is pure: no clock, no filesystem, no network. Rendering returns a
string and the caller (``pxe.cli``, A23) writes the file.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from pxe.errors import InvalidConfigError
from pxe.events import Event, MMQuoted, SettlementApplied, TradeExecuted
from pxe.types import (
    MILLI_ONE,
    MM_ACCOUNT_ID,
    PPM_ONE,
    LiquidityProfileName,
    MMConfig,
    liquidity_profile,
    sorted_ids,
)

__all__ = [
    "mm_config_for",
    "LiquidityCostRow",
    "LiquidityStudy",
    "liquidity_cost_row",
    "build_liquidity_study",
    "render_liquidity_study",
]

#: Neutral valuation price, in cents, used for a residual market maker position
#: on a market that produced no quote at all. Unreachable in a real match, since
#: the market maker quotes every open market on every tick (FR-5.8.1).
_NEUTRAL_PRICE_CENTS = 50


def mm_config_for(name: str | LiquidityProfileName) -> MMConfig:
    """Return the market maker parameters of one FR-5.8.6 preset.

    Args:
        name: ``"liquid"``, ``"standard"`` or ``"illiquid"``, as a string or as
            a :class:`~pxe.types.LiquidityProfileName`.

    Returns:
        The preset's :class:`~pxe.types.MMConfig`. It is a frozen dataclass, so
        the caller cannot mutate the shared table.

    Raises:
        UnknownProfileError: If the name is not one of the three presets.
    """
    return liquidity_profile(name).mm


@dataclass(frozen=True)
class LiquidityCostRow:
    """What one liquidity preset cost, measured over a set of match journals.

    Money is cents, ratios are parts per million and the mean spread is
    thousandths of a cent, per CONTRACTS section 2.1: the study is journalled
    into a document and must not carry a float.

    Attributes:
        profile_name: The preset measured.
        base_spread_cents: ``MMConfig.base_spread_cents`` of that preset, so the
            document states the target next to the measurement.
        quote_qty: ``MMConfig.quote_qty`` of that preset.
        inventory_max: ``MMConfig.inventory_max`` of that preset.
        matches: Number of journals aggregated.
        quotes: Number of ``mm_quoted`` events seen, that is (tick, market)
            pairs the market maker acted on.
        two_sided_quotes: How many of those showed both a bid and an ask.
        two_sided_ppm: ``two_sided_quotes / quotes`` in parts per million. AC-P9
            requires at least ``950_000``.
        mean_effective_spread_milli: Mean ``ask - bid`` over **every** two sided
            quote, in thousandths of a cent. It is the spread an agent actually
            paid, so it is what the cost of liquidity is read against, and it
            sits **above** :attr:`base_spread_cents` by construction whenever
            FR-5.8.4 widened anything.
        mean_base_spread_milli: Mean ``ask - bid`` over the two sided quotes
            that were **not** widened (``MMQuoted.widened is False``), in
            thousandths of a cent. This, and not
            :attr:`mean_effective_spread_milli`, is the FR-5.8.6 measurement:
            "the mean spread of a preset is within one cent of the preset" is a
            statement about the recipe, and FR-5.8.4 deliberately doubles the
            spread for ``w`` ticks after a high impact news item. Measuring the
            recipe over the widened ticks too would make FR-5.8.6 and FR-5.8.4
            contradict each other in the same document, which is exactly what
            the first published version of ``docs/MM_LIQUIDITY_COST.md`` did
            (see ruling R96).
        widened_quotes: How many two sided quotes carried ``widened=True``. It
            is published because a study where it is zero has not exercised
            FR-5.8.4 at all, and then the two spreads above are the same number
            twice.
        max_abs_inventory_qty: Largest absolute market maker inventory observed
            on any market. Invariant I10 requires it at or below
            :attr:`inventory_max`.
        mm_trades: Executions the market maker was a party to.
        mm_volume_qty: Contracts the market maker traded.
        mm_realised_cents: Cash the market maker gained or lost through
            executions and settlements, summed over the journals.
        mm_inventory_value_cents: Value of the market maker positions still open
            at the end of each journal, marked at the last reference price it
            quoted off. Zero for a finished match, where finalisation settles
            every market.
        mm_pnl_cents: :attr:`mm_realised_cents` plus
            :attr:`mm_inventory_value_cents`. Negative means the market maker
            paid for the liquidity it provided, which is the expected sign.
        mm_pnl_cents_per_match: :attr:`mm_pnl_cents` divided by
            :attr:`matches`, rounded toward zero.
    """

    profile_name: str
    base_spread_cents: int
    quote_qty: int
    inventory_max: int
    matches: int
    quotes: int
    two_sided_quotes: int
    two_sided_ppm: int
    mean_effective_spread_milli: int
    mean_base_spread_milli: int
    widened_quotes: int
    max_abs_inventory_qty: int
    mm_trades: int
    mm_volume_qty: int
    mm_realised_cents: int
    mm_inventory_value_cents: int
    mm_pnl_cents: int
    mm_pnl_cents_per_match: int


@dataclass(frozen=True)
class LiquidityStudy:
    """The whole T2.6 measurement: one row per preset plus how it was produced.

    Attributes:
        seed: Root seed the matches were generated from, so the document states
            how to reproduce itself.
        ticks_total: Horizon of one match.
        n_markets: Markets per match.
        n_agents: Ranked agents per match.
        rows: One :class:`LiquidityCostRow` per preset, in the order of
            :data:`pxe.types.LIQUIDITY_PROFILES`.
    """

    seed: int
    ticks_total: int
    n_markets: int
    n_agents: int
    rows: tuple[LiquidityCostRow, ...]


def _mean_toward_zero(total: int, count: int) -> int:
    """Integer mean rounded toward zero, so a gain and the mirror loss agree.

    ``//`` rounds toward minus infinity on a signed numerator, which would
    overstate the market maker's loss by up to one cent per preset and report a
    different magnitude for a gain than for the mirror loss (CONTRACTS section
    2.1).

    Args:
        total: Signed total in cents.
        count: Number of matches, ``> 0``.

    Returns:
        ``total / count`` truncated toward zero, ``0`` when ``count`` is ``0``.
    """
    if count == 0:
        return 0
    magnitude = abs(total) // count
    return -magnitude if total < 0 else magnitude


@dataclass
class _QuoteTally:
    """Running counts over the ``mm_quoted`` events of a liquidity study.

    It exists so :func:`liquidity_cost_row` keeps one statement per concept:
    the two spreads FR-5.8.6 and FR-5.8.4 need are six counters, and inlining
    them made the row builder a wall of increments.
    """

    quotes: int = 0
    two_sided: int = 0
    spread_sum: int = 0
    base_quotes: int = 0
    base_spread_sum: int = 0
    widened: int = 0

    def add(self, event: MMQuoted) -> None:
        """Fold one quote in.

        Args:
            event: The ``mm_quoted`` event to count.
        """
        self.quotes += 1
        if event.bid_price is None or event.ask_price is None:
            return
        spread = event.ask_price - event.bid_price
        self.two_sided += 1
        self.spread_sum += spread
        if event.widened:
            self.widened += 1
        else:
            self.base_quotes += 1
            self.base_spread_sum += spread

    def mean_effective_milli(self) -> int:
        """Return the mean spread over every two sided quote, in milli-cents."""
        return 0 if self.two_sided == 0 else (self.spread_sum * MILLI_ONE) // self.two_sided

    def mean_base_milli(self) -> int:
        """Return the mean spread over the quotes FR-5.8.4 did not widen."""
        return 0 if self.base_quotes == 0 else (self.base_spread_sum * MILLI_ONE) // self.base_quotes

    def two_sided_ppm(self) -> int:
        """Return the AC-P9 two sided ratio in parts per million."""
        return 0 if self.quotes == 0 else (self.two_sided * PPM_ONE) // self.quotes


def liquidity_cost_row(
    *,
    profile_name: str | LiquidityProfileName,
    journals: Sequence[Sequence[Event]],
) -> LiquidityCostRow:
    """Reduce a set of match journals to the cost of one liquidity preset.

    Everything is read off events, in ``seq`` order inside each journal:

    * ``mm_quoted`` gives the two sided ratio (AC-P9), the effective spread
      (FR-5.8.6), the inventory the market maker saw and the reference price to
      mark a residual position at;
    * ``trade_executed`` gives the market maker's cash deltas and, through
      ``maker_position_after`` / ``taker_position_after``, its running
      inventory. ``taker_cash_delta_cents`` is already net of
      ``taker_fee_cents`` (invariant I5), so the fee must not be subtracted
      twice;
    * ``settlement_applied`` gives the cash a resolution or an unwind moved.

    Args:
        profile_name: The preset the journals were produced under. It is used to
            look the target parameters up, so a mislabelled call produces an
            obviously wrong row rather than a plausible one.
        journals: One event sequence per match. May be empty.

    Returns:
        The aggregated :class:`LiquidityCostRow`.

    Raises:
        UnknownProfileError: If ``profile_name`` is not one of the three presets.
        InvalidConfigError: If a journal holds no ``mm_quoted`` event at all.
            The market maker quotes every open market on every tick (FR-5.8.1),
            so a journal without one is either a match the market maker never
            ran in or a disabled preset, and averaging it in would silently
            report a spread of zero as "within one cent of the profile".
    """
    mm_config = mm_config_for(profile_name)
    tally = _QuoteTally()
    max_abs_inventory = 0
    mm_trades = 0
    mm_volume = 0
    realised_cents = 0
    inventory_value_cents = 0

    for index, events in enumerate(journals):
        last_ref_price: dict[str, int] = {}
        inventory: dict[str, int] = {}
        seen_quote = False
        for event in events:
            if isinstance(event, MMQuoted):
                seen_quote = True
                tally.add(event)
                last_ref_price[event.market_id] = event.ref_price
                max_abs_inventory = max(max_abs_inventory, abs(event.inventory_qty))
            elif isinstance(event, TradeExecuted):
                if event.maker_agent_id == MM_ACCOUNT_ID:
                    mm_trades += 1
                    mm_volume += event.qty
                    realised_cents += event.maker_cash_delta_cents
                    inventory[event.market_id] = event.maker_position_after
                if event.taker_agent_id == MM_ACCOUNT_ID:
                    mm_trades += 1
                    mm_volume += event.qty
                    realised_cents += event.taker_cash_delta_cents
                    inventory[event.market_id] = event.taker_position_after
                if MM_ACCOUNT_ID in (event.maker_agent_id, event.taker_agent_id):
                    max_abs_inventory = max(max_abs_inventory, abs(inventory[event.market_id]))
            elif isinstance(event, SettlementApplied) and event.account_id == MM_ACCOUNT_ID:
                realised_cents += event.cash_delta_cents
                inventory[event.market_id] = 0
        if not seen_quote:
            raise InvalidConfigError("a journal of the liquidity study holds no mm_quoted event", journal_index=index)
        # Value what is still open at the last public price the market maker
        # quoted off. In a finished match every market is settled at
        # finalisation, so every entry is zero and this term vanishes.
        for market_id in sorted_ids(tuple(inventory)):
            qty = inventory[market_id]
            if qty != 0:
                inventory_value_cents += qty * last_ref_price.get(market_id, _NEUTRAL_PRICE_CENTS)

    matches = len(journals)
    pnl_cents = realised_cents + inventory_value_cents
    return LiquidityCostRow(
        profile_name=str(liquidity_profile(profile_name).name),
        base_spread_cents=mm_config.base_spread_cents,
        quote_qty=mm_config.quote_qty,
        inventory_max=mm_config.inventory_max,
        matches=matches,
        quotes=tally.quotes,
        two_sided_quotes=tally.two_sided,
        two_sided_ppm=tally.two_sided_ppm(),
        mean_effective_spread_milli=tally.mean_effective_milli(),
        mean_base_spread_milli=tally.mean_base_milli(),
        widened_quotes=tally.widened,
        max_abs_inventory_qty=max_abs_inventory,
        mm_trades=mm_trades,
        mm_volume_qty=mm_volume,
        mm_realised_cents=realised_cents,
        mm_inventory_value_cents=inventory_value_cents,
        mm_pnl_cents=pnl_cents,
        mm_pnl_cents_per_match=_mean_toward_zero(pnl_cents, matches),
    )


def build_liquidity_study(
    *,
    seed: int,
    ticks_total: int,
    n_markets: int,
    n_agents: int,
    journals_by_profile: Mapping[str, Sequence[Sequence[Event]]],
) -> LiquidityStudy:
    """Assemble the T2.6 study from the journals of every preset.

    Args:
        seed: Root seed the matches were generated from.
        ticks_total: Horizon of one match.
        n_markets: Markets per match.
        n_agents: Ranked agents per match.
        journals_by_profile: Journals keyed by preset name. Keys are looked up
            in the fixed order of :data:`pxe.types.LIQUIDITY_PROFILES`, never
            iterated, so a caller's dict order cannot change the document
            (CONTRACTS section 2.3).

    Returns:
        The :class:`LiquidityStudy`, with one row per preset present in the
        mapping.

    Raises:
        InvalidConfigError: If the mapping is empty, or holds a key that is not
            one of the three presets.
    """
    if not journals_by_profile:
        raise InvalidConfigError("the liquidity study needs at least one profile")
    known = tuple(str(member) for member in LiquidityProfileName)
    for key in journals_by_profile:
        if key not in known:
            raise InvalidConfigError("unknown liquidity profile in the study", name=key)
    rows = tuple(
        liquidity_cost_row(profile_name=name, journals=journals_by_profile[name])
        for name in known
        if name in journals_by_profile
    )
    return LiquidityStudy(
        seed=seed,
        ticks_total=ticks_total,
        n_markets=n_markets,
        n_agents=n_agents,
        rows=rows,
    )


def render_liquidity_study(study: LiquidityStudy) -> str:
    """Render the study as the Markdown of ``docs/MM_LIQUIDITY_COST.md``.

    The function returns a string and writes nothing: :mod:`pxe.mm` is inside
    the pure half of the purity boundary (CONTRACTS section 2.7), so the caller
    (``pxe mm study``, A23) owns the file handle.

    Args:
        study: The measurement to render.

    Returns:
        A Markdown document, LF terminated, with no em-dash (contract rule 4).

    Raises:
        InvalidConfigError: If the study holds no row.
    """
    if not study.rows:
        raise InvalidConfigError("nothing to render: the study holds no row")
    lines: list[str] = [
        "# Cost of liquidity of the reference market maker",
        "",
        "Generated by `pxe mm study`. Do not edit by hand.",
        "",
        "This document answers T2.6 and FR-5.8.5: what the reference market maker",
        "(PRD section 5.8) pays to keep every market two sided, per liquidity preset.",
        "The market maker PnL is excluded from the ranking and from the ratings and is",
        "published here instead. Every number is read from finished match journals, so",
        "it is reproducible from the journals alone (decision 16).",
        "",
        "## How it was measured",
        "",
        f"- root seed: `{study.seed}`",
        f"- ticks per match: {study.ticks_total}",
        f"- markets per match: {study.n_markets}",
        f"- ranked agents per match: {study.n_agents}",
        f"- matches per preset: {study.rows[0].matches}",
        "",
        "Money is cents. A negative market maker PnL means the market maker paid for the",
        "liquidity it provided: it quotes off the public reference price only (FR-5.8.2)",
        "and is therefore adversely selected by any agent that knows more than the price",
        "does. The sign is not guaranteed and is itself the measurement: a preset whose",
        "spread is wide relative to the information in the flow collects more from",
        "uninformed crossings than it loses to informed ones and comes out ahead. That is",
        "the same dial seen from the other end, and it is why the number is published per",
        "preset rather than asserted once.",
        "",
        "## Result",
        "",
        "| Preset | Target spread | Base spread | Effective spread | Widened quotes | Two sided "
        "| Max abs inventory | I_max | MM trades | MM PnL per match | MM PnL total |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for row in study.rows:
        base_spread = f"{row.mean_base_spread_milli / MILLI_ONE:.3f}"
        mean_spread = f"{row.mean_effective_spread_milli / MILLI_ONE:.3f}"
        widened_pct = f"{0.0 if row.two_sided_quotes == 0 else 100.0 * row.widened_quotes / row.two_sided_quotes:.2f}"
        two_sided_pct = f"{row.two_sided_ppm / (PPM_ONE // 100):.2f}"
        lines.append(
            f"| {row.profile_name} | {row.base_spread_cents} c | {base_spread} c | {mean_spread} c "
            f"| {widened_pct} % | {two_sided_pct} % | {row.max_abs_inventory_qty} | {row.inventory_max} "
            f"| {row.mm_trades} | {row.mm_pnl_cents_per_match} | {row.mm_pnl_cents} |"
        )
    lines += [
        "",
        "## Acceptance criteria of T2.6",
        "",
        "| Criterion | Requirement | Result |",
        "|---|---|---|",
    ]
    for row in study.rows:
        spread_delta = abs(row.mean_base_spread_milli - row.base_spread_cents * MILLI_ONE)
        lines.append(
            f"| {row.profile_name}: two sided quote per open market and tick | >= 95 % | "
            f"{row.two_sided_ppm / (PPM_ONE // 100):.2f} % |"
        )
        lines.append(
            f"| {row.profile_name}: base spread within one cent of the preset (FR-5.8.6) | "
            f"distance to {row.base_spread_cents} c is <= 1 c | {spread_delta / MILLI_ONE:.3f} c |"
        )
        lines.append(
            f"| {row.profile_name}: absolute inventory never above I_max | <= {row.inventory_max} | "
            f"{row.max_abs_inventory_qty} |"
        )
    lines += [
        "",
        "## Reading the numbers",
        "",
        "- the spread is the cost of expressing a belief, so it is the difficulty dial of",
        "  the arena: the `illiquid` preset makes an informed agent pay several times more",
        "  per unit of conviction than the `liquid` one for the same edge;",
        "- the market maker PnL is the arena's difficulty read backwards: where it loses",
        "  money the agents are being paid to be right, and where it gains the spread is",
        "  wide enough that being right no longer pays for the crossing;",
        "- the quoted size `q` bounds how much of an edge one agent can harvest in a single",
        "  tick, and the inventory cap `I_max` bounds how long the market maker keeps",
        "  absorbing a one directional flow before it stops showing that side (FR-5.8.3);",
        "- the market maker never widens on the content of a news item, only on the fact",
        "  that a high impact one landed (FR-5.8.4), so the widening is symmetric and",
        "  carries no directional information for an agent to read.",
        "",
    ]
    return "\n".join(lines)
