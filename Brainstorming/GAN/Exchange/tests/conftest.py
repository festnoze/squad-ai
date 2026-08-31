"""Shared pytest fixtures for the whole suite (owner A01, CONTRACTS section 10).

Ten fixture names are reserved here and **no other module may define a
fixture with one of these names**:

``repo_root``, ``schemas_dir``, ``standard_config``, ``rng_tree``,
``tmp_journal``, ``tiny_world``, ``flat_accounts``, ``scripted_gateway``,
``action_schema``, ``observation_schema``.

Four of them (``tmp_journal``, ``tiny_world``, ``flat_accounts``,
``scripted_gateway``) depend on modules that other workstreams have not
landed yet. They are declared now, with the exact signature and the exact
return type the contract promises, and they call ``pytest.importorskip`` so a
test that uses one **skips** until its module exists instead of erroring with
``fixture not found``. That is deliberate: the name is the contract, and
reserving it today is what stops twenty-four workstreams from inventing
twenty-four incompatible spellings of "a flat account book".

The ``src`` path is on ``sys.path`` through ``[tool.pytest.ini_options]
pythonpath = ["src"]``; the ``_src_on_path`` fixture below asserts it rather
than mutating ``sys.path`` a second time, so a broken configuration fails
loudly instead of being papered over.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent


# ---------------------------------------------------------------------------
# Paths and configuration
# ---------------------------------------------------------------------------
@pytest.fixture(scope="session")
def repo_root() -> Path:
    """Absolute path of the repository root (the directory holding pyproject.toml)."""
    return REPO_ROOT


@pytest.fixture(scope="session")
def schemas_dir(repo_root: Path) -> Path:
    """Absolute path of ``schemas/``, the versioned agent interface contracts."""
    return repo_root / "schemas"


@pytest.fixture(scope="session", autouse=True)
def _src_on_path() -> None:
    """Fail the whole session if ``pythonpath = ["src"]`` stopped working."""
    src = str(REPO_ROOT / "src")
    on_path = any(Path(entry).resolve() == Path(src).resolve() for entry in sys.path if entry)
    assert on_path, "pyproject's [tool.pytest.ini_options] pythonpath = ['src'] is not in effect"


@pytest.fixture
def standard_config() -> Any:
    """The reference ``MatchConfig``: PRD section 5.7 defaults, seed 20260827.

    Every test that needs "a normal match" uses this one, so a default that
    moves moves one fixture and not twenty-five literals.
    """
    from pxe.types import MatchConfig

    return MatchConfig(seed=20260827)


@pytest.fixture
def rng_tree(standard_config: Any) -> Any:
    """The root ``RngTree`` of the reference match, built by the caller (section 3.1)."""
    from pxe.rng import RngTree

    return RngTree(standard_config.seed)


# ---------------------------------------------------------------------------
# Fixtures reserved for modules that are not written yet
# ---------------------------------------------------------------------------
@pytest.fixture
def tmp_journal(tmp_path: Path) -> Iterator[Any]:
    """An open ``pxe.journal.Journal`` writing to ``tmp_path/journal.jsonl``.

    Opened by ``Journal`` itself with ``encoding="utf-8", newline="\\n"``
    (CONTRACTS section 4.2), so a test may compare the file bytes with
    ``journal_hash`` directly. Closed on teardown. Owner of the module: A02.
    """
    journal_mod = pytest.importorskip("pxe.journal", reason="A02 has not landed pxe.journal yet")
    journal = journal_mod.Journal("m-test-0-01", tmp_path / "journal.jsonl")
    try:
        yield journal
    finally:
        journal.close()


#: Ticks and markets of ``tiny_world``. They are the smallest values a legal
#: ``MatchConfig`` accepts (``__post_init__`` enforces ``24 <= ticks_total`` and
#: ``2 <= n_markets``), so a test can pair the fixture with
#: ``MatchConfig(ticks_total=TINY_TICKS, n_markets=TINY_MARKETS)`` without
#: tripping the CONTRACTS section 2.6 agreement check.
TINY_TICKS = 24
TINY_MARKETS = 2


@pytest.fixture
def tiny_world(standard_config: Any, rng_tree: Any) -> Any:
    """A two market, twenty-four tick ``World`` from the ``election`` template.

    Small enough that a whole match runs inside a unit test, big enough that
    FR-5.2.1 correlations exist and that ``MatchConfig`` accepts the horizon.
    Owner of the module: A03.
    """
    generator = pytest.importorskip("pxe.world.generator", reason="A03 has not landed pxe.world yet")
    return generator.generate_world(
        template_id="election",
        seed=standard_config.seed,
        ticks_total=TINY_TICKS,
        n_markets=TINY_MARKETS,
    )


@pytest.fixture
def flat_accounts(standard_config: Any) -> Any:
    """An ``AccountBook`` with six seats, five markets and every position flat.

    Nothing is reserved, nothing is held: the state every accounting test
    starts from. Owner of the module: A06.
    """
    accounts_mod = pytest.importorskip("pxe.exchange.accounts", reason="A06 has not landed pxe.exchange.accounts yet")
    from pxe.types import make_agent_id, make_market_id

    return accounts_mod.AccountBook(
        agent_ids=[make_agent_id(i) for i in range(1, 7)],
        market_ids=[make_market_id(i) for i in range(1, standard_config.n_markets + 1)],
        config=standard_config,
    )


@pytest.fixture
def scripted_gateway(standard_config: Any, rng_tree: Any) -> Any:
    """A ``ScriptedGateway`` over six ``mute`` baselines.

    ``mute`` declares predictions and places no order, which is the AC-P9
    population and the cheapest way to drive a whole match with no LLM.
    Owners of the modules: A12 (agents) and A13 (gateway).
    """
    agents_mod = pytest.importorskip("pxe.agents.base", reason="A12 has not landed pxe.agents yet")
    scripted_mod = pytest.importorskip("pxe.gateway.scripted", reason="A13 has not landed pxe.gateway yet")
    from pxe.types import make_agent_id

    agents = {}
    for index in range(1, 7):
        agent_id = make_agent_id(index)
        agents[agent_id] = agents_mod.make_baseline(
            "mute",
            agent_id=agent_id,
            config=standard_config,
            rng=rng_tree.child(f"agent/{agent_id}").substream(f"agent.{agent_id}"),
        )
    return scripted_mod.ScriptedGateway(agents=agents)


# ---------------------------------------------------------------------------
# Small helpers used by more than one A01 test module
# ---------------------------------------------------------------------------
@pytest.fixture(scope="session")
def action_schema(schemas_dir: Path) -> dict[str, Any]:
    """The parsed ``schemas/action.v1.json``."""
    return json.loads((schemas_dir / "action.v1.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="session")
def observation_schema(schemas_dir: Path) -> dict[str, Any]:
    """The parsed ``schemas/observation.v1.json``."""
    return json.loads((schemas_dir / "observation.v1.json").read_text(encoding="utf-8"))
