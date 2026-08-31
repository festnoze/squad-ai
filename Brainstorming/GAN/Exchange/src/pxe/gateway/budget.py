"""The USD and token budgets of the gateway (FR-6.2.3, T2.5).

One public name: :class:`BudgetTracker`. It is a pure accumulator with no clock,
no network and no I/O; it is the thing that makes "the harness has a token
budget and a timeout per tick, configured per tournament" checkable.

Two mechanisms, both mandatory
------------------------------
FR-6.2.3 has two halves and this module owns one of them:

* the **timeout** per tick is ``GatewayConfig.timeout_s``, applied by
  :class:`~pxe.gateway.protocol.BaseGateway` to each ``acall_agent``;
* the **token budget** per tick is ``GatewayConfig.max_input_tokens_per_call``
  and ``.max_output_tokens_per_call``, applied by :meth:`BudgetTracker.check_tokens`.

"Per call" and "per tick" are the same quantity **because decision 14 fixes
exactly one provider call per agent per tick**, covering every market. That
equality is a consequence of a decision and not a coincidence, so
:meth:`BudgetTracker.tick_tokens` exists to let a test assert it on the tick and
not on the call. The day a second call per tick appears,
``test_budget.py::test_per_tick_tokens_equal_per_call_tokens`` fails, which is
the point.

A breach is not an exception at the engine boundary
---------------------------------------------------
Every check raises :class:`~pxe.errors.BudgetExceededError`, and the gateway
catches it and returns
``AgentReply(raw=None, source=FALLBACK, error=RejectReason.BUDGET_EXCEEDED)``
(CONTRACTS section 2.4 and section 7.16). The match never stops because one
agent got greedy. Both caps are enforced **before** the call is sent, so a
breach costs nothing.

Money here is a float, and that is legal
----------------------------------------
``cost_usd`` is a provider reported USD amount, never a journal field and never
an accounting field (CONTRACTS section 2.1 allows floats exactly outside the
journal). Comparisons therefore use a tiny epsilon so that spending exactly up
to the cap is allowed and floating point noise never turns a legal call into a
fallback.
"""

import logging
from collections.abc import Mapping

from pxe.errors import BudgetExceededError, InvalidConfigError
from pxe.gateway.protocol import AgentReply
from pxe.types import GatewayConfig

__all__ = [
    "BudgetTracker",
]

_LOG = logging.getLogger("pxe.gateway.budget")

#: The three budget scopes. ``call`` is a single call and does not accumulate:
#: its :meth:`BudgetTracker.check` compares the amount against the cap directly,
#: and :meth:`BudgetTracker.spent_usd` reports the last recorded call.
_SCOPES: tuple[str, ...] = ("call", "match", "tournament")

#: Tolerance of the USD comparisons, in USD. Spending exactly up to the cap is
#: allowed; a sum of provider reported floats landing one bit above it is not a
#: breach.
_USD_EPSILON: float = 1e-9


class BudgetTracker:
    """Accumulates cost and tokens, and refuses a call that would breach a cap.

    One tracker is built per match (or per tournament, with
    :meth:`reset_match` between matches) and shared by every seat, because the
    caps of FR-6.2.3 are per match and per tournament quantities, not per agent
    objects.

    Attributes:
        config: The gateway configuration holding every cap. Never journalled.
    """

    def __init__(self, config: GatewayConfig) -> None:
        """Build an empty tracker over one gateway configuration.

        Args:
            config: The caps to enforce. ``GatewayConfig`` is frozen, so the
                tracker holds it directly.
        """
        self.config = config
        self._spent_usd: dict[str, float] = dict.fromkeys(_SCOPES, 0.0)
        self._input_tokens: dict[str, int] = dict.fromkeys(_SCOPES, 0)
        self._output_tokens: dict[str, int] = dict.fromkeys(_SCOPES, 0)
        self._calls: dict[str, int] = dict.fromkeys(_SCOPES, 0)
        self._agent_tokens: dict[str, tuple[int, int]] = {}
        self._tick_tokens: dict[tuple[str, int], tuple[int, int]] = {}
        self._current_tick: int = 0

    # -- scopes -----------------------------------------------------------
    @staticmethod
    def _validated_scope(scope: str) -> str:
        """Return ``scope`` if it is one of the three known scopes.

        Args:
            scope: ``"call"``, ``"match"`` or ``"tournament"``.

        Returns:
            The same string.

        Raises:
            InvalidConfigError: If the scope is not one of the three.
        """
        if scope not in _SCOPES:
            raise InvalidConfigError("unknown budget scope", scope=scope, known=",".join(_SCOPES))
        return scope

    def _cap_usd(self, scope: str) -> float:
        """Return the USD cap of one scope.

        Args:
            scope: An already validated scope name.

        Returns:
            The cap in USD. A non positive cap forbids spending: the caps are
            written down in :class:`~pxe.types.GatewayConfig` and there is no
            "unlimited" spelling for money, deliberately (a runaway tournament
            is the failure this class exists to prevent).
        """
        caps: Mapping[str, float] = {
            "call": self.config.max_budget_usd_per_call,
            "match": self.config.max_budget_usd_per_match,
            "tournament": self.config.max_budget_usd_per_tournament,
        }
        return caps[scope]

    # -- the checks -------------------------------------------------------
    def check(self, *, scope: str, amount_usd: float) -> None:
        """Refuse a call whose cost would breach the USD cap of one scope.

        Called **before** the call is sent, so a breach costs nothing. The
        ``call`` scope does not accumulate: the amount is compared against the
        per call cap on its own.

        Args:
            scope: ``"call"``, ``"match"`` or ``"tournament"``.
            amount_usd: The cost about to be incurred, in USD.

        Raises:
            InvalidConfigError: If the scope is unknown or the amount negative.
            BudgetExceededError: If the cap cannot absorb the amount.
        """
        name = self._validated_scope(scope)
        if amount_usd < 0.0:
            raise InvalidConfigError("a budget amount cannot be negative", scope=name, amount_usd=amount_usd)
        cap = self._cap_usd(name)
        already = 0.0 if name == "call" else self._spent_usd[name]
        if already + amount_usd > cap + _USD_EPSILON:
            raise BudgetExceededError(
                "usd budget exceeded",
                scope=name,
                amount_usd=amount_usd,
                spent_usd=already,
                cap_usd=cap,
            )

    def check_tokens(
        self,
        *,
        input_tokens: int,
        output_tokens: int,
        agent_id: str | None = None,
        tick: int | None = None,
    ) -> None:
        """FR-6.2.3's other half: the per call (that is per tick) token budget.

        Raises against ``GatewayConfig.max_input_tokens_per_call`` and
        ``.max_output_tokens_per_call`` before the call is sent (the input side
        from the rendered prompt, the output side by passing the limit to the
        provider), and against ``max_tokens_per_match`` after it.

        Cached input tokens are deliberately not part of this arithmetic: the
        CLI overhead alone is about 35k cached tokens and would breach any sane
        per call input cap (CONTRACTS section 7.16, cost model).

        Args:
            input_tokens: Non cached input tokens the call will consume.
            output_tokens: Output tokens the call is allowed to produce.
            agent_id: The seat about to be called. Optional, and only used to
                read ``max_tokens_per_match`` per agent, which is how
                :class:`~pxe.types.GatewayConfig` documents that cap. Without
                it, the cumulative check is made against the whole match.
            tick: The tick being decided. Optional; when given it becomes the
                tick :meth:`record` attributes tokens to.

        Raises:
            InvalidConfigError: If a token count is negative.
            BudgetExceededError: If a per call cap or the cumulative cap of
                ``max_tokens_per_match`` is breached.
        """
        if input_tokens < 0 or output_tokens < 0:
            raise InvalidConfigError(
                "token counts cannot be negative",
                input_tokens=input_tokens,
                output_tokens=output_tokens,
            )
        if tick is not None:
            self.note_tick(tick)
        config = self.config
        if config.max_input_tokens_per_call > 0 and input_tokens > config.max_input_tokens_per_call:
            raise BudgetExceededError(
                "input token budget exceeded",
                agent_id=agent_id,
                input_tokens=input_tokens,
                cap=config.max_input_tokens_per_call,
            )
        if config.max_output_tokens_per_call > 0 and output_tokens > config.max_output_tokens_per_call:
            raise BudgetExceededError(
                "output token budget exceeded",
                agent_id=agent_id,
                output_tokens=output_tokens,
                cap=config.max_output_tokens_per_call,
            )
        cap = config.max_tokens_per_match
        if cap <= 0:
            return
        if agent_id is None:
            already = self._input_tokens["match"] + self._output_tokens["match"]
        else:
            spent_in, spent_out = self._agent_tokens.get(agent_id, (0, 0))
            already = spent_in + spent_out
        if already + input_tokens + output_tokens > cap:
            raise BudgetExceededError(
                "cumulative token budget exceeded",
                agent_id=agent_id,
                spent_tokens=already,
                requested_tokens=input_tokens + output_tokens,
                cap=cap,
            )

    # -- recording --------------------------------------------------------
    def note_tick(self, tick: int) -> None:
        """Declare the tick every following :meth:`record` belongs to.

        The bridge calls this once per tick, before dispatching the calls, so a
        provider adapter can record a reply without repeating the tick it
        already handed to ``acall_agent``. It is not part of the section 7.16
        surface: :class:`~pxe.gateway.protocol.AgentReply` carries no tick and
        ``record(reply)`` takes none, so the tick has to reach the tracker
        somehow for :meth:`tick_tokens` to exist at all.

        Args:
            tick: The tick being decided.
        """
        self._current_tick = int(tick)

    def record(self, reply: AgentReply, *, tick: int | None = None) -> None:
        """Book what one call actually cost.

        Args:
            reply: The reply produced by that call, successful or not. A
                fallback reply usually carries zeros, but a provider that
                charged for a failed attempt reports it here and it is counted.
            tick: The tick the call belongs to. Defaults to the last
                :meth:`note_tick` value, which the bridge sets per tick.
        """
        cost = max(0.0, float(reply.cost_usd))
        input_tokens = max(0, int(reply.input_tokens))
        output_tokens = max(0, int(reply.output_tokens))
        for scope in ("match", "tournament"):
            self._spent_usd[scope] += cost
            self._input_tokens[scope] += input_tokens
            self._output_tokens[scope] += output_tokens
            self._calls[scope] += 1
        self._spent_usd["call"] = cost
        self._input_tokens["call"] = input_tokens
        self._output_tokens["call"] = output_tokens
        self._calls["call"] = 1
        agent_in, agent_out = self._agent_tokens.get(reply.agent_id, (0, 0))
        self._agent_tokens[reply.agent_id] = (agent_in + input_tokens, agent_out + output_tokens)
        key = (reply.agent_id, self._current_tick if tick is None else int(tick))
        tick_in, tick_out = self._tick_tokens.get(key, (0, 0))
        self._tick_tokens[key] = (tick_in + input_tokens, tick_out + output_tokens)
        _LOG.debug(
            "call recorded",
            extra={
                "agent_id": reply.agent_id,
                "tick": key[1],
                "cost_usd": cost,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
            },
        )

    def reset_match(self) -> None:
        """Clear the match scope, keeping the tournament totals.

        A tournament reuses one tracker across matches, so the per match cap has
        to be released between them. The per agent and per tick token maps are
        cleared with it: they are per match quantities by definition.
        """
        self._spent_usd["match"] = 0.0
        self._spent_usd["call"] = 0.0
        self._input_tokens["match"] = 0
        self._output_tokens["match"] = 0
        self._input_tokens["call"] = 0
        self._output_tokens["call"] = 0
        self._calls["match"] = 0
        self._calls["call"] = 0
        self._agent_tokens.clear()
        self._tick_tokens.clear()
        self._current_tick = 0

    # -- readers ----------------------------------------------------------
    def spent_usd(self, scope: str = "match") -> float:
        """Return what has been spent in one scope, in USD.

        Args:
            scope: ``"call"`` (the last recorded call), ``"match"`` or
                ``"tournament"``.

        Returns:
            The cumulative cost of that scope.

        Raises:
            InvalidConfigError: If the scope is unknown.
        """
        return self._spent_usd[self._validated_scope(scope)]

    def remaining_usd(self, scope: str = "match") -> float:
        """Return what is left to spend in one scope, in USD.

        Args:
            scope: ``"call"``, ``"match"`` or ``"tournament"``.

        Returns:
            ``cap - spent``, never below zero. For the ``call`` scope the cap
            itself, since a call does not accumulate.

        Raises:
            InvalidConfigError: If the scope is unknown.
        """
        name = self._validated_scope(scope)
        already = 0.0 if name == "call" else self._spent_usd[name]
        return max(0.0, self._cap_usd(name) - already)

    def spent_tokens(self, scope: str = "match") -> tuple[int, int]:
        """Return the tokens consumed in one scope.

        Args:
            scope: ``"call"`` (the last recorded call), ``"match"`` or
                ``"tournament"``.

        Returns:
            ``(input_tokens, output_tokens)``. Cached input tokens are not
            included: they are traced, not budgeted.

        Raises:
            InvalidConfigError: If the scope is unknown.
        """
        name = self._validated_scope(scope)
        return (self._input_tokens[name], self._output_tokens[name])

    def tick_tokens(self, agent_id: str, tick: int) -> tuple[int, int]:
        """What one agent spent on one tick.

        This is the per tick view FR-6.2.3 is written against. With decision 14
        (one call per agent per tick) it equals the per call numbers, and the
        test that asserts that equality over a whole match is what fails the day
        a second call per tick appears.

        Args:
            agent_id: The seat.
            tick: The tick.

        Returns:
            ``(input_tokens, output_tokens)``, ``(0, 0)`` when nothing was
            recorded for that pair.
        """
        return self._tick_tokens.get((agent_id, int(tick)), (0, 0))

    def calls(self, scope: str = "match") -> int:
        """Number of calls recorded in one scope.

        Args:
            scope: ``"call"``, ``"match"`` or ``"tournament"``.

        Returns:
            The call count of that scope.

        Raises:
            InvalidConfigError: If the scope is unknown.
        """
        return self._calls[self._validated_scope(scope)]
