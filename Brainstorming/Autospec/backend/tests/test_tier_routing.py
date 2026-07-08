"""Wave 4 tests: role→tier→model routing + per-tier cost ledger."""

from __future__ import annotations

from autospec.agents.personas import persona
from autospec.agents.runner import AgentResult, FakeRunner
from autospec.config import settings as cfg
from autospec.models import PipelinePhase, ProjectState
from autospec.orchestrator.pipeline import Pipeline


# --------------------------------------------------------------------------- #
# model_for_role matrix                                                        #
# --------------------------------------------------------------------------- #

def test_role_routing_off_uses_phase_router(monkeypatch):
    monkeypatch.setattr(cfg, "role_routing_enabled", False)
    assert cfg.model_for_role("dev", "build") == cfg.model_for_phase("build")


def test_role_routing_maps_tiers(monkeypatch):
    monkeypatch.setattr(cfg, "role_routing_enabled", True)
    monkeypatch.setattr(cfg, "model_tiers", {"boss": "B", "worker": "W", "checker": "C"})
    assert cfg.model_for_role("architect", "plan") == "B"
    assert cfg.model_for_role("dev", "build") == "W"
    assert cfg.model_for_role("critic", "build") == "C"
    assert cfg.model_for_role("arbiter", "build") == "B"


def test_boss_never_codes_guard(monkeypatch):
    # Misconfiguration: the worker tier points at the boss model.
    monkeypatch.setattr(cfg, "role_routing_enabled", True)
    monkeypatch.setattr(cfg, "model_tiers", {"boss": "B", "worker": "B"})
    # A build dev call must NOT run on the boss model → falls back to phase router.
    assert cfg.model_for_role("dev", "build") == cfg.model_for_phase("build")


def test_unmapped_role_falls_back(monkeypatch):
    monkeypatch.setattr(cfg, "role_routing_enabled", True)
    monkeypatch.setattr(cfg, "model_tiers", {"boss": "B", "worker": "W", "checker": "C"})
    assert cfg.model_for_role("totally-unknown", "plan") == cfg.model_for_phase("plan")


# --------------------------------------------------------------------------- #
# chokepoint routing                                                           #
# --------------------------------------------------------------------------- #

async def test_chokepoint_routes_by_role(monkeypatch):
    monkeypatch.setattr(cfg, "role_routing_enabled", True)
    monkeypatch.setattr(cfg, "model_tiers", {"boss": "B", "worker": "W", "checker": "C"})
    pipeline = Pipeline(ProjectState(id="p-tier1", name="g", goal="g"), FakeRunner(["1", "2", "3"]))
    pipeline.state.phase = PipelinePhase.BUILD

    await pipeline._tracked.arun("p", persona("dev"))
    assert pipeline.runner.calls[-1]["model"] == "W"        # worker codes
    await pipeline._tracked.arun("p", persona("architect"))
    assert pipeline.runner.calls[-1]["model"] == "B"        # boss designs
    await pipeline._tracked.arun("p", persona("critic"))
    assert pipeline.runner.calls[-1]["model"] == "C"        # checker verifies


# --------------------------------------------------------------------------- #
# per-tier cost ledger + zero-cost estimation                                  #
# --------------------------------------------------------------------------- #

class _TokenRunner:
    """Runner that reports tokens but zero cost (like Codex/OpenAI/Ollama)."""

    def __init__(self):
        self.calls = []

    async def arun(self, prompt, system_prompt, cwd=None, session_id=None, model=None):
        self.calls.append({"model": model})
        return AgentResult(text="ok", cost_usd=0.0, input_tokens=1_000_000, output_tokens=2_000_000)


async def test_cost_ledger_estimates_when_runner_reports_zero(monkeypatch):
    monkeypatch.setattr(cfg, "role_routing_enabled", True)
    monkeypatch.setattr(cfg, "model_tiers", {"worker": "W"})
    monkeypatch.setattr(cfg, "tier_price_in", {"worker": 1.0})   # $/1M in
    monkeypatch.setattr(cfg, "tier_price_out", {"worker": 3.0})  # $/1M out
    pipeline = Pipeline(ProjectState(id="p-tier2", name="g", goal="g"), _TokenRunner())
    pipeline.state.phase = PipelinePhase.BUILD

    await pipeline._tracked.arun("p", persona("dev"))
    u = pipeline.state.usage
    # 1M in * $1 + 2M out * $3 = $7 estimated, attributed to the worker tier.
    assert abs(u.cost_by_tier["worker"] - 7.0) < 1e-6
    assert abs(u.cost_usd - 7.0) < 1e-6
    assert u.calls_by_tier["worker"] == 1
