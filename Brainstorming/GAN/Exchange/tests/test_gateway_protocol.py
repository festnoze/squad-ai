"""Acceptance tests for the gateway protocol and the scripted gateway (A13).

CONTRACTS sections 7.16 and 13. What is asserted here is the seam itself: the
shape of a reply, the ``agent_id`` ordering, the FR-5.1.1 fallback, and the
three things this package must never do (validate, reject, produce an
``AgentAction``).

The anti vacuous rule, applied to a module that has no journal
--------------------------------------------------------------
Section 10's rule is "assert the thing under test is non empty before claiming
anything about it". A gateway produces replies and not events, so every test
here goes through :func:`assert_replies_cover`, which asserts the tuple is non
empty **and** that it covers exactly the seats that were asked, before any other
claim is made. A gateway that returned ``()`` would fail every test in this file
instead of passing all of them.

The one test that does assert on a real journal is
``test_scripted_gateway_drives_a_real_match``: it needs A09's runner, so it
names the missing module through ``importorskip`` rather than passing on
nothing.
"""

import ast
import asyncio
import random
import time
from collections.abc import Mapping, Sequence
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from pxe.agents.base import make_baseline
from pxe.errors import GatewayError, InvalidConfigError, MalformedResponseError, ProviderError
from pxe.gateway.protocol import AgentGateway, AgentReply, BaseGateway
from pxe.gateway.scripted import CompositeGateway, ScriptedGateway
from pxe.rng import RngTree
from pxe.types import (
    DEFAULT_PREDICTION_PPM,
    AgentAction,
    AgentSource,
    GatewayConfig,
    MarketObservation,
    MarketStatus,
    MatchConfig,
    Observation,
    ObservationLimits,
    RejectReason,
    action_to_payload,
    make_agent_id,
    make_market_id,
)

GATEWAY_DIR = Path(__file__).resolve().parent.parent / "src" / "pxe" / "gateway"

#: Reference price of every toy market, in cents.
TOY_REF_PRICE = 55
#: Half spread of the toy book, in cents.
TOY_HALF_SPREAD = 2
#: Depth at each side of the toy touch, in contracts.
TOY_DEPTH_QTY = 100


# ---------------------------------------------------------------------------
# Observation scaffolding
# ---------------------------------------------------------------------------
def make_observation(*, agent_id: str, tick: int = 1, n_markets: int = 2) -> Observation:
    """Build a small but complete observation for one seat.

    Args:
        agent_id: The seat the observation is for.
        tick: The tick it describes.
        n_markets: How many open markets it carries.

    Returns:
        A fully populated ``Observation``. It is built by hand on purpose: A10
        owns the real renderer and this file must not depend on it.
    """
    config = MatchConfig(seed=20260827)
    markets = tuple(
        MarketObservation(
            market_id=make_market_id(index),
            question=f"toy question {index}",
            status=MarketStatus.OPEN,
            prior_price=50,
            resolution_tick=config.ticks_total,
            ref_price=TOY_REF_PRICE,
            mid_price=TOY_REF_PRICE,
            best_bid=TOY_REF_PRICE - TOY_HALF_SPREAD,
            best_ask=TOY_REF_PRICE + TOY_HALF_SPREAD,
            bid_depth=((TOY_REF_PRICE - TOY_HALF_SPREAD, TOY_DEPTH_QTY),),
            ask_depth=((TOY_REF_PRICE + TOY_HALF_SPREAD, TOY_DEPTH_QTY),),
            last_price=TOY_REF_PRICE,
            ref_history=(TOY_REF_PRICE,),
            position_qty=0,
            cost_basis_cents=0,
            my_orders=(),
            my_last_prediction_ppm=DEFAULT_PREDICTION_PPM,
        )
        for index in range(1, n_markets + 1)
    )
    return Observation(
        obs_version=config.obs_version,
        match_id="m-election-20260827-01",
        tick=tick,
        ticks_total=config.ticks_total,
        agent_id=agent_id,
        cash_cents=config.initial_cash_cents,
        reserved_cents=0,
        free_cash_cents=config.initial_cash_cents,
        equity_cents=config.initial_cash_cents,
        news=(),
        signals=(),
        markets=markets,
        messages=(),
        limits=ObservationLimits(
            max_active_orders_per_market=config.max_active_orders_per_market,
            price_min=1,
            price_max=99,
            market_band_cents=config.market_band_cents,
            taker_fee_bps=config.taker_fee_bps,
            message_max_chars=config.message_max_chars,
            max_orders_per_action=config.max_orders_per_action,
        ),
    )


def seat_ids(n: int) -> tuple[str, ...]:
    """Return the first ``n`` ranked seat ids.

    Args:
        n: How many seats.

    Returns:
        ``("A1", ..., "An")``.
    """
    return tuple(make_agent_id(index) for index in range(1, n + 1))


def observations_for(seats: Sequence[str], *, tick: int = 1) -> tuple[Observation, ...]:
    """Build one observation per seat, in the order the seats are given.

    Args:
        seats: The seats to build for. Deliberately not sorted by the caller in
            most tests: the gateway is the thing that must sort.
        tick: The tick to describe.

    Returns:
        One observation per seat.
    """
    return tuple(make_observation(agent_id=agent_id, tick=tick) for agent_id in seats)


def assert_replies_cover(replies: Sequence[AgentReply], seats: Sequence[str]) -> None:
    """Assert the reply tuple is non empty and covers exactly ``seats``.

    This is section 10's anti vacuous rule for a module that produces replies
    instead of events: nothing else in this file is claimed before this holds.

    Args:
        replies: What the gateway returned.
        seats: The seats that were asked.
    """
    assert replies, "the gateway returned no reply at all"
    assert len(replies) == len(seats), f"expected {len(seats)} replies, got {len(replies)}"
    assert sorted(reply.agent_id for reply in replies) == sorted(seats)


def scripted_over(names: Mapping[str, str], *, config: MatchConfig | None = None) -> ScriptedGateway:
    """Build a scripted gateway over ``{seat: baseline name}``.

    Args:
        names: Seat id to baseline name.
        config: Match configuration handed to the baselines.

    Returns:
        The gateway, with one freshly built baseline per seat.
    """
    from pxe.rng import RngTree

    match_config = config if config is not None else MatchConfig(seed=20260827)
    tree = RngTree(match_config.seed)
    agents = {
        agent_id: make_baseline(
            name,
            agent_id=agent_id,
            config=match_config,
            rng=tree.child(f"agent/{agent_id}").substream(f"agent.{agent_id}"),
        )
        for agent_id, name in names.items()
    }
    return ScriptedGateway(agents=agents)


# ---------------------------------------------------------------------------
# Fake gateways: what A14's adapter does, without a provider
# ---------------------------------------------------------------------------
class SlowGateway(BaseGateway):
    """A gateway whose calls sleep, fail or answer, per seat.

    It mimics the only three things a provider adapter can do, so the bridge can
    be tested without spending a token: sleep for a while, raise a
    ``GatewayError``, or return a reply.
    """

    def __init__(
        self,
        *,
        gateway_config: GatewayConfig,
        delays_s: Mapping[str, float] | None = None,
        failures: Mapping[str, Exception] | None = None,
    ) -> None:
        """Bind the per seat behaviour.

        Args:
            gateway_config: Timeouts and parallelism.
            delays_s: Seat to seconds of ``asyncio.sleep`` before answering.
            failures: Seat to the exception raised instead of answering.
        """
        super().__init__(gateway_config=gateway_config)
        self._delays = dict(delays_s or {})
        self._failures = dict(failures or {})
        self.calls: list[tuple[str, int]] = []
        self.live = 0
        self.peak = 0

    async def acall_agent(self, *, agent_id: str, observation: Observation, tick: int) -> AgentReply:
        """Sleep, fail or answer, according to the per seat behaviour.

        Args:
            agent_id: The seat being called.
            observation: The observation to answer.
            tick: The tick being decided.

        Returns:
            A reply carrying an empty but schema shaped action.

        Raises:
            Exception: Whatever ``failures`` declared for that seat.
        """
        self.calls.append((agent_id, tick))
        self.live += 1
        self.peak = max(self.peak, self.live)
        try:
            failure = self._failures.get(agent_id)
            if failure is not None:
                raise failure
            delay = self._delays.get(agent_id, 0.0)
            if delay > 0.0:
                await asyncio.sleep(delay)
            return AgentReply(
                agent_id=agent_id,
                raw={
                    "action_version": observation.obs_version,
                    "predictions": [],
                    "orders": [],
                    "message_public": None,
                    "rationale": None,
                },
                raw_text="{}",
                source=AgentSource.LLM,
                error=None,
                cost_usd=0.001,
                latency_ms=1,
                input_tokens=10,
                output_tokens=5,
            )
        finally:
            self.live -= 1


# ---------------------------------------------------------------------------
# Rule 1: replies, sorted by agent_id, one per observation
# ---------------------------------------------------------------------------
async def test_replies_are_sorted_by_agent_id() -> None:
    """T2.3: the reply tuple is ascending by seat whatever order it was asked in."""
    seats = seat_ids(6)
    gateway = scripted_over(dict.fromkeys(seats, "mute"))
    scrambled = tuple(reversed(observations_for(seats)))
    replies = await gateway.acollect_actions(tick=3, observations=scrambled, config=MatchConfig(seed=20260827))
    assert_replies_cover(replies, seats)
    assert [reply.agent_id for reply in replies] == list(seats)


async def test_replies_are_sorted_independently_of_completion_order() -> None:
    """The order is the seat order, not the order the provider answered in."""
    seats = seat_ids(4)
    config = GatewayConfig(timeout_s=5.0, max_parallel_calls=4)
    # A1 answers last, A4 first: completion order is the reverse of seat order.
    delays = {"A1": 0.12, "A2": 0.08, "A3": 0.04, "A4": 0.0}
    gateway = SlowGateway(gateway_config=config, delays_s=delays)
    replies = await gateway.acollect_actions(tick=1, observations=observations_for(seats), config=MatchConfig(seed=1))
    assert_replies_cover(replies, seats)
    assert [reply.agent_id for reply in replies] == list(seats)
    assert all(reply.error is None for reply in replies)


async def test_ten_seats_sort_numerically_not_lexicographically() -> None:
    """``A10`` follows ``A9``, because the ordering goes through ``sorted_ids``."""
    seats = ("A10", "A2", "A1", "A9")
    gateway = SlowGateway(gateway_config=GatewayConfig(timeout_s=5.0))
    replies = await gateway.acollect_actions(tick=1, observations=observations_for(seats), config=MatchConfig(seed=1))
    assert_replies_cover(replies, seats)
    assert [reply.agent_id for reply in replies] == ["A1", "A2", "A9", "A10"]


async def test_no_observation_means_no_call_and_no_reply() -> None:
    """Section 5.0: with no open market P2 skips the gateway entirely."""
    gateway = SlowGateway(gateway_config=GatewayConfig(timeout_s=5.0))
    assert await gateway.acollect_actions(tick=7, observations=(), config=MatchConfig(seed=1)) == ()
    assert gateway.collect_actions(tick=7, observations=(), config=MatchConfig(seed=1)) == ()
    assert gateway.calls == [], "a provider call was made for a tick with no observation"


# ---------------------------------------------------------------------------
# Rule 2: raw is always the action.v1.json shape, or None
# ---------------------------------------------------------------------------
async def test_scripted_raw_is_action_to_payload_and_validates(action_schema: dict[str, object]) -> None:
    """Rule 2: a scripted agent and an LLM agent enter validation through one door."""
    seats = seat_ids(3)
    config = MatchConfig(seed=20260827)
    gateway = scripted_over(dict.fromkeys(seats, "fundamentalist"), config=config)
    observations = observations_for(seats)
    replies = await gateway.acollect_actions(tick=2, observations=observations, config=config)
    assert_replies_cover(replies, seats)
    validator = Draft202012Validator(action_schema)
    for reply in replies:
        assert reply.source is AgentSource.SCRIPTED
        assert reply.error is None
        assert isinstance(reply.raw, Mapping), "raw must be a mapping, never an AgentAction"
        validator.validate(dict(reply.raw))
        assert reply.raw_text is None
        assert reply.cost_usd == 0.0
    # The same seat, the same observation, the same payload: no hidden state.
    twin = scripted_over(dict.fromkeys(seats, "fundamentalist"), config=config)
    expected = action_to_payload(twin._agents[seats[0]].act(observations[0]))
    assert replies[0].raw == expected


async def test_a_reply_is_never_an_action_object() -> None:
    """Rule 1: no ``AgentAction`` escapes this package."""
    seats = seat_ids(2)
    gateway = scripted_over(dict.fromkeys(seats, "mute"))
    replies = await gateway.acollect_actions(tick=1, observations=observations_for(seats), config=MatchConfig(seed=1))
    assert_replies_cover(replies, seats)
    for reply in replies:
        assert type(reply).__name__ == "AgentReply"
        assert not hasattr(reply.raw, "predictions"), "raw looks like an AgentAction, not a payload"
        assert reply.ok


# ---------------------------------------------------------------------------
# Rule 3 and FR-5.1.1: the fallback
# ---------------------------------------------------------------------------
async def test_timeout_falls_back_to_no_action() -> None:
    """FR-5.1.1: a silent agent becomes ``raw=None``, ``FALLBACK``, ``AGENT_TIMEOUT``."""
    seats = seat_ids(3)
    config = GatewayConfig(timeout_s=0.05, max_parallel_calls=3)
    gateway = SlowGateway(gateway_config=config, delays_s={"A2": 5.0})
    replies = await gateway.acollect_actions(tick=4, observations=observations_for(seats), config=MatchConfig(seed=1))
    assert_replies_cover(replies, seats)
    by_id = {reply.agent_id: reply for reply in replies}
    timed_out = by_id["A2"]
    assert timed_out.raw is None
    assert timed_out.raw_text is None
    assert timed_out.source is AgentSource.FALLBACK
    assert timed_out.error is RejectReason.AGENT_TIMEOUT
    assert not timed_out.ok
    # The match continues for everybody else.
    assert by_id["A1"].ok and by_id["A3"].ok


@pytest.mark.parametrize(
    ("failure", "expected"),
    [
        (ProviderError("exit 1"), RejectReason.PROVIDER_ERROR),
        (MalformedResponseError("not json"), RejectReason.MALFORMED_RESPONSE),
        (GatewayError("something odd"), RejectReason.PROVIDER_ERROR),
        (OSError("cannot spawn"), RejectReason.PROVIDER_ERROR),
    ],
)
async def test_provider_failure_falls_back_with_the_matching_reason(failure: Exception, expected: RejectReason) -> None:
    """Rule 3: the only judgement is "did the call succeed", and it is a reason."""
    seats = seat_ids(2)
    gateway = SlowGateway(
        gateway_config=GatewayConfig(timeout_s=1.0, max_parallel_calls=2),
        failures={"A1": failure},
    )
    replies = await gateway.acollect_actions(tick=1, observations=observations_for(seats), config=MatchConfig(seed=1))
    assert_replies_cover(replies, seats)
    by_id = {reply.agent_id: reply for reply in replies}
    assert by_id["A1"].error is expected
    assert by_id["A1"].source is AgentSource.FALLBACK
    assert by_id["A1"].raw is None
    assert by_id["A2"].ok, "one failing seat must not affect another"


async def test_an_engine_error_is_not_swallowed() -> None:
    """Section 2.4: only gateway failures are swallowed, nothing else."""

    class Boom(BaseGateway):
        async def acall_agent(self, *, agent_id: str, observation: Observation, tick: int) -> AgentReply:
            raise ZeroDivisionError("an engine bug must abort the match")

    gateway = Boom(gateway_config=GatewayConfig(timeout_s=1.0))
    with pytest.raises(ZeroDivisionError):
        await gateway.acollect_actions(tick=1, observations=observations_for(("A1",)), config=MatchConfig(seed=1))


async def test_an_unseated_scripted_seat_falls_back() -> None:
    """A misseated table degrades to "no action", it does not abort the match."""
    gateway = scripted_over({"A1": "mute"})
    replies = await gateway.acollect_actions(
        tick=1, observations=observations_for(("A1", "A2")), config=MatchConfig(seed=1)
    )
    assert_replies_cover(replies, ("A1", "A2"))
    by_id = {reply.agent_id: reply for reply in replies}
    assert by_id["A1"].ok
    assert by_id["A2"].error is RejectReason.PROVIDER_ERROR
    assert by_id["A2"].source is AgentSource.FALLBACK


# ---------------------------------------------------------------------------
# The synchronous bridge (decision 15)
# ---------------------------------------------------------------------------
def test_collect_actions_is_the_synchronous_bridge() -> None:
    """``collect_actions`` is a plain synchronous call, which is what P2 makes."""
    seats = seat_ids(6)
    gateway = scripted_over(dict.fromkeys(seats, "mute"))
    config = MatchConfig(seed=20260827)
    observations = observations_for(seats)
    replies = gateway.collect_actions(tick=1, observations=observations, config=config)
    assert_replies_cover(replies, seats)
    assert [reply.agent_id for reply in replies] == list(seats)
    # Twice in a row, from a fresh event loop each time.
    again = gateway.collect_actions(tick=2, observations=observations, config=config)
    assert_replies_cover(again, seats)


async def test_collect_actions_refuses_a_running_event_loop() -> None:
    """``asyncio.run`` inside a loop is a programming error, reported as one."""
    gateway = scripted_over({"A1": "mute"})
    with pytest.raises(GatewayError):
        gateway.collect_actions(tick=1, observations=observations_for(("A1",)), config=MatchConfig(seed=1))


def test_the_scripted_gateway_satisfies_the_protocol() -> None:
    """Five packages type against ``AgentGateway``; the concrete ones must fit it."""
    gateway = scripted_over({"A1": "mute"})
    assert isinstance(gateway, AgentGateway)
    assert isinstance(gateway, BaseGateway)
    composite = CompositeGateway(gateways=[(("A1",), gateway)])
    assert isinstance(composite, AgentGateway)
    gateway.close()
    composite.close()


def test_base_gateway_demands_acall_agent() -> None:
    """A gateway that implements nothing fails loudly rather than silently."""
    gateway = BaseGateway()
    with pytest.raises(NotImplementedError):
        asyncio.run(gateway.acall_agent(agent_id="A1", observation=make_observation(agent_id="A1"), tick=1))


# ---------------------------------------------------------------------------
# The mapping is iterated through sorted_ids (section 2.3)
# ---------------------------------------------------------------------------
def test_agents_mapping_is_iterated_through_sorted_ids() -> None:
    """Section 2.3: a dict built in another order is not another gateway."""
    scrambled = {"A4": "mute", "A1": "mute", "A3": "mute", "A2": "mute"}
    gateway = scripted_over(scrambled)
    assert gateway.agent_ids == ("A1", "A2", "A3", "A4")


def test_a_reserved_account_is_not_a_seat() -> None:
    """``MM`` and ``FEES`` never receive an observation, so they are refused."""
    with pytest.raises(InvalidConfigError):
        scripted_over({"A1": "mute", "MM": "mute"})


def test_a_misseated_agent_is_refused() -> None:
    """An agent filed under a seat it does not play would answer for someone else."""
    from pxe.rng import RngTree

    config = MatchConfig(seed=20260827)
    tree = RngTree(config.seed)
    agent = make_baseline("mute", agent_id="A1", config=config, rng=tree.child("agent/A1").substream("agent.A1"))
    with pytest.raises(InvalidConfigError):
        ScriptedGateway(agents={"A2": agent})


# ---------------------------------------------------------------------------
# CompositeGateway: a mixed table
# ---------------------------------------------------------------------------
async def test_composite_routes_every_seat_to_its_own_gateway() -> None:
    """A mixed table reaches two gateways and comes back as one sorted tuple."""
    mute_seats = ("A1", "A2", "A3")
    fundamentalist_seats = ("A4", "A5", "A6")
    composite = CompositeGateway(
        gateways=[
            (mute_seats, scripted_over(dict.fromkeys(mute_seats, "mute"))),
            (fundamentalist_seats, scripted_over(dict.fromkeys(fundamentalist_seats, "fundamentalist"))),
        ]
    )
    seats = mute_seats + fundamentalist_seats
    observations = tuple(reversed(observations_for(seats)))
    replies = await composite.acollect_actions(tick=5, observations=observations, config=MatchConfig(seed=20260827))
    assert_replies_cover(replies, seats)
    assert [reply.agent_id for reply in replies] == list(seats)
    by_id = {reply.agent_id: reply for reply in replies}
    for agent_id in mute_seats:
        raw = by_id[agent_id].raw
        assert raw is not None
        assert str(raw["rationale"]).startswith("mute"), "a mute seat was routed to the wrong gateway"
    for agent_id in fundamentalist_seats:
        raw = by_id[agent_id].raw
        assert raw is not None
        assert str(raw["rationale"]).startswith("fundamentalist")
    assert composite.agent_ids == seats


async def test_composite_single_call_routes_too() -> None:
    """``acall_agent`` on a composite is the one seat version of the same routing."""
    composite = CompositeGateway(gateways=[(("A1",), scripted_over({"A1": "mute"}))])
    reply = await composite.acall_agent(agent_id="A1", observation=make_observation(agent_id="A1"), tick=1)
    assert_replies_cover((reply,), ("A1",))
    assert reply.ok


def test_composite_refuses_a_seat_claimed_twice() -> None:
    """Two gateways for one seat is two replies for one observation."""
    with pytest.raises(InvalidConfigError):
        CompositeGateway(
            gateways=[
                (("A1", "A2"), scripted_over({"A1": "mute", "A2": "mute"})),
                (("A2",), scripted_over({"A2": "mute"})),
            ]
        )


async def test_composite_refuses_an_unrouted_seat() -> None:
    """An unrouted seat would silently never act, so it is a configuration error."""
    composite = CompositeGateway(gateways=[(("A1",), scripted_over({"A1": "mute"}))])
    with pytest.raises(InvalidConfigError):
        await composite.acollect_actions(
            tick=1, observations=observations_for(("A1", "A2")), config=MatchConfig(seed=1)
        )


async def test_composite_fills_a_missing_reply() -> None:
    """A sub-gateway that drops a seat cannot drop it from the tick."""

    class Forgetful(BaseGateway):
        async def acollect_actions(
            self, *, tick: int, observations: Sequence[Observation], config: MatchConfig
        ) -> tuple[AgentReply, ...]:
            return ()

        async def acall_agent(self, *, agent_id: str, observation: Observation, tick: int) -> AgentReply:
            raise NotImplementedError

    composite = CompositeGateway(gateways=[(("A1",), Forgetful())])
    replies = await composite.acollect_actions(
        tick=1, observations=observations_for(("A1",)), config=MatchConfig(seed=1)
    )
    assert_replies_cover(replies, ("A1",))
    assert replies[0].source is AgentSource.FALLBACK
    assert replies[0].error is RejectReason.PROVIDER_ERROR


def test_composite_close_closes_every_sub_gateway() -> None:
    """Closing the table closes every provider handle in it."""
    closed: list[str] = []

    class Closing(BaseGateway):
        def __init__(self, label: str) -> None:
            super().__init__()
            self._label = label

        async def acall_agent(self, *, agent_id: str, observation: Observation, tick: int) -> AgentReply:
            raise NotImplementedError

        def close(self) -> None:
            closed.append(self._label)

    composite = CompositeGateway(gateways=[(("A1",), Closing("a")), (("A2",), Closing("b"))])
    composite.close()
    assert closed == ["a", "b"]


# ---------------------------------------------------------------------------
# Rule 3, statically: the gateway cannot validate because it cannot import it
# ---------------------------------------------------------------------------
def test_the_gateway_never_imports_the_action_validator() -> None:
    """Section 13, A13's row: never ``pxe.runner.action_validator``.

    Asserted over the source and not over behaviour, because the thing being
    forbidden is a dependency: a gateway that could reach ``validate_action``
    would eventually build a ``Rejection`` list and throw it away, which is what
    makes FR-6.2.2 unimplementable.
    """
    owned = ("__init__.py", "budget.py", "protocol.py", "scripted.py")
    present = {path.name for path in GATEWAY_DIR.glob("*.py")}
    assert set(owned) <= present, f"the A13 file set is incomplete: {sorted(present)}"
    forbidden = ("pxe.runner", "action_validator", "schema_registry", "jsonschema")
    seen: list[str] = []
    for name in owned:
        tree = ast.parse((GATEWAY_DIR / name).read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            imported: list[str] = []
            if isinstance(node, ast.Import):
                imported = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported = [node.module]
            seen.extend(imported)
            for module in imported:
                assert not any(module.startswith(bad) for bad in forbidden), f"{name} imports {module}"
    # The scan really parsed the modules: their own imports are in the list.
    assert "pxe.types" in seen, f"the import scan saw nothing meaningful: {sorted(set(seen))}"
    assert "pxe.agents.base" in seen


# ---------------------------------------------------------------------------
# The one test that asserts on a real journal (needs A09)
# ---------------------------------------------------------------------------
@pytest.mark.e2e
def test_scripted_gateway_drives_a_real_match(tmp_path: Path) -> None:
    """The scripted gateway drives a whole match and the journal is non empty.

    Section 13.1's "assert on a non empty journal first", made literal for this
    package: the gateway has no journal of its own, so the claim is made against
    the runner's. It skips by name until A09 lands rather than passing on
    nothing.
    """
    from pxe.rng import RngTree
    from pxe.runner import match_runner as runner_mod
    from pxe.types import AgentSpec, HarnessConfig, InfoProfile, InfoProfileKind
    from pxe.world import generator

    config = MatchConfig(seed=20260827, ticks_total=24, n_markets=2, n_agents=6)
    world = generator.generate_world(
        template_id="election",
        seed=config.seed,
        ticks_total=config.ticks_total,
        n_markets=config.n_markets,
    )
    tree = RngTree(config.seed)
    seats = seat_ids(config.n_agents)
    agents = {
        agent_id: make_baseline(
            "mute",
            agent_id=agent_id,
            config=config,
            rng=tree.child(f"agent/{agent_id}").substream(f"agent.{agent_id}"),
        )
        for agent_id in seats
    }
    harness = HarnessConfig(harness_id="mute", version="1.0.0", kind="scripted")
    specs = tuple(
        AgentSpec(agent_id=agent_id, harness=harness, info_profile=InfoProfile(kind=InfoProfileKind.GENERALIST))
        for agent_id in seats
    )
    result = runner_mod.run_match(
        config=config,
        world=world,
        agents=specs,
        gateway=ScriptedGateway(agents=agents),
        out_dir=tmp_path,
        rng=tree,
    )
    # Path.read_text(newline=...) only exists from Python 3.12+ on 3.13; the
    # project targets 3.12, where the keyword is a TypeError. open() carries it
    # on every supported version, and newline="\n" is contractual (section 4.2):
    # a stray "\r" must not be swallowed by universal newline translation.
    with open(tmp_path / "journal.jsonl", encoding="utf-8", newline="\n") as handle:
        lines = handle.read().splitlines()
    assert lines, "the match produced an empty journal"
    types = [line.split('"type":"', 1)[1].split('"', 1)[0] for line in lines]
    assert types.count("agent_action_received") > 0, "no action reached the journal through the gateway"
    assert types.count("agent_timed_out") == 0, "a scripted agent must never time out"
    assert result is not None


# ---------------------------------------------------------------------------
# The carrier itself
# ---------------------------------------------------------------------------
def test_agent_reply_is_frozen_and_defaults_to_no_telemetry() -> None:
    """The five contractual fields are required; the six telemetry ones default."""
    reply = AgentReply(
        agent_id="A1", raw=None, raw_text=None, source=AgentSource.FALLBACK, error=RejectReason.AGENT_TIMEOUT
    )
    assert (reply.cost_usd, reply.latency_ms, reply.input_tokens) == (0.0, 0, 0)
    assert (reply.output_tokens, reply.cached_input_tokens, reply.attempts) == (0, 0, 1)
    assert not reply.ok
    with pytest.raises(FrozenInstanceError):
        reply.agent_id = "A2"  # type: ignore[misc]


def test_the_timeout_never_reaches_a_reply() -> None:
    """Section 3.5: no wall clock value of ``GatewayConfig`` is journal material.

    The reply carries ``latency_ms``, which is wall clock and is written to
    ``llm_trace.jsonl``; what it must never carry is a configured timeout, a
    budget or a retry policy, because that is what would make two runs of the
    same seed differ.
    """
    fields = set(AgentReply.__dataclass_fields__)
    for forbidden in ("timeout_s", "retries", "max_budget_usd_per_call", "max_parallel_calls"):
        assert forbidden not in fields
    assert {"cost_usd", "latency_ms", "input_tokens", "output_tokens", "attempts"} <= fields


def test_wall_clock_of_a_timeout_is_reported_not_configured() -> None:
    """A timed out reply reports how long it actually waited."""
    seats = ("A1",)
    gateway = SlowGateway(gateway_config=GatewayConfig(timeout_s=0.05, max_parallel_calls=1), delays_s={"A1": 5.0})
    started = time.perf_counter()
    replies = gateway.collect_actions(tick=1, observations=observations_for(seats), config=MatchConfig(seed=1))
    elapsed_s = time.perf_counter() - started
    assert_replies_cover(replies, seats)
    assert replies[0].error is RejectReason.AGENT_TIMEOUT
    assert replies[0].latency_ms >= 0
    # The tick ended on the timeout, not on the five second sleep (T2.5).
    assert elapsed_s < 2.0, f"the tick took {elapsed_s:.2f}s for a 0.05s timeout"


# ---------------------------------------------------------------------------
# Ruling R59: reset_agents is part of the AgentGateway protocol
# ---------------------------------------------------------------------------
def test_reset_agents_reseats_every_scripted_agent() -> None:
    """``reset_agents`` is on the protocol and does the work section 3.1 needs.

    The runner may not reach inside a gateway to find its agents, so section 3.1's
    per match reset is the gateway's job. Four claims:

    * ``AgentGateway`` declares ``reset_agents``, so a gateway that forgets it is
      a type error at the call site rather than a silent no-op;
    * ``ScriptedGateway`` calls ``reset`` on every seat it holds, exactly once,
      in canonical order;
    * the generator each seat receives is the one section 3.1 spells out,
      ``rng.child(f"agent/{aid}").substream(f"agent.{aid}")``, checked by
      comparing the first draw against a generator built independently;
    * ``BaseGateway``'s default is a no-op, so a provider backed gateway with no
      scripted state inherits something harmless.
    """
    assert hasattr(AgentGateway, "reset_agents"), "the protocol does not declare the hook"
    assert callable(BaseGateway.reset_agents)

    seen: list[tuple[str, int]] = []

    class Recorder:
        """A scripted agent that records the first draw of the rng it is reset with."""

        name = "recorder"

        def __init__(self, agent_id: str) -> None:
            self.agent_id = agent_id

        def reset(self, *, config: MatchConfig, rng: random.Random) -> None:
            seen.append((self.agent_id, rng.getrandbits(32)))

        def act(self, observation: Observation) -> AgentAction:
            return AgentAction.no_action()

    seats = ("A1", "A2", "A3")
    gateway = ScriptedGateway(agents={aid: Recorder(aid) for aid in seats})  # type: ignore[arg-type]
    config = MatchConfig(seed=20260827)
    tree = RngTree(config.seed)
    gateway.reset_agents(config=config, rng=tree)

    assert [aid for aid, _draw in seen] == list(seats), f"seats were reset in the wrong order: {seen}"
    # The generator is the contracted one: rebuilt independently, it yields the
    # same first draw. A gateway handing over the wrong substream (the root, or a
    # tree without the child step) fails here and nowhere else.
    expected = [RngTree(config.seed).child(f"agent/{aid}").substream(f"agent.{aid}").getrandbits(32) for aid in seats]
    assert [draw for _aid, draw in seen] == expected, "a seat was handed the wrong substream"
    assert len(set(expected)) == len(expected), "the seats share a generator, so the check above is weak"

    # BaseGateway's default is a no-op and must not raise.
    class Bare(BaseGateway):
        async def acall_agent(self, *, agent_id: str, observation: Observation, tick: int) -> AgentReply:
            raise AssertionError("not called")

    Bare().reset_agents(config=config, rng=tree)


def test_composite_gateway_resets_every_sub_gateway() -> None:
    """``CompositeGateway.reset_agents`` delegates in table order (ruling R59)."""
    resets: list[str] = []

    class Watched(ScriptedGateway):
        def __init__(self, *, agents: dict[str, object], label: str) -> None:
            super().__init__(agents=agents)  # type: ignore[arg-type]
            self.label = label

        def reset_agents(self, *, config: MatchConfig, rng: RngTree) -> None:
            resets.append(self.label)
            super().reset_agents(config=config, rng=rng)

    config = MatchConfig(seed=7)
    left = Watched(
        agents={"A1": make_baseline("mute", agent_id="A1", config=config, rng=random.Random(1))}, label="left"
    )
    right = Watched(
        agents={"A2": make_baseline("mute", agent_id="A2", config=config, rng=random.Random(2))}, label="right"
    )
    composite = CompositeGateway(gateways=(((("A1",)), left), ((("A2",)), right)))
    composite.reset_agents(config=config, rng=RngTree(config.seed))
    assert resets == ["left", "right"], f"sub-gateways were not reset in table order: {resets}"
