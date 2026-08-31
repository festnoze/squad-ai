"""End-to-end runner tests: a full tiny match and the closed-system property (W9, AC-3).

Why these: ``run_match`` is the referee that ties kernel, tools, scorer, gateway, and scenario together.
A tiny match must complete and lay down a well-formed journal, and the ledger must stay closed: every
credit in any account traces back to a source the journal records, so no money is conjured or lost
unnoticed.

The exact identity checked (documented here so the assertion is not a black box). Replaying the journal
and maintaining a per-agent balance, the only credit movements are:
  agent_born      : +budget                (the initial pool, start_budget per born agent)
  tool_called     : -cost                  (a sink: spent on tool use, cost 0 for dropped calls)
  scored          : +paid                  (a source: scorer payments)
  agent_cloned    : child := balance(parent) at that tick (a source: cloning duplicates a balance)
Deaths are recorded (agent_died.credits) as the agent's balance at death and the account persists; they
do not remove ledger credits. Conservation then reads:
  sum(all reconstructed balances)
    == sum(born budgets) + sum(clone-injected balances) - sum(tool costs) + sum(scored paid)
and no reconstructed balance is ever negative (the validator forbids unaffordable calls, payments are
non-negative). The task's headline figure, start_budget * n_born - spent + paid - died, stays >= 0.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from ala.journal import read_events
from ala.metrics import MatchProjection
from ala.types import MatchResult

RunTinyMatch = Callable[..., tuple[MatchResult, Path, MatchProjection]]


def test_tiny_match_completes_and_journals_the_key_events(run_tiny_match: RunTinyMatch) -> None:
    result, journal_path, projection = run_tiny_match()
    assert isinstance(result, MatchResult)
    assert isinstance(projection, MatchProjection)

    events = read_events(journal_path)
    kinds = {e.kind for e in events}
    for required in ("match_started", "agent_born", "submit", "scored", "match_ended"):
        assert required in kinds, f"missing {required} in journal"

    # The journal opens with match_started and closes with match_ended.
    assert events[0].kind == "match_started"
    assert events[-1].kind == "match_ended"

    # The result agrees with the journalled fingerprint and ranking.
    assert result.ticks == projection.ticks == 12
    assert result.final_ranking == tuple(projection.final_ranking)
    assert len(result.journal_hash) == 64  # sha256 hex digest


def test_every_seq_is_unique_and_monotonic(run_tiny_match: RunTinyMatch) -> None:
    _, journal_path, _ = run_tiny_match()
    seqs = [e.seq for e in read_events(journal_path)]
    assert seqs == sorted(seqs)
    assert len(seqs) == len(set(seqs))
    assert seqs[0] == 0


def test_closed_system_ledger_balances(run_tiny_match: RunTinyMatch) -> None:
    """AC-3: recompute the whole ledger from the journal alone and prove it is closed and non-negative."""
    _, journal_path, _ = run_tiny_match()
    events = read_events(journal_path)

    balance: dict[str, int] = {}
    born_total = 0
    spent_total = 0
    paid_total = 0
    clone_injected = 0
    died_total = 0
    n_born = 0
    start_budget = 0

    for ev in events:
        kind = ev.kind
        p = ev.payload
        if kind == "match_started":
            start_budget = int(p["config"]["start_budget"])
        elif kind == "agent_born":
            aid = str(p["agent_id"])
            balance[aid] = int(p["budget"])
            born_total += int(p["budget"])
            n_born += 1
        elif kind == "tool_called":
            aid = str(p["agent_id"])
            assert aid in balance, f"tool_called before agent_born for {aid}"
            balance[aid] -= int(p["cost"])
            spent_total += int(p["cost"])
        elif kind == "scored":
            aid = str(p["agent_id"])
            assert aid in balance, f"scored an unknown agent {aid}"
            balance[aid] += int(p["paid"])
            paid_total += int(p["paid"])
        elif kind == "agent_cloned":
            parent = str(p["parent_id"])
            child = str(p["child_id"])
            assert parent in balance, f"clone of unknown parent {parent}"
            balance[child] = balance[parent]
            clone_injected += balance[parent]
        elif kind == "agent_died":
            aid = str(p["agent_id"])
            # The recorded death credits are exactly the ledger balance at the moment of death.
            assert balance[aid] == int(p["credits"])
            died_total += int(p["credits"])

    # No account is ever negative: the validator forbids unaffordable calls and payments are non-negative.
    assert all(v >= 0 for v in balance.values()), balance

    # The conservation identity documented in this module's docstring.
    assert sum(balance.values()) == born_total + clone_injected - spent_total + paid_total

    # The headline closed-system figure the contract names stays non-negative.
    closed = start_budget * n_born - spent_total + paid_total - died_total
    assert closed >= 0

    # Sanity: at least the four seats were born and the pool started from the configured budget.
    assert n_born >= 4
    assert born_total == start_budget * n_born


def test_projection_agrees_with_raw_events(run_tiny_match: RunTinyMatch) -> None:
    """The projection is a faithful replay: rebuilding it from the same file gives the same tables."""
    _, journal_path, projection = run_tiny_match()
    rebuilt = MatchProjection.from_journal(journal_path)
    assert rebuilt.final_ranking == projection.final_ranking
    assert len(rebuilt.scores) == len(projection.scores)
    assert len(rebuilt.submits) == len(projection.submits)
    # Someone submitted and someone was scored during the match.
    assert projection.submits
    assert projection.scores
