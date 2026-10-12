"""A verified foundation must not be turned back into pending scaffold work."""

import pytest

from autospec.agents import prompts
from autospec.config import settings
from autospec.models import BackendLanguage, ProjectState, UserStory


def foundation_state(**overrides):
    return ProjectState(
        id="verified-foundation", name="demo", goal="Un endpoint hello et son écran",
        brief="Un endpoint hello et un petit écran React qui affiche la réponse.",
        **{
            "bootstrap_status": "ready",
            "technical_stack": {"kind": "fullstack", "backend": "python", "framework": "fastapi", "frontend": "react", "database": "none"},
            **overrides,
        },
    )


def story():
    return UserStory(id="US-1", epic_id="EPIC-1", title="Afficher hello")


@pytest.mark.parametrize("build", [
    lambda state: prompts.architect_design(state, "demo"),
    lambda state: prompts.po_plan(state, "demo"),
    lambda state: prompts.po_structure(state, "demo"),
    lambda state: prompts.structure_criteria(state),
    lambda state: prompts.po_cross_review([], state=state),
    lambda state: prompts.decompose_story(story(), "demo", state=state),
    lambda state: prompts.decompose_finer(story(), "demo", state=state),
    lambda state: prompts.po_spec_story(state, {"id": "US-1"}, "demo", merged=True),
])
def test_planning_and_critics_do_not_recreate_verified_foundation(monkeypatch, build):
    monkeypatch.setattr(settings, "streams_enabled", True)
    prompt = build(foundation_state())
    assert "SOCLE TECHNIQUE DÉJÀ VÉRIFIÉ" in prompt
    assert "Ne planifie AUCUNE story/tâche d'amorçage" in prompt
    assert "MAXIMUM 2 stories" in prompt
    assert "register(app)" in prompt
    assert "AMORÇAGE WEB" not in prompt
    assert "porte TOUJOURS une tâche" not in prompt
    assert "l'ajoute d'office" not in prompt
    assert "uvicorn.run(" not in prompt


@pytest.mark.parametrize("overrides", [
    {"bootstrap_status": ""},
    {"bootstrap_status": "preparing"},
    {"bootstrap_status": "failed"},
    {"technical_stack": {}},
])
def test_legacy_startup_requirements_remain_without_verified_contract(monkeypatch, overrides):
    monkeypatch.setattr(settings, "streams_enabled", True)
    state = foundation_state(**overrides)
    for prompt in [prompts.po_plan(state, "demo"), prompts.po_structure(state, "demo"), prompts.decompose_story(story(), "demo", state=state)]:
        assert "AMORÇAGE WEB" in prompt
        assert "SOCLE TECHNIQUE DÉJÀ VÉRIFIÉ" not in prompt


def test_structure_does_not_claim_verified_repository_is_absent():
    prompt = prompts.po_structure(foundation_state(), "demo")
    assert "le repo existe déjà" in prompt
    assert "le repo n'existe pas encore" not in prompt


def test_dev_adds_fastapi_routes_to_existing_application():
    state = foundation_state()
    prompt = prompts.dev_story(story(), "demo", "features/hello.feature", state=state)
    assert "def register(app):" in prompt
    assert "app` est l'instance FastAPI existante" in prompt
    assert "Préserve le serveur, la factory" in prompt
    assert "exposant `register()`" not in prompt
    assert "uvicorn.run(" not in prompt
    scope = prompts.file_scope_block(["demo/features/hello.py"], state=state)
    assert "fonction `register(app)`" in scope


def test_legacy_dev_wiring_contract_is_preserved():
    prompt = prompts.dev_story(story(), "demo", "features/hello.feature")
    assert "exposant `register()`" in prompt
    assert "SI TA TÂCHE PORTE `main.py` DANS SON PÉRIMÈTRE" in prompt


@pytest.mark.parametrize("builder", [prompts.dev_fix_deploy, prompts.dev_fix_integration])
def test_repair_verifies_native_backend_and_frontend_suites(builder):
    prompt = builder("demo", "failure report")
    assert "Lis les manifests présents" in prompt
    for manifest, command in [("pyproject.toml", "uv run pytest"), ("go.mod", "go test ./..."), ("Cargo.toml", "cargo test"), ("package.json", "npm test")]:
        assert manifest in prompt and command in prompt
    assert "ses tests et son build depuis son propre répertoire" in prompt
    assert "N'exécute pas une commande Python sur un projet sans Python" in prompt
    assert "toute la suite `uv run pytest` doit RESTER verte" not in prompt


def test_frontend_only_contract_does_not_add_python_backend():
    state = foundation_state(technical_stack={"kind": "frontend", "backend": "none", "frontend": "react", "database": "none"})
    prompt = prompts.architect_design(state, "demo")
    assert "aucun backend ni projet Python à ajouter" in prompt
    assert "Un frontend-only reste autonome" in prompt
    assert "register(app)" not in prompt


def test_node_dev_and_refinement_keep_native_entrypoint_and_tests():
    state = foundation_state(backend_language=BackendLanguage.NODE, technical_stack={"kind": "api", "backend": "node", "frontend": "none", "database": "none"})
    prompt = prompts.dev_story(story(), "demo", "features/hello.feature", backend_language="node", state=state)
    assert "point d'entrée (main.js)" in prompt
    assert "src/main.rs" not in prompt
    refined = prompts.dev_revise(story(), "demo", "features/hello.feature", "clarify response", state=state)
    assert "node --test" in refined
    assert "répertoire courant, qui est un projet Python" not in refined
    scope = prompts.file_scope_block(["main.js"], state=state)
    assert "CÂBLAGE NATIF" in scope
    assert "features/<feature>.py" not in scope
