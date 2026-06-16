"""L2a: deterministic backend-language recommender."""

from autospec.language_selector import recommend_language


def test_simple_low_criticality_goal_recommends_python():
    r = recommend_language("Une calculatrice de démonstration", "")
    assert r["language"] == "python"
    assert r["criticality"] <= 2 and r["complexity"] <= 2
    assert r["rationale"]


def test_critical_domain_recommends_rust():
    r = recommend_language("Une application bancaire de paiement avec gestion fiscale", "")
    assert r["language"] == "rust"
    assert r["criticality"] >= 4


def test_high_complexity_recommends_rust():
    r = recommend_language(
        "Un moteur temps réel distribué haute performance avec parsing crypto", ""
    )
    assert r["language"] == "rust"
    assert r["complexity"] >= 4


def test_generic_app_defaults_to_go():
    r = recommend_language("Un SaaS de gestion de tâches pour équipes", "")
    assert r["language"] == "go"


def test_scores_are_clamped_1_5():
    r = recommend_language(
        "banque paiement santé sécurité finance assurance trading bourse fiscal", ""
    )
    assert 1 <= r["criticality"] <= 5
    assert 1 <= r["complexity"] <= 5


def test_brief_text_is_considered():
    # No signal in the goal, but the brief reveals a critical domain.
    r = recommend_language("Une application", "Traitement de données médicales et santé")
    assert r["language"] == "rust"


# --- L2b: agent phase (env-gated) ------------------------------------------
import json

from autospec.agents.runner import FakeRunner
from autospec.config import settings
from autospec.models import BackendLanguage, ProjectState
from autospec.orchestrator.pipeline import Pipeline


async def test_language_phase_noop_when_selector_off(monkeypatch):
    # Selector OFF -> Python stays the safe default, no analysis (rétro-compat).
    monkeypatch.setattr(settings, "language_selector_enabled", False)
    state = ProjectState(id="lang-off", name="n", goal="Une application bancaire de paiement")
    pipeline = Pipeline(state, FakeRunner([]))
    await pipeline._aselect_language()
    assert state.backend_language == BackendLanguage.PYTHON
    assert state.language_complexity == -1


async def test_language_phase_heuristic_when_enabled_no_agent(monkeypatch):
    # Selector ON but the agent fails -> deterministic heuristic (critical -> rust).
    monkeypatch.setattr(settings, "language_selector_enabled", True)
    state = ProjectState(id="lang-heur", name="n", goal="Une application bancaire de paiement")
    pipeline = Pipeline(state, FakeRunner([]))  # no reply -> AgentError -> heuristic
    await pipeline._aselect_language()
    assert state.backend_language == BackendLanguage.RUST
    assert state.language_criticality >= 4
    assert state.language_rationale


async def test_language_phase_agent_overrides_heuristic(monkeypatch):
    monkeypatch.setattr(settings, "language_selector_enabled", True)
    # Heuristic alone would say python (calculatrice) ; the agent says rust.
    state = ProjectState(id="lang-agent", name="n", goal="Une calculatrice")
    reply = json.dumps(
        {"language": "rust", "complexity": 5, "criticality": 5, "rationale": "choix agent"}
    )
    pipeline = Pipeline(state, FakeRunner([reply]))
    await pipeline._aselect_language()
    assert state.backend_language == BackendLanguage.RUST
    assert state.language_rationale == "choix agent"


async def test_language_phase_falls_back_on_agent_error(monkeypatch):
    monkeypatch.setattr(settings, "language_selector_enabled", True)
    state = ProjectState(id="lang-fb", name="n", goal="Une calculatrice de démo")
    pipeline = Pipeline(state, FakeRunner([]))  # no reply -> AgentError -> heuristic
    await pipeline._aselect_language()
    assert state.backend_language == BackendLanguage.PYTHON


async def test_language_phase_idempotent(monkeypatch):
    monkeypatch.setattr(settings, "language_selector_enabled", True)
    state = ProjectState(id="lang-idem", name="n", goal="Un SaaS de gestion")
    pipeline = Pipeline(state, FakeRunner([]))  # agent fails -> heuristic -> go
    await pipeline._aselect_language()
    assert state.backend_language == BackendLanguage.GO
    # Re-run must not re-analyze (already set).
    state.backend_language = BackendLanguage.RUST
    await pipeline._aselect_language()
    assert state.backend_language == BackendLanguage.RUST


def test_prompts_are_language_specific():
    # L2d/L2g-4: QA/Dev prompts adapt to the backend language.
    from autospec.agents import prompts
    from autospec.models import UserStory

    story = UserStory(id="US-1", epic_id="E1", title="t", description="d", gherkin="Feature: f")

    # Python (default): pytest flow, no native Go/Rust markers.
    dev_py = prompts.dev_story(story, "pkg", "features/us-1.feature")
    assert "uv run pytest" in dev_py
    assert "pytest-bdd" in dev_py
    assert "go test" not in dev_py and "cargo test" not in dev_py

    # Go: native prompt (go test, testing package, no pytest step defs).
    dev_go = prompts.dev_story(story, "pkg", "features/us-1.feature", backend_language="go")
    assert "go test ./..." in dev_go
    assert "PROCESSUS OBLIGATOIRE" in dev_go  # recognised by the scripted runner
    assert "pytest" not in dev_go

    # Rust: native prompt (cargo test).
    dev_rust = prompts.dev_story(story, "pkg", "features/us-1.feature", backend_language="rust")
    assert "cargo test" in dev_rust
    assert "pytest" not in dev_rust

    # QA plan surfaces the target test command too.
    assert "cargo test" in prompts.qa_test_plan(story, "pkg", backend_language="rust")
    assert "go test" in prompts.qa_test_plan(story, "pkg", backend_language="go")
