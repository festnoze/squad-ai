"""Persistent state of a v2 project. Small on purpose: every field is used."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Profile(str, Enum):
    LIB = "lib"
    CLI = "cli"
    API = "api"
    FULLSTACK = "fullstack"


class Phase(str, Enum):
    CREATED = "created"
    BRIEF = "brief"
    PLAN = "plan"
    BUILD = "build"
    DELIVER = "deliver"
    DONE = "done"
    NEEDS_ATTENTION = "needs_attention"
    STOPPED = "stopped"
    ERROR = "error"


TERMINAL_PHASES = frozenset({Phase.DONE, Phase.NEEDS_ATTENTION, Phase.STOPPED, Phase.ERROR})


class StoryStatus(str, Enum):
    TODO = "todo"
    IN_PROGRESS = "in_progress"
    DONE = "done"
    FAILED = "failed"


class _Model(BaseModel):
    # Old or newer state files may carry fields this version does not know.
    model_config = ConfigDict(extra="ignore")


class AcceptanceCriterion(_Model):
    id: str  # qualified, e.g. "US-1.AC-2"
    text: str


class AcceptanceTest(_Model):
    """Tests written by the QA agent for one criterion (pytest nodeids)."""

    ac_id: str
    nodeids: list[str]


class Epic(_Model):
    id: str
    title: str
    description: str = ""


class Story(_Model):
    id: str  # "US-1"
    epic_id: str
    title: str
    description: str = ""
    criteria: list[AcceptanceCriterion]
    gherkin: str = ""
    depends_on: list[str] = Field(default_factory=list)
    priority: int = 3  # 1 = highest
    status: StoryStatus = StoryStatus.TODO
    attempts: int = 0
    acceptance_tests: list[AcceptanceTest] = Field(default_factory=list)
    # sha256 of every QA-authored test file, keyed by repo-relative POSIX path.
    test_fingerprint: dict[str, str] = Field(default_factory=dict)
    dev_session_id: str | None = None
    last_error: str = ""


class Usage(_Model):
    calls: int = 0
    cost_usd: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0
    duration_ms: int = 0

    def add(self, cost_usd: float, input_tokens: int, output_tokens: int, duration_ms: int) -> None:
        self.calls += 1
        self.cost_usd = round(self.cost_usd + cost_usd, 6)
        self.input_tokens += input_tokens
        self.output_tokens += output_tokens
        self.duration_ms += duration_ms


class ProjectState(_Model):
    version: int = 2
    id: str
    name: str
    package: str  # importable Python package name of the product
    profile: Profile | None = None  # None until given at creation or chosen by the PO
    goal: str = ""
    brief: str = ""
    phase: Phase = Phase.CREATED
    epics: list[Epic] = Field(default_factory=list)
    stories: list[Story] = Field(default_factory=list)
    usage: Usage = Field(default_factory=Usage)
    error: str = ""
    created_at: str = Field(default_factory=utcnow)
    updated_at: str = Field(default_factory=utcnow)

    def story(self, story_id: str) -> Story:
        for story in self.stories:
            if story.id == story_id:
                return story
        raise KeyError(story_id)
