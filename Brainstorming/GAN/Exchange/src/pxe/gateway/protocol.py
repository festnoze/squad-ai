"""The gateway protocol, the reply carrier and the synchronous bridge.

Three names are public and they are the whole contract of this module
(CONTRACTS section 7.16): :class:`AgentReply`, :class:`AgentGateway` and
:class:`BaseGateway`. Five other work packages type against them.

The boundary, restated
----------------------
The engine is pure and synchronous and never calls an LLM. This module is the
only place where it touches the impure world, and it does so through exactly
one synchronous call, ``collect_actions``, whose default implementation drives
the asynchronous one with :func:`asyncio.run` (decision 15).

Four rules of CONTRACTS section 7.16 are implemented here, literally:

1. **Replies, never actions.** ``collect_actions`` and ``acollect_actions``
   return ``tuple[AgentReply, ...]``, one reply per observation, sorted by
   ``agent_id`` regardless of completion order. There is no ``AgentAction``
   anywhere in this package's public API.
2. **``AgentReply.raw`` is a JSON compatible mapping matching
   ``schemas/action.v1.json``, or ``None``.** Never an ``AgentAction``, never a
   string, never a list.
3. **The gateway never validates and never rejects.** It has no
   ``open_market_ids``, no ``resting_order_ids`` and no ``MatchConfig``
   semantics. Its only judgement is "did the call succeed": on a timeout, a
   provider failure, a parse failure or a budget breach it returns
   ``raw=None``, ``source=FALLBACK`` and the matching
   :class:`~pxe.types.RejectReason` in ``error`` (FR-5.1.1). This module
   therefore never imports :mod:`pxe.runner.action_validator`.
4. **``raw_text``, ``cost_usd``, ``latency_ms``, the token counts and
   ``attempts`` never reach the journal.** They are wall clock and provider
   dependent (CONTRACTS section 3.5) and go to
   ``runs/<match_id>/llm_trace.jsonl``, written by A14.

Why this module swallows errors, and only here
----------------------------------------------
CONTRACTS section 2.4 forbids the engine from catching :class:`PxeError`
broadly, and grants exactly one exception: the gateway, and only to implement
the FR-5.1.1 "no action" fallback. :meth:`BaseGateway._acall_guarded` is that
exception, and its ``except`` clauses are deliberately narrow. A
:class:`~pxe.errors.GatewayError` (timeout, provider, budget, malformed
response) and an :class:`OSError` (a subprocess that could not even be
launched) become a fallback reply and the match continues. Anything else (an
:class:`~pxe.errors.InvariantViolationError`, a bug in a scripted baseline)
propagates and aborts the match loudly, which is what it should do.

The tick bound (T2.5)
---------------------
Each ``acall_agent`` is wrapped in :func:`asyncio.wait_for` with
``GatewayConfig.timeout_s``, and calls run concurrently under a semaphore of
``GatewayConfig.max_parallel_calls``. One agent's timeout therefore costs the
tick ``timeout_s``, not ``timeout_s`` per remaining agent: the whole tick is
bounded by ``ceil(n_agents / max_parallel_calls) * timeout_s`` plus scheduling
overhead, which is ``timeout_s`` when the parallelism covers the table.
"""

import asyncio
import logging
import time
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

from pxe.errors import GatewayError, InvalidConfigError, PxeError
from pxe.rng import RngTree
from pxe.types import (
    AgentSource,
    GatewayConfig,
    MatchConfig,
    Observation,
    RejectReason,
    reject_reason_of,
    sorted_ids,
)

if TYPE_CHECKING:  # pragma: no cover - typing only, so there is no import cycle
    from pxe.gateway.budget import BudgetTracker

__all__ = [
    "AgentReply",
    "AgentGateway",
    "BaseGateway",
]

_LOG = logging.getLogger("pxe.gateway")


@dataclass(frozen=True, slots=True)
class AgentReply:
    """Everything one agent produced for one tick. The gateway's only output.

    Journalled: ``agent_id``, ``source``, ``error``, and ``raw`` once it has
    been validated by the runner. Not journalled, written to
    ``llm_trace.jsonl`` instead: ``raw_text``, ``cost_usd``, ``latency_ms``,
    the token counts and ``attempts`` (CONTRACTS section 3.5).

    Attributes:
        agent_id: The seat that produced it, ``A1``..``A8``.
        raw: The parsed JSON payload in the ``schemas/action.v1.json`` shape, or
            ``None`` on failure. Never an ``AgentAction``, never a string.
        raw_text: Verbatim provider text, for the trace only. ``None`` for a
            scripted agent, which produces no text.
        source: ``scripted``, ``llm`` or ``fallback``.
        error: ``None`` on success. On failure it is the reason
            ``AgentTimedOut.reason`` carries, and it is the only place that
            reason exists.
        cost_usd: Provider cost of the call in USD. Never journalled.
        latency_ms: Wall clock duration of the call. Never journalled.
        input_tokens: Non cached input tokens billed by the provider.
        output_tokens: Output tokens billed by the provider.
        cached_input_tokens: Cached input tokens (prompt cache reads). Traced
            but deliberately **not** budgeted: the CLI overhead alone is about
            35k cached tokens, which would breach any sane per call input cap
            (CONTRACTS section 7.16, cost model).
        attempts: Number of provider attempts, ``1`` when the first one worked.

    Note:
        The six telemetry fields carry defaults so that a scripted or fallback
        reply, which has nothing to report, is constructible without six zeros.
        The five contractual fields have none.
    """

    agent_id: str
    raw: Mapping[str, Any] | None
    raw_text: str | None
    source: AgentSource
    error: RejectReason | None
    cost_usd: float = 0.0
    latency_ms: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cached_input_tokens: int = 0
    attempts: int = 1

    @property
    def ok(self) -> bool:
        """True when the call succeeded and ``raw`` can be validated.

        Returns:
            Whether ``error`` is ``None`` and ``raw`` is present.
        """
        return self.error is None and self.raw is not None


@runtime_checkable
class AgentGateway(Protocol):
    """What the runner needs from any source of agent decisions.

    The runner holds exactly one of these and calls ``collect_actions`` once per
    tick, in P2. Nothing else in the engine touches this object.
    """

    def collect_actions(
        self, *, tick: int, observations: Sequence[Observation], config: MatchConfig
    ) -> tuple[AgentReply, ...]:
        """Collect one reply per observation, synchronously.

        Args:
            tick: The tick being decided, 1 based.
            observations: One observation per ranked, non frozen agent.
            config: The match configuration, for the agents that need it.

        Returns:
            One reply per observation, sorted by ``agent_id``.
        """
        ...

    async def acollect_actions(
        self, *, tick: int, observations: Sequence[Observation], config: MatchConfig
    ) -> tuple[AgentReply, ...]:
        """Collect one reply per observation, asynchronously.

        Args:
            tick: The tick being decided, 1 based.
            observations: One observation per ranked, non frozen agent.
            config: The match configuration, for the agents that need it.

        Returns:
            One reply per observation, sorted by ``agent_id``.
        """
        ...

    def reset_agents(self, *, config: MatchConfig, rng: RngTree) -> None:
        """Reset every scripted seat behind this gateway (section 3.1).

        The runner calls this exactly once per match, after ``MatchStarted`` and
        before tick 1. An orchestrator reuses agent objects across matches, so
        without it the second match inherits the first one's internal state and
        O1 dies silently. A gateway with no scripted state (an LLM gateway)
        implements it as a no-op.

        The per seat generator is
        ``rng.child(f"agent/{agent_id}").substream(f"agent.{agent_id}")``, built
        here and not by the runner, because only the gateway knows which seats
        it actually holds.

        Args:
            config: The match configuration handed to every agent.
            rng: The match ``RngTree`` the caller built (section 3.1).
        """
        ...

    def close(self) -> None:
        """Release every provider resource. Idempotent."""
        ...


def _sorted_replies(replies: Iterable[AgentReply]) -> tuple[AgentReply, ...]:
    """Order replies by ``agent_id``, whatever order they completed in.

    The ordering goes through :func:`pxe.types.sorted_ids`, the one canonical
    implementation (CONTRACTS section 2.3), so ``A10`` follows ``A9`` and a
    reserved account id (``MM``, ``FEES``) is refused rather than silently
    misplaced: neither ever receives an observation.

    Args:
        replies: The replies of one tick, in completion order.

    Returns:
        The same replies, ascending by ``agent_id``. A duplicated seat keeps its
        relative arrival order, because dropping one would break the "one reply
        per observation" promise.

    Raises:
        InvalidConfigError: If a reply carries ``MM`` or ``FEES``.
    """
    pending: dict[str, list[AgentReply]] = {}
    ids: list[str] = []
    for reply in replies:
        pending.setdefault(reply.agent_id, []).append(reply)
        ids.append(reply.agent_id)
    return tuple(pending[agent_id].pop(0) for agent_id in sorted_ids(ids))


def _reason_of(error: PxeError) -> RejectReason:
    """Map a caught gateway error onto the reason the reply carries.

    Args:
        error: The error caught at the gateway boundary.

    Returns:
        The mapped :class:`~pxe.types.RejectReason`. An error whose ``code`` has
        no reason (the bare :class:`~pxe.errors.GatewayError` base, whose code is
        deliberately not a journal reason) degrades to ``PROVIDER_ERROR`` rather
        than raising from inside the fallback path.
    """
    try:
        return reject_reason_of(error)
    except InvalidConfigError:
        return RejectReason.PROVIDER_ERROR


def _elapsed_ms(started: float) -> int:
    """Return the milliseconds elapsed since a :func:`time.perf_counter` mark.

    Args:
        started: The mark taken before the call.

    Returns:
        A non negative integer number of milliseconds.
    """
    return max(0, int((time.perf_counter() - started) * 1000.0))


class BaseGateway(AgentGateway):
    """The synchronous bridge, the timeout and the parallelism.

    Subclasses implement :meth:`acall_agent` and nothing else. This class owns
    everything that must not vary between gateways: the ``asyncio.run`` bridge,
    the per call timeout, the bounded parallelism, the FR-5.1.1 fallback and the
    ``agent_id`` ordering of the result.

    A subclass either calls ``super().__init__(gateway_config=..., budget=...)``
    or assigns ``self.gateway_config`` itself; the class level defaults below
    keep a subclass that does neither working with the stock
    :class:`~pxe.types.GatewayConfig`.

    Attributes:
        gateway_config: Timeouts, budgets and concurrency. Never journalled.
        budget: The tracker enforcing the USD and token caps, or ``None`` when no
            budget is attached (a scripted gateway spends nothing).
    """

    #: Class level default so a subclass that never calls ``super().__init__``
    #: still has a timeout and a parallelism bound. ``GatewayConfig`` is frozen,
    #: so sharing one instance between subclasses is safe.
    gateway_config: GatewayConfig = GatewayConfig()
    #: Class level default: no budget attached.
    budget: "BudgetTracker | None" = None

    def __init__(
        self,
        *,
        gateway_config: GatewayConfig | None = None,
        budget: "BudgetTracker | None" = None,
    ) -> None:
        """Bind the runtime settings of this gateway.

        Args:
            gateway_config: Timeouts, budgets and concurrency. Defaults to the
                stock :class:`~pxe.types.GatewayConfig`.
            budget: Budget tracker shared by every seat of the match, or
                ``None``.
        """
        if gateway_config is not None:
            self.gateway_config = gateway_config
        if budget is not None:
            self.budget = budget

    # -- the one method a subclass implements -----------------------------
    async def acall_agent(self, *, agent_id: str, observation: Observation, tick: int) -> AgentReply:
        """Produce one reply for one agent. Implemented by the subclass.

        The implementation may raise: :meth:`_acall_guarded` turns a
        :class:`~pxe.errors.GatewayError` or an :class:`OSError` into the
        FR-5.1.1 fallback reply.

        Args:
            agent_id: The seat to call.
            observation: What that seat is allowed to know this tick.
            tick: The tick being decided.

        Returns:
            The reply of that agent.

        Raises:
            NotImplementedError: Always, in this class.
        """
        raise NotImplementedError("a gateway must implement acall_agent (CONTRACTS section 7.16)")

    # -- the bridge -------------------------------------------------------
    def collect_actions(
        self, *, tick: int, observations: Sequence[Observation], config: MatchConfig
    ) -> tuple[AgentReply, ...]:
        """Drive :meth:`acollect_actions` with :func:`asyncio.run` (decision 15).

        This is the single call the pure engine makes into the impure world.

        Args:
            tick: The tick being decided, 1 based.
            observations: One observation per ranked, non frozen agent. Empty
                when no market is open, in which case no provider call is made
                at all (CONTRACTS section 5.0).
            config: The match configuration.

        Returns:
            One reply per observation, sorted by ``agent_id``.

        Raises:
            GatewayError: If called from inside a running event loop, where
                ``asyncio.run`` cannot be used. Await ``acollect_actions``
                instead.
        """
        if not observations:
            return ()
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            pass
        else:
            raise GatewayError(
                "collect_actions is the synchronous bridge and cannot run inside an event loop; "
                "await acollect_actions instead",
                tick=tick,
            )
        return asyncio.run(self.acollect_actions(tick=tick, observations=observations, config=config))

    async def acollect_actions(
        self, *, tick: int, observations: Sequence[Observation], config: MatchConfig
    ) -> tuple[AgentReply, ...]:
        """Call every agent concurrently, bounded by timeout and parallelism.

        Args:
            tick: The tick being decided, 1 based.
            observations: One observation per ranked, non frozen agent.
            config: The match configuration. Unused here: it is handed to the
                agents by the concrete gateway, which is what keeps this method
                free of any ``MatchConfig`` semantics (rule 3).

        Returns:
            One reply per observation, sorted by ``agent_id``.
        """
        del config  # rule 3: the bridge has no MatchConfig semantics.
        if not observations:
            return ()
        budget = self.budget
        if budget is not None:
            # So that a provider adapter can record a reply without repeating
            # the tick it was already handed (CONTRACTS section 7.16, per tick
            # budget): AgentReply carries no tick and record() takes none.
            budget.note_tick(tick)
        limit = max(1, self.gateway_config.max_parallel_calls)
        semaphore = asyncio.Semaphore(limit)

        async def call_one(observation: Observation) -> AgentReply:
            async with semaphore:
                return await self._acall_guarded(observation=observation, tick=tick)

        replies = await asyncio.gather(*[call_one(observation) for observation in observations])
        return _sorted_replies(replies)

    def reset_agents(self, *, config: MatchConfig, rng: RngTree) -> None:
        """Reset every scripted seat. The default gateway holds none.

        ``ClaudeCliGateway`` and any other provider backed gateway inherits this
        no-op: there is no scripted state to clear. ``ScriptedGateway`` and
        ``CompositeGateway`` override it.

        Args:
            config: The match configuration handed to every agent.
            rng: The match ``RngTree`` the caller built (section 3.1).
        """

    def close(self) -> None:
        """Release provider resources. The default gateway holds none."""

    # -- the fallback path ------------------------------------------------
    async def _acall_guarded(self, *, observation: Observation, tick: int) -> AgentReply:
        """Call one agent under the per call timeout and the FR-5.1.1 fallback.

        Args:
            observation: The observation to answer.
            tick: The tick being decided.

        Returns:
            The agent's reply, or a fallback reply carrying the failure reason.
        """
        agent_id = observation.agent_id
        started = time.perf_counter()
        timeout = self.gateway_config.timeout_s
        try:
            self._check_match_budget()
            return await asyncio.wait_for(
                self.acall_agent(agent_id=agent_id, observation=observation, tick=tick),
                timeout=timeout if timeout > 0 else None,
            )
        except TimeoutError:
            reason = RejectReason.AGENT_TIMEOUT
        except GatewayError as error:
            reason = _reason_of(error)
        except OSError as error:
            _LOG.warning(
                "provider could not be launched",
                extra={"tick": tick, "agent_id": agent_id, "detail": str(error)[:200]},
            )
            reason = RejectReason.PROVIDER_ERROR
        latency_ms = _elapsed_ms(started)
        _LOG.warning(
            "agent produced no action, falling back (FR-5.1.1)",
            extra={"tick": tick, "agent_id": agent_id, "reason": str(reason), "latency_ms": latency_ms},
        )
        return self._fallback_reply(agent_id=agent_id, error=reason, latency_ms=latency_ms)

    def _check_match_budget(self) -> None:
        """Refuse a call whose worst case cost would breach the match cap.

        The check happens **before** the call is sent, so a breach costs nothing
        (CONTRACTS section 7.16). The amount checked is the per call cap, which
        is the worst case of a single call.

        Raises:
            BudgetExceededError: If the match cap cannot absorb another call.
        """
        budget = self.budget
        if budget is None:
            return
        budget.check(scope="match", amount_usd=self.gateway_config.max_budget_usd_per_call)

    def _fallback_reply(
        self,
        *,
        agent_id: str,
        error: RejectReason,
        latency_ms: int = 0,
        raw_text: str | None = None,
        cost_usd: float = 0.0,
        attempts: int = 1,
    ) -> AgentReply:
        """Build the FR-5.1.1 "no action" reply.

        Protected rather than public on purpose: it is the shape every gateway of
        this package must produce on failure, and A14's CLI adapter uses it after
        its last retry so that exactly one spelling of "no action" exists.

        Args:
            agent_id: The seat that failed.
            error: Why it failed. Becomes ``AgentTimedOut.reason``.
            latency_ms: Wall clock spent before giving up.
            raw_text: Whatever text the provider did produce, for the trace.
            cost_usd: Cost already incurred by the failed attempts.
            attempts: How many attempts were made.

        Returns:
            A reply with ``raw=None`` and ``source=FALLBACK``.
        """
        return AgentReply(
            agent_id=agent_id,
            raw=None,
            raw_text=raw_text,
            source=AgentSource.FALLBACK,
            error=error,
            cost_usd=cost_usd,
            latency_ms=latency_ms,
            attempts=attempts,
        )
