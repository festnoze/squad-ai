"""The Claude Code CLI adapter (A14, CONTRACTS section 7.16).

This is the LLM provider of the whole product, and it is a hard requirement:
**every** model call goes through the Claude Code CLI. There is no HTTP client
here, no API key and no SDK; the transport is one subprocess per agent per tick,
launched with :func:`asyncio.create_subprocess_exec` and never through a shell.

The measured cost model (decision 14)
-------------------------------------
About 0.027 USD and about 6 s per call, with roughly 35 000 cached input tokens
of unavoidable CLI overhead on every call. Two consequences are structural and
not tunable:

* **one call per agent per tick, covering every market at once.** One call per
  market would multiply the fixed overhead by ``n_markets``.
* **budget caps are mandatory.** Every call is bounded before it is sent, by
  USD (:meth:`~pxe.gateway.budget.BudgetTracker.check`) and by tokens
  (:meth:`~pxe.gateway.budget.BudgetTracker.check_tokens`), so a breach costs
  nothing.

``--bare`` is never passed. It requires ``ANTHROPIC_API_KEY`` and this
environment authenticates with OAuth, so the flag turns every call into an
authentication error.

What this module judges, and what it refuses to judge
----------------------------------------------------
Rule 3 of CONTRACTS section 7.16: the gateway never validates semantics. It
answers exactly one question, "did the call succeed", and it carries the model's
answer through verbatim. Concretely it does check that stdout is a JSON object
and that the model's ``result`` field parses into a JSON **object** (rule 2:
``AgentReply.raw`` is a mapping or ``None``), and it checks nothing else: an
action naming a resolved market, an out of range price or a missing prediction
is A11's business, in the runner, where ``open_market_ids`` and the
``MatchConfig`` semantics actually exist.

FR-5.1.1, spelled out
---------------------
A timeout, a non zero exit code, an ``is_error`` payload, unparsable stdout or a
``result`` that is not a JSON object is a failed attempt. Attempts are retried
up to ``GatewayConfig.retries`` times; after the last one the call returns
``AgentReply(raw=None, source=FALLBACK, error=<reason>)`` and the match
continues. The runner turns that reply into ``AgentTimedOut`` and carries the
agent's previous predictions (FR-6.2.4). Nothing here raises at the engine
boundary.

The per attempt timeout, and why it is a division
-------------------------------------------------
``BaseGateway._acall_guarded`` already wraps the whole of :meth:`acall_agent` in
``asyncio.wait_for(..., GatewayConfig.timeout_s)``: that is FR-6.2.3's per tick
timeout and it is not negotiable. So the retries have to fit **inside** it, or
the outer bound would cut the second attempt off, report ``AGENT_TIMEOUT`` with
``attempts=1`` and lose the retry accounting FR-5.1.1 asks for. Each attempt is
therefore allowed ``timeout_s / (retries + 1)`` seconds. ``timeout_s <= 0``
disables both bounds, exactly as in ``BaseGateway``.

The trace artefact
------------------
``runs/<match_id>/llm_trace.jsonl`` (CONTRACTS section 4.6) is written here and
nowhere else, one line per call, through :func:`write_llm_trace`. It carries the
five families of fact that are forbidden in a journal because they vary between
two runs of the same seed (CONTRACTS section 3.5): cost, latency, token counts,
attempt counts and verbatim model text. It is outside the AC-P1 hash by
construction, which is why an LLM match can be replayed from its journal while
its cost cannot be reproduced.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import math
import sys
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from pxe.errors import BudgetExceededError, InvalidConfigError, MalformedResponseError
from pxe.events import JOURNAL_ENCODING, JOURNAL_NEWLINE, stable_json
from pxe.gateway.budget import BudgetTracker
from pxe.gateway.prompt import PROMPT_TEMPLATE_VERSION, build_system_prompt, build_user_prompt
from pxe.gateway.protocol import AgentReply, BaseGateway
from pxe.runner.observation_builder import TOKEN_CHARS_PER_TOKEN, observation_to_json
from pxe.runner.schema_registry import action_schema
from pxe.types import (
    AgentSource,
    GatewayConfig,
    HarnessConfig,
    MatchConfig,
    Observation,
    RejectReason,
    sorted_ids,
)

__all__ = [
    "DEFAULT_MODEL",
    "ClaudeCliGateway",
    "ClaudeCliResult",
    "LlmTraceEntry",
    "build_cli_argv",
    "claude_executable",
    "parse_cli_stdout",
    "write_llm_trace",
]

_LOG = logging.getLogger("pxe.gateway.claude_cli")

#: The one model this product runs on (a hard user requirement). A harness may
#: name another one, and ``build_cli_argv`` passes whatever it is given; this is
#: the value every shipped preset uses.
DEFAULT_MODEL = "claude-sonnet-5"

#: Maximum characters of model text kept in a log record (CONTRACTS section 2.5:
#: a log line never carries a raw model output longer than 200 characters). The
#: trace file is not a log and keeps the whole text.
_LOG_TEXT_LIMIT = 200

#: Fence markers a model sometimes wraps structured output in, even under
#: ``--json-schema``. Stripped before parsing, never interpreted.
_FENCES = ("```json", "```JSON", "```")


# --------------------------------------------------------------------------
# The provider answer
# --------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class ClaudeCliResult:
    """One parsed stdout payload of the Claude Code CLI.

    Attributes:
        is_error: The CLI's own verdict on the call. ``True`` means the call
            failed even though the process may have exited with code ``0``.
        result_text: The model's answer, verbatim. Under ``--json-schema`` it is
            a JSON document, but this field is a string and is never trusted to
            be one: :meth:`ClaudeCliGateway.acall_agent` parses it and treats a
            failure as a failed attempt.
        total_cost_usd: What the call cost, in USD, as reported by the CLI.
        duration_ms: Wall clock duration reported by the CLI. The gateway
            measures its own latency as well, and traces that one.
        input_tokens: Non cached input tokens billed.
        output_tokens: Output tokens billed.
        cache_creation_input_tokens: Input tokens written into the prompt cache.
        cache_read_input_tokens: Input tokens served from the prompt cache. This
            is where the roughly 35 000 tokens of CLI overhead land, which is
            why cached tokens are excluded from the token budget (ruling R66).
    """

    is_error: bool
    result_text: str
    total_cost_usd: float
    duration_ms: int
    input_tokens: int
    output_tokens: int
    cache_creation_input_tokens: int
    cache_read_input_tokens: int

    @property
    def cached_input_tokens(self) -> int:
        """Cached input tokens of the call, creation plus read.

        Returns:
            The sum of the two cache counters, which is what
            ``AgentReply.cached_input_tokens`` carries.
        """
        return self.cache_creation_input_tokens + self.cache_read_input_tokens


# --------------------------------------------------------------------------
# The trace artefact
# --------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class LlmTraceEntry:
    """One line of ``runs/<match_id>/llm_trace.jsonl`` (CONTRACTS section 4.6).

    Every field here is forbidden in a journal (CONTRACTS section 3.5): cost,
    latency, token counts, attempt counts and verbatim model text all vary
    between two runs of the same seed. The file is outside the AC-P1 hash, so
    T2.3's "cost and latency logged per tick and per agent" is satisfiable
    without touching determinism.

    Attributes:
        tick: The tick the call decided.
        agent_id: The seat that was called.
        harness_key: ``HarnessConfig.key`` of the seat, so a trace joins onto
            ratings and elites without a second lookup.
        model: The provider model id actually passed to the CLI.
        prompt_template_version: :data:`~pxe.gateway.prompt.PROMPT_TEMPLATE_VERSION`.
        ok: Whether the call produced a usable payload.
        error: The ``RejectReason`` value on failure, ``None`` on success.
        attempts: Provider attempts made, ``0`` when a budget cap refused the
            call before it was sent.
        cost_usd: Total USD across every attempt.
        latency_ms: Wall clock the gateway spent on the whole call.
        input_tokens: Non cached input tokens, summed over attempts.
        output_tokens: Output tokens, summed over attempts.
        cache_creation_input_tokens: Prompt cache writes, summed over attempts.
        cache_read_input_tokens: Prompt cache reads, summed over attempts.
        estimated_input_tokens: What the budget check estimated before sending,
            so a systematic gap between estimate and bill is visible.
        raw_text: Verbatim model text of the last attempt, whole and untruncated.
    """

    tick: int
    agent_id: str
    harness_key: str
    model: str
    prompt_template_version: str
    ok: bool
    error: str | None
    attempts: int
    cost_usd: float
    latency_ms: int
    input_tokens: int
    output_tokens: int
    cache_creation_input_tokens: int
    cache_read_input_tokens: int
    estimated_input_tokens: int
    raw_text: str

    def to_dict(self) -> dict[str, Any]:
        """Render the entry as a JSON friendly mapping.

        Returns:
            A dict of ``str``, ``int``, ``float``, ``bool`` and ``None`` only.
            Keys are written in declaration order and re-sorted by
            :func:`pxe.events.stable_json`, so no writer chooses a key order.
        """
        return {
            "tick": self.tick,
            "agent_id": self.agent_id,
            "harness_key": self.harness_key,
            "model": self.model,
            "prompt_template_version": self.prompt_template_version,
            "ok": self.ok,
            "error": self.error,
            "attempts": self.attempts,
            "cost_usd": self.cost_usd,
            "latency_ms": self.latency_ms,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cache_creation_input_tokens": self.cache_creation_input_tokens,
            "cache_read_input_tokens": self.cache_read_input_tokens,
            "estimated_input_tokens": self.estimated_input_tokens,
            "raw_text": self.raw_text,
        }


def write_llm_trace(path: Path, entry: LlmTraceEntry) -> None:
    r"""Append one line to ``runs/<match_id>/llm_trace.jsonl``.

    The file is opened with the artefact conventions of CONTRACTS section 4.2
    (``encoding="utf-8"``, ``newline="\\n"``) so a Windows run and a Linux run
    produce the same bytes, even though this file is not hashed. The parent
    directory is created on demand: the caller passes a path inside a run
    directory that may not exist yet.

    Args:
        path: Destination file. Created if missing, appended to otherwise.
        entry: The call to record.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    line = stable_json(entry.to_dict())
    with path.open("a", encoding=JOURNAL_ENCODING, newline=JOURNAL_NEWLINE) as handle:
        handle.write(line + "\n")


# --------------------------------------------------------------------------
# The transport
# --------------------------------------------------------------------------
def claude_executable() -> str:
    """Return the name of the Claude Code CLI executable for this platform.

    Resolved at runtime and never cached: a cached value would be baked into a
    wheel built on one platform and used on another.

    Returns:
        ``"claude.cmd"`` on Windows, ``"claude"`` everywhere else. The name is
        resolved against ``PATH`` by the operating system, never by a shell:
        every call uses :func:`asyncio.create_subprocess_exec`, so a seat id or
        a news headline can never be interpreted as a shell metacharacter.
    """
    return "claude.cmd" if sys.platform.startswith("win") else "claude"


def build_cli_argv(
    *,
    prompt: str,
    system_prompt: str,
    model: str,
    schema: Mapping[str, Any],
    max_budget_usd: float,
) -> list[str]:
    """Build the exact argv of one Claude Code CLI call.

    The list is frozen by CONTRACTS section 7.16 and
    ``test_gateway_claude_cli.py::test_argv_is_frozen`` compares it element by
    element. Notably absent, and deliberately: ``--bare`` (it needs
    ``ANTHROPIC_API_KEY`` and this environment authenticates with OAuth) and any
    tool, MCP or settings source (an agent must not reach the filesystem, the
    network or a slash command).

    Args:
        prompt: The per tick user prompt, from
            :func:`~pxe.gateway.prompt.build_user_prompt`.
        system_prompt: The seat's system prompt, from
            :func:`~pxe.gateway.prompt.build_system_prompt`.
        model: Provider model id, ``claude-sonnet-5`` for every shipped preset.
        schema: The action JSON Schema, handed verbatim through
            ``--json-schema``. It is never patched at runtime (section 8.2): a
            mutated schema is a different schema and the provider caches it.
        max_budget_usd: Per call USD cap handed to the CLI itself, formatted with
            four decimals so the argv is byte stable.

    Returns:
        The argv, ready for :func:`asyncio.create_subprocess_exec`.
    """
    return [
        claude_executable(),
        "-p",
        prompt,
        "--model",
        model,
        "--output-format",
        "json",
        "--system-prompt",
        system_prompt,
        "--json-schema",
        json.dumps(schema),
        "--allowed-tools",
        "",
        "--disable-slash-commands",
        "--strict-mcp-config",
        "--setting-sources",
        "",
        "--max-budget-usd",
        f"{max_budget_usd:.4f}",
    ]


def _as_int(value: Any, *, field_name: str) -> int:
    """Coerce a JSON number into an ``int`` or refuse the payload.

    Args:
        value: The decoded JSON value.
        field_name: Name used in the error context.

    Returns:
        The integer value. ``None`` and a missing key become ``0``: the CLI omits
        a counter it has nothing to report for.

    Raises:
        MalformedResponseError: If the value is present and not a number.
    """
    if value is None:
        return 0
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise MalformedResponseError("cli field is not a number", field=field_name, value=repr(value)[:80])
    return int(value)


def _as_float(value: Any, *, field_name: str) -> float:
    """Coerce a JSON number into a ``float`` or refuse the payload.

    Args:
        value: The decoded JSON value.
        field_name: Name used in the error context.

    Returns:
        The float value, ``0.0`` when absent.

    Raises:
        MalformedResponseError: If the value is present and not a number.
    """
    if value is None:
        return 0.0
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise MalformedResponseError("cli field is not a number", field=field_name, value=repr(value)[:80])
    return float(value)


def _decode_json_object(text: str) -> dict[str, Any]:
    """Decode ``text`` into a JSON object, tolerating a code fence.

    Args:
        text: Candidate JSON document.

    Returns:
        The decoded object.

    Raises:
        MalformedResponseError: If the text does not decode, or decodes into
            something that is not an object. Rule 2 of CONTRACTS section 7.16:
            ``AgentReply.raw`` is a mapping or ``None``, never a list and never a
            scalar.
    """
    stripped = text.strip()
    for fence in _FENCES:
        if stripped.startswith(fence):
            stripped = stripped[len(fence) :].strip()
            break
    if stripped.endswith("```"):
        stripped = stripped[: -len("```")].strip()
    if not stripped:
        raise MalformedResponseError("provider returned no text")
    candidates = [stripped]
    opening = stripped.find("{")
    closing = stripped.rfind("}")
    if opening > 0 and closing > opening:
        # A model that prefixed one sentence to an otherwise valid object. The
        # object is extracted, never repaired: a second failure is a failed
        # attempt, not a guess.
        candidates.append(stripped[opening : closing + 1])
    for candidate in candidates:
        try:
            decoded = json.loads(candidate)
        except ValueError:
            continue
        if isinstance(decoded, dict):
            return decoded
        raise MalformedResponseError("provider answer is not a JSON object", kind=type(decoded).__name__)
    raise MalformedResponseError("provider answer is not valid JSON", text=stripped[:_LOG_TEXT_LIMIT])


def parse_cli_stdout(stdout: str) -> ClaudeCliResult:
    """Parse the ``--output-format json`` payload the CLI writes on stdout.

    The payload is a single JSON object carrying ``is_error``, ``result`` (a
    string holding the model's own answer), ``total_cost_usd``, ``duration_ms``
    and a ``usage`` object. A stray line before it (a warning, a progress
    notice) is tolerated by scanning backwards for the last line that decodes
    into an object; nothing else is repaired.

    Args:
        stdout: Whatever the process wrote on stdout.

    Returns:
        The parsed result.

    Raises:
        MalformedResponseError: If stdout holds no JSON object, or if a field it
            does hold has the wrong type. The caller treats that as a failed
            attempt (FR-5.1.1) and retries.
    """
    text = stdout.strip()
    if not text:
        raise MalformedResponseError("provider wrote nothing on stdout")
    payload: dict[str, Any] | None = None
    try:
        payload = _decode_json_object(text)
    except MalformedResponseError:
        for line in reversed([candidate for candidate in text.splitlines() if candidate.strip()]):
            with contextlib.suppress(MalformedResponseError):
                payload = _decode_json_object(line)
                break
    if payload is None:
        raise MalformedResponseError("cli stdout is not a JSON object", text=text[:_LOG_TEXT_LIMIT])
    raw_result = payload.get("result")
    if raw_result is None:
        result_text = ""
    elif isinstance(raw_result, str):
        result_text = raw_result
    else:
        raise MalformedResponseError("cli result field is not a string", kind=type(raw_result).__name__)
    usage_any = payload.get("usage")
    usage: Mapping[str, Any] = usage_any if isinstance(usage_any, Mapping) else {}
    return ClaudeCliResult(
        is_error=bool(payload.get("is_error", False)),
        result_text=result_text,
        total_cost_usd=_as_float(payload.get("total_cost_usd"), field_name="total_cost_usd"),
        duration_ms=_as_int(payload.get("duration_ms"), field_name="duration_ms"),
        input_tokens=_as_int(usage.get("input_tokens"), field_name="usage.input_tokens"),
        output_tokens=_as_int(usage.get("output_tokens"), field_name="usage.output_tokens"),
        cache_creation_input_tokens=_as_int(
            usage.get("cache_creation_input_tokens"), field_name="usage.cache_creation_input_tokens"
        ),
        cache_read_input_tokens=_as_int(
            usage.get("cache_read_input_tokens"), field_name="usage.cache_read_input_tokens"
        ),
    )


# --------------------------------------------------------------------------
# Internal call bookkeeping
# --------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class _CallPlan:
    """Everything one call needs, computed once before the first attempt."""

    agent_id: str
    tick: int
    harness: HarnessConfig
    argv: tuple[str, ...]
    estimated_input_tokens: int


@dataclass(slots=True)
class _Telemetry:
    """What the attempts of one call actually consumed, accumulated."""

    attempts: int = 0
    cost_usd: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0
    cache_creation_input_tokens: int = 0
    cache_read_input_tokens: int = 0
    raw_text: str = ""
    reason: RejectReason | None = None

    def absorb(self, result: ClaudeCliResult) -> None:
        """Add one provider answer to the running totals.

        Args:
            result: The parsed answer of one attempt, successful or not. A failed
                attempt is billed too, which is why this is called before the
                verdict is known.
        """
        self.cost_usd += max(0.0, result.total_cost_usd)
        self.input_tokens += max(0, result.input_tokens)
        self.output_tokens += max(0, result.output_tokens)
        self.cache_creation_input_tokens += max(0, result.cache_creation_input_tokens)
        self.cache_read_input_tokens += max(0, result.cache_read_input_tokens)
        self.raw_text = result.result_text

    @property
    def cached_input_tokens(self) -> int:
        """Cached input tokens of the whole call, creation plus read."""
        return self.cache_creation_input_tokens + self.cache_read_input_tokens


def _estimate_prompt_tokens(*texts: str) -> int:
    """Estimate the billable input tokens of a rendered prompt.

    The rule is the T2.4 counting rule of
    :func:`pxe.runner.observation_builder.estimate_tokens`, applied to prompt
    **text** rather than to an observation payload: ``ceil(len(text) / 3.6)``,
    counting characters. The divisor is imported rather than duplicated so there
    is one ratio in the repository. ``estimate_tokens`` itself is documented as
    "used by the T2.4 budget test only, never by the engine", so it is not
    called here.

    The estimate is deliberately conservative and deliberately excludes the
    roughly 35 000 cached tokens of CLI overhead: those are cached input tokens
    and cached input tokens are outside the token budget (ruling R66).

    Args:
        *texts: The rendered prompt parts, typically the system prompt and the
            user prompt.

    Returns:
        The estimated number of input tokens, rounded up.
    """
    return math.ceil(sum(len(text) for text in texts) / TOKEN_CHARS_PER_TOKEN)


# --------------------------------------------------------------------------
# The gateway
# --------------------------------------------------------------------------
class ClaudeCliGateway(BaseGateway):
    """One Claude Code CLI subprocess per agent per tick.

    Attributes:
        agent_ids: The seats this gateway serves, in canonical order.
        trace_path: Destination of ``llm_trace.jsonl``, or ``None`` to trace
            nothing. The file is outside the journal hash (CONTRACTS section
            4.6), so a unit test may omit it and nothing moves.
    """

    def __init__(
        self,
        *,
        harnesses: Mapping[str, HarnessConfig],
        gateway_config: GatewayConfig,
        budget: BudgetTracker,
        trace_path: Path | None = None,
    ) -> None:
        """Seat one harness per agent and bind the runtime settings.

        Args:
            harnesses: Seat id to harness. Iterated only through
                :func:`pxe.types.sorted_ids` (CONTRACTS section 2.3), so the
                order the caller happened to build the mapping in cannot
                influence anything. ``MM`` and ``FEES`` are refused by that
                helper: neither ever receives an observation.
            gateway_config: Timeouts, retries, budgets and concurrency. Never
                journalled.
            budget: The tracker shared by every seat of the match. Required and
                not optional: the cost model of CONTRACTS section 7.16 makes
                budget caps mandatory, so a gateway without one must not exist.
            trace_path: ``runs/<match_id>/llm_trace.jsonl``, or ``None``.

        Raises:
            InvalidConfigError: If a key is ``MM`` or ``FEES``, if a harness is
                not of kind ``"llm"``, or if a harness names no model. Each of
                those would only be discovered mid match otherwise, after money
                had been spent.
        """
        super().__init__(gateway_config=gateway_config, budget=budget)
        ordered = sorted_ids(tuple(harnesses.keys()))
        for agent_id in ordered:
            harness = harnesses[agent_id]
            if harness.kind != "llm":
                raise InvalidConfigError(
                    "the CLI gateway only seats llm harnesses",
                    agent_id=agent_id,
                    harness_id=harness.harness_id,
                    kind=harness.kind,
                )
            if not harness.model:
                raise InvalidConfigError(
                    "an llm harness must name a model",
                    agent_id=agent_id,
                    harness_id=harness.harness_id,
                )
        self._harnesses: dict[str, HarnessConfig] = {agent_id: harnesses[agent_id] for agent_id in ordered}
        self.trace_path = trace_path
        #: The configuration of the tick being collected. ``acall_agent`` has no
        #: ``config`` argument (CONTRACTS section 7.16) yet the system prompt is
        #: built from a ``MatchConfig``, so the group entry point remembers what
        #: it was handed for the single call entry point to reuse (ruling R67).
        self._config: MatchConfig | None = None
        #: Cached once: the schema file is read only and never patched at
        #: runtime (section 8.2), and re-reading it per call would pay a file
        #: system round trip per agent per tick.
        self._schema: dict[str, Any] = action_schema()

    @property
    def agent_ids(self) -> tuple[str, ...]:
        """The seats served by this gateway, ascending.

        Returns:
            The seat ids in canonical order.
        """
        return tuple(self._harnesses)

    def harness_of(self, agent_id: str) -> HarnessConfig:
        """Return the harness seated at one seat.

        Args:
            agent_id: The seat.

        Returns:
            Its harness.

        Raises:
            InvalidConfigError: If no harness occupies that seat. This aborts the
                match on purpose: a seat behind an LLM gateway with no harness
                would silently never act, and no cost signal would show it
                (CONTRACTS section 2.4, a configuration bug is not an agent
                behaviour).
        """
        harness = self._harnesses.get(agent_id)
        if harness is None:
            raise InvalidConfigError(
                "no harness for this seat",
                agent_id=agent_id,
                known=",".join(self.agent_ids),
            )
        return harness

    async def acollect_actions(
        self, *, tick: int, observations: Sequence[Observation], config: MatchConfig
    ) -> tuple[AgentReply, ...]:
        """Remember the tick's configuration, then run the standard bridge.

        Args:
            tick: The tick being decided, 1 based.
            observations: One observation per ranked, non frozen agent.
            config: The match configuration, the source of every number in the
                system prompt.

        Returns:
            One reply per observation, sorted by ``agent_id``.
        """
        self._config = config
        return await super().acollect_actions(tick=tick, observations=observations, config=config)

    async def acall_agent(self, *, agent_id: str, observation: Observation, tick: int) -> AgentReply:
        """Run one CLI call for one seat, with retries, budget and trace.

        Args:
            agent_id: The seat to call.
            observation: What that seat is allowed to know this tick. It is
                rendered once, in full: one call covers every market
                (decision 14).
            tick: The tick being decided.

        Returns:
            The seat's reply. On success ``raw`` is the model's JSON object and
            ``source`` is ``llm``; on failure, after the configured retries,
            ``raw`` is ``None``, ``source`` is ``fallback`` and ``error`` carries
            the reason ``AgentTimedOut`` will report (FR-5.1.1).

        Raises:
            InvalidConfigError: If no harness occupies the seat.
        """
        started = time.perf_counter()
        plan = self._plan(agent_id=agent_id, observation=observation, tick=tick)
        telemetry = _Telemetry()
        refusal = self._budget_refusal(plan)
        if refusal is not None:
            telemetry.reason = refusal
            return self._finish(plan=plan, telemetry=telemetry, raw=None, started=started)
        raw = await self._aattempt_all(plan=plan, telemetry=telemetry)
        return self._finish(plan=plan, telemetry=telemetry, raw=raw, started=started)

    # -- planning ---------------------------------------------------------
    def _plan(self, *, agent_id: str, observation: Observation, tick: int) -> _CallPlan:
        """Render the prompts and the argv of one call.

        Args:
            agent_id: The seat to call.
            observation: The observation to answer.
            tick: The tick being decided.

        Returns:
            The immutable plan of that call.

        Raises:
            InvalidConfigError: If no harness occupies the seat.
        """
        harness = self.harness_of(agent_id)
        config = self._config if self._config is not None else MatchConfig()
        system_prompt = build_system_prompt(harness, config=config)
        user_prompt = build_user_prompt(observation_to_json(observation))
        argv = build_cli_argv(
            prompt=user_prompt,
            system_prompt=system_prompt,
            model=harness.model,
            schema=self._schema,
            max_budget_usd=self.gateway_config.max_budget_usd_per_call,
        )
        return _CallPlan(
            agent_id=agent_id,
            tick=tick,
            harness=harness,
            argv=tuple(argv),
            estimated_input_tokens=_estimate_prompt_tokens(system_prompt, user_prompt),
        )

    def _budget_refusal(self, plan: _CallPlan) -> RejectReason | None:
        """Check every cap that must hold before a single cent is spent.

        The USD caps of the ``call`` and ``tournament`` scopes and both token
        caps of FR-6.2.3 are evaluated here; ``BaseGateway`` has already checked
        the ``match`` scope before dispatching (ruling R62: the bridge checks,
        the adapter records).

        Args:
            plan: The call about to be made.

        Returns:
            ``RejectReason.BUDGET_EXCEEDED`` when the call must not be sent, and
            ``None`` when it may. A breach is never an exception at the engine
            boundary (CONTRACTS section 2.4).
        """
        budget = self.budget
        if budget is None:  # pragma: no cover - __init__ requires a tracker
            return None
        config = self.gateway_config
        try:
            budget.check_tokens(
                input_tokens=plan.estimated_input_tokens,
                output_tokens=config.max_output_tokens_per_call,
                agent_id=plan.agent_id,
                tick=plan.tick,
            )
            budget.check(scope="call", amount_usd=config.max_budget_usd_per_call)
            budget.check(scope="tournament", amount_usd=config.max_budget_usd_per_call)
        except BudgetExceededError as error:
            _LOG.warning(
                "call refused before it was sent, budget cap reached (FR-6.2.3)",
                extra={
                    "agent_id": plan.agent_id,
                    "tick": plan.tick,
                    "detail": str(error)[:_LOG_TEXT_LIMIT],
                },
            )
            return RejectReason.BUDGET_EXCEEDED
        return None

    # -- attempts ---------------------------------------------------------
    def _attempt_timeout_s(self) -> float | None:
        """Return the wall clock one attempt is allowed, in seconds.

        ``BaseGateway`` bounds the whole of :meth:`acall_agent` by
        ``timeout_s``, so the attempts have to share that budget or the outer
        bound cuts the retries off and the retry accounting is lost.

        Returns:
            ``timeout_s / (retries + 1)``, or ``None`` when ``timeout_s`` is not
            positive, which disables the bound exactly as in ``BaseGateway``.
        """
        timeout = self.gateway_config.timeout_s
        if timeout <= 0:
            return None
        return timeout / float(max(1, self.gateway_config.retries + 1))

    async def _aattempt_all(self, *, plan: _CallPlan, telemetry: _Telemetry) -> Mapping[str, Any] | None:
        """Run the attempts of one call until one succeeds or they run out.

        Args:
            plan: The call to make.
            telemetry: Accumulator, mutated in place. Its ``reason`` holds the
                failure of the last attempt once this returns ``None``.

        Returns:
            The model's JSON object, or ``None`` when every attempt failed.
        """
        max_attempts = max(1, self.gateway_config.retries + 1)
        timeout_s = self._attempt_timeout_s()
        for attempt in range(1, max_attempts + 1):
            telemetry.attempts = attempt
            raw = await self._aattempt_once(plan=plan, telemetry=telemetry, timeout_s=timeout_s)
            if raw is not None:
                telemetry.reason = None
                return raw
            _LOG.warning(
                "provider attempt failed",
                extra={
                    "agent_id": plan.agent_id,
                    "tick": plan.tick,
                    "attempt": attempt,
                    "of": max_attempts,
                    "reason": str(telemetry.reason),
                },
            )
        return None

    async def _aattempt_once(
        self, *, plan: _CallPlan, telemetry: _Telemetry, timeout_s: float | None
    ) -> Mapping[str, Any] | None:
        """Run one attempt and classify its outcome.

        Args:
            plan: The call to make.
            telemetry: Accumulator, mutated in place.
            timeout_s: Wall clock this attempt is allowed, or ``None``.

        Returns:
            The model's JSON object on success, ``None`` on any failure, with
            ``telemetry.reason`` set to the matching reason.
        """
        try:
            return_code, stdout, stderr = await self._arun_cli(plan.argv, timeout_s=timeout_s)
        except TimeoutError:
            telemetry.reason = RejectReason.AGENT_TIMEOUT
            return None
        except OSError as error:
            # The CLI is not installed or could not be launched. Retrying will
            # not fix it, but the loop is cheap and the reason is recorded.
            _LOG.warning(
                "the claude cli could not be launched",
                extra={"agent_id": plan.agent_id, "tick": plan.tick, "detail": str(error)[:_LOG_TEXT_LIMIT]},
            )
            telemetry.reason = RejectReason.PROVIDER_ERROR
            return None
        try:
            result = parse_cli_stdout(stdout)
        except MalformedResponseError:
            telemetry.reason = RejectReason.PROVIDER_ERROR if return_code != 0 else RejectReason.MALFORMED_RESPONSE
            telemetry.raw_text = stdout.strip()[: 4 * _LOG_TEXT_LIMIT] or stderr.strip()[: 4 * _LOG_TEXT_LIMIT]
            return None
        telemetry.absorb(result)
        if return_code != 0 or result.is_error:
            telemetry.reason = RejectReason.PROVIDER_ERROR
            return None
        try:
            return _decode_json_object(result.result_text)
        except MalformedResponseError:
            telemetry.reason = RejectReason.MALFORMED_RESPONSE
            return None

    async def _arun_cli(self, argv: Sequence[str], *, timeout_s: float | None) -> tuple[int, str, str]:
        """Launch the CLI once and collect its output.

        This is the only place in the product that starts a process, and it is
        the seam every offline test replaces: ``tests/test_gateway_claude_cli.py``
        overrides it, so the whole suite runs with no provider, no network and no
        money.

        Args:
            argv: The exact argv, from :func:`build_cli_argv`. Passed as
                separate arguments to :func:`asyncio.create_subprocess_exec`;
                ``shell=True`` is never used, so no part of a prompt can be
                interpreted as a shell metacharacter.
            timeout_s: Wall clock allowed, or ``None`` for no bound.

        Returns:
            ``(return_code, stdout, stderr)``, both streams decoded as UTF-8
            with undecodable bytes replaced.

        Raises:
            TimeoutError: If the process outlived ``timeout_s``. It is killed
                first, so no orphan survives the tick.
            OSError: If the process could not be launched at all.
        """
        process = await asyncio.create_subprocess_exec(
            *argv,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout_bytes, stderr_bytes = await asyncio.wait_for(process.communicate(), timeout=timeout_s)
        except TimeoutError:
            with contextlib.suppress(ProcessLookupError, OSError):
                process.kill()
            with contextlib.suppress(ProcessLookupError, OSError):
                await process.wait()
            raise
        return (
            process.returncode if process.returncode is not None else 0,
            stdout_bytes.decode("utf-8", errors="replace"),
            stderr_bytes.decode("utf-8", errors="replace"),
        )

    # -- finishing --------------------------------------------------------
    def _finish(
        self,
        *,
        plan: _CallPlan,
        telemetry: _Telemetry,
        raw: Mapping[str, Any] | None,
        started: float,
    ) -> AgentReply:
        """Build the reply, book it against the budget and trace it.

        This is the single exit of :meth:`acall_agent`, so every call is
        recorded exactly once (ruling R62) and every call produces exactly one
        trace line, successful or not.

        Args:
            plan: The call that was made.
            telemetry: What it consumed.
            raw: The model's JSON object, or ``None``.
            started: The :func:`time.perf_counter` mark taken before planning.

        Returns:
            The reply handed back to the bridge.
        """
        latency_ms = max(0, int((time.perf_counter() - started) * 1000.0))
        if raw is not None:
            reply = AgentReply(
                agent_id=plan.agent_id,
                raw=raw,
                raw_text=telemetry.raw_text,
                source=AgentSource.LLM,
                error=None,
                cost_usd=telemetry.cost_usd,
                latency_ms=latency_ms,
                input_tokens=telemetry.input_tokens,
                output_tokens=telemetry.output_tokens,
                cached_input_tokens=telemetry.cached_input_tokens,
                attempts=telemetry.attempts,
            )
        else:
            reason = telemetry.reason if telemetry.reason is not None else RejectReason.PROVIDER_ERROR
            reply = replace(
                self._fallback_reply(
                    agent_id=plan.agent_id,
                    error=reason,
                    latency_ms=latency_ms,
                    raw_text=telemetry.raw_text or None,
                    cost_usd=telemetry.cost_usd,
                    attempts=telemetry.attempts,
                ),
                input_tokens=telemetry.input_tokens,
                output_tokens=telemetry.output_tokens,
                cached_input_tokens=telemetry.cached_input_tokens,
            )
        self._book(plan=plan, reply=reply)
        self._trace(plan=plan, telemetry=telemetry, reply=reply)
        return reply

    def _book(self, *, plan: _CallPlan, reply: AgentReply) -> None:
        """Record the call against the budget, then re-check the cumulative cap.

        CONTRACTS section 7.16 asks for ``max_tokens_per_match`` to be checked
        "after it" as well as before. The money is already spent by then, so a
        breach discovered here does **not** discard a valid answer: it is logged,
        and it binds the next call, because the pre-call check of
        :meth:`_budget_refusal` reads the totals this method just updated.

        Args:
            plan: The call that was made.
            reply: What it produced.
        """
        budget = self.budget
        if budget is None:  # pragma: no cover - __init__ requires a tracker
            return
        budget.record(reply, tick=plan.tick)
        try:
            budget.check_tokens(input_tokens=0, output_tokens=0, agent_id=plan.agent_id)
        except BudgetExceededError as error:
            _LOG.warning(
                "cumulative token budget reached, the next call for this seat will fall back",
                extra={
                    "agent_id": plan.agent_id,
                    "tick": plan.tick,
                    "detail": str(error)[:_LOG_TEXT_LIMIT],
                },
            )

    def _trace(self, *, plan: _CallPlan, telemetry: _Telemetry, reply: AgentReply) -> None:
        """Log the call and append its line to ``llm_trace.jsonl``.

        Args:
            plan: The call that was made.
            telemetry: What it consumed.
            reply: What it produced.
        """
        _LOG.info(
            "llm call",
            extra={
                "agent_id": plan.agent_id,
                "tick": plan.tick,
                "model": plan.harness.model,
                "attempts": telemetry.attempts,
                "cost_usd": reply.cost_usd,
                "latency_ms": reply.latency_ms,
                "input_tokens": reply.input_tokens,
                "output_tokens": reply.output_tokens,
                "error": None if reply.error is None else str(reply.error),
            },
        )
        if self.trace_path is None:
            return
        write_llm_trace(
            self.trace_path,
            LlmTraceEntry(
                tick=plan.tick,
                agent_id=plan.agent_id,
                harness_key=plan.harness.key,
                model=plan.harness.model,
                prompt_template_version=PROMPT_TEMPLATE_VERSION,
                ok=reply.ok,
                error=None if reply.error is None else str(reply.error),
                attempts=telemetry.attempts,
                cost_usd=reply.cost_usd,
                latency_ms=reply.latency_ms,
                input_tokens=telemetry.input_tokens,
                output_tokens=telemetry.output_tokens,
                cache_creation_input_tokens=telemetry.cache_creation_input_tokens,
                cache_read_input_tokens=telemetry.cache_read_input_tokens,
                estimated_input_tokens=plan.estimated_input_tokens,
                raw_text=telemetry.raw_text,
            ),
        )
