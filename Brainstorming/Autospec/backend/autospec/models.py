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


class BackendLanguage(str, Enum):
    """L2: backend language chosen for the generated product. Python is the safe
    default (most reliable generation, no compile barrier)."""
    PYTHON = "python"
    GO = "go"
    RUST = "rust"


class StreamKind(str, Enum):
    """ST-1: a work area's nature. Each stream owns a toolchain + a (presumed
    disjoint) file zone, which is what lets agents run in parallel across
    streams. `backend` always exists; the others are selected per project."""
    BACKEND = "backend"
    FRONTEND = "frontend"
    CACHE = "cache"
    DATABASE = "database"
    OTHER = "other"


class TestState(str, Enum):
    __test__ = False              # not a pytest test class

    NONEXISTENT = "nonexistent"   # not written yet
    RED = "red"                   # written and failing
    GREEN = "green"               # passing


class BuildStage(str, Enum):
    """B1 (UX): the fine-grained stage one work item is in during BUILD. Mapped
    to the real transitions in ``pipeline._abuild_work_item``/``_arun_item_dev``/
    ``_adesign_tests``. ``QUEUED`` is the safe default so any pre-UX persisted
    state (which has no ``current_stage``) loads unchanged as "not started"."""

    QUEUED = "queued"            # not started (todo)
    ANALYZING = "analyzing"      # QA test-plan design (_adesign_tests)
    CONTRACTS = "contracts"      # dev wrote failing tests (status RED)
    IMPLEMENTING = "implementing"  # dev writing code toward green
    VERIFYING = "verifying"      # orchestrator re-runs pytest + coverage/refine/mutation
    MERGE_WAIT = "merge_wait"    # green, waiting for the merge lock
    MERGING = "merging"          # git merge into the shared repo
    DONE = "done"                # terminal: merged
    FAILED = "failed"            # terminal: gave up


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


class RecoveryState(BaseModel):
    """B1 (UX): the auto-repair state of one work item — surfaced on the stepper
    so the operator sees the factory healing itself (refine 2/3, regression
    rerun…) instead of reading a stalled item as broken. All defaults are safe
    so legacy persisted state loads as "no recovery in flight"."""

    attempt: int = 0
    max_attempts: int = 0
    # "" | "refining" | "critic_restored" | "regression_rerun" | "mutation_rerun" | "retry"
    kind: str = ""


class GuidanceEntry(BaseModel):
    """P10 (UX): one targeted chat directive aimed at a single work item, injected
    into THAT item's dev prompt. ``status`` tracks delivery: queued (not yet seen
    by a dev run), applied (injected into a dev prompt), too_late (the item was
    already terminal when it arrived)."""

    id: str = Field(default_factory=lambda: new_id("g"))
    text: str = ""
    ts: float = Field(default_factory=time.time)
    status: str = "queued"  # "queued" | "applied" | "too_late"


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


class Stream(BaseModel):
    """ST-1: a parallelizable work area with its own toolchain, language and
    (presumed disjoint) file zone. The `backend` stream is always present; the
    others (frontend/cache/database) are chosen per project by the architect.
    An empty ``ProjectState.streams`` means "one implicit backend stream" — the
    pre-streams behaviour, so legacy/flag-off projects keep working unchanged."""

    id: str                          # short stable id, e.g. "backend", "frontend"
    kind: StreamKind = StreamKind.BACKEND
    language: str = ""               # toolchain language: python/go/rust/react/sql…
    toolchain: str = ""              # explicit toolchain id ("" = derive from language)
    file_root: str = ""              # workspace-relative root ("" = repo root)
    primary: bool = False            # the project's default stream (the backend)


# ST-1: reference catalog the architect picks from (ST-4). The cache/database
# toolchains are placeholders until their dedicated tasks land (deferred).
DEFAULT_STREAM_CATALOG: dict[str, dict] = {
    "backend": {"kind": StreamKind.BACKEND, "language": "python", "file_root": "", "primary": True},
    "frontend": {"kind": StreamKind.FRONTEND, "language": "react", "file_root": "frontend"},
    "cache": {"kind": StreamKind.CACHE, "language": "python", "file_root": "cache"},
    "database": {"kind": StreamKind.DATABASE, "language": "sql", "file_root": "database"},
}


def backend_stream_for(language: str | BackendLanguage = BackendLanguage.PYTHON) -> Stream:
    """The implicit/primary backend stream for a project, carrying its backend
    language. Used as the default when ``ProjectState.streams`` is empty."""
    lang = language.value if isinstance(language, BackendLanguage) else str(language or "python")
    return Stream(id="backend", kind=StreamKind.BACKEND, language=lang, primary=True)


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


class Task(BaseModel):
    """ST-2: a unit of work within a SINGLE stream, below a UserStory. A
    multi-stream feature's US is decomposed into tasks (e.g. a front task + a
    back task); tasks of different streams run in parallel while ``depends_on``
    (other Task ids, possibly cross-stream) reflects the functional ordering
    (e.g. the front task depends on the back task that exposes the API)."""

    id: str
    story_id: str
    stream: str = ""          # stream id ("" = the project's primary/backend stream)
    title: str = ""
    description: str = ""
    acceptance_criteria: list[AcceptanceCriterion] = Field(default_factory=list)
    gherkin: str = ""
    depends_on: list[str] = Field(default_factory=list)   # other Task ids
    status: StoryStatus = StoryStatus.TODO
    attempts: int = 0
    last_error: str = ""
    files_hint: list[str] = Field(default_factory=list)   # files/zones it expects to touch
    # B1/N4/P10 (UX): fine-grained stage tracking for the stepper. All defaults
    # are safe so a pre-UX persisted Task loads as "queued, no persona, no
    # recovery, no guidance".
    current_stage: BuildStage = BuildStage.QUEUED
    stage_started_at: float = 0.0
    current_persona: str = ""        # "qa" | "dev" | "critic" | "" while the stage runs
    recovery: RecoveryState = Field(default_factory=RecoveryState)
    guidance: list[GuidanceEntry] = Field(default_factory=list)


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
    mutation_score: int = -1  # last mutation-testing robustness score, %% (-1 = not run)
    coverage_score: int = -1  # last test-coverage percentage (-1 = not run)
    ui: bool = False         # story has a visual/UI dimension (QA routes it to Playwright)
    ui_tests: list[str] = Field(default_factory=list)  # replayable UI test files (tests/ui/…)
    # ST-2: stream tagging + optional multi-stream decomposition. ``stream`` ""
    # means the project's primary/backend stream (so legacy stories are
    # unchanged). When ``tasks`` is non-empty the US is a container and its
    # status is DERIVED from its tasks (see ``effective_status``).
    stream: str = ""
    tasks: list[Task] = Field(default_factory=list)
    # B1/N4/P10 (UX): fine-grained stage tracking for the stepper. All defaults
    # are safe so a pre-UX persisted UserStory loads as "queued, no persona, no
    # recovery, no guidance".
    current_stage: BuildStage = BuildStage.QUEUED
    stage_started_at: float = 0.0
    current_persona: str = ""        # "qa" | "dev" | "critic" | "" while the stage runs
    recovery: RecoveryState = Field(default_factory=RecoveryState)
    guidance: list[GuidanceEntry] = Field(default_factory=list)

    @field_validator("priority")
    @classmethod
    def _clamp_priority(cls, v: int) -> int:
        return _clamp_1_5(v)

    def effective_status(self) -> StoryStatus:
        """The US status. For a taskless US it's the stored ``status``; for a US
        decomposed into tasks it's DERIVED: all tasks done → DONE; any active
        (in_progress/red/green) → IN_PROGRESS; any failed → FAILED; else TODO."""
        if not self.tasks:
            return self.status
        states = [t.status for t in self.tasks]
        if all(s == StoryStatus.DONE for s in states):
            return StoryStatus.DONE
        if any(s in (StoryStatus.IN_PROGRESS, StoryStatus.RED, StoryStatus.GREEN) for s in states):
            return StoryStatus.IN_PROGRESS
        if any(s == StoryStatus.FAILED for s in states):
            return StoryStatus.FAILED
        return StoryStatus.TODO

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


class AgentInteraction(BaseModel):
    """One LLM round-trip captured for live introspection: the exact prompt sent
    and the raw answer received, plus who/where/how-much. Deliberately NOT part of
    ``ProjectState`` — prompts/answers are large, and the state is re-serialized +
    broadcast on every ``_sync``; these are stored apart (in-memory ring + JSONL
    sidecar) and fetched on demand when the operator opens an item's activity."""

    id: str = Field(default_factory=lambda: new_id("call"))
    item_id: str = ""        # work-item id (US/task), or "phase:<phase>" otherwise
    phase: str = ""          # pipeline phase the call ran in
    persona: str = ""        # agent role (dev/qa/critic/…), reverse-mapped from the system prompt
    prompt: str = ""
    response: str = ""
    ok: bool = True
    error: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    duration_ms: int = 0
    prompt_truncated: bool = False
    response_truncated: bool = False
    ts: float = Field(default_factory=time.time)


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
    brownfield_path: str = ""  # B1: existing repo to extend ("" = greenfield)
    architecture: str = ""  # current technical design (from the optional Architect phase)
    plan_quality: int = -1  # last refinement score for the PO plan (-1 = not run)
    # L2: recommended/chosen backend language + the two analysis axes (1-5) and
    # the rationale. Python by default (safe), overridable by the user.
    backend_language: BackendLanguage = BackendLanguage.PYTHON
    language_complexity: int = -1   # technical complexity 1-5 (-1 = not analyzed)
    language_criticality: int = -1  # error-sensitivity 1-5 (-1 = not analyzed)
    language_rationale: str = ""
    # B-IDEA: idea-maturity assessment + brainstorming-assist state.
    idea_maturity: str = ""        # "" (not assessed) | "structured" | "vague"
    idea_rationale: str = ""       # why the idea was judged structured/vague
    brainstorm_techniques: list[str] = Field(default_factory=list)  # BMAD-chosen
    awaiting_brainstorm_decision: bool = False  # UI: offer brainstorming (oui/non)
    # ST-1: parallelizable work areas chosen by the architect. EMPTY = one
    # implicit backend stream (legacy / flag-off behaviour, unchanged).
    streams: list[Stream] = Field(default_factory=list)
    backlog: list[FeatureHypothesis] = Field(default_factory=list)
    components: list[Component] = Field(default_factory=list)
    epics: list[Epic] = Field(default_factory=list)
    stories: list[UserStory] = Field(default_factory=list)
    chat: list[ChatMessage] = Field(default_factory=list)
    feedback: list[str] = Field(default_factory=list)
    findings: list[Finding] = Field(default_factory=list)  # E6 evaluator observations
    lessons: list[str] = Field(default_factory=list)  # E7 durable retro lessons (injected into prompts)
    green_tests: list[str] = Field(default_factory=list)  # R2: nodeids known green (regression baseline)
    regressions: list[str] = Field(default_factory=list)  # R2: flagged "was green, now red" events
    retro_recommendations: list[str] = Field(default_factory=list)  # E7 tuning advice (UI only)
    build_guidance: list[str] = Field(default_factory=list)  # user directives given during the build
    iteration: int = 1
    usage: Usage = Field(default_factory=Usage)  # accumulated tokens/cost across agent calls
    # Per-iteration usage breakdown (keyed by iteration number). The global
    # `usage` above stays the project-wide total; this lets the UI show cost/
    # tokens spent in each build iteration. Old persisted states default to {}.
    iteration_usage: dict[int, Usage] = Field(default_factory=dict)
    running: bool = False  # generated app currently running
    paused: bool = False   # pipeline paused by the user (gates between steps)
    awaiting_approval: str = ""  # U4: stage awaiting human approval before build ("" = none)
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

    # ------------------------------------------------------------ streams (ST-1)

    @property
    def primary_stream_id(self) -> str:
        """The id every empty (``""``) stream reference resolves to — the
        project's primary/backend stream, or ``"backend"`` when none declared."""
        for s in self.streams:
            if s.primary:
                return s.id
        for s in self.streams:
            if s.kind == StreamKind.BACKEND:
                return s.id
        return self.streams[0].id if self.streams else "backend"

    def effective_streams(self) -> list[Stream]:
        """Declared streams, or one implicit backend stream (carrying the
        project's backend language) when none were chosen yet."""
        return self.streams or [backend_stream_for(self.backend_language)]

    def stream(self, stream_id: str) -> Stream:
        """Resolve a stream id (``""`` → primary). Falls back to a synthesized
        backend stream so callers never crash on a legacy/empty reference."""
        target = stream_id or self.primary_stream_id
        for s in self.effective_streams():
            if s.id == target:
                return s
        return backend_stream_for(self.backend_language)

    def all_tasks(self) -> list[Task]:
        return [t for s in self.stories for t in s.tasks]

    def task(self, task_id: str) -> Task:
        for t in self.all_tasks():
            if t.id == task_id:
                return t
        raise KeyError(task_id)
