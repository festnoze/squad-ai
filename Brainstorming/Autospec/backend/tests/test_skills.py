"""SK-1: skill registry, prompt catalog, workspace seeding, runner wiring."""

from __future__ import annotations

import json

import pytest

from autospec.agents import prompts, runner as runner_mod
from autospec.agents.runner import ClaudeCliRunner
from autospec.config import settings
from autospec.models import AcceptanceCriterion, ProjectState, UserStory
from autospec.orchestrator import skill_validation, skills as skill_lib
from autospec.orchestrator.pipeline import Pipeline


def _story() -> UserStory:
    return UserStory(
        id="US-1", epic_id="E1", title="Additionner", description="somme",
        acceptance_criteria=[AcceptanceCriterion(id="AC-1", text="2+3=5")],
        gherkin="Feature: F\n  Scenario: S\n    Given 2\n    When +3\n    Then 5",
    )


# ---------------------------------------------------------------- config helper

def test_skills_for_requires_master_and_role(monkeypatch):
    monkeypatch.setattr(settings, "skills_enabled", False)
    monkeypatch.setattr(settings, "skills_qa", True)
    assert settings.skills_for("qa") is False           # master off
    monkeypatch.setattr(settings, "skills_enabled", True)
    monkeypatch.setattr(settings, "skills_dev", False)
    assert settings.skills_for("qa") is True
    assert settings.skills_for("dev") is False           # role off


# ---------------------------------------------------------------- catalog block

def test_catalog_block_is_role_scoped():
    qa = skill_lib.catalog_block("qa")
    dev = skill_lib.catalog_block("dev")
    assert "obligatoires quand applicables" in qa
    assert "OBLIGATOIRE" in dev
    assert "`bdd-gherkin`" in qa and "`test-generator`" in qa
    assert "`bdd-gherkin`" not in dev                     # qa-only skill
    assert "`db-entity-change`" in dev and "`endpoint-search-or-create`" in dev
    # Every registry name targeting a role appears in that role's block.
    for s in skill_lib.SKILL_REGISTRY:
        if "qa" in s["roles"]:
            assert f"`{s['name']}`" in qa


def test_pipeline_skills_catalog_gated(monkeypatch):
    state = ProjectState(id="p", name="n", goal="g")
    pipe = Pipeline(state, runner_mod.FakeRunner([]))
    monkeypatch.setattr(settings, "skills_enabled", False)
    assert pipe._skills_catalog("qa") == ""
    monkeypatch.setattr(settings, "skills_enabled", True)
    monkeypatch.setattr(settings, "skills_qa", True)
    assert "COMPÉTENCES DISPONIBLES" in pipe._skills_catalog("qa")


# ---------------------------------------------------------------- prompt injection

def test_qa_and_dev_prompts_inject_skills_only_when_provided():
    story = _story()
    catalog = skill_lib.catalog_block("qa")
    with_skills = prompts.qa_test_plan(story, "pkg", available_skills=catalog)
    without = prompts.qa_test_plan(story, "pkg")
    assert "COMPÉTENCES DISPONIBLES" in with_skills
    assert "COMPÉTENCES DISPONIBLES" not in without       # byte-identical opt-out

    dev_with = prompts.dev_story(story, "pkg", "f.feature",
                                 available_skills=skill_lib.catalog_block("dev"))
    dev_without = prompts.dev_story(story, "pkg", "f.feature")
    assert "`db-entity-change`" in dev_with
    assert "COMPÉTENCES DISPONIBLES" not in dev_without


# ---------------------------------------------------------------- seeding

def test_seed_skills_copies_library_and_is_idempotent(tmp_path):
    ws = tmp_path / "ws"
    ws.mkdir()
    written = skill_lib.seed_skills(ws)
    assert written > 0
    seeded = ws / ".claude" / "skills"
    # Every registry skill landed as a SKILL.md, plus the rules file.
    for s in skill_lib.SKILL_REGISTRY:
        assert (seeded / s["name"] / "SKILL.md").is_file()
    assert (seeded / "skill-rules.json").is_file()
    # rules JSON is valid and lists the same skills.
    rules = json.loads((seeded / "skill-rules.json").read_text(encoding="utf-8"))
    assert set(rules["skills"]) == {s["name"] for s in skill_lib.SKILL_REGISTRY}
    assert all(
        rule["enforcement"] == "required_when_applicable"
        for name, rule in rules["skills"].items()
        if name != "skill-creator"
    )
    assert skill_validation.validate_seeded_skills(ws).ok is True
    # Second run writes nothing (idempotent).
    assert skill_lib.seed_skills(ws) == 0


def test_seed_skills_missing_source_is_noop(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "skills_dir", tmp_path / "does-not-exist")
    assert skill_lib.seed_skills(tmp_path / "ws") == 0


def test_skill_validation_blocks_missing_or_weak_library(tmp_path):
    ws = tmp_path / "ws"
    ws.mkdir()
    missing = skill_validation.validate_seeded_skills(ws)
    assert missing.ok is False
    assert any(i.code == "missing_skills_dir" for i in missing.blockers)

    seeded = ws / ".claude" / "skills"
    (seeded / "architecture").mkdir(parents=True)
    (seeded / "architecture" / "SKILL.md").write_text("# Architecture", encoding="utf-8")
    (seeded / "skill-rules.json").write_text(
        json.dumps({"skills": {"architecture": {"enforcement": "suggest"}}}),
        encoding="utf-8",
    )
    weak = skill_validation.validate_seeded_skills(ws)
    assert weak.ok is False
    assert any(i.code == "weak_enforcement" for i in weak.blockers)


# ---------------------------------------------------------------- runner --add-dir

@pytest.mark.asyncio
async def test_claude_runner_adds_skills_dir_when_enabled(tmp_path, monkeypatch):
    captured: dict = {}

    def _fake_run_tracked(args, input_text, cwd, timeout):
        captured["args"] = args
        return 0, json.dumps({"result": "ok", "session_id": "s"}), ""

    monkeypatch.setattr(runner_mod, "_run_tracked", _fake_run_tracked)
    ws = tmp_path / "ws"
    (ws / ".claude" / "skills").mkdir(parents=True)

    monkeypatch.setattr(settings, "skills_enabled", True)
    await ClaudeCliRunner().arun("p", "sys", cwd=ws)
    assert "--add-dir" in captured["args"]
    assert str(ws / ".claude" / "skills") in captured["args"]

    monkeypatch.setattr(settings, "skills_enabled", False)
    await ClaudeCliRunner().arun("p", "sys", cwd=ws)
    assert "--add-dir" not in captured["args"]            # off → no grant
