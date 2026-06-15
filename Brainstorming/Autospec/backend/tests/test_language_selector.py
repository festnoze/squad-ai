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


async def test_language_phase_uses_heuristic_when_selector_off(monkeypatch):
    monkeypatch.setattr(settings, "language_selector_enabled", False)
    state = ProjectState(id="lang-off", name="n", goal="Une application bancaire de paiement")
    pipeline = Pipeline(state, FakeRunner([]))
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
    monkeypatch.setattr(settings, "language_selector_enabled", False)
    state = ProjectState(id="lang-idem", name="n", goal="Un SaaS de gestion")
    pipeline = Pipeline(state, FakeRunner([]))
    await pipeline._aselect_language()
    assert state.backend_language == BackendLanguage.GO
    # Re-run must not re-analyze (already set).
    state.backend_language = BackendLanguage.RUST
    await pipeline._aselect_language()
    assert state.backend_language == BackendLanguage.RUST


def test_prompts_surface_non_python_language():
    # L2d: the chosen backend language is threaded into the QA/Dev prompts.
    from autospec.agents import prompts
    from autospec.models import UserStory

    story = UserStory(id="US-1", epic_id="E1", title="t", description="d", gherkin="Feature: f")
    dev_go = prompts.dev_story(story, "pkg", "features/us-1.feature", backend_language="go")
    qa_rust = prompts.qa_test_plan(story, "pkg", backend_language="rust")
    assert "Langage backend cible : go" in dev_go
    assert "Langage backend cible : rust" in qa_rust
    # Python (default) keeps the existing prompt unchanged (no extra note).
    assert "Langage backend cible" not in prompts.dev_story(
        story, "pkg", "features/us-1.feature"
    )
