"""O1, FR-5.1.4, FR-5.1.5 and AC-P1: the determinism harness (A09).

AC-P1 is "same seed, two machines, bit identical journals", and CONTRACTS
section 3.7 scopes it to **scripted** matches. Three things are proved here and
they are not the same claim:

1. the same seed replayed in the **same** process gives the same hash
   (``test_same_seed_same_hash``);
2. the same seed replayed in a **fresh subprocess**, with ``PYTHONHASHSEED``
   unset and then set to two different values, gives the hash frozen in
   ``tests/golden/`` (``test_golden_journal_hashes`` and
   ``test_golden_hashes_survive_a_fresh_interpreter``). A salted builtin
   ``hash()`` anywhere in the engine, or a set iteration reaching output, fails
   exactly here and nowhere else;
3. the P3 fairness shuffle is a function of ``(seed, tick)`` alone, never of
   agent behaviour (``test_tick_shuffle_depends_only_on_seed_and_tick``).

Regenerating ``tests/golden/`` is a deliberate act. Exactly four kinds of
change legitimately move a golden hash and each requires a version bump in the
same commit (CONTRACTS section 10): a ``MatchConfig`` field or default, an
event payload or phase order, a draw algorithm in :mod:`pxe.rng`, or a world or
info generation rule. A change to :mod:`pxe.runner.observation_builder` is
deliberately **not** on that list. Run ``regenerate_golden()`` from a Python
shell, justify it in the commit message, and commit the three journals with
their hashes.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from pxe.events import (
    JOURNAL_ENCODING,
    JOURNAL_NEWLINE,
    Event,
    MMQuoted,
    OrderPlaced,
    OrderRejected,
    event_to_line,
    journal_hash_from_lines,
)
from pxe.events import journal_hash as journal_hash_of
from pxe.gateway.protocol import AgentReply
from pxe.gateway.scripted import ScriptedGateway
from pxe.journal import Journal
from pxe.rng import RngTree, shuffle_seeded
from pxe.runner.match_runner import MatchRunner, _legacy_scripted_agents_of
from pxe.types import MatchConfig, Observation, sorted_ids
from tests.test_match_runner import (
    GOLDEN_DIR,
    GOLDEN_RECIPES,
    SMALL,
    WIDE,
    Recipe,
    agents_of,
    config_of,
    match_id_of,
    of_type,
    play,
    specs_of,
    world_of,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = REPO_ROOT / "src"

#: What a golden fixture is called on disk.
JOURNAL_SUFFIX = ".journal.jsonl"
HASH_SUFFIX = ".hash"

#: The script a fresh interpreter runs to reproduce every golden hash. It
#: imports nothing but the repository, so a PYTHONHASHSEED difference is the
#: only thing that varies between the three invocations.
_SUBPROCESS_SCRIPT = """
import json
import sys

sys.path.insert(0, {repo!r})
sys.path.insert(0, {src!r})

from tests.test_match_runner import GOLDEN_RECIPES, play

print(json.dumps({{recipe.name: play(recipe)[0].journal_hash for recipe in GOLDEN_RECIPES}}))
"""


def golden_journal_path(recipe: Recipe) -> Path:
    """Path of the frozen journal of one recipe."""
    return GOLDEN_DIR / f"{recipe.name}{JOURNAL_SUFFIX}"


def golden_hash_path(recipe: Recipe) -> Path:
    """Path of the frozen hash of one recipe."""
    return GOLDEN_DIR / f"{recipe.name}{HASH_SUFFIX}"


def regenerate_golden() -> dict[str, str]:
    """Rewrite the three frozen journals and their hashes. Deliberate act only.

    Returns:
        The new hashes, keyed by recipe name.
    """
    GOLDEN_DIR.mkdir(parents=True, exist_ok=True)
    hashes: dict[str, str] = {}
    for recipe in GOLDEN_RECIPES:
        result, events = play(recipe)
        with open(golden_journal_path(recipe), "w", encoding=JOURNAL_ENCODING, newline=JOURNAL_NEWLINE) as handle:
            handle.write("".join(event_to_line(event) for event in events))
        with open(golden_hash_path(recipe), "w", encoding=JOURNAL_ENCODING, newline=JOURNAL_NEWLINE) as handle:
            handle.write(result.journal_hash + JOURNAL_NEWLINE)
        hashes[recipe.name] = result.journal_hash
    return hashes


def read_golden_hash(recipe: Recipe) -> str:
    """Read the committed hash of one recipe."""
    return golden_hash_path(recipe).read_text(encoding=JOURNAL_ENCODING).strip()


def run_in_fresh_process(hash_seed: str | None) -> dict[str, str]:
    """Reproduce every golden hash in a fresh interpreter.

    Args:
        hash_seed: Value of ``PYTHONHASHSEED``, or ``None`` to unset it.

    Returns:
        The hashes that process computed, keyed by recipe name.
    """
    script = _SUBPROCESS_SCRIPT.format(repo=str(REPO_ROOT), src=str(SRC_DIR))
    env = dict(os.environ)
    env.pop("PYTHONHASHSEED", None)
    if hash_seed is not None:
        env["PYTHONHASHSEED"] = hash_seed
    completed = subprocess.run(  # noqa: S603
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(REPO_ROOT),
        check=True,
    )
    payload = completed.stdout.strip().splitlines()[-1]
    parsed: dict[str, str] = json.loads(payload)
    return parsed


def p3_order_of_tick(events: tuple[Event, ...], tick: int) -> list[str]:
    """Recover the P3 permutation of one tick from the journal.

    The runner applies each agent's whole block contiguously (P3 step 11), so
    the order in which ranked seats first appear in that tick's
    ``OrderPlaced`` and ``OrderRejected`` events is a subsequence of the
    fairness shuffle. The market maker is excluded: it requotes **before** the
    shuffle and is not in the seat list (FR-5.8.1).

    Args:
        events: The whole journal.
        tick: The tick to inspect.

    Returns:
        The ranked seats in the order they acted, without repetition.
    """
    order: list[str] = []
    after_mm = False
    for event in events:
        if event.tick != tick:
            continue
        if isinstance(event, MMQuoted):
            after_mm = True
            continue
        if not after_mm or not isinstance(event, OrderPlaced | OrderRejected):
            continue
        agent_id = event.agent_id
        if agent_id == "MM" or agent_id in order:
            continue
        order.append(agent_id)
    return order


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------
@pytest.mark.determinism
def test_same_seed_same_hash() -> None:
    """O1 and FR-5.1.4: one seed, one journal, byte for byte."""
    first_result, first_events = play(SMALL)
    second_result, second_events = play(SMALL)
    assert first_events, "the reference match produced an empty journal"
    assert first_result.journal_hash == second_result.journal_hash
    assert [event.to_dict() for event in first_events] == [event.to_dict() for event in second_events]
    # And the hash is a function of the seed: a different seed moves it.
    other = Recipe(
        name=SMALL.name,
        template_id=SMALL.template_id,
        seed=SMALL.seed + 1,
        ticks_total=SMALL.ticks_total,
        n_markets=SMALL.n_markets,
        baselines=SMALL.baselines,
    )
    other_result, other_events = play(other)
    assert other_events
    assert other_result.journal_hash != first_result.journal_hash


@pytest.mark.determinism
def test_the_in_memory_hash_equals_the_file_bytes(tmp_path: Path) -> None:
    """Section 4.3: the digest of the events is the digest of the file."""
    path = tmp_path / "journal.jsonl"
    result, events = play(SMALL, path=path)
    assert events
    raw = path.read_bytes()
    assert raw
    assert b"\r" not in raw
    import hashlib

    assert hashlib.blake2b(raw, digest_size=32).hexdigest() == result.journal_hash
    assert journal_hash_of(events) == result.journal_hash
    with open(path, encoding=JOURNAL_ENCODING, newline=JOURNAL_NEWLINE) as handle:
        assert journal_hash_from_lines(handle.readlines()) == result.journal_hash


@pytest.mark.determinism
def test_golden_journal_hashes() -> None:
    """AC-P1: the three frozen scenarios have not moved, byte for byte."""
    assert GOLDEN_DIR.is_dir(), "tests/golden/ is missing; run regenerate_golden()"
    for recipe in GOLDEN_RECIPES:
        journal_path = golden_journal_path(recipe)
        hash_path = golden_hash_path(recipe)
        assert journal_path.exists(), f"missing golden journal for {recipe.name}"
        assert hash_path.exists(), f"missing golden hash for {recipe.name}"
        frozen_bytes = journal_path.read_bytes()
        assert frozen_bytes, f"the golden journal of {recipe.name} is empty"
        assert b"\r" not in frozen_bytes
        result, events = play(recipe)
        assert events, f"replaying {recipe.name} produced an empty journal"
        expected = read_golden_hash(recipe)
        assert result.journal_hash == expected, (
            f"{recipe.name}: the journal hash moved. If that is deliberate, bump the version "
            "CONTRACTS section 10 names and run regenerate_golden() in the same commit."
        )
        produced = "".join(event_to_line(event) for event in events).encode("utf-8")
        assert produced == frozen_bytes, f"{recipe.name}: the journal bytes moved"
        import hashlib

        assert hashlib.blake2b(frozen_bytes, digest_size=32).hexdigest() == expected


@pytest.mark.determinism
@pytest.mark.slow
def test_golden_hashes_survive_a_fresh_interpreter() -> None:
    """AC-P1 procedure: fresh processes, PYTHONHASHSEED unset then two values.

    This is the only test that can catch a salted builtin ``hash()`` or a set
    iteration reaching the journal, because both are stable inside one process
    and unstable across two.
    """
    expected = {recipe.name: read_golden_hash(recipe) for recipe in GOLDEN_RECIPES}
    assert expected and all(expected.values())
    for hash_seed in (None, "0", "12345"):
        produced = run_in_fresh_process(hash_seed)
        assert produced == expected, f"PYTHONHASHSEED={hash_seed} produced {produced}"


@pytest.mark.determinism
def test_tick_shuffle_depends_only_on_seed_and_tick() -> None:
    """FR-5.1.5: the full seat list is shuffled, then the frozen seats drop out."""
    seats = sorted_ids([f"A{i}" for i in range(1, 9)])
    # (a) fresh_substream makes the permutation independent of how much
    # randomness earlier ticks consumed.
    clean = RngTree(WIDE.seed)
    busy = RngTree(WIDE.seed)
    for tick in range(1, 40):
        busy.fresh_substream(f"runner.tick_shuffle.{tick}")
        busy.child("info").fresh_substream(f"info.news.tick.{tick}")
    for tick in (1, 7, 24):
        assert shuffle_seeded(clean.fresh_substream(f"runner.tick_shuffle.{tick}"), seats) == shuffle_seeded(
            busy.fresh_substream(f"runner.tick_shuffle.{tick}"), seats
        )
    # (b) the two readings differ, so the assertion in (c) is not vacuous.
    frozen = {"A3"}
    full_then_filter = [
        agent_id
        for agent_id in shuffle_seeded(RngTree(WIDE.seed).fresh_substream("runner.tick_shuffle.5"), seats)
        if agent_id not in frozen
    ]
    filter_then_shuffle = shuffle_seeded(
        RngTree(WIDE.seed).fresh_substream("runner.tick_shuffle.5"),
        [agent_id for agent_id in seats if agent_id not in frozen],
    )
    assert full_then_filter != filter_then_shuffle
    # (c) the runner uses the first reading. The permutation is recovered from
    # the journal, because P3 applies each agent's block contiguously.
    _result, events = play(WIDE)
    assert events
    wide_seats = sorted_ids([f"A{i}" for i in range(1, len(WIDE.baselines) + 1)])
    checked = 0
    for tick in range(1, WIDE.ticks_total + 1):
        observed = p3_order_of_tick(events, tick)
        if len(observed) < 2:
            continue
        expected = shuffle_seeded(RngTree(WIDE.seed).fresh_substream(f"runner.tick_shuffle.{tick}"), wide_seats)
        positions = [expected.index(agent_id) for agent_id in observed]
        assert positions == sorted(positions), (
            f"tick {tick}: P3 order {observed} is not a subsequence of the shuffle {expected}"
        )
        checked += 1
    assert checked >= 5, f"only {checked} ticks had two or more acting agents, the check is too weak"


@pytest.mark.determinism
def test_reused_agent_objects_replay_identically() -> None:
    """Section 3.1: ScriptedAgent.reset is not decoration.

    Two consecutive matches over the **same** agent instances must produce the
    two journals two fresh runs produce. Without the reset call the second
    match inherits the first one's internal state and every single match test
    still passes while every tournament is silently non deterministic.
    """
    second = Recipe(
        name="harvest_small_second",
        template_id=SMALL.template_id,
        seed=SMALL.seed + 7,
        ticks_total=SMALL.ticks_total,
        n_markets=SMALL.n_markets,
        baselines=SMALL.baselines,
    )
    fresh_first = play(SMALL)[0].journal_hash
    fresh_second = play(second)[0].journal_hash
    assert fresh_first != fresh_second

    # One set of agent objects, two consecutive matches.
    reused = agents_of(SMALL, config_of(SMALL), RngTree(SMALL.seed))
    reused_hashes: list[str] = []
    for recipe in (SMALL, second):
        config = config_of(recipe)
        world = world_of(recipe)
        journal = Journal(match_id_of(recipe))
        runner = MatchRunner(
            config=config,
            world=world,
            agents=specs_of(recipe, world),
            gateway=ScriptedGateway(agents=reused),  # type: ignore[arg-type]
            journal=journal,
            match_id=journal.match_id,
            rng=RngTree(config.seed),
        )
        result = runner.run()
        assert journal.events
        reused_hashes.append(result.journal_hash)
    assert reused_hashes == [fresh_first, fresh_second]


@pytest.mark.determinism
def test_the_runner_consumes_only_its_own_substream_family() -> None:
    """Section 3.3: there is no ``runner.agent_order``, only the per tick family."""
    _result, events = play(SMALL)
    assert events
    quotes = of_type(events, MMQuoted)
    assert quotes, "the market maker never quoted, so the mm substream was never used"
    tree = RngTree(SMALL.seed)
    # The two registered names the runner hands over exist, and the one family
    # it consumes itself is accepted for every tick of the match.
    tree.child("info")
    tree.child("mm")
    for tick in range(1, SMALL.ticks_total + 1):
        tree.fresh_substream(f"runner.tick_shuffle.{tick}")
    from pxe.errors import UnknownSubstreamError

    with pytest.raises(UnknownSubstreamError):
        tree.fresh_substream("runner.agent_order")


@pytest.mark.determinism
def test_the_runner_resets_agents_through_the_gateway_hook() -> None:
    """The runner resets seats through ``reset_agents``, not through reflection.

    Ruling R59. ``test_reused_agent_objects_replay_identically`` above proves the
    reset *happens*; it cannot see *how*, and the how matters: the runner used to
    discover agents by reflecting on a private attribute named ``agents`` or
    ``_agents``. That works for ``ScriptedGateway`` and silently does nothing for
    any gateway storing its seats under another name (``ClaudeCliGateway`` keeps
    ``harnesses``), so O1 would die for LLM and mixed matches with every test
    still green.

    Two claims:

    * a gateway that implements the contracted hook has it called exactly once
      per match, with the match config and the match ``RngTree``;
    * that call, and not reflection, is what does the work: a gateway that hides
      its agents from reflection entirely still gets its seats reset, which is
      proven by the journal hash matching the fresh run.
    """
    calls: list[tuple[MatchConfig, RngTree]] = []

    class OpaqueGateway(ScriptedGateway):
        """A gateway whose seats reflection cannot find.

        ``ScriptedGateway`` keeps its agents in ``_agents``; this subclass moves
        them into a closure-held mapping under a name the old structural walk
        never looked at, so the only way its seats can be reset is the hook.
        """

        def __init__(self, *, agents: dict[str, object]) -> None:
            super().__init__(agents=agents)  # type: ignore[arg-type]
            self._hidden = dict(self._agents)
            self._agents = {}
            self._seats = tuple(sorted_ids(tuple(self._hidden)))

        @property
        def agent_ids(self) -> tuple[str, ...]:
            return self._seats

        async def acall_agent(self, *, agent_id: str, observation: Observation, tick: int) -> AgentReply:
            self._agents = self._hidden
            try:
                return await super().acall_agent(agent_id=agent_id, observation=observation, tick=tick)
            finally:
                self._agents = {}

        def reset_agents(self, *, config: MatchConfig, rng: RngTree) -> None:
            calls.append((config, rng))
            for agent_id in self._seats:
                self._hidden[agent_id].reset(  # type: ignore[attr-defined]
                    config=config,
                    rng=rng.child(f"agent/{agent_id}").substream(f"agent.{agent_id}"),
                )

    fresh = play(SMALL)[0].journal_hash

    config = config_of(SMALL)
    opaque = OpaqueGateway(agents=agents_of(SMALL, config, RngTree(SMALL.seed)))
    # Reflection finds nothing on this object, which is the point.
    assert _legacy_scripted_agents_of(opaque) == {}, "the gateway is not opaque, so this test proves nothing"

    result, events = play(SMALL, gateway=opaque, config=config)
    assert events, "the match produced an empty journal"
    assert len(calls) == 1, f"reset_agents was called {len(calls)} times, expected exactly once per match"
    assert calls[0][0] is config, "reset_agents was not handed the match config"
    assert isinstance(calls[0][1], RngTree)
    assert result.journal_hash == fresh, (
        "the hook reset the seats differently from the reference run, so the per seat substream is wrong"
    )
