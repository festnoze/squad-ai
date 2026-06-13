"""Domain models: project, epics, user stories, chat."""

from __future__ import annotations

import time
import uuid
from enum import Enum

from pydantic import BaseModel, Field, field_validator


class PipelinePhase(str, Enum):
    IDLE = "idle"
    SPEC = "spec"          # PM is interviewing the user (or self-answering in auto-spec)
    ANALYZE = "analyze"    # Analyst is exploring/prioritizing the next feature hypotheses
    PLAN = "plan"          # PO is breaking the brief into epics / user stories
    ARCHITECT = "architect"  # Architect designs the technical solution (optional phase)
    BUILD = "build"        # dev agents are implementing stories (BDD/TDD)
    DONE = "done"          # iteration finished, waiting for user (or next auto-spec cycle)
    STOPPED = "stopped"
    ERROR = "error"


class StoryStatus(str, Enum):
    TODO = "todo"
    IN_PROGRESS = "in_progress"   # dev agent assigned, writing step definitions
    RED = "red"                   # acceptance tests written and failing, implementing
    GREEN = "green"               # tests pass, awaiting orchestrator verification
    DONE = "done"
    FAILED = "failed"


class ChatRole(str, Enum):
    USER = "user"
    PM = "pm"
    PO = "po"
    DEV = "dev"
    ANALYST = "analyst"
    ARCHITECT = "architect"
    QA = "qa"
    CRITIC = "critic"
    JUDGE = "judge"
    SYSTEM = "system"


class HypothesisStatus(str, Enum):
    PROPOSED = "proposed"
    SELECTED = "selected"   # being built in the current iteration
    DONE = "done"
    REJECTED = "rejected"


class ComponentStatus(str, Enum):
    PROPOSED = "proposed"   # suggested by the solution agent, awaiting the user
    APPROVED = "approved"   # validated by the user, ready for the setup executor
    CREATED = "created"     # folders/manifests actually created in the workspace
    REJECTED = "rejected"   # discarded by the user


class TestState(str, Enum):
    __test__ = False              # not a pytest test class

    NONEXISTENT = "nonexistent"   # not written yet
    RED = "red"                   # written and failing
    GREEN = "green"               # passing


def new_id(prefix: str) -> str:
    """Generate a short unique id like 'us-1a2b3c4d'."""
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


def _clamp_1_5(v: int) -> int:
    """Clamp a 1..5 score so out-of-range agent output or a legacy persisted
    state never fails Pydantic validation (which would drop the whole project
    at load time)."""
    return max(1, min(5, v))


class ChatMessage(BaseModel):
    role: ChatRole
    content: str
    ts: float = Field(default_factory=time.time)


class FeatureHypothesis(BaseModel):
    """A candidate next feature proposed and scored by the Analyst agent."""

    id: str
    title: str
    rationale: str = ""
    value: int = 3        # 1 (low) .. 5 (high)
    complexity: int = 3   # 1 (trivial) .. 5 (hard)
    status: HypothesisStatus = HypothesisStatus.PROPOSED
    rank: int = 1         # analyst's priority order, 1 = next to build

    @field_validator("value", "complexity")
    @classmethod
    def _clamp_scores(cls, v: int) -> int:
        return _clamp_1_5(v)

    @field_validator("rank")
    @classmethod
    def _rank_at_least_one(cls, v: int) -> int:
        return max(1, v)

    @property
    def score(self) -> float:
        return self.value / max(self.complexity, 1)


class Component(BaseModel):
    """A technical component of the generated product (backend, frontend,
    database…), proposed by the solution agent and validated by the user."""

    id: str
    kind: str = "other"      # backend | frontend | database | cache | other
    name: str = ""
    technology: str = ""     # e.g. "Python + FastAPI", "React + Vite", "PostgreSQL"
    rationale: str = ""
    optional: bool = False   # optional components default to not-approved
    status: ComponentStatus = ComponentStatus.PROPOSED


class PlannedTest(BaseModel):
    """One unit test planned by the QA agent when decomposing the acceptance
    test outside-in (London style): each layer's test mocks its direct
    collaborators, written red-first before any implementation."""

    id: str
    layer: str = ""              # e.g. "api", "facade", "service", "repository", "llm"
    description: str = ""
    mocks: list[str] = Field(default_factory=list)   # collaborators to mock
    file_hint: str = ""          # suggested test file path
    criteria: list[str] = Field(default_factory=list)   # acceptance-criterion ids covered
    status: TestState = TestState.NONEXISTENT


class AcceptanceCriterion(BaseModel):
    id: str
    text: str


class UserStory(BaseModel):
    id: str
    epic_id: str
    title: str
    description: str = ""
    acceptance_criteria: list[AcceptanceCriterion] = Field(default_factory=list)
    gherkin: str = ""
    test_plan: list[PlannedTest] = Field(default_factory=list)
    depends_on: list[str] = Field(default_factory=list)
    priority: int = 3     # kanban priority, 1 (haute) .. 5 (basse)
    status: StoryStatus = StoryStatus.TODO
    iteration: int = 1
    attempts: int = 0
    last_error: str = ""
    quality_score: int = -1  # last refinement score for this story's code (-1 = not run)
    ui: bool = False         # story has a visual/UI dimension (QA routes it to Playwright)
    ui_tests: list[str] = Field(default_factory=list)  # replayable UI test files (tests/ui/…)

    @field_validator("priority")
    @classmethod
    def _clamp_priority(cls, v: int) -> int:
        return _clamp_1_5(v)

    def tests_for_criterion(self, criterion_id: str) -> list[PlannedTest]:
        return [t for t in self.test_plan if criterion_id in t.criteria]

    def criterion_state(self, criterion_id: str) -> TestState:
        """A criterion is green when all its tests are green (and it has at
        least one); red if any test is red; otherwise nonexistent. A done story
        has a fully green suite, so all its criteria are green."""
        if self.status == StoryStatus.DONE:
            return TestState.GREEN
        tests = self.tests_for_criterion(criterion_id)
        if any(t.status == TestState.RED for t in tests):
            return TestState.RED
        if tests and all(t.status == TestState.GREEN for t in tests):
            return TestState.GREEN
        return TestState.NONEXISTENT


class Epic(BaseModel):
    id: str
    title: str
    description: str = ""
    iteration: int = 1


class Finding(BaseModel):
    """A problem the closed-loop evaluator (E6) observed while actually
    exercising the generated product: a bug that slipped past pytest, a broken
    integration between stories, a UX friction or a missing capability. Findings
    are fed into the feedback-impact pipeline as evidence."""

    id: str
    severity: str = "medium"   # low | medium | high
    kind: str = "bug"          # bug | integration | ux | gap
    title: str = ""
    detail: str = ""
    iteration: int = 1


class Usage(BaseModel):
    """Accumulated token/cost observability for a project, summed across every
    agent call (parsed from the Claude CLI's per-call usage)."""

    cost_usd: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0
    agent_calls: int = 0


class ProjectState(BaseModel):
    id: str
    name: str
    goal: str
    auto_spec: bool = False
    spec_mode: str = "interview"  # "interview" (Socratic) | "brainstorm" (refine the need)
    budget_usd: float = 0.0       # cost cap in USD (0 = no limit) — auto-stops when reached
    budget_tokens: int = 0        # token cap (0 = no limit)
    phase: PipelinePhase = PipelinePhase.IDLE
    brief: str = ""
    architecture: str = ""  # current technical design (from the optional Architect phase)
    plan_quality: int = -1  # last refinement score for the PO plan (-1 = not run)
    backlog: list[FeatureHypothesis] = Field(default_factory=list)
    components: list[Component] = Field(default_factory=list)
    epics: list[Epic] = Field(default_factory=list)
    stories: list[UserStory] = Field(default_factory=list)
    chat: list[ChatMessage] = Field(default_factory=list)
    feedback: list[str] = Field(default_factory=list)
    findings: list[Finding] = Field(default_factory=list)  # E6 evaluator observations
    lessons: list[str] = Field(default_factory=list)  # E7 durable retro lessons (injected into prompts)
    retro_recommendations: list[str] = Field(default_factory=list)  # E7 tuning advice (UI only)
    build_guidance: list[str] = Field(default_factory=list)  # user directives given during the build
    iteration: int = 1
    usage: Usage = Field(default_factory=Usage)  # accumulated tokens/cost across agent calls
    running: bool = False  # generated app currently running
    paused: bool = False   # pipeline paused by the user (gates between steps)
    resume_at: float = 0.0  # epoch of the scheduled auto-resume (0 = none) — M2 watchdog
    archived: bool = False  # hidden from the default project list (not deleted)
    error: str = ""
    created_at: float = Field(default_factory=time.time)

    def story(self, story_id: str) -> UserStory:
        for s in self.stories:
            if s.id == story_id:
                return s
        raise KeyError(story_id)

    def stories_of_iteration(self, iteration: int) -> list[UserStory]:
        return [s for s in self.stories if s.iteration == iteration]
