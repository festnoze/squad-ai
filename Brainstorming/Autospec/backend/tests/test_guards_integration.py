"""Wave 0.5 integration: the anti-cheating guard wiring + flaky-rerun in the
pipeline (the pure detectors themselves live in test_guards.py / test_signatures.py)."""

from __future__ import annotations

from pathlib import Path

from autospec.agents.runner import FakeRunner
from autospec.config import settings as cfg
from autospec.models import ProjectState, UserStory
from autospec.orchestrator import signatures, workspace
from autospec.orchestrator.pipeline import Pipeline


def _pipeline(pid):
    state = ProjectState(id=pid, name="g", goal="g")
    pipeline = Pipeline(state, FakeRunner([]))
    ws = Path(workspace.scaffold(state))
    return pipeline, ws


# --------------------------------------------------------------------------- #
# T05 — test tampering                                                         #
# --------------------------------------------------------------------------- #

async def test_tamper_strict_detects_and_reverts(monkeypatch):
    monkeypatch.setattr(cfg, "test_tamper_guard", "strict")
    pipeline, ws = _pipeline("p-tamper1")
    tdir = ws / "tests"
    tdir.mkdir(parents=True, exist_ok=True)
    tf = tdir / "test_feature.py"
    original = b"def test_ok():\n    assert real_impl() == 42\n"
    tf.write_bytes(original)

    before = pipeline._snapshot_test_files(ws)
    assert "tests/test_feature.py" in before

    # Dev "cheats": rewrites the test to pass trivially.
    tf.write_bytes(b"def test_ok():\n    assert True\n")

    story = UserStory(id="US-1", epic_id="E-1", title="feat")
    findings = await pipeline._arun_cheat_guards(story, ws, before)

    assert signatures.guard_signature(signatures.TAMPERED, "tests/test_feature.py") in findings
    # strict mode restored the QA-authored test verbatim
    assert tf.read_bytes() == original


async def test_tamper_warn_detects_without_revert(monkeypatch):
    monkeypatch.setattr(cfg, "test_tamper_guard", "warn")
    pipeline, ws = _pipeline("p-tamper2")
    tdir = ws / "tests"
    tdir.mkdir(parents=True, exist_ok=True)
    tf = tdir / "test_feature.py"
    tf.write_bytes(b"def test_ok():\n    assert real() == 1\n")
    before = pipeline._snapshot_test_files(ws)
    cheated = b"def test_ok():\n    assert True\n"
    tf.write_bytes(cheated)

    findings = await pipeline._arun_cheat_guards(UserStory(id="US-1", epic_id="E-1", title="x"), ws, before)
    assert any(signatures.TAMPERED in f for f in findings)
    assert tf.read_bytes() == cheated  # warn does NOT revert


async def test_tamper_off_is_noop(monkeypatch):
    monkeypatch.setattr(cfg, "test_tamper_guard", "off")
    pipeline, ws = _pipeline("p-tamper3")
    (ws / "tests").mkdir(parents=True, exist_ok=True)
    (ws / "tests" / "test_x.py").write_bytes(b"def test_x():\n    assert 1\n")
    before = pipeline._snapshot_test_files(ws)
    assert before == {}  # snapshot skipped when guard off
    findings = await pipeline._arun_cheat_guards(UserStory(id="US-1", epic_id="E-1", title="x"), ws, before)
    assert findings == []


# --------------------------------------------------------------------------- #
# T07 — skeleton implementation                                                #
# --------------------------------------------------------------------------- #

async def test_skeleton_guard_flags_pass_only(monkeypatch):
    monkeypatch.setattr(cfg, "skeleton_guard", "warn")
    pipeline, ws = _pipeline("p-skel")
    (ws / "app").mkdir(parents=True, exist_ok=True)
    (ws / "app" / "mod.py").write_text(
        "def compute():\n    pass\n", encoding="utf-8"
    )

    async def fake_changed(_ws):
        return ["app/mod.py"]

    monkeypatch.setattr(pipeline, "_achanged_paths", fake_changed)
    findings = await pipeline._arun_cheat_guards(UserStory(id="US-1", epic_id="E-1", title="x"), ws, {})
    assert any(f.startswith(f"guard:{signatures.SKELETON}") for f in findings)


# --------------------------------------------------------------------------- #
# T10 — hallucinated imports                                                   #
# --------------------------------------------------------------------------- #

async def test_import_guard_flags_hallucinated(monkeypatch):
    monkeypatch.setattr(cfg, "import_guard", "warn")
    pipeline, ws = _pipeline("p-imp")
    (ws / "pyproject.toml").write_text(
        '[project]\nname = "x"\ndependencies = ["fastapi>=0.1"]\n', encoding="utf-8"
    )
    (ws / "app").mkdir(parents=True, exist_ok=True)
    (ws / "app" / "mod.py").write_text(
        "import os\nimport fastapi\nimport leftpadpkg\n", encoding="utf-8"
    )

    async def fake_changed(_ws):
        return ["app/mod.py"]

    monkeypatch.setattr(pipeline, "_achanged_paths", fake_changed)
    findings = await pipeline._arun_cheat_guards(UserStory(id="US-1", epic_id="E-1", title="x"), ws, {})
    assert any("leftpadpkg" in f for f in findings)
    assert not any("fastapi" in f for f in findings)  # declared dep is fine
    assert not any("guard:unresolved_import:app/mod.py: os" in f for f in findings)  # stdlib fine


# --------------------------------------------------------------------------- #
# T08 — flaky-check quarantine                                                 #
# --------------------------------------------------------------------------- #

async def test_flaky_rerun_flips_red_to_green(monkeypatch, tmp_path):
    import autospec.orchestrator.pipeline as pipe_mod

    monkeypatch.setattr(cfg, "fake_agents", False)
    monkeypatch.setattr(cfg, "flaky_rerun_enabled", True)
    pipeline, _ws = _pipeline("p-flaky")
    iso = tmp_path / "iso"
    iso.mkdir()
    monkeypatch.setattr(pipeline, "_is_shared_ws", lambda ws: False)

    results = [(False, "red output", {}), (True, "green output", {"t::a": "passed"})]

    async def fake_to_thread(fn, *a, **k):
        return results.pop(0)

    monkeypatch.setattr(pipe_mod.asyncio, "to_thread", fake_to_thread)
    ok, output, real = await pipeline._arun_pytest(ws=iso)
    assert ok is True                # red suite flipped green on rerun
    assert results == []             # both runs consumed
    assert real == {"t::a": "passed"}


async def test_flaky_rerun_disabled_keeps_red(monkeypatch, tmp_path):
    import autospec.orchestrator.pipeline as pipe_mod

    monkeypatch.setattr(cfg, "fake_agents", False)
    monkeypatch.setattr(cfg, "flaky_rerun_enabled", False)
    pipeline, _ws = _pipeline("p-flaky2")
    iso = tmp_path / "iso2"
    iso.mkdir()
    monkeypatch.setattr(pipeline, "_is_shared_ws", lambda ws: False)

    calls = {"n": 0}

    async def fake_to_thread(fn, *a, **k):
        calls["n"] += 1
        return (False, "red", {})

    monkeypatch.setattr(pipe_mod.asyncio, "to_thread", fake_to_thread)
    ok, _out, _real = await pipeline._arun_pytest(ws=iso)
    assert ok is False
    assert calls["n"] == 1  # no rerun when disabled
