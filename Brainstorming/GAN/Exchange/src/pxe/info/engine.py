"""The information engine: public news and private signals (A04, CONTRACTS 7.6).

``InfoEngine`` is **pure**. Two instances built from the same world, the same
profiles and the same seed answer identically for any tick, in any call order,
and neither the filesystem, the clock nor engine state is ever consulted. Three
properties buy that, and each one is load bearing:

1. **Every draw comes from a fresh substream.** Per tick content uses
   ``info.news.tick.<tick>`` and ``info.signals.tick.<tick>``, obtained through
   :meth:`pxe.rng.RngTree.fresh_substream`, so the content of tick ``t`` is a
   function of ``(seed, t)`` alone and never of how many draws an earlier call
   happened to consume. Calling ``signals_for_tick(7)`` before
   ``signals_for_tick(3)`` changes nothing, which is exactly what a replay
   needs.
2. **Match level calibration is drawn once, in ``__init__``**, from the four
   exact substreams ``info.schedule``, ``info.news``, ``info.noise`` and
   ``info.profiles``. Those are the per market noise levels, the news sources,
   the news calendar itself and the per seat attention weights.
3. **The engine is never told what has resolved.** ``__init__`` receives a
   world, a profile mapping, an ``RngTree`` and a horizon, and not one of them
   is a live view of engine state. A private signal about a market that is no
   longer tradable is therefore drawn here and dropped by the **runner** at P1
   step 3 (CONTRACTS section 5, decision 37). That order is deliberate: the
   ``info.signals.tick.<tick>`` stream consumes the same draws whether a signal
   survives or not, so the information stream cannot depend on resolution
   history and FR-5.1.4 holds.

``profiles`` is a ``Mapping`` and :meth:`signals_for_tick` loops over agents, so
CONTRACTS section 2.3 applies literally: the loop iterates
``sorted_ids(profiles.keys())`` and never ``profiles.items()``. A caller that
built the mapping in seat order and a caller that built it in harness order
would otherwise draw the per agent signals in a different order out of the same
substream and produce two different journals from one seed.
"""

from __future__ import annotations

import random
from collections.abc import Mapping
from dataclasses import dataclass

from pxe.errors import InvalidConfigError
from pxe.info.noise import (
    BASE_PUBLIC_SIGMA_MILLI,
    BASE_SIGNAL_SIGMA_MILLI,
    DELAY_SIGMA_PENALTY_MILLI,
    FOCUS_NOISE_SCALE_PPM,
    OUTSIDE_FOCUS_NOISE_SCALE_PPM,
    SIGMA_MAX_MILLI,
    direction_milli,
    noisy_latent_milli,
    precision_ppm_for_sigma,
    probability_milli_from_latent,
    pure_noise_latent_milli,
    scaled_sigma_milli,
    threshold_milli,
)
from pxe.info.profiles import SIGNALS_MAX_PER_TICK
from pxe.rng import RngTree, bernoulli, choice, choices_weighted, randint
from pxe.types import (
    PPM_ONE,
    InfoProfile,
    NewsImpact,
    NewsItem,
    Outcome,
    Signal,
    SignalKind,
    make_news_id,
    make_signal_id,
    sorted_ids,
)
from pxe.world.generator import World

__all__ = ["InfoEngine", "NEWS_MAX_PER_TICK", "NEWS_SOURCES"]

#: Hard cap on the number of information engine items published in one tick.
#: ``schemas/observation.v1.json`` accepts twenty ``news`` entries and the runner
#: appends one further item per market resolved or cancelled at the same tick
#: (P1 steps 4d and 5), so the engine keeps a margin instead of spending the
#: whole budget and letting a resolution heavy tick overflow the schema.
NEWS_MAX_PER_TICK = 12

#: Named publishers a headline is attributed to. Cosmetic, drawn once per market
#: from the ``info.news`` substream, and identical for a genuine reading and a
#: pure noise item: an agent must not be able to spot
#: :attr:`pxe.types.NewsItem.is_noise` from the wording, only from the long run
#: behaviour of the value.
NEWS_SOURCES: tuple[str, ...] = (
    "Meridian Institute",
    "Northgate Panel",
    "Civic Ledger",
    "Harbour Review",
    "Talbot Survey",
    "Fairhaven Desk",
    "Ostend Monitor",
    "Rowan Bureau",
)

#: Probability, in ppm, that a slot the calendar believes informative is
#: published as pure noise instead (PRD section 5.3, "qualite variable").
DEGRADE_TO_NOISE_PPM = 150_000

#: Probability, in ppm, that a ``MEDIUM`` slot is promoted to ``HIGH``. Drawn
#: from ``info.schedule`` and never from the latent value, so the impact tag
#: stays a statement about the *fact* that information landed and leaks no
#: direction (FR-5.8.4).
UPGRADE_TO_HIGH_PPM = 250_000

#: Relative weight multiplier of a specialist's focus market when the engine
#: picks what its next signal is about.
FOCUS_PICK_WEIGHT = 6

#: Bounds of the per market noise jitter drawn at construction, in ppm. Markets
#: are not equally legible, and a flat noise level across a world would make the
#: specialist profile the only source of asymmetry.
MARKET_NOISE_JITTER_MIN_PPM = 850_000
MARKET_NOISE_JITTER_MAX_PPM = 1_200_000

#: Bounds of the per seat, per market attention weight drawn at construction.
ATTENTION_WEIGHT_MIN = 8
ATTENTION_WEIGHT_MAX = 12

#: Cumulative percentage thresholds selecting a :class:`pxe.types.SignalKind`.
#: A point estimate is the majority case because it is the only shape that
#: carries a full reading, and FR-5.3.1 asks a Bayesian agent to beat a random
#: one from the signal stream alone.
KIND_POINT_ESTIMATE_MAX = 70
KIND_DIRECTION_MAX = 88

_HEADLINE_MAX_CHARS = 120
_BODY_MAX_CHARS = 400
_PERCENT_PER_MILLI = 10


@dataclass(frozen=True)
class _NewsSlot:
    """One resolved calendar slot, fixed at construction.

    Attributes:
        market_ids: Markets the item refers to, sorted, possibly empty.
        impact: Final impact tag, after the ``info.schedule`` promotion draw.
        is_noise: True when the slot publishes a value independent of the latent
            state.
        source: Publisher the headline is attributed to.
    """

    market_ids: tuple[str, ...]
    impact: NewsImpact
    is_noise: bool
    source: str


def _clip(text: str, limit: int) -> str:
    """Shorten ``text`` to ``limit`` characters.

    :class:`pxe.types.NewsItem` raises when a headline or a body is too long, so
    the engine clips rather than trusting a question length it does not own.

    Args:
        text: Text to shorten.
        limit: Maximum number of characters, ``>= 1``.

    Returns:
        ``text`` unchanged when it fits, otherwise its first ``limit``
        characters with the last one replaced by a full stop.
    """
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "."


class InfoEngine:
    """The per match source of public news and private signals (CONTRACTS 7.6)."""

    def __init__(
        self,
        *,
        world: World,
        profiles: Mapping[str, InfoProfile],
        rng: RngTree,
        ticks_total: int,
    ) -> None:
        """Build the engine and draw its match level calibration.

        Args:
            world: The generated world (A03). Its ``news_plan`` is the calendar
                and its ``latent`` process is what every observation is a noisy
                view of.
            profiles: One :class:`pxe.types.InfoProfile` per ranked seat, keyed
                by agent id. Iterated through ``sorted_ids`` and never in
                mapping order (section 2.3).
            rng: The ``info`` sub-tree, that is ``root.child("info")``, built by
                the runner (section 3.1).
            ticks_total: Horizon ``T``, ``>= 1``. Slots outside ``1..T`` are
                dropped from the calendar.

        Raises:
            InvalidConfigError: If ``ticks_total`` is under one, if a profile is
                keyed by something that is not a ranked agent id, or if a
                profile focuses on a market this world does not have.
        """
        if ticks_total < 1:
            raise InvalidConfigError("ticks_total must be >= 1", ticks_total=ticks_total)
        self._world = world
        self._rng = rng
        self._ticks_total = ticks_total
        self._agent_ids: tuple[str, ...] = sorted_ids(list(profiles.keys()))
        self._profiles: dict[str, InfoProfile] = {agent_id: profiles[agent_id] for agent_id in self._agent_ids}
        self._market_ids: tuple[str, ...] = world.market_ids()
        self._latent_key_of: dict[str, str] = {market.market_id: market.latent_key for market in world.scenario.markets}
        self._question_of: dict[str, str] = {market.market_id: market.question for market in world.scenario.markets}
        self._check_focus_markets()

        news_rng = rng.fresh_substream("info.news")
        self._source_of: dict[str, str] = {market_id: choice(news_rng, NEWS_SOURCES) for market_id in self._market_ids}
        noise_rng = rng.fresh_substream("info.noise")
        self._public_sigma_of: dict[str, int] = {
            market_id: scaled_sigma_milli(
                BASE_PUBLIC_SIGMA_MILLI,
                scale_ppm=randint(noise_rng, MARKET_NOISE_JITTER_MIN_PPM, MARKET_NOISE_JITTER_MAX_PPM),
            )
            for market_id in self._market_ids
        }
        signal_rng = rng.fresh_substream("info.signals")
        self._signal_sigma_of: dict[str, int] = {
            market_id: scaled_sigma_milli(
                BASE_SIGNAL_SIGMA_MILLI,
                scale_ppm=randint(signal_rng, MARKET_NOISE_JITTER_MIN_PPM, MARKET_NOISE_JITTER_MAX_PPM),
            )
            for market_id in self._market_ids
        }
        profile_rng = rng.fresh_substream("info.profiles")
        self._attention_of: dict[str, tuple[int, ...]] = {
            agent_id: tuple(randint(profile_rng, ATTENTION_WEIGHT_MIN, ATTENTION_WEIGHT_MAX) for _ in self._market_ids)
            for agent_id in self._agent_ids
        }
        self._calendar: dict[int, tuple[_NewsSlot, ...]] = self._build_calendar()

    # ------------------------------------------------------------------
    # Construction helpers
    # ------------------------------------------------------------------
    def _check_focus_markets(self) -> None:
        """Refuse a profile focusing on a market this world does not have.

        Raises:
            InvalidConfigError: If a focus market is unknown.
        """
        for agent_id in self._agent_ids:
            for market_id in self._profiles[agent_id].focus_market_ids:
                if market_id not in self._latent_key_of:
                    raise InvalidConfigError(
                        "profile focuses on an unknown market",
                        agent_id=agent_id,
                        market_id=market_id,
                        market_ids=list(self._market_ids),
                    )

    def _build_calendar(self) -> dict[int, tuple[_NewsSlot, ...]]:
        """Turn the world's ``news_plan`` into the engine's own calendar.

        The plan (A03) says *when* something is published and about which
        markets; the engine decides the final impact tag and which slots are
        pure noise. Both decisions come from ``info.schedule`` and neither reads
        the latent value, so the tags are a function of the seed alone and the
        FR-5.8.4 widening they drive is reproducible.

        Returns:
            ``{tick: slots}``, at most :data:`NEWS_MAX_PER_TICK` slots per tick,
            in publication order. The mapping is a lookup table only: nothing
            iterates it to produce output (section 2.3).
        """
        schedule_rng = self._rng.fresh_substream("info.schedule")
        by_tick: dict[int, list[_NewsSlot]] = {}
        for item in self._world.news_plan:
            if not 1 <= item.tick <= self._ticks_total:
                continue
            # Both draws are unconditional, and that is deliberate: a
            # short circuited ``or`` would make the number of draws consumed
            # depend on the plan's own flags, so re-tagging one slot would
            # silently shift every following slot's quality.
            degraded = bernoulli(schedule_rng, DEGRADE_TO_NOISE_PPM / PPM_ONE)
            promoted = bernoulli(schedule_rng, UPGRADE_TO_HIGH_PPM / PPM_ONE)
            is_noise = item.is_noise or degraded
            impact = NewsImpact.HIGH if (item.impact is NewsImpact.MEDIUM and promoted) else item.impact
            primary = item.market_ids[0] if item.market_ids else ""
            by_tick.setdefault(item.tick, []).append(
                _NewsSlot(
                    market_ids=item.market_ids,
                    impact=impact,
                    is_noise=is_noise,
                    source=self._source_of.get(primary, NEWS_SOURCES[0]),
                )
            )
        return {tick: tuple(by_tick[tick][:NEWS_MAX_PER_TICK]) for tick in sorted(by_tick)}

    # ------------------------------------------------------------------
    # Public news
    # ------------------------------------------------------------------
    def news_for_tick(self, tick: int) -> tuple[NewsItem, ...]:
        """Return the public news of ``tick``.

        Deterministic, in publication order, ids from
        :func:`pxe.types.make_news_id` with the index of the item inside the
        tick. The runner emits one ``NewsPublished`` per returned item with
        ``origin="info_engine"`` (P1 step 2) and hands the whole tick's news to
        the market maker once, at step 5b.

        Args:
            tick: Tick of publication, ``>= 1``. A tick beyond the horizon
                carries no scheduled slot and returns an empty tuple.

        Returns:
            The published items, possibly empty.

        Raises:
            InvalidConfigError: If ``tick`` is under one.
        """
        slots = self._slots_for_tick(tick)
        if not slots:
            return ()
        news_rng = self._rng.fresh_substream(f"info.news.tick.{tick}")
        items: list[NewsItem] = []
        for index, slot in enumerate(slots):
            observed_milli = self._observe_public(news_rng, slot=slot, tick=tick)
            percent = probability_milli_from_latent(observed_milli) // _PERCENT_PER_MILLI
            coverage = ", ".join(slot.market_ids) if slot.market_ids else "the wider field"
            question = self._question_of.get(slot.market_ids[0], "") if slot.market_ids else ""
            items.append(
                NewsItem(
                    news_id=make_news_id(tick, index),
                    tick=tick,
                    market_ids=slot.market_ids,
                    headline=_clip(f"{slot.source} on {coverage}: reading at {percent} percent", _HEADLINE_MAX_CHARS),
                    body=_clip(
                        f"{question} Published at tick {tick} by {slot.source}. "
                        f"Latest public reading: {percent} percent. Coverage: {coverage}.",
                        _BODY_MAX_CHARS,
                    ),
                    impact=slot.impact,
                    is_noise=slot.is_noise,
                )
            )
        return tuple(items)

    def high_impact_market_ids(self, tick: int) -> tuple[str, ...]:
        """Return the markets named by a ``HIGH`` impact news item at ``tick``.

        The market maker widens on the *fact* that a high impact item landed
        (FR-5.8.4), so this reads the calendar's tags and never the values: it
        consumes no per tick randomness and cannot leak a direction.

        Args:
            tick: Tick of publication, ``>= 1``.

        Returns:
            The market ids, deduplicated and in canonical order (section 2.3).

        Raises:
            InvalidConfigError: If ``tick`` is under one.
        """
        collected: list[str] = []
        for slot in self._slots_for_tick(tick):
            if slot.impact is not NewsImpact.HIGH:
                continue
            for market_id in slot.market_ids:
                if market_id not in collected:
                    collected.append(market_id)
        return sorted_ids(collected)

    def resolution_news(self, *, tick: int, market_id: str, outcome: Outcome, index: int) -> NewsItem:
        """Build the item announcing that a market resolved.

        Impact is always ``HIGH``; origin is set by the runner (P1 step 4d). The
        item is a pure function of its arguments and draws nothing: a resolution
        is a fact, not an observation, so there is no noise to add.

        Args:
            tick: Tick the resolution is announced at, that is ``r + 1`` for a
                market whose ``resolution_tick`` is ``r`` (section 5.0).
            market_id: The resolved market.
            outcome: The published outcome.
            index: 0 based index of this item inside ``tick``, which the runner
                continues from the count of :meth:`news_for_tick`.

        Returns:
            The item.

        Raises:
            InvalidConfigError: If ``tick`` is under one, if ``index`` is
                negative, or if ``market_id`` is not part of this world.
        """
        self._check_item_args(tick=tick, market_id=market_id, index=index)
        question = self._question_of[market_id]
        return NewsItem(
            news_id=make_news_id(tick, index),
            tick=tick,
            market_ids=(market_id,),
            headline=_clip(f"Resolved: {market_id} settles {outcome.value.upper()}", _HEADLINE_MAX_CHARS),
            body=_clip(
                f"{question} The oracle resolved {market_id} to {outcome.value} at tick {tick}. "
                f"Each contract pays {outcome.payout_cents} cents; resting orders on this market were "
                "cancelled and positions settled.",
                _BODY_MAX_CHARS,
            ),
            impact=NewsImpact.HIGH,
            is_noise=False,
        )

    def cancellation_news(self, *, tick: int, market_id: str, reason: str, index: int) -> NewsItem:
        """Build the item announcing that a market was cancelled.

        Impact is always ``HIGH``; origin is set by the runner (P1 step 5).
        Without it ``NewsPublished.origin == "cancellation"`` and ``NewsDto``'s
        third origin value have no producer.

        Args:
            tick: Tick the cancellation fires at, that is the scheduled
                cancellation tick itself (P1 step 5).
            market_id: The cancelled market.
            reason: Free form reason carried by the scenario, echoed verbatim.
            index: 0 based index of this item inside ``tick``.

        Returns:
            The item.

        Raises:
            InvalidConfigError: If ``tick`` is under one, if ``index`` is
                negative, or if ``market_id`` is not part of this world.
        """
        self._check_item_args(tick=tick, market_id=market_id, index=index)
        question = self._question_of[market_id]
        return NewsItem(
            news_id=make_news_id(tick, index),
            tick=tick,
            market_ids=(market_id,),
            headline=_clip(f"Cancelled: {market_id} will not resolve", _HEADLINE_MAX_CHARS),
            body=_clip(
                f"{question} {market_id} was cancelled at tick {tick}. Stated reason: {reason}. "
                "Every execution on this market is unwound and the cash is restored.",
                _BODY_MAX_CHARS,
            ),
            impact=NewsImpact.HIGH,
            is_noise=False,
        )

    # ------------------------------------------------------------------
    # Private signals
    # ------------------------------------------------------------------
    def signals_for_tick(self, tick: int) -> tuple[Signal, ...]:
        """Return every private signal delivered at ``tick``.

        Sorted by ``(agent_id, signal_id)``. Honours ``delay_ticks`` and focus
        markets: a delayed seat observes the latent value of
        ``tick - delay_ticks`` (clamped at the pre match tick ``0``) rather than
        today's, and a specialist draws its focus market far more often and sees
        it far more sharply.

        The draw is a pure function of ``(world, profiles, seed, tick)``. In
        particular it does **not** know which markets are still tradable: the
        runner filters the result against ``TickStarted.open_market_ids`` at P1
        step 3, after the draw, so RNG consumption is independent of resolution
        history (decision 37).

        Args:
            tick: Delivery tick, ``>= 1``.

        Returns:
            The signals, possibly empty.

        Raises:
            InvalidConfigError: If ``tick`` is under one.
        """
        if tick < 1:
            raise InvalidConfigError("a tick is >= 1", tick=tick)
        if not self._agent_ids or not self._market_ids:
            return ()
        signal_rng = self._rng.fresh_substream(f"info.signals.tick.{tick}")
        rank_of = {agent_id: position for position, agent_id in enumerate(self._agent_ids)}
        drawn: list[Signal] = []
        for agent_id in self._agent_ids:
            drawn.extend(self._signals_of_agent(signal_rng, agent_id=agent_id, tick=tick))
        return tuple(sorted(drawn, key=lambda item: (rank_of[item.agent_id], item.signal_id)))

    def _signals_of_agent(self, rng: random.Random, *, agent_id: str, tick: int) -> tuple[Signal, ...]:
        """Draw one seat's signals for one tick.

        Args:
            rng: The ``info.signals.tick.<tick>`` generator.
            agent_id: The recipient seat.
            tick: Delivery tick.

        Returns:
            Zero to :data:`pxe.info.profiles.SIGNALS_MAX_PER_TICK` signals, in
            draw order.
        """
        profile = self._profiles[agent_id]
        low = min(profile.signals_min, SIGNALS_MAX_PER_TICK)
        high = max(low, min(profile.signals_max, SIGNALS_MAX_PER_TICK))
        count = randint(rng, low, high)
        weights = self._pick_weights(agent_id, profile)
        source_tick = max(0, tick - profile.delay_ticks)
        out: list[Signal] = []
        for index in range(count):
            market_id = choices_weighted(rng, self._market_ids, weights, k=1)[0]
            kind = self._draw_kind(rng)
            sigma_milli = self._sigma_of(market_id, profile)
            truth_milli = self._world.latent.value_milli(self._latent_key_of[market_id], source_tick)
            observed_milli = noisy_latent_milli(rng, truth_milli=truth_milli, sigma_milli=sigma_milli)
            out.append(
                Signal(
                    signal_id=make_signal_id(tick, agent_id, index),
                    tick=tick,
                    agent_id=agent_id,
                    market_id=market_id,
                    kind=kind,
                    value_milli=_value_milli(kind, observed_milli),
                    precision_ppm=precision_ppm_for_sigma(sigma_milli),
                )
            )
        return tuple(out)

    def _pick_weights(self, agent_id: str, profile: InfoProfile) -> tuple[float, ...]:
        """Return the market selection weights of one seat.

        Args:
            agent_id: The seat.
            profile: Its profile.

        Returns:
            One weight per market, in the canonical market order.
        """
        attention = self._attention_of[agent_id]
        return tuple(
            float(weight * FOCUS_PICK_WEIGHT if market_id in profile.focus_market_ids else weight)
            for market_id, weight in zip(self._market_ids, attention, strict=True)
        )

    def _sigma_of(self, market_id: str, profile: InfoProfile) -> int:
        """Return the observation sigma of one seat on one market.

        Args:
            market_id: Target market.
            profile: The seat's profile.

        Returns:
            The standard deviation in latent ``_milli``, clamped by
            :func:`pxe.info.noise.scaled_sigma_milli`.
        """
        scale_ppm = profile.noise_scale_ppm
        if profile.focus_market_ids:
            focus_scale = (
                FOCUS_NOISE_SCALE_PPM if market_id in profile.focus_market_ids else OUTSIDE_FOCUS_NOISE_SCALE_PPM
            )
            scale_ppm = (scale_ppm * focus_scale) // PPM_ONE
        sigma_milli = scaled_sigma_milli(self._signal_sigma_of[market_id], scale_ppm=scale_ppm)
        return min(SIGMA_MAX_MILLI, sigma_milli + DELAY_SIGMA_PENALTY_MILLI * profile.delay_ticks)

    @staticmethod
    def _draw_kind(rng: random.Random) -> SignalKind:
        """Draw the shape of one signal.

        Args:
            rng: The ``info.signals.tick.<tick>`` generator.

        Returns:
            The drawn kind.
        """
        roll = randint(rng, 1, 100)
        if roll <= KIND_POINT_ESTIMATE_MAX:
            return SignalKind.POINT_ESTIMATE
        if roll <= KIND_DIRECTION_MAX:
            return SignalKind.DIRECTION
        return SignalKind.THRESHOLD

    # ------------------------------------------------------------------
    # Shared helpers
    # ------------------------------------------------------------------
    def _slots_for_tick(self, tick: int) -> tuple[_NewsSlot, ...]:
        """Return the calendar slots of ``tick``.

        Args:
            tick: Tick, ``>= 1``.

        Returns:
            The slots, possibly empty.

        Raises:
            InvalidConfigError: If ``tick`` is under one.
        """
        if tick < 1:
            raise InvalidConfigError("a tick is >= 1", tick=tick)
        return self._calendar.get(tick, ())

    def _observe_public(self, rng: random.Random, *, slot: _NewsSlot, tick: int) -> int:
        """Observe the latent state behind one calendar slot.

        Both branches consume exactly one normal draw, so the per tick stream
        advances identically whether a slot is noise or not and the calendar can
        be re-tagged without moving the values of the following items.

        Args:
            rng: The ``info.news.tick.<tick>`` generator.
            slot: The slot being published.
            tick: Tick of publication.

        Returns:
            The observed latent value in signed thousandths.
        """
        if slot.is_noise or not slot.market_ids:
            return pure_noise_latent_milli(rng)
        market_id = slot.market_ids[0]
        truth_milli = self._world.latent.value_milli(self._latent_key_of[market_id], tick)
        return noisy_latent_milli(rng, truth_milli=truth_milli, sigma_milli=self._public_sigma_of[market_id])

    def _check_item_args(self, *, tick: int, market_id: str, index: int) -> None:
        """Validate the shared arguments of the two runner facing factories.

        Args:
            tick: Tick of publication.
            market_id: Target market.
            index: 0 based index inside the tick.

        Raises:
            InvalidConfigError: If ``tick`` is under one, ``index`` is negative,
                or ``market_id`` is not part of this world.
        """
        if tick < 1:
            raise InvalidConfigError("a tick is >= 1", tick=tick)
        if index < 0:
            raise InvalidConfigError("news index must be >= 0", index=index)
        if market_id not in self._question_of:
            raise InvalidConfigError(
                "unknown market",
                market_id=market_id,
                market_ids=list(self._market_ids),
            )


def _value_milli(kind: SignalKind, observed_milli: int) -> int:
    """Encode one observation into :attr:`pxe.types.Signal.value_milli`.

    Args:
        kind: Shape of the signal.
        observed_milli: The observed latent value in signed thousandths.

    Returns:
        A ``POINT_ESTIMATE`` probability in thousandths ``0..1_000``, a
        ``DIRECTION`` of ``-1_000`` or ``+1_000``, or a signed ``THRESHOLD``
        level as :func:`pxe.info.noise.threshold_milli` documents.
    """
    if kind is SignalKind.POINT_ESTIMATE:
        return probability_milli_from_latent(observed_milli)
    if kind is SignalKind.DIRECTION:
        return direction_milli(observed_milli)
    return threshold_milli(observed_milli)
