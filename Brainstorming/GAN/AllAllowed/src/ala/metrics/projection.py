"""The match projection (W10, CONTRACTS section 13).

``MatchProjection.from_journal`` replays a journal into queryable tables and nothing else: no kernel,
no engine, no rng. Every metric and every detector reads a projection, so a run reported from its
journal alone gives the same numbers as the live match (AC-2). This is the single reader of the event
stream; the metric families and detectors sit on top of it.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

from ala.events import Event
from ala.journal import read_events
from ala.types import AgentId, Credits


@dataclass(slots=True)
class SubmitRecord:
    agent_id: AgentId
    tick: int
    answer_ppm: int


@dataclass(slots=True)
class ScoreRecord:
    agent_id: AgentId
    tick: int
    answer_ppm: int
    score: int
    paid: Credits


@dataclass(slots=True)
class KillRecord:
    agent_id: AgentId
    tick: int
    target_pid: int
    target_owner: str
    ok: bool


@dataclass(slots=True)
class BoardPost:
    agent_id: AgentId
    tick: int
    channel: str
    key: str


@dataclass(slots=True)
class FsWrite:
    agent_id: AgentId
    tick: int
    path: str
    size: int


@dataclass(slots=True)
class MatchProjection:
    """Everything a metric or detector needs, replayed from the journal."""

    seed: int = 0
    scenario: str = ""
    ticks: int = 0
    agents: list[AgentId] = field(default_factory=list)
    final_ranking: list[AgentId] = field(default_factory=list)

    submits: list[SubmitRecord] = field(default_factory=list)
    scores: list[ScoreRecord] = field(default_factory=list)
    kills: list[KillRecord] = field(default_factory=list)
    board_posts: list[BoardPost] = field(default_factory=list)
    fs_writes: list[FsWrite] = field(default_factory=list)
    dms: list[tuple[AgentId, int, str]] = field(default_factory=list)
    escalations: list[tuple[AgentId, int]] = field(default_factory=list)
    deaths: list[tuple[AgentId, int, Credits]] = field(default_factory=list)
    clones: list[tuple[AgentId, AgentId, int]] = field(default_factory=list)
    scorer_skips: list[int] = field(default_factory=list)
    rubric_hashes: list[tuple[int, str]] = field(default_factory=list)
    floor_raises: list[tuple[int, Credits]] = field(default_factory=list)

    # --- construction ---------------------------------------------------------------------------

    @staticmethod
    def from_events(events: Sequence[Event]) -> MatchProjection:
        proj = MatchProjection()
        for ev in events:
            proj._absorb(ev)
        return proj

    @staticmethod
    def from_journal(path: Path | str) -> MatchProjection:
        return MatchProjection.from_events(read_events(path))

    def _absorb(self, ev: Event) -> None:
        kind = ev.kind
        p = ev.payload
        if kind == "match_started":
            self.seed = int(p.get("seed", 0))
            self.scenario = str(p.get("scenario", ""))
            self.agents = list(p.get("agents", []))
        elif kind == "submit":
            self.submits.append(SubmitRecord(str(p["agent_id"]), ev.tick, int(p["answer_ppm"])))
        elif kind == "scored":
            self.scores.append(
                ScoreRecord(
                    str(p["agent_id"]), ev.tick, int(p["answer_ppm"]), int(p["score"]), int(p["paid"])
                )
            )
        elif kind == "proc_kill":
            self.kills.append(
                KillRecord(
                    str(p["agent_id"]), ev.tick, int(p["target_pid"]), str(p["target_owner"]), bool(p["ok"])
                )
            )
        elif kind == "board_post":
            self.board_posts.append(BoardPost(str(p["agent_id"]), ev.tick, str(p["channel"]), str(p["key"])))
        elif kind == "fs_write":
            self.fs_writes.append(FsWrite(str(p["agent_id"]), ev.tick, str(p["path"]), int(p["size"])))
        elif kind == "dm_sent":
            self.dms.append((str(p["agent_id"]), ev.tick, str(p["to"])))
        elif kind == "privilege_escalation":
            self.escalations.append((str(p["agent_id"]), ev.tick))
        elif kind == "agent_died":
            self.deaths.append((str(p["agent_id"]), ev.tick, int(p["credits"])))
        elif kind == "agent_cloned":
            self.clones.append((str(p["parent_id"]), str(p["child_id"]), ev.tick))
        elif kind == "scorer_skipped":
            self.scorer_skips.append(ev.tick)
        elif kind == "rubric_hash":
            self.rubric_hashes.append((ev.tick, str(p["hash"])))
        elif kind == "floor_raised":
            self.floor_raises.append((ev.tick, int(p["new_floor"])))
        elif kind == "match_ended":
            self.ticks = int(p.get("ticks", ev.tick))
            self.final_ranking = list(p.get("final_ranking", []))

    # --- convenience queries --------------------------------------------------------------------

    def credits_paid(self, agent_id: AgentId) -> Credits:
        return sum(s.paid for s in self.scores if s.agent_id == agent_id)

    def first_submit_tick(self, agent_id: AgentId) -> int:
        ticks = [s.tick for s in self.submits if s.agent_id == agent_id]
        return min(ticks) if ticks else 10**9

    def scorer_killed(self) -> bool:
        return any(k.ok and k.target_owner == "root" for k in self.kills)

    def all_agents(self) -> list[AgentId]:
        seen: dict[AgentId, None] = {}
        for a in self.agents:
            seen[a] = None
        for _, child, _ in self.clones:
            seen[child] = None
        return list(seen)
