"""Product profiles: validated bundles of factory flags."""

import pytest

from autospec.config import settings
from autospec.models import ProjectState
from autospec.orchestrator import profiles
from autospec.orchestrator.pipeline import Pipeline
from autospec.agents.runner import FakeRunner


def test_profile_normalization_and_unknown():
    assert profiles.normalize_name("lib") == "library-fast"
    assert profiles.normalize_name("full-stack") == "fullstack"
    assert profiles.normalize_name("", brownfield_path="C:/repo") == "brownfield"
    with pytest.raises(ValueError):
        profiles.normalize_name("mobile-native")


def test_library_fast_profile_disables_runtime_gates(monkeypatch):
    monkeypatch.setattr(settings, "smoke_run", True)
    monkeypatch.setattr(settings, "runtime_acceptance_enabled", True)
    state = ProjectState(id="p-prof-lib", name="n", goal="g", product_profile="library")
    applied = profiles.apply_to_settings(state)
    assert state.product_profile == "library-fast"
    assert applied["smoke_run"] is False
    assert settings.smoke_run is True
    assert settings.runtime_acceptance_enabled is True


def test_fullstack_profile_enables_streams_and_runtime(monkeypatch):
    monkeypatch.setattr(settings, "streams_enabled", False)
    monkeypatch.setattr(settings, "runtime_acceptance_enabled", False)
    state = ProjectState(id="p-prof-full", name="n", goal="g", product_profile="fullstack")
    overrides = profiles.apply_to_settings(state)
    assert overrides["streams_enabled"] is True
    assert overrides["runtime_acceptance_enabled"] is True
    assert overrides["ui_tests_enabled"] is True
    assert settings.streams_enabled is False
    assert settings.runtime_acceptance_enabled is False


def test_profile_resolution_is_per_project_not_global(monkeypatch):
    monkeypatch.setattr(settings, "streams_enabled", False)
    full = ProjectState(id="p-prof-full", name="n", goal="g", product_profile="fullstack")
    auto = ProjectState(id="p-prof-auto", name="n", goal="g", product_profile="auto")

    full_overrides = profiles.resolve_overrides(full)
    auto_overrides = profiles.resolve_overrides(auto)

    assert full_overrides["streams_enabled"] is True
    assert auto_overrides == {}
    assert settings.streams_enabled is False


def test_pipeline_carries_profile_overrides_without_global_mutation(monkeypatch):
    monkeypatch.setattr(settings, "streams_enabled", False)
    state = ProjectState(id="p-prof-pipeline", name="n", goal="g", product_profile="fullstack")
    pipeline = Pipeline(state, FakeRunner([]))

    assert pipeline._setting("streams_enabled") is True
    assert pipeline._setting("runtime_acceptance_enabled") is True
    assert settings.streams_enabled is False
