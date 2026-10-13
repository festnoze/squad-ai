import pytest

from autospec.models import BackendLanguage, ProjectState
from autospec.orchestrator import stack


def test_sealed_stack_survives_resume_without_reparsing_new_prose():
    state = ProjectState(id="sealed", name="app", goal="API Python et frontend React avec SQLite")
    state.technical_stack = stack.freeze(stack.resolve(state), rationale="Choix validé")
    original = dict(state.technical_stack)
    state.brief += "\nUne vue client ; comparaison avec Django et PostgreSQL dans les travaux futurs."
    assert stack.resolve(state) == original
    assert original["rationale"] == "Choix validé"


def test_sealed_stack_cannot_be_mutated_into_another_scaffold():
    state = ProjectState(id="sealed", name="app", goal="API Python")
    state.technical_stack = stack.freeze(stack.resolve(state))
    state.technical_stack["backend"] = "rust"
    with pytest.raises(ValueError, match="modifiée"):
        stack.resolve(state)


def test_architect_does_not_override_explicit_backend_in_brief():
    state = ProjectState(id="contradiction", name="app", goal="Backend Python, frontend React",
                         technical_stack={"backend": "rust"})
    with pytest.raises(ValueError, match="contradictoires"):
        stack.resolve(state)


def test_unknown_frozen_version_is_not_silently_accepted():
    state = ProjectState(id="version", name="app", goal="API Python")
    state.technical_stack = stack.freeze(stack.resolve(state))
    state.technical_stack["version"] = "99"
    with pytest.raises(ValueError, match="version"):
        stack.resolve(state)


def test_two_required_backends_fail_before_scaffold():
    state = ProjectState(id="conflict", name="app", goal="Backend Python obligatoire. Backend Rust obligatoire.")
    with pytest.raises(ValueError, match="contradictoires"):
        stack.resolve(state)


def test_comparison_is_not_a_mandatory_second_backend():
    state = ProjectState(id="choice", name="app", goal="Comparer Python ou Rust pour le backend",
                         technical_stack={"backend": "python"})
    assert stack.resolve(state)["backend"] == "python"


def test_unrelated_or_in_brief_does_not_hide_stack_conflict():
    state = ProjectState(id="conflict-filter", name="app", goal="Backend en Python et backend en Rust. Filtrer les tickets par nom ou tags.")
    with pytest.raises(ValueError, match="contradictoires"):
        stack.resolve(state)


def test_node_toolchain_is_not_a_second_required_backend():
    state = ProjectState(id="node-tools", name="app", goal="API en Python, React construit avec Node.js", technical_stack={"backend": "python"})
    assert stack.resolve(state)["backend"] == "python"


@pytest.mark.parametrize("language", ["go", "rust"])
def test_explicit_unqualified_backend_fails_during_stack_resolution(language):
    state = ProjectState(id=f"explicit-{language}", name="app", goal=f"API backend en {language}")
    with pytest.raises(ValueError, match="initialisation complète.*Aucune substitution automatique"):
        stack.resolve(state)


@pytest.mark.parametrize("language", ["go", "rust"])
def test_context_recommendation_is_clamped_to_a_complete_initialization_stack(language):
    state = ProjectState(
        id=f"inferred-{language}", name="app", goal="Service web",
        backend_language=BackendLanguage(language), product_profile="api",
    )
    decision = stack.resolve(state)
    assert decision["backend"] == "python"
    assert decision["framework"] == "fastapi"
    assert decision["source"] == "inferred"


@pytest.mark.parametrize("language,framework", [("go", "net/http"), ("rust", "axum")])
def test_persisted_inferred_unsupported_stack_falls_back_as_one_decision(language, framework):
    state = ProjectState(
        id=f"persisted-{language}", name="app", goal="Service web",
        technical_stack={
            "kind": "api", "backend": language, "framework": framework,
            "frontend": "none", "database": "none", "source": "inferred",
        },
    )
    decision = stack.resolve(state)
    assert (decision["backend"], decision["framework"], decision["source"]) == (
        "python", "fastapi", "inferred",
    )


@pytest.mark.parametrize("language,framework", [("go", "net/http"), ("rust", "axum")])
def test_frozen_inferred_unsupported_stack_migrates_as_one_decision(language, framework):
    decision = stack.freeze({
        "kind": "api", "backend": language, "framework": framework,
        "frontend": "none", "database": "none", "source": "inferred",
    })
    state = ProjectState(
        id=f"frozen-inferred-{language}", name="app", goal="Service web",
        technical_stack=decision,
    )
    resolved = stack.resolve(state)
    assert (resolved["backend"], resolved["framework"], resolved["source"]) == (
        "python", "fastapi", "inferred",
    )


@pytest.mark.parametrize("language", ["go", "rust"])
def test_explicit_unsupported_backend_is_detected_before_spec_analysis(language):
    state = ProjectState(id=f"early-{language}", name="app", goal=f"API en {language}")
    assert stack.explicit_unsupported_initial_backend(state) == language
    state.backend_language = BackendLanguage(language)
    state.goal = "Service web"
    assert stack.explicit_unsupported_initial_backend(state) == ""
