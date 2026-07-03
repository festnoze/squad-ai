"""PO pipeline (RFC po-pipeline-v2): the multi-stage planning pipeline.

S1 structure + complexity (sequential: deterministic checks each round, then ONE
critic-first structure review) → deterministic post-S1 gate on the MEASURED
skeleton size (small project → S2+S3 merged into one pass per story) → S2 spec
fan-out per STORY (schema + referential validation, 1 auto-repair retry, resize
verdicts) → resize barrier (deterministic, one bounded turn, the §5 common
splitting brain) → ONE transversal critic (inter-node defects only) → targeted
re-makes → S3 gherkin fan-out (deterministic AC alignment, LLM critic reserved
for `complex` stories, mechanical fallback derived from the ACs) → merge into a
legacy-shaped plan dict consumed by ``pipeline._aplan_phase``.

Degradation semantics (§ Merge & dégradation): a story whose S2 failed after
repair gets ONE mono-pass attempt (merged spec+gherkin on that single node);
if that fails too it keeps its skeleton, flagged ``spec_incomplete``. A story
whose S3 failed keeps its ACs and receives a MECHANICAL gherkin (one skeleton
scenario per criterion) — never empty. A stage exception never abandons the
plan: the best artifact continues, every degradation is logged AND counted.
"""

from __future__ import annotations

import asyncio
import fnmatch
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from pydantic import BaseModel, Field, ValidationError, field_validator

from ..agents import prompts
from ..agents.personas import persona
from ..agents.runner import AgentError, AgentRunner, extract_json
from ..config import settings
from ..models import AcceptanceCriterion, ProjectState, StreamKind, UserStory
from . import independence, refine

LogFn = Callable[[str, str], None]

COMPLEXITIES = ("trivial", "standard", "complex")
AC_KINDS = ("happy", "error", "edge", "nonfunctional")
RESIZE_VERDICTS = ("ok", "split", "merge")

_LOG_SRC = "po-pipeline"


class PlanPipelineError(Exception):
    """S1 could not produce a valid skeleton: the caller falls back to the
    legacy mono-pass PO (a stage exception never abandons the plan)."""


# ------------------------------------------------------------ stage artifacts

def _coerce_complexity(v: str) -> str:
    v = str(v or "").strip().lower()
    return v if v in COMPLEXITIES else "standard"


class S1Task(BaseModel):
    id: str
    title: str = ""
    stream: str = ""
    depends_on: list[str] = Field(default_factory=list)
    complexity: str = "standard"
    rationale: str = ""
    estimated_files: int = 1
    file_globs: list[str] = Field(default_factory=list)
    area: str = ""

    @field_validator("complexity")
    @classmethod
    def _cx(cls, v: str) -> str:
        return _coerce_complexity(v)


class S1Story(BaseModel):
    id: str
    title: str = ""
    depends_on: list[str] = Field(default_factory=list)
    priority: int = 3
    ui: bool = False
    stream: str = ""
    complexity: str = "standard"
    rationale: str = ""
    estimated_files: int = 1
    file_globs: list[str] = Field(default_factory=list)
    area: str = ""
    tasks: list[S1Task] = Field(default_factory=list)

    @field_validator("complexity")
    @classmethod
    def _cx(cls, v: str) -> str:
        return _coerce_complexity(v)

    @field_validator("priority")
    @classmethod
    def _prio(cls, v: int) -> int:
        return max(1, min(5, v))


class S1Epic(BaseModel):
    id: str
    title: str = ""
    description: str = ""
    stories: list[S1Story] = Field(default_factory=list)


class S1Skeleton(BaseModel):
    epics: list[S1Epic] = Field(default_factory=list)

    def stories(self) -> list[S1Story]:
        return [s for e in self.epics for s in e.stories]

    def leaves(self) -> list[tuple[S1Story, S1Task | None]]:
        """The schedulable leaves: every task of a decomposed story, or the
        (taskless) story itself. This measured count drives the post-S1 gate."""
        out: list[tuple[S1Story, S1Task | None]] = []
        for story in self.stories():
            if story.tasks:
                out.extend((story, t) for t in story.tasks)
            else:
                out.append((story, None))
        return out


class S2Criterion(BaseModel):
    id: str
    text: str = ""
    kind: str = ""


class S2TaskSpec(BaseModel):
    id: str
    description: str = ""
    acceptance_criteria: list[S2Criterion] = Field(default_factory=list)


class S2Resize(BaseModel):
    verdict: str = "ok"
    proposal: str = ""


class S2StorySpec(BaseModel):
    id: str
    description: str = ""
    acceptance_criteria: list[S2Criterion] = Field(default_factory=list)
    tasks: list[S2TaskSpec] = Field(default_factory=list)
    resize: S2Resize = Field(default_factory=S2Resize)
    gherkin: str = ""  # merged (small-project) mode only


class S3Gherkin(BaseModel):
    id: str
    gherkin: str = ""


@dataclass
class PlanPipelineReport:
    """What happened, for logging + the §6 calibration counters."""

    mode: str = "full"                  # "full" | "merged"
    leaves: int = 0
    resizes: list[str] = field(default_factory=list)       # "US-1: split …"
    flagged: list[str] = field(default_factory=list)        # cross-critic re-makes
    cross_issues: list[str] = field(default_factory=list)
    degradations: list[str] = field(default_factory=list)   # "S2:US-1 — reason"
    warnings: list[str] = field(default_factory=list)


# ------------------------------------------------------ deterministic checks

def _detect_cycle(edges: dict[str, list[str]]) -> list[str] | None:
    """Three-colour DFS over ``edges`` (id -> dependency ids). Returns a cycle
    as an id list, else None. Unknown targets are ignored (checked separately)."""
    WHITE, GREY, BLACK = 0, 1, 2
    colour = {k: WHITE for k in edges}
    stack: list[str] = []

    def visit(node: str) -> list[str] | None:
        colour[node] = GREY
        stack.append(node)
        for dep in edges.get(node, []):
            if dep not in colour:
                continue
            if colour[dep] == GREY:
                return stack[stack.index(dep):] + [dep]
            if colour[dep] == WHITE:
                found = visit(dep)
                if found:
                    return found
        colour[node] = BLACK
        stack.pop()
        return None

    for node in edges:
        if colour[node] == WHITE:
            found = visit(node)
            if found:
                return found
    return None


_ROOT_GLOBS = {"**", "**/*", "*", "**/**"}


def validate_skeleton(
    skel: S1Skeleton,
    *,
    existing_story_ids: set[str] | None = None,
    repo_files: list[str] | None = None,
    budget: int | None = None,
    stream_roots: dict[str, str] | None = None,
) -> tuple[list[str], list[str]]:
    """S1 deterministic gate (blocks acceptance): id/uniqueness + referential
    integrity, acyclic DAG, per-leaf file budget, `complex` leaves must be
    decomposed, real-repo glob confrontation (iteration ≥ 2), zone/stream
    coherence of the globs (``stream_roots``), plus catch-all heuristics.
    Returns ``(errors, warnings)`` — errors block, warnings are injected/logged."""
    errors: list[str] = []
    warnings: list[str] = []
    budget = settings.task_file_budget if budget is None else budget
    existing = existing_story_ids or set()

    stories = skel.stories()
    if not stories:
        errors.append("le squelette ne contient aucune user story")
        return errors, warnings

    seen: set[str] = set()
    for e in skel.epics:
        if e.id in seen:
            errors.append(f"id dupliqué : {e.id}")
        seen.add(e.id)
    story_ids: set[str] = set()
    task_ids: set[str] = set()
    for s in stories:
        if s.id in seen:
            errors.append(f"id dupliqué : {s.id}")
        seen.add(s.id)
        story_ids.add(s.id)
        for t in s.tasks:
            if t.id in seen:
                errors.append(f"id dupliqué : {t.id}")
            seen.add(t.id)
            task_ids.add(t.id)

    # Referential integrity: story deps -> stories (this plan or existing);
    # task deps -> tasks of this plan.
    for s in stories:
        for dep in s.depends_on:
            if dep not in story_ids and dep not in existing:
                errors.append(f"{s.id} : dépendance inconnue « {dep} »")
        for t in s.tasks:
            for dep in t.depends_on:
                if dep not in task_ids:
                    errors.append(f"{t.id} : dépendance de tâche inconnue « {dep} »")

    # Acyclic DAG (stories and tasks are two disjoint edge families).
    story_cycle = _detect_cycle({s.id: list(s.depends_on) for s in stories})
    if story_cycle:
        errors.append("cycle de dépendances entre stories : " + " → ".join(story_cycle))
    task_cycle = _detect_cycle(
        {t.id: list(t.depends_on) for s in stories for t in s.tasks}
    )
    if task_cycle:
        errors.append("cycle de dépendances entre tâches : " + " → ".join(task_cycle))

    # Per-leaf complexity judgment checks.
    for story, task in skel.leaves():
        leaf = task if task is not None else story
        if leaf.estimated_files > budget:
            errors.append(
                f"{leaf.id} : estimated_files={leaf.estimated_files} dépasse le "
                f"budget de {budget} fichiers par feuille — découper"
            )
        if task is None and story.complexity == "complex":
            errors.append(
                f"{story.id} : story `complex` sans découpe en tâches — refusée "
                "(découpe-la en tâches plus petites)"
            )
        if task is not None and task.complexity == "complex":
            errors.append(
                f"{task.id} : tâche `complex` — une feuille doit être au plus "
                "`standard` (re-découpe la story)"
            )

    # Iteration ≥ 2: globs are confronted with the REAL file tree.
    if repo_files is not None:
        for story, task in skel.leaves():
            leaf = task if task is not None else story
            if not leaf.file_globs:
                errors.append(
                    f"{leaf.id} : `file_globs` obligatoire (le repo existe) — "
                    "déclare les fichiers/zones touchés"
                )
                continue
            for g in leaf.file_globs:
                g_norm = str(g).strip().replace("\\", "/")
                if g_norm in _ROOT_GLOBS or g_norm.startswith("**"):
                    errors.append(
                        f"{leaf.id} : glob trop large « {g} » (racine) — refusé"
                    )
                elif repo_files and not any(
                    fnmatch.fnmatch(f, g_norm) for f in repo_files
                ):
                    warnings.append(
                        f"{leaf.id} : le glob « {g} » ne matche aucun fichier du "
                        "repo (fichier nouveau ? vérifie le chemin)"
                    )

    # Zone/stream coherence: a glob outside its stream's file_root (or inside
    # ANOTHER stream's root for a root-zoned stream) is a future inter-stream
    # merge conflict — refused at PLAN time, where fixing costs one repair.
    if stream_roots:
        claims = []
        for story, task in skel.leaves():
            leaf = task if task is not None else story
            stream_id = (task.stream if task is not None else story.stream) or ""
            if leaf.file_globs:
                claims.append(
                    independence.TaskClaim(
                        id=leaf.id, stream=stream_id, file_globs=tuple(leaf.file_globs)
                    )
                )
        errors.extend(independence.zone_mismatches(claims, stream_roots))

    # Catch-all heuristics (fourre-tout).
    for s in stories:
        if len(s.tasks) > 6:
            warnings.append(
                f"{s.id} : {len(s.tasks)} tâches sous une seule US — probable "
                "fourre-tout, envisager un second epic/US"
            )
        title = f" {s.title.lower()} "
        if title.count(" et ") >= 2:
            warnings.append(
                f"{s.id} : le titre enchaîne plusieurs responsabilités "
                f"(« {s.title} ») — une seule intention par story"
            )

    return errors, warnings


def validate_story_spec(
    spec: S2StorySpec, skeleton_story: S1Story, *, merged: bool = False
) -> list[str]:
    """S2 deterministic gate, per story: referential integrity against the
    skeleton, unique AC ids, valid taxonomy, minimal happy+error coverage."""
    errors: list[str] = []
    if spec.id != skeleton_story.id:
        errors.append(
            f"id de story « {spec.id} » ≠ « {skeleton_story.id} » (le squelette)"
        )
    if not spec.description.strip():
        errors.append("description vide")
    if not spec.acceptance_criteria:
        errors.append("aucun critère d'acceptance")
    ac_ids: set[str] = set()
    kinds: set[str] = set()
    for c in spec.acceptance_criteria:
        if c.id in ac_ids:
            errors.append(f"id de critère dupliqué : {c.id}")
        ac_ids.add(c.id)
        if not c.text.strip():
            errors.append(f"{c.id} : texte de critère vide")
        if c.kind not in AC_KINDS:
            errors.append(
                f"{c.id} : kind « {c.kind} » invalide (attendu : {', '.join(AC_KINDS)})"
            )
        kinds.add(c.kind)
    if spec.acceptance_criteria and "happy" not in kinds:
        errors.append("couverture minimale : aucun critère « happy »")
    if spec.acceptance_criteria and "error" not in kinds:
        errors.append("couverture minimale : aucun critère « error »")
    skel_task_ids = [t.id for t in skeleton_story.tasks]
    spec_task_ids = [t.id for t in spec.tasks]
    for tid in spec_task_ids:
        if tid not in skel_task_ids:
            errors.append(f"tâche inconnue du squelette : {tid}")
    for tid in skel_task_ids:
        if tid not in spec_task_ids:
            errors.append(f"tâche du squelette sans mini-spec : {tid}")
    for t in spec.tasks:
        if not t.description.strip():
            errors.append(f"{t.id} : description de tâche vide")
        t_ids: set[str] = set()
        for c in t.acceptance_criteria:
            if c.id in t_ids:
                errors.append(f"{t.id} : id de critère dupliqué {c.id}")
            t_ids.add(c.id)
            if c.kind not in AC_KINDS:
                errors.append(f"{t.id}/{c.id} : kind « {c.kind} » invalide")
    if spec.resize.verdict not in RESIZE_VERDICTS:
        errors.append(
            f"resize.verdict « {spec.resize.verdict} » invalide "
            f"(attendu : {', '.join(RESIZE_VERDICTS)})"
        )
    if merged:
        errors.extend(
            validate_gherkin(
                spec.gherkin, [c.id for c in spec.acceptance_criteria],
                ui=skeleton_story.ui,
            )
        )
    return errors


_SCENARIO_RE = re.compile(r"^\s*Scenario(?: Outline)?\s*:", re.MULTILINE)
_AC_TAG_RE = re.compile(r"@(AC-[\w.]+)")
_UI_STEP_RES = (
    re.compile(r"\bje clique\b", re.IGNORECASE),
    re.compile(r"\bcliqu\w*\b", re.IGNORECASE),
    re.compile(r"à l'écran", re.IGNORECASE),
    re.compile(r"\bnavigateur\b", re.IGNORECASE),
    re.compile(r"https?://", re.IGNORECASE),
)


def validate_gherkin(gherkin: str, ac_ids: list[str], *, ui: bool = False) -> list[str]:
    """S3 deterministic gate: Feature/Scenario structure, strict 1-for-1
    scenario ↔ AC alignment via @AC-x tags, and a regex hunt for forbidden
    UI/network steps in non-UI stories."""
    errors: list[str] = []
    text = gherkin or ""
    if "Feature:" not in text:
        errors.append("gherkin : mot-clé `Feature:` absent")
    scenarios = _SCENARIO_RE.findall(text)
    if not scenarios:
        errors.append("gherkin : aucun `Scenario:`")
    tags = _AC_TAG_RE.findall(text)
    expected = list(ac_ids)
    if sorted(tags) != sorted(expected):
        errors.append(
            "gherkin : alignement scénario↔critère rompu — tags trouvés "
            f"[{', '.join(tags) or '∅'}], attendus exactement [{', '.join(expected)}] "
            "(un tag @AC-x par scénario)"
        )
    elif len(scenarios) != len(expected):
        errors.append(
            f"gherkin : {len(scenarios)} scénario(s) pour {len(expected)} critère(s) "
            "— exactement un scénario par critère"
        )
    if not ui:
        for rx in _UI_STEP_RES:
            m = rx.search(text)
            if m:
                errors.append(
                    f"gherkin : step UI/réseau interdit pour une story non-UI "
                    f"(« {m.group(0)} ») — teste des fonctions/classes Python"
                )
                break
    return errors


def fallback_gherkin(story_id: str, title: str, criteria: list[S2Criterion]) -> str:
    """§ dégradation : a MECHANICAL gherkin derived from the ACs (one skeleton
    scenario per criterion) — never empty, downstream QA always has a base."""
    lines = [f"Feature: {title or story_id}"]
    items = criteria or [S2Criterion(id="AC-1", text=title or story_id, kind="happy")]
    for c in items:
        lines += [
            f"  @{c.id}",
            f"  Scenario: {c.text or c.id}",
            f"    Given le contexte du critère {c.id}",
            "    When le comportement est exercé",
            f"    Then {c.text or 'le critère est vérifié'}",
        ]
    return "\n".join(lines)


def _stream_roots(state: ProjectState) -> dict[str, str] | None:
    """Stream id → file_root, for the zone/stream coherence check. ``""``
    (unspecified stream) resolves to the primary stream's root. None when the
    project has no declared streams — nothing to check."""
    if not (settings.streams_enabled or state.streams):
        return None
    roots = {
        s.id: (s.file_root or ("frontend" if s.kind == StreamKind.FRONTEND else ""))
        for s in state.effective_streams()
    }
    roots[""] = roots.get(state.primary_stream_id, "")
    return roots


def repo_file_tree(root: Path, limit: int = 400) -> list[str]:
    """The generated repo's file listing (workspace-relative, posix separators)
    used to confront the S1 file_globs with reality from iteration 2 on."""
    skip_parts = {".git", ".venv", "node_modules", "__pycache__", ".pytest_cache", "dist"}
    out: list[str] = []
    try:
        for p in sorted(root.rglob("*")):
            if not p.is_file():
                continue
            rel = p.relative_to(root)
            if any(part in skip_parts for part in rel.parts):
                continue
            out.append(rel.as_posix())
            if len(out) >= limit:
                break
    except OSError:
        return []
    return out


# --------------------------------------------------- maker + 1-retry repair

ParseFn = Callable[[str], tuple[Any, list[str]]]


async def amake_validated(
    runner: AgentRunner,
    *,
    prompt: str,
    system_prompt: str,
    parse: ParseFn,
) -> tuple[Any, str]:
    """Run a maker once, validate deterministically, and on failure re-prompt
    ONCE with the validation error (§ auto-repair). Returns ``(artifact, "")``
    or ``(None, last_error)`` — the caller decides the degradation."""
    try:
        res = await runner.arun(prompt, system_prompt=system_prompt)
    except AgentError as exc:
        return None, f"appel agent en échec : {exc}"
    obj, errors = parse(res.text)
    if obj is not None and not errors:
        return obj, ""
    error_text = "\n".join(f"- {e}" for e in errors) or "- réponse inexploitable"
    try:
        res2 = await runner.arun(
            prompts.repair_reply(prompt, res.text, error_text),
            system_prompt=system_prompt,
        )
    except AgentError as exc:
        return None, f"réparation en échec : {exc}"
    obj2, errors2 = parse(res2.text)
    if obj2 is not None and not errors2:
        return obj2, ""
    return None, "; ".join(errors2 or errors)


def _parse_model(model_cls, validate: Callable[[Any], list[str]] | None = None) -> ParseFn:
    """Build a ParseFn: extract_json → pydantic → optional deterministic checks."""

    def _parse(text: str) -> tuple[Any, list[str]]:
        try:
            data = extract_json(text)
        except AgentError as exc:
            return None, [f"JSON illisible : {exc}"]
        try:
            obj = model_cls.model_validate(data)
        except ValidationError as exc:
            return None, [
                f"schéma invalide : {err['loc']} — {err['msg']}"
                for err in exc.errors()[:8]
            ]
        errors = validate(obj) if validate is not None else []
        return (obj, errors) if not errors else (obj, errors)

    return _parse


# ------------------------------------------------------------------ stage S1

async def _arun_s1(
    runner: AgentRunner,
    state: ProjectState,
    pkg: str,
    *,
    repo_files: list[str] | None,
    log: LogFn,
    report: PlanPipelineReport,
) -> S1Skeleton:
    """S1: maker + deterministic validation (1 repair retry), then ONE
    critic-first structure review whose every revision is re-validated
    deterministically (a revision that breaks the contract is rejected)."""
    existing_ids = {s.id for s in state.stories}
    stream_roots = _stream_roots(state)

    def _validate(skel: S1Skeleton) -> list[str]:
        errors, warnings = validate_skeleton(
            skel,
            existing_story_ids=existing_ids,
            repo_files=repo_files,
            stream_roots=stream_roots,
        )
        for w in warnings:
            if w not in report.warnings:
                report.warnings.append(w)
        return errors

    parse = _parse_model(S1Skeleton, _validate)
    prompt = prompts.po_structure(state, pkg, repo_files)
    skeleton, error = await amake_validated(
        runner, prompt=prompt, system_prompt=persona("po-structure"), parse=parse
    )
    if skeleton is None:
        raise PlanPipelineError(f"S1 : squelette invalide après réparation — {error}")

    # Critic-first structure review (no opening judge; a failed critic call is
    # distinguished from a satisfied critic and logged as such).
    accepted: dict[str, S1Skeleton] = {"current": skeleton}

    async def _revise(previous: str, critique: str) -> str:
        res = await runner.arun(
            prompts.repair_reply(
                prompt, previous, f"(revue du critique structure)\n{critique}"
            ),
            system_prompt=persona("po-structure"),
        )
        return res.text

    async def _accept(revised: str) -> bool:
        obj, errors = parse(revised)
        if obj is None or errors:
            return False
        accepted["current"] = obj
        return True

    outcome = await refine.arefine_critic_first(
        runner,
        kind="le squelette du plan (epics, stories, tâches, complexité)",
        criteria=prompts.structure_criteria(),
        initial_text=skeleton.model_dump_json(),
        revise=_revise,
        accept=_accept,
    )
    if outcome.stopped_reason == "critic_error":
        log(_LOG_SRC, "S1 : critique structure INDISPONIBLE (échec d'appel) — squelette conservé tel quel.")
    else:
        log(
            _LOG_SRC,
            f"S1 : revue structure en {outcome.rounds} tour(s) "
            f"(arrêt : {outcome.stopped_reason}).",
        )
    return accepted["current"]


# ------------------------------------------------------------------ stage S2

async def _aspec_story(
    runner: AgentRunner,
    state: ProjectState,
    story: S1Story,
    pkg: str,
    *,
    merged: bool,
    remake_reason: str = "",
) -> tuple[S2StorySpec | None, str]:
    parse = _parse_model(
        S2StorySpec, lambda spec: validate_story_spec(spec, story, merged=merged)
    )
    prompt = prompts.po_spec_story(
        state, story.model_dump(), pkg, merged=merged, remake_reason=remake_reason
    )
    spec, error = await amake_validated(
        runner, prompt=prompt, system_prompt=persona("po-spec"), parse=parse
    )
    return spec, error  # type: ignore[return-value]


async def _adegrade_story(
    runner: AgentRunner,
    state: ProjectState,
    story: S1Story,
    pkg: str,
    *,
    log: LogFn,
    report: PlanPipelineReport,
    reason: str,
) -> S2StorySpec:
    """S2 degradation: ONE mono-pass attempt on this single node (merged
    spec+gherkin); failing that, the skeleton survives flagged
    ``spec_incomplete`` with a mechanical gherkin — never an empty artifact."""
    report.degradations.append(f"S2:{story.id} — {reason}")
    log(_LOG_SRC, f"S2 : spec de {story.id} en échec ({reason}) — repli mono-passe sur ce nœud.")
    spec, error = await _aspec_story(runner, state, story, pkg, merged=True)
    if spec is not None:
        return spec
    log(_LOG_SRC, f"S2 : mono-passe de {story.id} aussi en échec ({error}) — squelette conservé, marqué spec_incomplete.")
    report.degradations.append(f"S2-mono:{story.id} — {error}")
    fallback = S2StorySpec(
        id=story.id,
        description=story.title,
        acceptance_criteria=[
            S2Criterion(id="AC-1", text=story.title or story.id, kind="happy")
        ],
        tasks=[S2TaskSpec(id=t.id, description=t.title) for t in story.tasks],
        gherkin=fallback_gherkin(story.id, story.title, []),
    )
    return fallback


def _spec_is_fallback(spec: S2StorySpec, report: PlanPipelineReport) -> bool:
    return any(d.startswith(f"S2-mono:{spec.id} ") for d in report.degradations)


# ------------------------------------------------------- resize barrier (S2)

def _remap_split_tasks(story: S1Story, raw: list[dict]) -> list[S1Task]:
    """Materialize the common brain's split reply into skeleton tasks with
    story-scoped unique ids and remapped intra-split dependencies."""
    id_map: dict[str, str] = {}
    for i, data in enumerate(raw, start=1):
        old = str(data.get("id") or f"R-{i}")
        id_map[old] = f"{story.id}-R{i}"
    out: list[S1Task] = []
    for i, data in enumerate(raw, start=1):
        old = str(data.get("id") or f"R-{i}")
        globs = [str(g) for g in (data.get("file_globs") or []) if str(g).strip()]
        out.append(
            S1Task(
                id=id_map[old],
                title=str(data.get("title") or old),
                stream=str(data.get("stream") or story.stream or ""),
                depends_on=[id_map[d] for d in (data.get("depends_on") or []) if d in id_map],
                complexity="standard",
                rationale="issue du re-dimensionnement S2 (resize:split)",
                estimated_files=max(1, len(globs)) if globs else 1,
                file_globs=globs,
                area=str(data.get("area") or ""),
            )
        )
    return out


async def _aapply_resize(
    runner: AgentRunner,
    state: ProjectState,
    skeleton: S1Skeleton,
    specs: dict[str, S2StorySpec],
    pkg: str,
    *,
    log: LogFn,
    report: PlanPipelineReport,
) -> None:
    """The resize barrier — deterministic application, bounded to ONE turn.
    ``split`` goes through the §5 common splitting brain (``decompose_finer``,
    proactive mode); ``merge`` is applied when two ADJACENT trivial stories of
    the same epic both ask for it. Resized nodes re-run S2 once; no 2nd turn."""
    to_respec: list[S1Story] = []

    # --- splits
    for epic in skeleton.epics:
        for story in epic.stories:
            spec = specs.get(story.id)
            if spec is None or spec.resize.verdict != "split":
                continue
            subject = UserStory(
                id=story.id,
                epic_id=epic.id,
                title=story.title,
                description=spec.description,
                acceptance_criteria=[
                    AcceptanceCriterion(id=c.id, text=c.text, kind=c.kind)
                    for c in spec.acceptance_criteria
                ],
                gherkin=spec.gherkin,
            )
            try:
                res = await runner.arun(
                    prompts.decompose_finer(
                        subject, pkg, reason=spec.resize.proposal, proactive=True
                    ),
                    system_prompt=persona("architect"),
                )
                reply = extract_json(res.text)
            except AgentError as exc:
                log(_LOG_SRC, f"Resize : découpe de {story.id} indisponible ({exc}) — spec conservée.")
                continue
            raw = [t for t in (reply.get("tasks") or []) if isinstance(t, dict)]
            if len(raw) < 2:
                log(_LOG_SRC, f"Resize : {story.id} jugée indivisible — spec conservée.")
                continue
            story.tasks = _remap_split_tasks(story, raw)
            report.resizes.append(
                f"{story.id}: split → {len(story.tasks)} tâches ({spec.resize.proposal})"
            )
            log(_LOG_SRC, f"Resize : {story.id} re-découpée en {len(story.tasks)} tâches (verdict du rédacteur S2).")
            to_respec.append(story)

    # --- merges: two ADJACENT trivial stories of the same epic, both asking.
    for epic in skeleton.epics:
        i = 0
        while i < len(epic.stories) - 1:
            a, b = epic.stories[i], epic.stories[i + 1]
            sa, sb = specs.get(a.id), specs.get(b.id)
            if (
                sa is not None and sb is not None
                and sa.resize.verdict == "merge" and sb.resize.verdict == "merge"
                and a.complexity == "trivial" and b.complexity == "trivial"
            ):
                a.title = f"{a.title} + {b.title}"
                a.depends_on = list(dict.fromkeys([*a.depends_on, *b.depends_on]))
                a.depends_on = [d for d in a.depends_on if d not in (a.id, b.id)]
                a.tasks = [*a.tasks, *b.tasks]
                a.estimated_files = min(
                    settings.task_file_budget, a.estimated_files + b.estimated_files
                )
                epic.stories.pop(i + 1)
                specs.pop(b.id, None)
                # Anything depending on the absorbed story now depends on the merged one.
                for other in skeleton.stories():
                    if b.id in other.depends_on:
                        other.depends_on = [
                            a.id if d == b.id else d for d in other.depends_on
                        ]
                        other.depends_on = list(dict.fromkeys(other.depends_on))
                report.resizes.append(f"{a.id}: merge ← {b.id}")
                log(_LOG_SRC, f"Resize : {b.id} fusionnée dans {a.id} (deux stories triviales adjacentes).")
                to_respec.append(a)
            i += 1

    # --- resized nodes go through S2 exactly once more.
    for story in to_respec:
        spec, error = await _aspec_story(runner, state, story, pkg, merged=False)
        if spec is None:
            specs[story.id] = await _adegrade_story(
                runner, state, story, pkg, log=log, report=report, reason=error
            )
        else:
            spec.resize = S2Resize()  # one turn only: further verdicts ignored
            specs[story.id] = spec


# ------------------------------------------------- transversal critic (S2)

async def _across_review(
    runner: AgentRunner,
    state: ProjectState,
    skeleton: S1Skeleton,
    specs: dict[str, S2StorySpec],
    pkg: str,
    *,
    log: LogFn,
    report: PlanPipelineReport,
) -> None:
    """ONE transversal critic over ALL the specs (compact form), hunting
    exclusively inter-node defects; flagged nodes get ONE targeted re-make.
    A failed critic call is logged as such — not treated as « satisfait »."""
    compact = [
        {
            "id": s.id,
            "title": next((st.title for st in skeleton.stories() if st.id == s.id), ""),
            "complexity": next(
                (st.complexity for st in skeleton.stories() if st.id == s.id), ""
            ),
            "description": s.description[:300],
            "criteria": [f"[{c.kind}] {c.text}" for c in s.acceptance_criteria],
            "tasks": [t.description[:120] for t in s.tasks],
        }
        for s in specs.values()
    ]
    try:
        res = await runner.arun(
            prompts.po_cross_review(compact), system_prompt=persona("critic")
        )
        reply = extract_json(res.text)
    except AgentError as exc:
        log(_LOG_SRC, f"S2 : critique transversal EN ÉCHEC ({exc}) — revue inter-stories sautée (distinct d'un critique satisfait).")
        return
    report.cross_issues = [str(i) for i in reply.get("issues") or []]
    flagged = [
        f for f in (reply.get("flagged") or [])
        if isinstance(f, dict) and str(f.get("id") or "") in specs
    ]
    if not flagged:
        log(_LOG_SRC, "S2 : critique transversal satisfait — aucune re-spécification.")
        return
    by_id = {s.id: s for s in skeleton.stories()}
    for f in flagged:
        sid = str(f.get("id"))
        reason = str(f.get("reason") or "défaut inter-stories signalé")
        story = by_id.get(sid)
        if story is None:
            continue
        report.flagged.append(f"{sid}: {reason}")
        log(_LOG_SRC, f"S2 : re-spécification ciblée de {sid} — {reason}")
        spec, error = await _aspec_story(
            runner, state, story, pkg, merged=False, remake_reason=reason
        )
        if spec is not None:
            spec.resize = S2Resize()  # the barrier already ran: verdicts ignored
            specs[sid] = spec
        else:
            log(_LOG_SRC, f"S2 : re-make de {sid} en échec ({error}) — spec précédente conservée.")


# ------------------------------------------------------------------ stage S3

async def _agherkin_story(
    runner: AgentRunner,
    story: S1Story,
    spec: S2StorySpec,
    pkg: str,
    *,
    log: LogFn,
    report: PlanPipelineReport,
) -> str:
    """S3 for one story: single-shot maker + deterministic validation (1 repair
    retry) + LLM critic reserved for `complex` stories; mechanical fallback."""
    ac_ids = [c.id for c in spec.acceptance_criteria]
    spec_payload = {
        "id": spec.id,
        "title": story.title,
        "description": spec.description,
        "acceptance_criteria": [c.model_dump() for c in spec.acceptance_criteria],
    }
    parse = _parse_model(
        S3Gherkin,
        lambda g: (
            [f"id « {g.id} » ≠ « {spec.id} »"] if g.id != spec.id else []
        ) + validate_gherkin(g.gherkin, ac_ids, ui=story.ui),
    )
    prompt = prompts.po_gherkin(spec_payload, pkg, ui=story.ui)
    artifact, error = await amake_validated(
        runner, prompt=prompt, system_prompt=persona("po-gherkin"), parse=parse
    )
    if artifact is None:
        report.degradations.append(f"S3:{spec.id} — {error}")
        log(_LOG_SRC, f"S3 : gherkin de {spec.id} en échec ({error}) — repli mécanique dérivé des critères.")
        return fallback_gherkin(spec.id, story.title, spec.acceptance_criteria)
    gherkin = artifact.gherkin

    # The S1 complexity field drives the effort: only `complex` stories get the
    # LLM executability critic; trivial|standard stop at the deterministic gate.
    if story.complexity == "complex":
        try:
            res = await runner.arun(
                prompts.critic_review(
                    f"le Gherkin d'acceptance de la story {spec.id}",
                    gherkin,
                    prompts.GHERKIN_CRITERIA,
                ),
                system_prompt=persona("critic"),
            )
            reply = extract_json(res.text)
        except AgentError as exc:
            log(_LOG_SRC, f"S3 : critique gherkin de {spec.id} en échec ({exc}) — version validée conservée.")
            return gherkin
        issues = [str(i) for i in reply.get("issues") or []]
        suggestions = [str(s) for s in reply.get("suggestions") or []]
        if issues or suggestions:
            critique = "\n".join(f"- {x}" for x in [*issues, *suggestions])
            remade, err2 = await amake_validated(
                runner,
                prompt=prompts.repair_reply(
                    prompt, gherkin, f"(revue du critique gherkin)\n{critique}"
                ),
                system_prompt=persona("po-gherkin"),
                parse=parse,
            )
            if remade is not None:
                return remade.gherkin
            log(_LOG_SRC, f"S3 : re-make gherkin de {spec.id} invalide ({err2}) — version validée conservée.")
    return gherkin


# ------------------------------------------------------------- orchestration

def _merge_plan(
    skeleton: S1Skeleton,
    specs: dict[str, S2StorySpec],
    gherkins: dict[str, str],
    report: PlanPipelineReport,
) -> dict:
    """Assemble the final legacy-shaped plan dict (the exact structure
    ``pipeline._aplan_phase`` materializes), enriched with the pipeline's
    first-order fields (AC kind, complexity, estimated_files, file_globs)."""
    epics_out = []
    for epic in skeleton.epics:
        stories_out = []
        for story in epic.stories:
            spec = specs.get(story.id) or S2StorySpec(id=story.id, description=story.title)
            spec_tasks = {t.id: t for t in spec.tasks}
            tasks_out = []
            for t in story.tasks:
                ts = spec_tasks.get(t.id)
                tasks_out.append(
                    {
                        "id": t.id,
                        "stream": t.stream,
                        "title": t.title,
                        "description": ts.description if ts else "",
                        "acceptance_criteria": [
                            c.model_dump() for c in (ts.acceptance_criteria if ts else [])
                        ],
                        "gherkin": "",
                        "file_globs": list(t.file_globs),
                        "depends_on": list(t.depends_on),
                        "complexity": t.complexity,
                        "estimated_files": t.estimated_files,
                    }
                )
            stories_out.append(
                {
                    "id": story.id,
                    "title": story.title,
                    "description": spec.description,
                    "acceptance_criteria": [
                        c.model_dump() for c in spec.acceptance_criteria
                    ],
                    "gherkin": gherkins.get(story.id, ""),
                    "depends_on": list(story.depends_on),
                    "priority": story.priority,
                    "ui": story.ui,
                    "stream": story.stream,
                    "tasks": tasks_out,
                    "complexity": story.complexity,
                    "estimated_files": story.estimated_files,
                    "spec_incomplete": _spec_is_fallback(spec, report),
                }
            )
        epics_out.append(
            {
                "id": epic.id,
                "title": epic.title,
                "description": epic.description,
                "stories": stories_out,
            }
        )
    return {"epics": epics_out}


async def arun_po_pipeline(
    runner: AgentRunner,
    state: ProjectState,
    pkg: str,
    *,
    workspace_root: Path | None = None,
    log: LogFn | None = None,
) -> tuple[dict, PlanPipelineReport]:
    """Run the full PO pipeline and return ``(plan_dict, report)``.

    ``plan_dict`` has the exact legacy ``po_plan`` shape (epics → stories →
    tasks) so the existing ``_aplan_phase`` materialization consumes it
    unchanged — enriched fields (AC ``kind``, ``complexity``…) ride along.
    Raises :class:`PlanPipelineError` only when S1 cannot produce a valid
    skeleton (the caller then falls back to the legacy mono-pass PO)."""
    log = log or (lambda _src, _line: None)
    report = PlanPipelineReport()

    repo_files: list[str] | None = None
    if state.iteration >= 2 and workspace_root is not None:
        tree = repo_file_tree(workspace_root)
        repo_files = tree if tree else None

    # ---- S1 : structure + complexity (sequential)
    skeleton = await _arun_s1(
        runner, state, pkg, repo_files=repo_files, log=log, report=report
    )
    report.leaves = len(skeleton.leaves())

    # ---- deterministic post-S1 gate on the MEASURED skeleton size
    merged_mode = report.leaves < settings.po_pipeline_min_leaves
    report.mode = "merged" if merged_mode else "full"
    log(
        _LOG_SRC,
        f"S1 : squelette accepté — {report.leaves} feuille(s) → mode "
        f"{'fusionné (S2+S3 en une passe/story)' if merged_mode else 'pipeline complet'}.",
    )

    # ---- S2 : spec fan-out per STORY (parallel)
    stories = skeleton.stories()
    results = await asyncio.gather(
        *(
            _aspec_story(runner, state, s, pkg, merged=merged_mode)
            for s in stories
        )
    )
    specs: dict[str, S2StorySpec] = {}
    for story, (spec, error) in zip(stories, results):
        if spec is None:
            spec = await _adegrade_story(
                runner, state, story, pkg, log=log, report=report, reason=error
            )
        specs[story.id] = spec

    if not merged_mode:
        # ---- resize barrier (deterministic, ONE bounded turn)
        await _aapply_resize(
            runner, state, skeleton, specs, pkg, log=log, report=report
        )
        # ---- ONE transversal critic + targeted re-makes
        await _across_review(
            runner, state, skeleton, specs, pkg, log=log, report=report
        )

    # ---- S3 : gherkin fan-out (unless merged — the S2 pass already wrote it)
    gherkins: dict[str, str] = {}
    by_id = {s.id: s for s in skeleton.stories()}
    if merged_mode:
        for sid, spec in specs.items():
            story = by_id[sid]
            gherkins[sid] = spec.gherkin or fallback_gherkin(
                sid, story.title, spec.acceptance_criteria
            )
    elif not settings.po_pipeline_gherkin:
        for sid, spec in specs.items():
            gherkins[sid] = fallback_gherkin(
                sid, by_id[sid].title, spec.acceptance_criteria
            )
        log(_LOG_SRC, "S3 coupé (AUTOSPEC_PO_PIPELINE_GHERKIN=0) — gherkin mécanique dérivé des critères.")
    else:
        ordered = [sid for sid in by_id if sid in specs]
        texts = await asyncio.gather(
            *(
                _agherkin_story(
                    runner, by_id[sid], specs[sid], pkg, log=log, report=report
                )
                for sid in ordered
            )
        )
        gherkins = dict(zip(ordered, texts))

    plan = _merge_plan(skeleton, specs, gherkins, report)
    if report.degradations:
        log(
            _LOG_SRC,
            f"{len(report.degradations)} dégradation(s) d'étape — comptées pour la calibration.",
        )
    return plan, report
