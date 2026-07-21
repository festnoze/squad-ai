"""Fixes issus du run supervisé « recettes » du 2026-07-20 (DEFECTS_RESOLUTION_PLAN.md).

Couvre les fixes déterministes hors gate : le .gitignore du scaffold ignore les
bases SQLite (D6), le marqueur d'infra « pipe refusé » du daemon Docker (PRE-1),
et le parseur des échecs de merge pré-conflit (D8).
"""

from __future__ import annotations

from autospec.orchestrator import docker_deploy, workspace
from autospec.orchestrator.pipeline import _parse_overwritten_files


# ------------------------------------------------------------------ D6 gitignore

def test_gitignore_template_ignores_sqlite_artifacts():
    """Un artefact SQLite créé par les tests (recipes.db) ne doit JAMAIS être
    commitable : traqué, il a cassé 3 merges du run supervisé (conflit binaire,
    modify/delete, « local changes would be overwritten »)."""
    for pattern in ("*.db", "*.sqlite", "*.sqlite3"):
        assert pattern in workspace.GITIGNORE_TEMPLATE


# ------------------------------------------------- PRE-1 marqueur pipe refusé

def test_docker_pipe_permission_denied_is_infra():
    out = (
        "permission denied while trying to connect to the docker API at "
        "npipe:////./pipe/dockerDesktopLinuxEngine"
    )
    assert docker_deploy.looks_like_daemon_down(out) is True
    assert any(m in out for m in docker_deploy.DOCKER_INFRA_MARKERS)


# ------------------------------------------------------- D8 parseur pré-merge

def test_parse_overwritten_files_local_changes_form():
    out = (
        "error: Your local changes to the following files would be overwritten by merge:\n"
        "\trecipes.db\n"
        "\tdata/cache.db\n"
        "Please commit your changes or stash them before you merge.\n"
        "Aborting\n"
        "Merge with strategy ort failed.\n"
    )
    assert _parse_overwritten_files(out) == ["recipes.db", "data/cache.db"]


def test_parse_overwritten_files_untracked_form():
    out = (
        "error: The following untracked working tree files would be overwritten by merge:\n"
        "\trecipes.db\n"
        "Please move or remove them before you merge.\n"
        "Aborting\n"
    )
    assert _parse_overwritten_files(out) == ["recipes.db"]


def test_parse_overwritten_files_ignores_regular_conflict_output():
    out = (
        "Auto-merging recettes/service.py\n"
        "CONFLICT (content): Merge conflict in recettes/service.py\n"
        "Automatic merge failed; fix conflicts and then commit the result.\n"
    )
    assert _parse_overwritten_files(out) == []


def test_parse_overwritten_files_empty_output():
    assert _parse_overwritten_files("") == []


# ------------------------------------------------- P1 traçabilité qualifiée

def test_traceability_qualified_ids_match_dotted_markers():
    """Les ids qualifiés par story (US-1.AC-2) évitent la déduplication globale
    des ids génériques (AC-1..AC-4 réutilisés par toutes les stories) qui
    réduisait le rapport à 4 critères déclarés sur ~35."""
    from autospec.orchestrator import traceability

    declared = {"US-1.AC-1", "US-1.AC-2", "US-2.AC-1"}
    sources = {
        "tests/unit/test_a.py": "# AC: US-1.AC-1, US-1.AC-2\ndef test_a():\n    pass\n",
        "frontend/src/App.test.tsx": "// AC: US-2.AC-1\nit('x', () => {})\n",
    }
    report = traceability.coverage_report(declared, sources)
    assert report["covered"] == ["US-1.AC-1", "US-1.AC-2", "US-2.AC-1"]
    assert report["uncovered"] == []
    assert report["orphans"] == []


def test_collect_frontend_test_sources_reads_vitest_files(tmp_path):
    from autospec.orchestrator.pipeline import Pipeline

    src = tmp_path / "frontend" / "src" / "features"
    src.mkdir(parents=True)
    (src / "Liste.test.tsx").write_text("// AC: US-5.AC-1\nit('ok', () => {})\n", encoding="utf-8")
    (src / "Liste.tsx").write_text("export const x = 1\n", encoding="utf-8")
    out = Pipeline._collect_frontend_test_sources(tmp_path)
    assert list(out.keys()) == ["frontend/src/features/Liste.test.tsx"]
    assert "US-5.AC-1" in out["frontend/src/features/Liste.test.tsx"]


# --------------------------------------------- P7 contexte anti-duplication

def test_existing_plan_block_lists_other_stories_tasks():
    from autospec.agents.runner import FakeRunner
    from autospec.models import ProjectState, Task, UserStory
    from autospec.orchestrator.pipeline import Pipeline

    state = ProjectState(id="p-dedup", name="app", goal="g")
    ts = UserStory(id="TS-1", epic_id="E", title="Socle")
    ts.tasks = [
        Task(id="TS-1-T1", story_id="TS-1", stream="backend", title="Entités ORM",
             files_hint=["app/orm.py", "app/db.py"]),
    ]
    us = UserStory(id="US-1", epic_id="E", title="CRUD")
    state.stories = [ts, us]
    pipeline = Pipeline(state, FakeRunner())

    block = pipeline._existing_plan_block(us)
    assert "TS-1-T1" in block and "app/orm.py" in block
    # La story en cours de décomposition n'apparaît pas dans son propre contexte.
    assert pipeline._existing_plan_block(ts) == ""


def test_decompose_prompt_embeds_existing_plan():
    from autospec.agents import prompts
    from autospec.models import UserStory

    story = UserStory(id="US-1", epic_id="E", title="CRUD")
    p = prompts.decompose_story(story, "app", existing_plan="- TS-1-T1 (TS-1) : Entités ORM")
    assert "MODULES DÉJÀ PLANIFIÉS" in p and "TS-1-T1" in p
    # Sans contexte, le prompt reste identique à l'historique (pas de bloc vide).
    assert "MODULES DÉJÀ PLANIFIÉS" not in prompts.decompose_story(story, "app")
