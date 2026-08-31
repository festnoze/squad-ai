"""The Claude Code CLI gateway (W8, CONTRACTS section 11), the paid LLM path.

This is the only opt-in, paid, non-deterministic surface of the package. Every
model call is one Claude Code CLI subprocess, launched with
:func:`asyncio.create_subprocess_exec` (never through a shell, so a seat id or a
task prompt can never be read as a shell metacharacter), one per agent per tick,
covering every intent of that tick in a single call.

Why one call per agent per tick
-------------------------------
The CLI carries a large fixed overhead per invocation (tens of thousands of
cached input tokens plus several seconds of latency). One call per tool would
multiply that overhead by the number of tools, so the whole tick's worth of
intents is decided in one call and parsed out of one JSON reply.

Budget caps are mandatory and checked first
-------------------------------------------
Every call is bounded before it is sent, by :class:`~ala.gateway.budget.BudgetTracker`.
The per call ceiling is the worst-case estimate checked before spawning, so a
breach costs nothing; the actual reported cost is recorded after the call so the
per match ceiling binds the next one. A match without a positive budget makes no
calls at all (the tracker forbids a non-positive ceiling), which keeps the paid
path opt-in.

Nothing raises at the engine boundary
-------------------------------------
A timeout, a non-zero exit, an ``is_error`` payload, or an unparsable reply makes
that one agent idle for the tick (``AgentAction(calls=())``) and the match
continues. The gateway never lets a provider failure reach the runner. ``--bare``
is never passed: it needs ``ANTHROPIC_API_KEY`` and this environment
authenticates with OAuth, so the flag would turn every call into an auth error.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import sys
from collections.abc import Mapping
from typing import Any

from ala.gateway.budget import BudgetTracker, usd_to_micro
from ala.gateway.prompt import parse_reply, render_prompt
from ala.gateway.protocol import GatewayConfig
from ala.types import AgentAction, AgentId, Observation

__all__ = ["ClaudeCliGateway", "GatewayConfig", "build_cli_argv", "claude_executable"]

#: Fallback model when a seat names none. A real match always names a model; this
#: only keeps a misconfigured seat from crashing the gateway constructor.
DEFAULT_MODEL = "claude-sonnet-5"


def claude_executable() -> str:
    """Return the Claude Code CLI executable name for this platform.

    Resolved at runtime, never cached: a cached value would be baked into a wheel
    built on one platform and run on another. The operating system resolves it
    against ``PATH``; no shell is ever involved.

    Returns:
        ``"claude.cmd"`` on Windows, ``"claude"`` elsewhere.
    """
    return "claude.cmd" if sys.platform.startswith("win") else "claude"


def build_cli_argv(*, prompt: str, model: str, max_budget_usd: int) -> list[str]:
    """Build the exact argv of one Claude Code CLI call.

    Notably absent, and deliberately: ``--bare`` (it needs an API key and this
    environment uses OAuth), and every tool, MCP, or slash-command source (an
    agent must not reach the real filesystem, network, or a command). The reply
    format is ``json`` so the wrapper carries the provider verdict and cost.

    Args:
        prompt: The rendered per-tick prompt.
        model: The provider model id for the seat.
        max_budget_usd: The per call USD ceiling handed to the CLI itself, a
            whole-dollar integer so the argv is byte stable.

    Returns:
        The argv, ready for :func:`asyncio.create_subprocess_exec`.
    """
    argv = [
        claude_executable(),
        "-p",
        prompt,
        "--model",
        model,
        "--output-format",
        "json",
        "--allowed-tools",
        "",
        "--disable-slash-commands",
        "--strict-mcp-config",
        "--setting-sources",
        "",
    ]
    if max_budget_usd > 0:
        argv.extend(["--max-budget-usd", str(max_budget_usd)])
    return argv


def _parse_cli_stdout(stdout: str) -> tuple[str, int, bool]:
    """Pull the model text, cost, and error verdict out of the CLI wrapper JSON.

    The ``--output-format json`` payload is a single object with ``result`` (the
    model's own answer, a string), ``total_cost_usd``, and ``is_error``. This
    reads only what the gateway needs and treats anything malformed as an error
    verdict, which the caller turns into an idle tick.

    Args:
        stdout: Whatever the process wrote on stdout.

    Returns:
        ``(result_text, cost_micro, is_error)``. ``is_error`` is ``True`` when the
        payload is missing, not an object, or flags an error, so the caller idles.
    """
    text = stdout.strip()
    if not text:
        return ("", 0, True)
    try:
        payload: Any = json.loads(text)
    except ValueError:
        return ("", 0, True)
    if not isinstance(payload, Mapping):
        return ("", 0, True)
    raw_result = payload.get("result")
    result_text = raw_result if isinstance(raw_result, str) else ""
    raw_cost = payload.get("total_cost_usd", 0.0)
    cost_micro = usd_to_micro(float(raw_cost)) if isinstance(raw_cost, (int, float)) else 0
    is_error = bool(payload.get("is_error", False)) or not isinstance(raw_result, str)
    return (result_text, cost_micro, is_error)


class ClaudeCliGateway:
    """One Claude Code CLI subprocess per agent per tick, under budget caps.

    Implements the :class:`~ala.gateway.protocol.Gateway` protocol. It never
    raises at ``acollect_actions``: a failing seat idles and the match continues.

    Attributes:
        agent_ids: The seats this gateway serves, in insertion order.
        budget: The shared per-match budget tracker, built from the config.
    """

    def __init__(
        self,
        models: Mapping[AgentId, str],
        config: GatewayConfig,
        permission: str,
        *,
        budget: BudgetTracker | None = None,
    ) -> None:
        """Seat one model per agent and bind the runtime settings.

        Args:
            models: Seat id to provider model id. A blank model falls back to
                :data:`DEFAULT_MODEL` so a misconfigured seat cannot crash the
                constructor.
            config: Timeouts, retries, and the USD ceilings. The budgets are
                read as whole USD and converted to micro-dollars for the tracker.
            permission: The AC-8 dial (``sandbox`` / ``silent`` / ``carte_blanche``)
                prepended to every prompt.
            budget: An explicit tracker, mostly for tests. When ``None`` one is
                built from ``config``'s per call and per match USD ceilings.
        """
        self._models: dict[AgentId, str] = {
            agent_id: (model or DEFAULT_MODEL) for agent_id, model in models.items()
        }
        self._config = config
        self._permission = permission
        self.budget = budget if budget is not None else self._budget_from_config(config)

    @staticmethod
    def _budget_from_config(config: GatewayConfig) -> BudgetTracker:
        """Build a tracker from the config's whole-USD ceilings.

        Args:
            config: The gateway configuration.

        Returns:
            A tracker whose ceilings are the config's USD values converted to
            micro-dollars.
        """
        return BudgetTracker(
            per_call_micro=usd_to_micro(float(config.budget_usd_per_call)),
            per_match_micro=usd_to_micro(float(config.budget_usd_per_match)),
        )

    @property
    def agent_ids(self) -> tuple[AgentId, ...]:
        """The seats served by this gateway.

        Returns:
            The seat ids, in insertion order.
        """
        return tuple(self._models.keys())

    async def acollect_actions(
        self, observations: Mapping[AgentId, Observation], tick: int
    ) -> Mapping[AgentId, AgentAction]:
        """Decide every seat's action for one tick, one CLI call per seat.

        The seats are called concurrently; each call is independently guarded, so
        one seat's timeout or budget refusal never stalls or fails another. A seat
        with no observation, or whose call fails, idles this tick.

        Args:
            observations: One observation per active seat.
            tick: The tick being decided.

        Returns:
            One action per seat in ``observations``. Never raises.
        """
        seats = [seat for seat in observations if seat in self._models]
        results = await asyncio.gather(*(self._acall_agent(seat, observations[seat]) for seat in seats))
        actions: dict[AgentId, AgentAction] = dict(zip(seats, results, strict=True))
        for seat in observations:
            actions.setdefault(seat, AgentAction(calls=()))
        return actions

    async def _acall_agent(self, agent_id: AgentId, obs: Observation) -> AgentAction:
        """Run one guarded CLI call for one seat.

        Enforces the budget before spawning, spawns at most once, and turns any
        timeout, launch error, non-zero exit, provider error verdict, or
        unparsable reply into an idle action. On success the actual cost is
        recorded so the per match ceiling binds the next call.

        Args:
            agent_id: The seat to call.
            obs: What that seat is allowed to know this tick.

        Returns:
            The seat's action, or ``AgentAction(calls=())`` on any failure.
        """
        prompt = render_prompt(obs, self._permission)
        estimate_micro = usd_to_micro(float(self._config.budget_usd_per_call))
        if not self.budget.check(estimate_micro):
            return AgentAction(calls=())
        argv = build_cli_argv(
            prompt=prompt,
            model=self._models[agent_id],
            max_budget_usd=self._config.budget_usd_per_call,
        )
        launched = await self._arun_cli(argv)
        if launched is None:
            return AgentAction(calls=())
        return_code, stdout = launched
        result_text, cost_micro, is_error = _parse_cli_stdout(stdout)
        self.budget.record(cost_micro)
        if return_code != 0 or is_error:
            return AgentAction(calls=())
        return parse_reply(result_text)

    async def _arun_cli(self, argv: list[str]) -> tuple[int, str] | None:
        """Launch the CLI once and collect its output, or report a launch failure.

        This is the single seam every offline test replaces, so the whole suite
        runs with no provider, no network, and no money. It applies the per-tick
        timeout and kills a process that outlives it, so no orphan survives.

        Args:
            argv: The exact argv from :func:`build_cli_argv`, passed as separate
                arguments (no shell).

        Returns:
            ``(return_code, stdout)`` on completion, or ``None`` on a timeout or a
            launch failure. Both map to an idle tick at the caller.
        """
        timeout = self._config.timeout_s if self._config.timeout_s > 0 else None
        try:
            process = await asyncio.create_subprocess_exec(
                *argv,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except OSError:
            return None
        try:
            stdout_bytes, _ = await asyncio.wait_for(process.communicate(), timeout=timeout)
        except TimeoutError:
            with contextlib.suppress(ProcessLookupError, OSError):
                process.kill()
            with contextlib.suppress(ProcessLookupError, OSError):
                await process.wait()
            return None
        return_code = process.returncode if process.returncode is not None else 0
        return (return_code, stdout_bytes.decode("utf-8", errors="replace"))

    def add_clone(self, parent_id: AgentId, child_id: AgentId) -> None:
        """Seat a clone at the parent's model.

        Args:
            parent_id: The seat being cloned. A missing parent falls back to
                :data:`DEFAULT_MODEL` so cloning never crashes the gateway.
            child_id: The new seat.
        """
        self._models[child_id] = self._models.get(parent_id, DEFAULT_MODEL)

    def retire(self, agent_id: AgentId) -> None:
        """Remove a culled seat so it receives no further calls.

        Args:
            agent_id: The seat to retire. A no-op if it is not seated.
        """
        self._models.pop(agent_id, None)
