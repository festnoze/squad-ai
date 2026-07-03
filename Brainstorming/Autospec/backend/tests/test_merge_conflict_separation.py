"""Séparation inter-stream après un « conflit de merge inter-stream » :
le conflit NOMME les fichiers en cause (diagnostic), recale les claims de
l'item sur les fichiers RÉELLEMENT touchés (apprentissage), re-planifie le
retry en mode strict (pas de co-run avec un rival possible) et émet une leçon
de dimensionnement injectée dans le prochain plan S1 (§6). Côté prompts, le
dev reçoit son PÉRIMÈTRE FICHIERS et le cerveau de découpe réserve les
fichiers partagés à une tâche d'intégration dédiée."""

from pathlib import Path

from autospec.agents import prompts
from autospec.agents.runner import FakeRunner
from autospec.models import Epic, ProjectState, StoryStatus, Stream, StreamKind, Task, UserStory
from autospec.orchestrator import independence
from autospec.orchestrator import streams as work_streams
from autospec.orchestrator.pipeline import Pipeline, _file_in_scope
from autospec.storage import workspace_dir


def _state() -> ProjectState:
    st = ProjectState(id="sep-proj", name="sep", goal="g")
    st.epics.append(Epic(id="EPIC-1", title="E"))
    return st


def _task_item(tid: str, stream: str = "backend") -> work_streams.WorkItem:
    return work_streams.WorkItem(
        id=tid, kind="task", story_id="US-1", stream=stream,
        title=tid, status=StoryStatus.TODO, depends_on=(),
    )


def _pipeline_with_task(files_hint=("pkg/a.py",)):
    state = _state()
    task = Task(
        id="T-1", story_id="US-1", stream="backend", title="Tâche A",
        files_hint=list(files_hint),
    )
    state.stories = [
        UserStory(id="US-1", epic_id="EPIC-1", title="S", tasks=[task])
    ]
    return Pipeline(state, FakeRunner([])), task


# ------------------------------------------------- _register_merge_conflict

def test_conflict_names_files_and_recalibrates_claims():
    pipeline, task = _pipeline_with_task()
    item = _task_item("T-1")

    pipeline._register_merge_conflict(
        item, task, conflict_files=["main.py"], touched=["pkg/a.py", "main.py"]
    )

    # 1. Diagnostic : l'erreur nomme les fichiers (fini l'erreur opaque).
    assert "main.py" in task.last_error
    assert task.last_error.startswith("conflit de merge inter-stream sur")
    # 2. Recalage : le footprint observé rejoint les claims déclarés.
    assert task.files_hint == ["pkg/a.py", "main.py"]
    # 3. Retry strict + leçon §6.
    assert "T-1" in pipeline._conflict_retry_ids
    assert any(
        "conflit de merge" in l and "main.py" in l
        for l in pipeline.state.sizing_lessons
    )


def test_conflict_on_taskless_story_is_safe_without_files_hint():
    state = _state()
    story = UserStory(id="US-1", epic_id="EPIC-1", title="S")
    state.stories = [story]
    pipeline = Pipeline(state, FakeRunner([]))
    item = work_streams.WorkItem(
        id="US-1", kind="story", story_id="US-1", stream="backend",
        title="S", status=StoryStatus.TODO, depends_on=(),
    )

    pipeline._register_merge_conflict(item, story, ["F.txt"], ["F.txt"])

    assert "F.txt" in story.last_error       # UserStory has no files_hint: no crash
    assert "US-1" in pipeline._conflict_retry_ids


def test_conflict_lesson_reaches_the_next_s1_prompt():
    pipeline, task = _pipeline_with_task()
    pipeline._register_merge_conflict(_task_item("T-1"), task, ["main.py"], [])
    p = prompts.po_structure(pipeline.state, "pkg")
    assert "LEÇONS DE DIMENSIONNEMENT" in p and "conflit de merge" in p


def test_recalibrated_claims_now_block_a_declared_rival():
    """La chaîne déterministe : avant le conflit, le rival déclarant main.py ne
    chevauche PAS les claims de T-1 ; après recalage il chevauche — la garde du
    scheduler (declared_overlap) et le floor le sérialisent donc au retry."""
    pipeline, task = _pipeline_with_task(files_hint=("pkg/a.py",))
    rival = independence.TaskClaim(id="T-2", stream="frontend", file_globs=("main.py",))

    before = independence.TaskClaim(id="T-1", stream="backend", file_globs=tuple(task.files_hint))
    assert independence.declared_overlap(before, rival) is False

    pipeline._register_merge_conflict(_task_item("T-1"), task, ["main.py"], ["main.py"])
    after = independence.TaskClaim(id="T-1", stream="backend", file_globs=tuple(task.files_hint))
    assert independence.declared_overlap(after, rival) is True


def test_strict_retry_holds_back_against_undeclared_same_stream_rival():
    """Le mode strict du retry utilise claims_overlap : un rival du MÊME stream
    SANS claims déclarés reste un rival possible (l'ancien mode declared_overlap
    l'aurait laissé co-runner et re-conflicter)."""
    retried = independence.TaskClaim(id="T-1", stream="backend", file_globs=("main.py",))
    undeclared_rival = independence.TaskClaim(id="T-3", stream="backend", file_globs=())
    assert independence.declared_overlap(retried, undeclared_rival) is False  # ancien garde
    assert independence.claims_overlap(retried, undeclared_rival) is True    # garde strict


# --------------------------------------------------------- prompts (proactif)

def test_file_scope_block_lists_globs_and_shared_files_rule():
    block = prompts.file_scope_block(["pkg/a.py", "tests/test_a.py"])
    assert "PÉRIMÈTRE FICHIERS" in block
    assert "`pkg/a.py`" in block and "`tests/test_a.py`" in block
    assert "CONFLIT DE MERGE" in block
    assert "tâche d'intégration" in block
    # Repli sur la zone du stream quand rien n'est déclaré.
    zone = prompts.file_scope_block([], stream_zone="frontend")
    assert "`frontend/`" in zone
    # Aucun périmètre connu → pas de bloc (ne pas contraindre à l'aveugle).
    assert prompts.file_scope_block([]) == ""


def test_dev_prompts_carry_the_file_scope():
    story = UserStory(id="US-1", epic_id="E1", title="S")
    scope = prompts.file_scope_block(["pkg/a.py"])
    assert "PÉRIMÈTRE FICHIERS" in prompts.dev_story(
        story, "pkg", "f.feature", file_scope=scope
    )
    assert "PÉRIMÈTRE FICHIERS" in prompts.dev_story_frontend(
        story, "pkg", "f.feature", file_scope=scope
    )
    assert "PÉRIMÈTRE FICHIERS" in prompts.dev_story(
        story, "pkg", "f.feature", backend_language="go", file_scope=scope
    )
    # Sans périmètre : prompts inchangés (octet-identiques au legacy).
    assert "PÉRIMÈTRE FICHIERS" not in prompts.dev_story(story, "pkg", "f.feature")


def test_shared_brain_reserves_shared_files_to_an_integration_task(monkeypatch):
    from autospec.config import settings

    rules = prompts.sizing_rules()
    assert "FICHIERS PARTAGÉS" in rules and "INTÉGRATION" in rules
    # La règle irrigue le plan multi-stream legacy aussi.
    monkeypatch.setattr(settings, "streams_enabled", True)
    block = prompts._streams_plan_block(_state())
    assert "FICHIERS PARTAGÉS" in block and "INTÉGRATION" in block
    assert "INTER-stream" in block


# ------------------------------------------- gate de périmètre pré-merge

def test_file_in_scope_predicate():
    globs = ["pkg/domain/*.py", "pkg/api/"]
    # Globs déclarés (fichier + sous-arbre d'un glob-répertoire).
    assert _file_in_scope("pkg/domain/todo.py", globs, "")
    assert _file_in_scope("pkg/api/router.py", globs, "")
    # Zone du stream.
    assert _file_in_scope("frontend/src/X.tsx", [], "frontend")
    # Collatéral légitime de tout dev : tests, features, fichiers .test colocalisés.
    assert _file_in_scope("tests/steps/test_us_1.py", globs, "")
    assert _file_in_scope("features/us_1.feature", globs, "")
    assert _file_in_scope("frontend/src/X.test.tsx", [], "other")
    # Hors périmètre : fichiers partagés et zones d'autres unités.
    assert not _file_in_scope("main.py", globs, "")
    assert not _file_in_scope("pyproject.toml", globs, "")
    assert not _file_in_scope("frontend/src/App.tsx", globs, "")
    assert not _file_in_scope("pkg/other/x.py", globs, "")


def _scope_state(pid: str) -> ProjectState:
    st = ProjectState(id=pid, name="scope", goal="g")
    st.epics.append(Epic(id="EPIC-1", title="E"))
    st.streams = [
        Stream(id="backend", kind=StreamKind.BACKEND, language="python", primary=True)
    ]
    task = Task(
        id="T-1", story_id="US-1", stream="backend", title="Tâche A",
        files_hint=["pkg/a.py"],
    )
    st.stories = [UserStory(id="US-1", epic_id="EPIC-1", title="S", tasks=[task])]
    return st


async def _scope_harness(tmp_path, monkeypatch, pid: str):
    """Un repo réel + une branche d'item qui modifie pkg/a.py (dans le périmètre)
    ET main.py (hors périmètre). Retourne (pipeline, ws, worktree, task)."""
    from autospec.agents.scripted import ScriptedRunner

    monkeypatch.setattr("autospec.config.settings.workspace_root", tmp_path)
    state = _scope_state(pid)
    pipeline = Pipeline(state, ScriptedRunner())
    ws = workspace_dir(pid)
    ws.mkdir(parents=True, exist_ok=True)
    assert await pipeline._agit_ensure_repo(ws)
    (ws / "pkg").mkdir()
    (ws / "pkg" / "a.py").write_text("base\n", encoding="utf-8")
    (ws / "main.py").write_text("entry\n", encoding="utf-8")
    await pipeline._agit(ws, "add", "-A")
    await pipeline._agit(ws, "commit", "-m", "base")
    worktree = await pipeline._aworktree_add(ws, "autospec/wi-t-1")
    assert worktree is not None
    (Path(worktree) / "pkg" / "a.py").write_text("changed\n", encoding="utf-8")
    (Path(worktree) / "main.py").write_text("entry + wiring\n", encoding="utf-8")
    await pipeline._acommit_story(worktree, "T-1")
    return pipeline, ws, worktree, state.stories[0].tasks[0]


async def test_scope_gate_reverts_harmless_out_of_scope_edits(tmp_path, monkeypatch):
    pipeline, ws, worktree, task = await _scope_harness(tmp_path, monkeypatch, "sg-ok")

    async def _green(ws=None):
        return True, "", {}

    monkeypatch.setattr(pipeline, "_arun_pytest", _green)
    item = _task_item("T-1")
    await pipeline._aenforce_file_scope(
        item, pipeline.state.stories[0], task, ws, worktree, "autospec/wi-t-1", False
    )

    # La graine de conflit (main.py) a été RETIRÉE de la branche avant merge…
    touched = await pipeline._abranch_files(ws, "autospec/wi-t-1")
    assert "main.py" not in touched and "pkg/a.py" in touched
    # …et la modification hors périmètre n'atteindra jamais HEAD.
    assert (Path(worktree) / "main.py").read_text(encoding="utf-8") == "entry\n"
    assert pipeline.state.calibration_for().scope_violations == 1
    assert any("débordé de son périmètre" in l for l in pipeline.state.sizing_lessons)
    assert task.files_hint == ["pkg/a.py"]         # claims inchangés : ils sont vrais


async def test_scope_gate_keeps_and_declares_load_bearing_edits(tmp_path, monkeypatch):
    pipeline, ws, worktree, task = await _scope_harness(tmp_path, monkeypatch, "sg-red")

    async def _red(ws=None):
        return False, "boom", {}

    monkeypatch.setattr(pipeline, "_arun_pytest", _red)
    await pipeline._aenforce_file_scope(
        _task_item("T-1"), pipeline.state.stories[0], task, ws, worktree,
        "autospec/wi-t-1", False,
    )

    # Modification porteuse : conservée sur la branche…
    assert (Path(worktree) / "main.py").read_text(encoding="utf-8") == "entry + wiring\n"
    touched = await pipeline._abranch_files(ws, "autospec/wi-t-1")
    assert "main.py" in touched
    # …mais DÉCLARÉE : la garde du scheduler sérialisera tout rival.
    assert "main.py" in task.files_hint
    assert pipeline.state.calibration_for().scope_violations == 1


async def test_scope_gate_is_a_noop_without_declared_scope(tmp_path, monkeypatch):
    pipeline, ws, worktree, task = await _scope_harness(tmp_path, monkeypatch, "sg-off")
    task.files_hint = []                            # plus de périmètre déclaré
    calls = []

    async def _spy(ws=None):
        calls.append(1)
        return True, "", {}

    monkeypatch.setattr(pipeline, "_arun_pytest", _spy)
    await pipeline._aenforce_file_scope(
        _task_item("T-1"), pipeline.state.stories[0], task, ws, worktree,
        "autospec/wi-t-1", False,
    )

    assert calls == []                              # pas de suite rejouée
    assert pipeline.state.calibration_for().scope_violations == 0
    touched = await pipeline._abranch_files(ws, "autospec/wi-t-1")
    assert "main.py" in touched                     # branche intacte


async def test_scope_gate_ignores_in_scope_work(tmp_path, monkeypatch):
    pipeline, ws, worktree, task = await _scope_harness(tmp_path, monkeypatch, "sg-in")
    # On retire la modification hors périmètre : plus rien à signaler.
    await pipeline._agit(worktree, "checkout", "HEAD~1", "--", "main.py")
    await pipeline._agit(worktree, "add", "-A")
    await pipeline._agit(worktree, "commit", "-m", "fix")
    calls = []

    async def _spy(ws=None):
        calls.append(1)
        return True, "", {}

    monkeypatch.setattr(pipeline, "_arun_pytest", _spy)
    await pipeline._aenforce_file_scope(
        _task_item("T-1"), pipeline.state.stories[0], task, ws, worktree,
        "autospec/wi-t-1", False,
    )
    assert calls == [] and pipeline.state.calibration_for().scope_violations == 0
