"""Wave 0 tests: verified preset, model-field telemetry, KPI scorecard."""

from __future__ import annotations

import json
import os

from autospec.orchestrator import scorecard


# --------------------------------------------------------------------------- #
# W0.2 — scorecard KPIs                                                        #
# --------------------------------------------------------------------------- #

def _timeline():
    """A synthetic build timeline: US-1 green on first try, US-2 green on the
    third, US-3 never green, plus one context-budget warning."""
    return [
        {"ts": 100.0, "kind": "phase", "name": "build"},
        {"ts": 101.0, "kind": "agent", "role": "dev", "item": "US-1",
         "ok": True, "in_tokens": 1000, "out_tokens": 500, "model": "worker-x"},
        {"ts": 102.0, "kind": "pytest", "item": "US-1", "ok": True},
        # US-2: two red attempts then green
        {"ts": 103.0, "kind": "agent", "role": "dev", "item": "US-2",
         "ok": True, "in_tokens": 900, "out_tokens": 400, "model": "worker-x"},
        {"ts": 104.0, "kind": "pytest", "item": "US-2", "ok": False},
        {"ts": 105.0, "kind": "agent", "role": "dev", "item": "US-2",
         "ok": True, "in_tokens": 900, "out_tokens": 400, "model": "worker-x"},
        {"ts": 106.0, "kind": "pytest", "item": "US-2", "ok": False},
        {"ts": 107.0, "kind": "agent", "role": "dev", "item": "US-2",
         "ok": True, "in_tokens": 900, "out_tokens": 400, "model": "boss-y"},
        {"ts": 108.0, "kind": "pytest", "item": "US-2", "ok": True},
        # US-3: never green
        {"ts": 109.0, "kind": "agent", "role": "dev", "item": "US-3",
         "ok": True, "in_tokens": 800, "out_tokens": 300, "model": "worker-x"},
        {"ts": 110.0, "kind": "pytest", "item": "US-3", "ok": False},
        {"ts": 111.0, "kind": "context_budget", "item": "US-3", "prompt_chars": 999999},
        # a phase-level check must not count as a story
        {"ts": 112.0, "kind": "pytest", "item": "phase:build", "ok": True},
        {"ts": 120.0, "kind": "agent", "role": "critic", "item": "US-2",
         "ok": False, "in_tokens": 10, "out_tokens": 0, "model": "checker-z"},
    ]


def test_scorecard_core_kpis():
    k = scorecard.compute(_timeline())
    assert k.items_tested == 3                 # US-1, US-2, US-3 (phase:build excluded)
    assert k.green_at_first_attempt == 1       # only US-1
    assert k.green_eventually == 2             # US-1, US-2
    assert k.items_failed == 1                 # US-3
    assert k.total_attempts == 1 + 3 + 1       # pytest runs across stories
    assert abs(k.green_at_1_rate - 1 / 3) < 1e-6
    assert k.context_budget_warnings == 1
    assert k.wall_clock_s == 20.0              # 120 - 100


def test_scorecard_avg_attempts_to_green():
    k = scorecard.compute(_timeline())
    # US-1 green in 1, US-2 green in 3 → mean 2.0 (US-3 excluded: never green)
    assert abs(k.avg_attempts_to_green - 2.0) < 1e-6


def test_scorecard_by_model_breakdown():
    k = scorecard.compute(_timeline())
    assert set(k.by_model) == {"worker-x", "boss-y", "checker-z"}
    assert k.by_model["worker-x"].calls == 4
    assert k.by_model["checker-z"].errors == 1
    assert k.by_model["boss-y"].tokens == 1300


def test_scorecard_load_events(tmp_path):
    p = tmp_path / "build-monitor.jsonl"
    p.write_text(
        "\n".join(json.dumps(e) for e in _timeline()) + "\ngarbage-not-json\n",
        encoding="utf-8",
    )
    events = scorecard.load_events(p)
    assert len(events) == len(_timeline())     # malformed trailing line skipped
    assert "green @ first attempt" in scorecard.format_report(scorecard.compute(events))


def test_scorecard_empty():
    k = scorecard.compute([])
    assert k.items_tested == 0
    assert k.green_at_1_rate == 0.0
    assert k.tokens_per_green_story == 0.0


# --------------------------------------------------------------------------- #
# W0.1 — verified preset                                                       #
# --------------------------------------------------------------------------- #

def _settings_in_clean_process(shell_env: dict[str, str], attrs: list[str]) -> dict:
    """Construct Settings in a FRESH interpreter with a controlled shell env, and
    return the requested attribute values.

    This mirrors production exactly: config is imported once, so ``_SHELL_ENV_KEYS``
    is snapshotted BEFORE ``load_dotenv`` fills the rest from ``.env``. Reloading
    in-process cannot reproduce this — the parent pytest already loaded ``.env``
    into ``os.environ``, which would make every ``.env`` var look shell-pinned. So
    we hand the child a minimal env containing only what the test declares."""
    import subprocess
    import sys

    base = {k: os.environ[k] for k in ("PATH", "SystemRoot", "PATHEXT", "PYTHONPATH")
            if k in os.environ}
    base.update(shell_env)
    snippet = (
        "import json, autospec.config as c; s=c.Settings();"
        "print(json.dumps({a: getattr(s, a)() if callable(getattr(s, a)) else getattr(s, a)"
        " for a in " + repr(attrs) + "}))"
    )
    out = subprocess.run(
        [sys.executable, "-c", snippet],
        capture_output=True, text=True, env=base,
        cwd=str(__import__("pathlib").Path(__file__).resolve().parent.parent),
    )
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout.strip().splitlines()[-1])


def test_preset_verified_overrides_env_defaults():
    r = _settings_in_clean_process(
        {"PRESET": "verified"},
        ["preset_active", "coverage_enabled", "mutation_enabled",
         "runtime_acceptance_enabled", "definition_of_done_strict_criteria"],
    )
    assert r["preset_active"] == "verified"
    # Gauntlet gates not pinned in the shell are turned on by the preset,
    # overriding the .env convenience-off defaults.
    assert r["coverage_enabled"] is True
    assert r["mutation_enabled"] is True
    assert r["runtime_acceptance_enabled"] is True
    assert r["definition_of_done_strict_criteria"] is True


def test_preset_verified_yields_to_shell_override():
    # REFINE pinned OFF in the shell must survive the preset.
    r = _settings_in_clean_process(
        {"PRESET": "verified", "REFINE": "0"},
        ["refine_enabled", "coverage_enabled"],
    )
    assert r["refine_enabled"] is False
    assert r["coverage_enabled"] is True  # still overridden (not shell-pinned)


def test_no_preset_leaves_env_defaults():
    r = _settings_in_clean_process(
        {"COVERAGE": "0"},
        ["preset_active", "coverage_enabled"],
    )
    assert r["preset_active"] == ""
    assert r["coverage_enabled"] is False


# --------------------------------------------------------------------------- #
# W0.3 — model field on the interaction record                                 #
# --------------------------------------------------------------------------- #

def test_interaction_record_carries_model():
    from autospec.orchestrator.interactions import InteractionStore

    store = InteractionStore(per_item=10)
    rec = store.record(
        item_id="US-1", phase="build", persona="dev", model="worker-x",
        prompt="p", response="r",
    )
    assert rec.model == "worker-x"
    assert store.for_item("US-1")[0].model == "worker-x"
