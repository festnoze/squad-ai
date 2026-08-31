"""The P1..P4 tick loop, the integrator of the whole engine (A09, CONTRACTS 5).

This module is the one place where the world, the information engine, the
CLOB, the ledger, the market maker, the oracle and the agent gateway meet. It
implements CONTRACTS section 5 step by step, in order, with nothing added and
nothing skipped: the numbered list there is the specification, and the step
numbers appear in the code as comments so a reader can check the two against
each other line by line.

What this class builds and what it is given
-------------------------------------------
Seven things are handed in (``config``, ``world``, ``agents``, ``gateway``,
``journal``, ``match_id``, ``rng``) and five collaborators are built here and
nowhere else (CONTRACTS section 7.12): the
:class:`~pxe.exchange.accounts.AccountBook`, the
:class:`~pxe.exchange.exchange.Exchange`, the
:class:`~pxe.info.engine.InfoEngine`, the
:class:`~pxe.mm.market_maker.ReferenceMarketMaker` and the
:class:`~pxe.oracle.resolver.Oracle`. A second copy of any of them, built by a
caller, is a second view of engine state that will disagree with this one.

Determinism
-----------
The ``RngTree`` is built by the **caller** and passed in (section 3.1): the
world and the scripted agents are constructed before this object exists and
already need their sub-trees. The runner consumes exactly one substream family
of its own, ``runner.tick_shuffle.<tick>``, through ``fresh_substream``, and
hands ``rng.child("info")`` and ``rng.child("mm")`` to the two components that
draw. It reads no clock, no file and no environment variable, and it never
calls an LLM: the single impure call of the whole engine is
``gateway.collect_actions`` in P2 (FR-5.1.2).

Emission ownership
------------------
Per CONTRACTS section 4.5 this module is the single emitter of
``match_started``, ``tick_started``, ``news_published``, ``signal_delivered``,
``observation_built``, ``agent_timed_out``, ``agent_action_rejected``,
``agent_action_received``, ``prediction_recorded``, ``message_posted``,
``agent_frozen``, ``mark_to_market``, ``position_snapshot`` and
``match_ended``. It emits **no** ``order_*``, ``trade_executed``,
``stp_cancelled``, ``mm_quoted``, ``market_resolved``, ``market_cancelled`` or
``settlement_applied`` event: those belong to the exchange, the market maker
and the oracle, which are handed the journal and emit into it themselves.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from pxe.errors import InvalidConfigError, PhaseOrderError
from pxe.events import (
    JOURNAL_ENCODING,
    JOURNAL_NEWLINE,
    AgentActionReceived,
    AgentActionRejected,
    AgentFrozen,
    AgentTimedOut,
    MarkToMarket,
    MatchEnded,
    MatchStarted,
    MessagePosted,
    NewsPublished,
    ObservationBuilt,
    PositionSnapshot,
    PredictionRecorded,
    SignalDelivered,
    TickStarted,
    canonical_json,
)
from pxe.exchange.accounts import AccountBook
from pxe.exchange.exchange import Exchange
from pxe.gateway.protocol import AgentGateway, AgentReply
from pxe.info.engine import InfoEngine
from pxe.journal import Journal
from pxe.mm.market_maker import ReferenceMarketMaker
from pxe.oracle.resolver import Oracle
from pxe.rng import RNG_ALGORITHM_VERSION, RngTree, shuffle_seeded
from pxe.runner.action_validator import resolve_predictions, validate_action
from pxe.runner.observation_builder import build_observation, write_observation
from pxe.runner.state import MatchState
from pxe.types import (
    FEES_ACCOUNT_ID,
    MM_ACCOUNT_ID,
    AgentAction,
    AgentSpec,
    CancelReason,
    MatchConfig,
    MatchRanking,
    MatchResult,
    NewsItem,
    Observation,
    PublicMessage,
    Side,
    Signal,
    action_to_journal_dict,
    bps_ratio,
    config_to_journal_dict,
    liquidity_profile,
    market_spec_to_dict,
    sorted_account_ids,
    sorted_ids,
)
from pxe.world.templates.base import World

__all__ = ["MatchRunner", "run_match"]

_LOG = logging.getLogger("pxe.runner")

#: The four phases of a tick, in the only legal order (CONTRACTS section 5).
_PHASE_ORDER: tuple[str, ...] = ("P1", "P2", "P3", "P4")

#: ``NewsPublished.origin`` has exactly three values (CONTRACTS section 5 P1).
_ORIGIN_INFO = "info_engine"
_ORIGIN_RESOLUTION = "resolution"
_ORIGIN_CANCELLATION = "cancellation"

#: ``MatchEnded.reason`` when the loop ran to completion.
_REASON_COMPLETED = "completed"

#: Name of the metadata artefact of section 4.6, written next to the journal.
_META_FILENAME = "meta.json"

#: Name of the journal artefact of section 4.6.
_JOURNAL_FILENAME = "journal.jsonl"

#: Name of the observation artefact of section 4.6, written by A10's
#: ``write_observation``. Explicitly outside the journal hash (section 3.5).
_OBSERVATIONS_FILENAME = "observations.jsonl"


def _legacy_scripted_agents_of(gateway: object) -> dict[str, Any]:
    """Discover scripted agents behind a gateway that predates ``reset_agents``.

    ``AgentGateway.reset_agents`` (section 7.16) is the contracted hook and the
    only path the shipped gateways take. This structural fallback exists for one
    case: a hand rolled test double that implements the three older protocol
    methods and not the fourth. It follows an attribute holding a ``Mapping`` of
    seat id to an object with a ``reset`` method, plus the routing table of a
    composite gateway.

    It is deliberately not the primary path. Reflection cannot see an agent a
    gateway stores under a name it does not guess (``ClaudeCliGateway`` keeps
    ``harnesses``), and a silently skipped reset is exactly the failure section
    3.1 exists to prevent, which is why the hook was added to the protocol.

    Args:
        gateway: The gateway handed to the runner.

    Returns:
        Seat id to agent object, for every seat that offers ``reset``.
    """
    found: dict[str, Any] = {}
    for attribute in ("agents", "_agents"):
        holder = getattr(gateway, attribute, None)
        if isinstance(holder, Mapping):
            for agent_id in sorted_ids(tuple(holder.keys())):
                candidate = holder[agent_id]
                if callable(getattr(candidate, "reset", None)):
                    found[agent_id] = candidate
    routing = getattr(gateway, "_gateways", None)
    if isinstance(routing, Sequence) and not isinstance(routing, str | bytes):
        for entry in routing:
            if isinstance(entry, tuple) and len(entry) == 2:
                found.update(_legacy_scripted_agents_of(entry[1]))
    return found


class MatchRunner:
    """Runs one match: ``MatchStarted``, ``T`` ticks of P1..P4, finalisation.

    One instance plays exactly one match. Calling :meth:`run` twice, or calling
    a phase out of turn, raises :class:`~pxe.errors.PhaseOrderError`.
    """

    def __init__(
        self,
        *,
        config: MatchConfig,
        world: World,
        agents: Sequence[AgentSpec],
        gateway: AgentGateway,
        journal: Journal,
        match_id: str,
        rng: RngTree,
        obs_path: Path | None = None,
    ) -> None:
        """Build the five collaborators and the initial ``MatchState``.

        ``rng`` is built by the caller, not here (CONTRACTS section 3.1): the
        world and the scripted agents are constructed before this object exists
        and already need their sub-trees. The runner uses it for
        ``runner.tick_shuffle.<tick>`` and for the two sub-trees it hands to the
        components it builds itself, ``rng.child("info")`` and
        ``rng.child("mm")``. It never constructs an ``RngTree`` of its own.

        Args:
            config: The authoritative match configuration.
            world: The generated world. Its scenario copies of ``ticks_total``,
                ``talking_mode`` and ``liquidity_profile_name`` are
                informational and must agree with ``config``.
            agents: One :class:`~pxe.types.AgentSpec` per seat. The ranked ones
                fund the ledger and receive observations; an unranked ``MM``
                seat is accepted and ignored, because the market maker account
                is created by :class:`~pxe.exchange.accounts.AccountBook`
                itself.
            gateway: The single source of agent decisions. Called exactly once
                per tick, in P2.
            journal: The append only log every component of the match emits
                into.
            match_id: Match id every event carries.
            rng: The root :class:`~pxe.rng.RngTree` of the match.
            obs_path: Where to append ``runs/<match_id>/observations.jsonl``
                (CONTRACTS sections 4.6 and 7.13), or ``None`` to write no
                observation artefact. It is a keyword with a default because it
                is outside AC-P1: the file is explicitly not hashed and not
                required to replay, so a unit test that only wants a journal
                omits it and the golden hashes do not move. ``run_match`` passes
                ``out_dir / "observations.jsonl"``, which is what gives
                ``write_observation`` the call site section 7.13 promises it.

        Raises:
            InvalidConfigError: When ``config`` and ``world.scenario`` disagree
                on ``ticks_total``, ``talking_mode``,
                ``liquidity_profile_name``, ``mm`` or ``n_markets`` (CONTRACTS
                section 2.6): ``MatchConfig`` is authoritative and the scenario
                copies are informational. Also when ``journal`` belongs to
                another match, which would corrupt two journals at once.
        """
        _check_config_agrees_with_scenario(config, world)
        if journal.match_id != match_id:
            raise InvalidConfigError(
                "the journal belongs to another match",
                match_id=match_id,
                journal_match_id=journal.match_id,
            )
        self._config = config
        self._world = world
        self._agents: tuple[AgentSpec, ...] = tuple(agents)
        self._gateway = gateway
        self._journal = journal
        self._match_id = match_id
        self._rng = rng
        self._obs_path = obs_path

        ranked = tuple(spec for spec in self._agents if spec.ranked)
        accounts = AccountBook(
            agent_ids=[spec.agent_id for spec in ranked],
            market_ids=world.market_ids(),
            config=config,
        )
        exchange = Exchange(config=config, scenario=world.scenario, accounts=accounts, journal=journal)
        self._info = InfoEngine(
            world=world,
            profiles={spec.agent_id: spec.info_profile for spec in ranked},
            rng=rng.child("info"),
            ticks_total=config.ticks_total,
        )
        self._mm = ReferenceMarketMaker(config=config.mm, market_ids=world.market_ids(), rng=rng.child("mm"))
        self._oracle = Oracle(world=world)
        self._state = MatchState(
            config=config,
            scenario=world.scenario,
            match_id=match_id,
            tick=0,
            accounts=accounts,
            exchange=exchange,
        )
        self._started = False
        self._finished = False
        self._phase_tick = 0
        self._next_phase = "P1"

    # ------------------------------------------------------------------
    # Read only state
    # ------------------------------------------------------------------
    @property
    def state(self) -> MatchState:
        """The live :class:`~pxe.runner.state.MatchState` of this match."""
        return self._state

    def __repr__(self) -> str:
        """Render the match id, the tick played and the phase that comes next."""
        return f"MatchRunner(match_id={self._match_id!r}, tick={self._phase_tick}, next={self._next_phase})"

    # ------------------------------------------------------------------
    # The loop
    # ------------------------------------------------------------------
    def run(self) -> MatchResult:
        """Play the whole match and return its :class:`~pxe.types.MatchResult`.

        Exactly CONTRACTS section 5: emit ``MatchStarted``, reset every
        scripted agent, run ``ticks_total`` ticks of P1..P4, then finalise at
        the virtual tick ``ticks_total + 1``.

        Returns:
            The result, including the journal hash AC-P1 compares.

        Raises:
            PhaseOrderError: If the match already ran.
            InvariantViolationError: On any breach of CONTRACTS section 6. An
                invariant breach is an engine bug and aborts the match; it is
                never downgraded into an integrity incident.
        """
        self._start()
        for tick in range(1, self._config.ticks_total + 1):
            self.run_tick(tick)
        return self._finalise()

    def run_tick(self, tick: int) -> None:
        """Run the four phases of one tick, in order.

        Args:
            tick: The tick to play, ``1..ticks_total``.

        Raises:
            PhaseOrderError: If this is not the tick that comes next.
        """
        observations = self.phase_p1_diffusion(tick)
        actions = self.phase_p2_decision(tick, observations)
        self.phase_p3_execution(tick, actions)
        self.phase_p4_close(tick)

    # ------------------------------------------------------------------
    # P1 Diffusion (pure)
    # ------------------------------------------------------------------
    def phase_p1_diffusion(self, tick: int) -> tuple[Observation, ...]:
        """Steps 0 to 6: open the tick, publish, resolve, observe.

        Args:
            tick: The tick being played.

        Returns:
            One observation per ranked, non frozen seat, ascending by
            ``agent_id``. Empty only when every seat is frozen.

        Raises:
            PhaseOrderError: If P1 of this tick is not what comes next.
        """
        self._enter_phase("P1", tick)
        self._state.tick = tick
        exchange = self._state.exchange

        # Step 0: reset the per tick counters MarkToMarket.tick_volume_qty reads.
        exchange.begin_tick(tick)

        # Step 1: TickStarted advertises what is tradable in P3 of this tick,
        # that is the open markets minus the ones resolving at step 4 AND minus
        # the ones the scenario cancels at step 5. A cancellation fires at tick
        # c, not c + 1 (section 5.0), so the cancelled market is closed before
        # P3 and is not tradable on the tick it is cancelled. Leaving it in the
        # set made TickStarted advertise a market no agent can touch and let a
        # SignalDelivered through for a market the observation does not carry,
        # which is exactly the dangling reference step 3's filter exists to
        # prevent.
        due = frozenset(self._oracle.due_market_ids(tick))
        cancelled = frozenset(market_id for market_id, _reason in self._oracle.due_cancellations(tick))
        untradable = due | cancelled
        tradable = tuple(market_id for market_id in self._state.open_market_ids() if market_id not in untradable)
        self._journal.emit(TickStarted, tick=tick, open_market_ids=tradable)

        # Step 2: the information engine's own news.
        news: list[NewsItem] = list(self._publish_news(tick))

        # Step 3: private signals, filtered against the tradable set.
        signals = self._deliver_signals(tick, tradable=frozenset(tradable))

        # Steps 4 and 5: resolutions then scripted cancellations, each followed
        # by the runner's own NewsPublished (sub-step d).
        news.extend(self._resolve_due_markets(tick, first_index=len(news)))
        news.extend(self._cancel_due_markets(tick, first_index=len(news)))

        # Step 5b: one news handover to the market maker, once every item exists.
        self._mm.note_news(tick=tick, items=tuple(news))

        # Step 6: one observation per active seat.
        return self._build_observations(tick, news=tuple(news), signals=signals)

    def _publish_news(self, tick: int) -> tuple[NewsItem, ...]:
        """Emit one ``NewsPublished`` per information engine item (step 2).

        Args:
            tick: The tick being played.

        Returns:
            The published items, in publication order.
        """
        items = self._info.news_for_tick(tick)
        for item in items:
            self._emit_news(tick, item, origin=_ORIGIN_INFO)
        return items

    def _emit_news(self, tick: int, item: NewsItem, *, origin: str) -> None:
        """Emit one ``NewsPublished`` event.

        Args:
            tick: Envelope tick of the event.
            item: The item to publish.
            origin: ``"info_engine"``, ``"resolution"`` or ``"cancellation"``.
        """
        self._journal.emit(
            NewsPublished,
            tick=tick,
            news_id=item.news_id,
            market_ids=item.market_ids,
            headline=item.headline,
            body=item.body,
            impact=str(item.impact),
            is_noise=item.is_noise,
            origin=origin,
        )

    def _deliver_signals(self, tick: int, *, tradable: frozenset[str]) -> dict[str, tuple[Signal, ...]]:
        """Emit one ``SignalDelivered`` per surviving signal (step 3).

        A signal about a market that is not tradable this tick is dropped, not
        journalled (CONTRACTS section 5 P1 step 3). The drop happens **after**
        the draw, so ``info.signals.tick.<tick>`` consumes the same randomness
        whether a signal survives or not.

        Args:
            tick: The tick being played.
            tradable: The market ids advertised by ``TickStarted``. Membership
                only, never iterated.

        Returns:
            The surviving signals grouped by recipient, in delivery order.
        """
        delivered: dict[str, list[Signal]] = {}
        for signal in self._info.signals_for_tick(tick):
            if signal.market_id not in tradable:
                continue
            self._journal.emit(
                SignalDelivered,
                tick=tick,
                signal_id=signal.signal_id,
                agent_id=signal.agent_id,
                market_id=signal.market_id,
                kind=str(signal.kind),
                value_milli=signal.value_milli,
                precision_ppm=signal.precision_ppm,
            )
            delivered.setdefault(signal.agent_id, []).append(signal)
        return {agent_id: tuple(rows) for agent_id, rows in delivered.items()}

    def _resolve_due_markets(self, tick: int, *, first_index: int) -> tuple[NewsItem, ...]:
        """Resolve every due market and announce it (step 4).

        ``Oracle.resolve`` performs sub-steps a, b, c and e itself; the runner
        performs only sub-step d, the resolution ``NewsPublished``, because the
        item comes from the information engine and must join the tick's other
        news in the single ``mm.note_news`` handover of step 5b.

        Args:
            tick: The tick being played, or ``ticks_total + 1`` in finalisation.
            first_index: Index the next news id of this tick continues from.

        Returns:
            The announcement items, in emission order.
        """
        items: list[NewsItem] = []
        for market_id in self._oracle.due_market_ids(tick):
            report = self._oracle.resolve(
                tick=tick,
                market_id=market_id,
                exchange=self._state.exchange,
                accounts=self._state.accounts,
                journal=self._journal,
            )
            if report.outcome is None:
                continue
            self._state.outcomes[market_id] = report.outcome
            item = self._info.resolution_news(
                tick=tick,
                market_id=market_id,
                outcome=report.outcome,
                index=first_index + len(items),
            )
            self._emit_news(tick, item, origin=_ORIGIN_RESOLUTION)
            items.append(item)
        return tuple(items)

    def _cancel_due_markets(self, tick: int, *, first_index: int) -> tuple[NewsItem, ...]:
        """Cancel every market the scenario scripted for this tick (step 5).

        Args:
            tick: The tick being played.
            first_index: Index the next news id of this tick continues from.

        Returns:
            The announcement items, in emission order.
        """
        items: list[NewsItem] = []
        for market_id, reason in self._oracle.due_cancellations(tick):
            self._oracle.cancel_market(
                tick=tick,
                market_id=market_id,
                reason=reason,
                exchange=self._state.exchange,
                accounts=self._state.accounts,
                journal=self._journal,
            )
            item = self._info.cancellation_news(
                tick=tick,
                market_id=market_id,
                reason=reason,
                index=first_index + len(items),
            )
            self._emit_news(tick, item, origin=_ORIGIN_CANCELLATION)
            items.append(item)
        return tuple(items)

    def _build_observations(
        self,
        tick: int,
        *,
        news: tuple[NewsItem, ...],
        signals: Mapping[str, tuple[Signal, ...]],
    ) -> tuple[Observation, ...]:
        """Build and journal one observation per active seat (step 6).

        When no market is open the observation is still built and still
        emitted, with ``n_markets = 0``; P2 then skips the gateway call for
        every agent that tick (CONTRACTS section 5.0).

        Args:
            tick: The tick being played.
            news: Every item published this tick, in emission order.
            signals: The surviving signals, keyed by recipient. Lookup only.

        Returns:
            The observations, ascending by ``agent_id``.
        """
        delivered = tuple(message for message in self._state.pending_messages if message.deliver_tick <= tick)
        self._state.pending_messages = tuple(
            message for message in self._state.pending_messages if message.deliver_tick > tick
        )
        observations: list[Observation] = []
        for agent_id in self._state.active_agent_ids():
            observation = build_observation(
                config=self._config,
                state=self._state,
                agent_id=agent_id,
                tick=tick,
                news=news,
                signals=signals.get(agent_id, ()),
                messages=delivered,
            )
            self._journal.emit(
                ObservationBuilt,
                tick=tick,
                agent_id=agent_id,
                obs_version=observation.obs_version,
                n_markets=len(observation.markets),
                n_news=len(observation.news),
                n_signals=len(observation.signals),
            )
            if self._obs_path is not None:
                write_observation(self._obs_path, observation)
            observations.append(observation)
        return tuple(observations)

    # ------------------------------------------------------------------
    # P2 Decision (the only impure step)
    # ------------------------------------------------------------------
    def phase_p2_decision(self, tick: int, observations: Sequence[Observation]) -> tuple[AgentAction, ...]:
        """Steps 7 and 8: collect replies, validate them, record predictions.

        Calls ``gateway.collect_actions``, which returns
        :class:`~pxe.gateway.protocol.AgentReply` objects, validates each one
        here (the single call site of ``validate_action``) and returns the
        surviving :class:`~pxe.types.AgentAction` of each agent, ascending by
        ``agent_id``. ``AgentReply`` never leaves this method.

        Args:
            tick: The tick being played.
            observations: What P1 built, ascending by ``agent_id``.

        Returns:
            One action per reply, ascending by ``agent_id``.

        Raises:
            PhaseOrderError: If P2 of this tick is not what comes next.
        """
        self._enter_phase("P2", tick)
        replies = self._collect_replies(tick, observations)
        actions: list[AgentAction] = []
        posted: list[PublicMessage] = []
        for reply in replies:
            actions.append(self._apply_reply(tick, reply, posted=posted))
        self._state.pending_messages = (*self._state.pending_messages, *posted)
        return tuple(actions)

    def _collect_replies(self, tick: int, observations: Sequence[Observation]) -> tuple[AgentReply, ...]:
        """Step 7: the single impure call of the engine, then a canonical sort.

        Args:
            tick: The tick being played.
            observations: One observation per active seat.

        Returns:
            The replies, ascending by ``agent_id``. Empty when there is no open
            market, in which case the gateway is not called at all (CONTRACTS
            section 5.0): no provider call, no cost, no event.
        """
        if not observations or not self._state.open_market_ids():
            return ()
        replies = self._gateway.collect_actions(
            tick=tick,
            observations=tuple(observations),
            config=self._config,
        )
        unique = tuple(dict.fromkeys(reply.agent_id for reply in replies))
        rank = {agent_id: index for index, agent_id in enumerate(sorted_ids(unique))}
        return tuple(sorted(replies, key=lambda reply: rank[reply.agent_id]))

    def _apply_reply(self, tick: int, reply: AgentReply, *, posted: list[PublicMessage]) -> AgentAction:
        """Step 8 a to d for one agent, in that order, contiguously.

        Args:
            tick: The tick being played.
            reply: What the gateway produced for this seat.
            posted: Accumulator of the messages that survived, appended to in
                agent order.

        Returns:
            The validated action of this agent.
        """
        agent_id = reply.agent_id
        raw = reply.raw
        # a. a failed call is journalled and treated as no payload at all.
        if reply.error is not None:
            self._journal.emit(AgentTimedOut, tick=tick, agent_id=agent_id, reason=str(reply.error))
            raw = None
        # b. the single call site of validate_action.
        outcome = validate_action(
            raw,
            agent_id=agent_id,
            tick=tick,
            config=self._config,
            open_market_ids=self._state.open_market_ids(),
            resting_order_ids=self._state.resting_order_ids(agent_id),
            source=reply.source,
        )
        for rejection in outcome.rejections:
            self._journal.emit(
                AgentActionRejected,
                tick=tick,
                agent_id=agent_id,
                scope=rejection.scope,
                item_index=rejection.item_index,
                reason=str(rejection.reason),
                detail=rejection.detail,
            )
        self._journal.emit(
            AgentActionReceived,
            tick=tick,
            **action_to_journal_dict(outcome.action, n_rejected=len(outcome.rejections)),
        )
        # c. prediction carry over every open market.
        self._record_predictions(tick, agent_id=agent_id, action=outcome.action)
        # d. the public message, delivered next tick.
        text = outcome.action.message_public
        if text is not None and self._config.talking_mode:
            self._journal.emit(MessagePosted, tick=tick, agent_id=agent_id, text=text, deliver_tick=tick + 1)
            posted.append(PublicMessage(agent_id=agent_id, tick=tick, text=text, deliver_tick=tick + 1))
        return outcome.action

    def _record_predictions(self, tick: int, *, agent_id: str, action: AgentAction) -> None:
        """Step 8c: the FR-6.2.4 carry, then one row per open market.

        Args:
            tick: The tick being played.
            agent_id: The declaring seat.
            action: Its validated action.
        """
        open_market_ids = self._state.open_market_ids()
        declared = {intent.market_id: intent.p_yes_ppm for intent in action.predictions}
        previous: dict[str, int] = {}
        for market_id in open_market_ids:
            known = self._state.last_prediction_ppm.get((agent_id, market_id))
            if known is not None:
                previous[market_id] = known
        rows = resolve_predictions(declared=declared, previous=previous, open_market_ids=open_market_ids)
        for market_id, p_yes_ppm, was_carried in rows:
            self._state.last_prediction_ppm[agent_id, market_id] = p_yes_ppm
            self._journal.emit(
                PredictionRecorded,
                tick=tick,
                agent_id=agent_id,
                market_id=market_id,
                p_yes_ppm=p_yes_ppm,
                carried=was_carried,
            )

    # ------------------------------------------------------------------
    # P3 Execution (pure)
    # ------------------------------------------------------------------
    def phase_p3_execution(self, tick: int, actions: Sequence[AgentAction]) -> None:
        """Steps 9 to 11: requote, shuffle, apply each agent's block.

        Args:
            tick: The tick being played.
            actions: What P2 returned, ascending by ``agent_id``.

        Raises:
            PhaseOrderError: If P3 of this tick is not what comes next.
        """
        self._enter_phase("P3", tick)
        exchange = self._state.exchange
        accounts = self._state.accounts

        # Step 9: the market maker requotes BEFORE the shuffle (FR-5.8.1), so
        # the liquidity an agent meets does not depend on its place in the
        # permutation. The inventory snapshot is taken at the top of the
        # requote, before any of this tick's market maker orders exist.
        self._mm.requote(
            tick=tick,
            exchange=exchange,
            inventory=accounts.inventory_view(MM_ACCOUNT_ID),
            journal=self._journal,
        )

        # Step 10: the fairness shuffle, exactly as CONTRACTS section 3.4. The
        # FULL seat list is shuffled and the frozen seats are dropped
        # afterwards, so the permutation is a function of (seed, tick) alone.
        order = [
            agent_id
            for agent_id in shuffle_seeded(
                self._rng.fresh_substream(f"runner.tick_shuffle.{tick}"),
                sorted_ids(self._state.ranked_agent_ids()),
            )
            if agent_id not in self._state.frozen_agent_ids
        ]

        # Step 11: each agent's whole block, contiguously, in submission order.
        by_agent = {action.agent_id: action for action in actions}
        for agent_id in order:
            action = by_agent.get(agent_id)
            if action is None:
                continue
            self._apply_orders(tick, agent_id=agent_id, action=action)

    def _apply_orders(self, tick: int, *, agent_id: str, action: AgentAction) -> None:
        """Apply one agent's intents, in the exact order it submitted them.

        "Atomic" means *not interleaved with another agent*, never
        all-or-nothing: each intent is independently accepted or rejected and
        the rest of the block still runs.

        Args:
            tick: The tick being played.
            agent_id: The acting seat.
            action: Its validated action.
        """
        exchange = self._state.exchange
        for item_index, intent in enumerate(action.orders):
            if intent.op == "cancel":
                exchange.cancel(
                    tick=tick,
                    agent_id=agent_id,
                    order_id=intent.order_id or "",
                    reason=CancelReason.AGENT_REQUEST,
                    item_index=item_index,
                )
            else:
                exchange.submit(tick=tick, agent_id=agent_id, intent=intent, item_index=item_index)

    # ------------------------------------------------------------------
    # P4 Close (pure)
    # ------------------------------------------------------------------
    def phase_p4_close(self, tick: int) -> None:
        """Steps 12 to 16: mark, snapshot, freeze, check, flush.

        Args:
            tick: The tick being played.

        Raises:
            PhaseOrderError: If P4 of this tick is not what comes next.
            InvariantViolationError: On any breach of CONTRACTS section 6.
        """
        self._enter_phase("P4", tick)
        ref_prices = self._mark_to_market(tick)
        self._snapshot_positions(tick, ref_prices=ref_prices)
        self._check_bankruptcy(tick, ref_prices=ref_prices)
        # Step 15: this runs on EVERY tick, not only in tests.
        self._state.accounts.check_invariants(
            ref_prices=self._state.ref_prices(),
            book_view=self._state.exchange.book_view(),
        )
        # Step 16.
        self._journal.flush()

    def _mark_to_market(self, tick: int) -> dict[str, int]:
        """Step 12: one ``MarkToMarket`` per open market, then push the history.

        Args:
            tick: The tick being played.

        Returns:
            The reference price of every open market, in canonical order.
        """
        exchange = self._state.exchange
        ref_prices: dict[str, int] = {}
        for market_id in self._state.open_market_ids():
            ref_price, ref_source = exchange.reference_price(market_id)
            book = exchange.book(market_id)
            self._journal.emit(
                MarkToMarket,
                tick=tick,
                market_id=market_id,
                ref_price=ref_price,
                ref_source=ref_source,
                best_bid=book.best_bid(),
                best_ask=book.best_ask(),
                mid_price=book.mid_price(),
                last_price=book.last_price(),
                bid_depth_qty=book.total_qty(Side.BUY),
                ask_depth_qty=book.total_qty(Side.SELL),
                tick_volume_qty=exchange.tick_volume(market_id),
            )
            exchange.push_ref_history(market_id, ref_price)
            ref_prices[market_id] = ref_price
        return ref_prices

    def _snapshot_positions(self, tick: int, *, ref_prices: Mapping[str, int]) -> None:
        """Step 13: one ``PositionSnapshot`` per account, in canonical order.

        Args:
            tick: The tick being played.
            ref_prices: Reference price per open market. Lookup only.
        """
        accounts = self._state.accounts
        for account_id in accounts.account_ids():
            snapshot = accounts.state(account_id)
            positions = tuple(
                {
                    "market_id": position.market_id,
                    "qty": position.qty,
                    "cost_basis_cents": position.cost_basis_cents,
                    "value_cents": position.value_cents(ref_prices.get(position.market_id, 0)),
                }
                for position in snapshot.positions
            )
            self._journal.emit(
                PositionSnapshot,
                tick=tick,
                account_id=account_id,
                cash_cents=snapshot.cash_cents,
                reserved_cents=snapshot.reserved_cents,
                free_cash_cents=snapshot.free_cash_cents,
                equity_cents=accounts.equity_cents(account_id, ref_prices),
                frozen=snapshot.frozen,
                positions=positions,
                resting_order_count=accounts.resting_order_count(account_id),
            )

    def _check_bankruptcy(self, tick: int, *, ref_prices: Mapping[str, int]) -> None:
        """Step 14: the FR-5.5.5 freeze, evaluated in ascending ``agent_id``.

        The PRD trigger is "cash et collateral libres epuises", that is free
        cash exhausted while nothing is resting; the equity branch is a
        defensive tripwire that, given I4 and I9, normally never fires.

        Args:
            tick: The tick being played.
            ref_prices: Reference price per open market. Lookup only.
        """
        accounts = self._state.accounts
        config = self._config
        for agent_id in self._state.ranked_agent_ids():
            if agent_id in self._state.frozen_agent_ids:
                continue
            free_cash = accounts.free_cash_cents(agent_id)
            equity = accounts.equity_cents(agent_id, ref_prices)
            starved = (
                free_cash <= config.bankruptcy_free_cash_floor_cents and accounts.resting_order_count(agent_id) == 0
            )
            if not starved and equity > config.bankruptcy_equity_floor_cents:
                continue
            cancelled = self._state.exchange.cancel_all(
                tick=tick,
                agent_id=agent_id,
                reason=CancelReason.AGENT_FROZEN,
            )
            accounts.freeze(agent_id)
            self._state.frozen_agent_ids = self._state.frozen_agent_ids | {agent_id}
            self._journal.emit(
                AgentFrozen,
                tick=tick,
                agent_id=agent_id,
                equity_cents=equity,
                cancelled_order_ids=cancelled,
            )
            _LOG.info(
                "agent frozen",
                extra={"match_id": self._match_id, "tick": tick, "agent_id": agent_id},
            )

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    def _start(self) -> None:
        """Emit ``MatchStarted`` (seq 1, tick 0) and reset every scripted agent.

        Idempotent, and triggered by the first phase call of a match that was
        not started explicitly, so a journal always begins with ``MatchStarted``
        whichever entry point a caller used.

        Raises:
            PhaseOrderError: If the match already finished.
        """
        if self._finished:
            raise PhaseOrderError("the match already finished", match_id=self._match_id)
        if self._started:
            return
        self._started = True
        config = self._config
        scenario = self._world.scenario
        journalled_config = config_to_journal_dict(config)
        self._journal.emit(
            MatchStarted,
            tick=0,
            seed=config.seed,
            engine_version=config.engine_version,
            obs_version=config.obs_version,
            action_version=config.action_version,
            scenario_template_id=scenario.template_id,
            scenario_template_version=scenario.template_version,
            ticks_total=config.ticks_total,
            initial_cash_cents=config.initial_cash_cents,
            config=journalled_config,
            markets=tuple(market_spec_to_dict(spec) for spec in scenario.markets),
            agents=self._agents_payload(),
            mm_config=journalled_config["mm"],
        )
        self._reset_agents()

    def _agents_payload(self) -> tuple[dict[str, Any], ...]:
        """Build ``MatchStarted.agents``, one mapping per seat, sorted by seat id.

        Returns:
            One mapping per seat holding ``agent_id``, ``harness_id``,
            ``harness_version``, ``config_hash``, ``info_profile_kind`` and
            ``ranked``.
        """
        by_id = {spec.agent_id: spec for spec in self._agents}
        rows: list[dict[str, Any]] = []
        for agent_id in sorted_account_ids(tuple(by_id.keys())):
            spec = by_id[agent_id]
            rows.append(
                {
                    "agent_id": spec.agent_id,
                    "harness_id": spec.harness.harness_id,
                    "harness_version": spec.harness.version,
                    "config_hash": spec.harness.config_hash,
                    "info_profile_kind": str(spec.info_profile.kind),
                    "ranked": spec.ranked,
                }
            )
        return tuple(rows)

    def _reset_agents(self) -> None:
        """Reset every scripted seat behind the gateway, ascending (section 3.1).

        An orchestrator reuses agent objects across matches; without this call
        the second match inherits the first one's internal state and O1 dies
        silently, which is what
        ``test_determinism.py::test_reused_agent_objects_replay_identically``
        pins.

        The contracted path is ``AgentGateway.reset_agents`` (section 7.16),
        which the gateway implements because only it knows which seats it holds.
        A gateway that predates the hook falls back to structural discovery so a
        hand rolled test double keeps working; the two are mutually exclusive,
        never both, so no agent is reset twice.
        """
        hook = getattr(self._gateway, "reset_agents", None)
        if callable(hook):
            hook(config=self._config, rng=self._rng)
            return
        found = _legacy_scripted_agents_of(self._gateway)
        for agent_id in sorted_ids(tuple(found.keys())):
            found[agent_id].reset(
                config=self._config,
                rng=self._rng.child(f"agent/{agent_id}").substream(f"agent.{agent_id}"),
            )

    def _finalise(self) -> MatchResult:
        """Steps 17 to 19, at the virtual tick ``ticks_total + 1``.

        Resolves every market still open through the same single
        ``Oracle.resolve`` call as P1 step 4, checks I11, ranks on cash after
        settlement (never on a mark to market), emits ``MatchEnded``, closes the
        journal and writes ``meta.json`` next to it.

        Returns:
            The :class:`~pxe.types.MatchResult` of this match.

        Raises:
            PhaseOrderError: If the match already finished.
        """
        if self._finished:
            raise PhaseOrderError("the match already finished", match_id=self._match_id)
        self._start()
        final_tick = self._config.ticks_total
        virtual_tick = final_tick + 1
        self._state.tick = virtual_tick
        # Step 17: no NewsPublished and no mm.note_news here, because there is
        # no P2 and no P3 at T + 1 for anybody to act in.
        for market_id in self._oracle.due_market_ids(virtual_tick):
            report = self._oracle.resolve(
                tick=virtual_tick,
                market_id=market_id,
                exchange=self._state.exchange,
                accounts=self._state.accounts,
                journal=self._journal,
            )
            if report.outcome is not None:
                self._state.outcomes[market_id] = report.outcome
        # Step 18.
        accounts = self._state.accounts
        accounts.check_final_invariant()
        rankings = self._rankings()
        mm_pnl_cents = accounts.cash_cents(MM_ACCOUNT_ID) - self._config.mm_initial_cash_cents
        fees_collected_cents = accounts.cash_cents(FEES_ACCOUNT_ID)
        # Step 19.
        self._journal.emit(
            MatchEnded,
            tick=virtual_tick,
            reason=_REASON_COMPLETED,
            final_tick=final_tick,
            rankings=tuple(_ranking_to_dict(row) for row in rankings),
            mm_pnl_cents=mm_pnl_cents,
            fees_collected_cents=fees_collected_cents,
            event_count=self._journal.next_seq,
        )
        self._finished = True
        journal_hash = self._journal.hash()
        event_count = len(self._journal.events)
        path = self._journal.path
        self._journal.close()
        result = MatchResult(
            match_id=self._match_id,
            seed=self._config.seed,
            scenario=self._world.scenario,
            rankings=rankings,
            journal_path=str(path) if path is not None else "",
            journal_hash=journal_hash,
            event_count=event_count,
            mm_pnl_cents=mm_pnl_cents,
            fees_collected_cents=fees_collected_cents,
        )
        if path is not None:
            self._write_meta(path.parent / _META_FILENAME, result)
        return result

    def _rankings(self) -> tuple[MatchRanking, ...]:
        """Rank the seats on cash after settlement (FR-5.5.4, step 18).

        Ties share the lowest rank and are broken, for display only, by
        ascending ``agent_id``. ``pnl_pct_bps`` goes through
        :func:`~pxe.types.bps_ratio`, never ``//``, so a gain and the mirror
        loss report the same magnitude.

        Returns:
            The ranking, best first.
        """
        initial = self._config.initial_cash_cents
        accounts = self._state.accounts
        seats = self._state.ranked_agent_ids()
        position_of = {agent_id: index for index, agent_id in enumerate(seats)}
        rows = [(agent_id, accounts.cash_cents(agent_id)) for agent_id in seats]
        ordered = sorted(rows, key=lambda row: (-row[1], position_of[row[0]]))
        rankings: list[MatchRanking] = []
        for place, (agent_id, final_cash) in enumerate(ordered, start=1):
            rank = rankings[-1].rank if rankings and final_cash == ordered[place - 2][1] else place
            pnl_cents = final_cash - initial
            rankings.append(
                MatchRanking(
                    rank=rank,
                    agent_id=agent_id,
                    pnl_cents=pnl_cents,
                    final_cash_cents=final_cash,
                    pnl_pct_bps=bps_ratio(pnl_cents, initial),
                )
            )
        return tuple(rankings)

    def _write_meta(self, path: Path, result: MatchResult) -> None:
        """Write ``meta.json`` next to the journal (section 4.6, step 19).

        Args:
            path: Destination file.
            result: The result the metadata describes.
        """
        payload = {
            "match_id": result.match_id,
            "seed": result.seed,
            "journal_hash": result.journal_hash,
            "event_count": result.event_count,
            "engine_version": self._config.engine_version,
            "obs_version": self._config.obs_version,
            "action_version": self._config.action_version,
            "rng_algorithm_version": RNG_ALGORITHM_VERSION,
            "scenario_template_id": self._world.scenario.template_id,
            "scenario_template_version": self._world.scenario.template_version,
            "ticks_total": self._config.ticks_total,
        }
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding=JOURNAL_ENCODING, newline=JOURNAL_NEWLINE) as handle:
            handle.write(canonical_json(payload) + JOURNAL_NEWLINE)

    def _enter_phase(self, phase: str, tick: int) -> None:
        """Refuse a phase called out of turn (CONTRACTS section 5).

        Args:
            phase: ``"P1"``, ``"P2"``, ``"P3"`` or ``"P4"``.
            tick: The tick the caller believes it is playing.

        Raises:
            PhaseOrderError: If this is not the phase, or not the tick, that
                comes next.
        """
        self._start()
        expected_tick = self._phase_tick + 1 if phase == "P1" else self._phase_tick
        if phase != self._next_phase or tick != expected_tick:
            raise PhaseOrderError(
                "phase called out of order",
                match_id=self._match_id,
                requested=f"{phase}@{tick}",
                expected=f"{self._next_phase}@{expected_tick}",
            )
        if phase == "P1":
            self._phase_tick = tick
        self._next_phase = _PHASE_ORDER[(_PHASE_ORDER.index(phase) + 1) % len(_PHASE_ORDER)]


def _ranking_to_dict(row: MatchRanking) -> dict[str, Any]:
    """Encode one :class:`~pxe.types.MatchRanking` for ``MatchEnded.rankings``.

    Float free by construction: ``pnl_pct_bps`` is an integer produced by
    :func:`~pxe.types.bps_ratio`.

    Args:
        row: One ranking line.

    Returns:
        A mapping holding ``rank``, ``agent_id``, ``pnl_cents``,
        ``final_cash_cents`` and ``pnl_pct_bps``.
    """
    return {
        "rank": row.rank,
        "agent_id": row.agent_id,
        "pnl_cents": row.pnl_cents,
        "final_cash_cents": row.final_cash_cents,
        "pnl_pct_bps": row.pnl_pct_bps,
    }


def _check_config_agrees_with_scenario(config: MatchConfig, world: World) -> None:
    """Refuse to start when ``MatchConfig`` and ``ScenarioSpec`` disagree.

    ``MatchConfig`` is authoritative and the scenario copies are informational
    (CONTRACTS section 2.6). The last two checks catch the nastier version of
    the same bug: ``MatchConfig.mm`` can silently disagree with the preset
    ``liquidity_profile_name`` names, and the market maker is built from
    ``config.mm``, so the journal would record one preset and the book would
    show another.

    Args:
        config: The authoritative configuration.
        world: The generated world.

    Raises:
        InvalidConfigError: On any of the five disagreements.
    """
    scenario = world.scenario
    if config.ticks_total != scenario.ticks_total:
        raise InvalidConfigError(
            "config and scenario disagree on ticks_total",
            config=config.ticks_total,
            scenario=scenario.ticks_total,
        )
    if config.talking_mode != scenario.talking_mode:
        raise InvalidConfigError(
            "config and scenario disagree on talking_mode",
            config=config.talking_mode,
            scenario=scenario.talking_mode,
        )
    if config.liquidity_profile_name != scenario.liquidity_profile_name:
        raise InvalidConfigError(
            "config and scenario disagree on liquidity_profile_name",
            config=str(config.liquidity_profile_name),
            scenario=str(scenario.liquidity_profile_name),
        )
    if config.mm != liquidity_profile(config.liquidity_profile_name).mm:
        raise InvalidConfigError(
            "config.mm does not match the named liquidity preset",
            liquidity_profile_name=str(config.liquidity_profile_name),
        )
    if config.n_markets != len(scenario.markets):
        raise InvalidConfigError(
            "config and scenario disagree on the market count",
            config=config.n_markets,
            scenario=len(scenario.markets),
        )


def run_match(
    *,
    config: MatchConfig,
    world: World,
    agents: Sequence[AgentSpec],
    gateway: AgentGateway,
    out_dir: Path,
    rng: RngTree,
    match_id: str | None = None,
) -> MatchResult:
    """Run one match end to end and write its artefacts into ``out_dir``.

    ``out_dir`` is **this match's** artefact directory, the
    ``runs/<match_id>/`` of CONTRACTS section 4.6, and this function writes
    ``out_dir/journal.jsonl``, ``out_dir/observations.jsonl`` and
    ``out_dir/meta.json`` into it. It is not the
    runs root: the ``runs_dir`` to ``runs_dir/<match_id>`` step belongs to
    ``pxe.store.files.match_dir`` (section 7.20), which is the one builder of
    that layout, and every reader of an artefact reaches it through
    ``artefact_paths(runs_dir, match_id)``. A caller that has a runs root
    therefore passes ``match_dir(runs_dir, match_id)`` here, with the same
    ``match_id``.

    The ``RngTree`` is built by the caller, not here (section 3.1).

    Args:
        config: The authoritative match configuration.
        world: The generated world.
        agents: One :class:`~pxe.types.AgentSpec` per seat.
        gateway: The single source of agent decisions.
        out_dir: This match's artefact directory. Created if absent.
        rng: The root :class:`~pxe.rng.RngTree` of the match, that is
            ``RngTree(config.seed)``.
        match_id: Match id, or ``None`` to derive ``m-<template>-<seed>-01``
            from the world and the seed.

    Returns:
        The :class:`~pxe.types.MatchResult`, including the AC-P1 journal hash.

    Raises:
        InvalidConfigError: When ``config`` and ``world.scenario`` disagree
            (CONTRACTS section 2.6).
    """
    resolved_id = match_id if match_id is not None else f"m-{world.scenario.template_id}-{config.seed}-01"
    match_directory = Path(out_dir)
    match_directory.mkdir(parents=True, exist_ok=True)
    journal = Journal(resolved_id, match_directory / _JOURNAL_FILENAME)
    try:
        runner = MatchRunner(
            config=config,
            world=world,
            agents=agents,
            gateway=gateway,
            journal=journal,
            match_id=resolved_id,
            rng=rng,
            obs_path=match_directory / _OBSERVATIONS_FILENAME,
        )
        return runner.run()
    finally:
        journal.close()
