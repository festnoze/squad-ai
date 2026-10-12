"""An inert exhausted fixture has known zero usage; real missing receipts do not."""
import pytest

from autospec.agents.runner import AgentError, FakeRunner
from autospec.models import PipelinePhase, ProjectState
from autospec.orchestrator.pipeline import Pipeline


async def test_empty_fake_runner_has_an_explicit_known_zero_receipt():
    with pytest.raises(AgentError) as caught:
        await FakeRunner([]).arun("local fixture only", "local fixture only")
    result = caught.value.usage
    assert result is not None
    assert result.usage_reported is True
    assert result.cost_usd == result.input_tokens == result.output_tokens == 0


async def test_fixture_failure_does_not_block_next_known_inert_reply():
    runner = FakeRunner([])
    pipeline = Pipeline(ProjectState(id="known-inert-failure", name="Fixture", goal="Local only",
                                     phase=PipelinePhase.BUILD, budget_usd=1), runner)
    with pytest.raises(AgentError, match="no queued reply"):
        await pipeline._tracked.arun("inert", "inert")
    assert pipeline.state.usage.unreported_calls == 0
    assert pipeline.state.usage.failed_calls == 1
    runner.queue("known inert success")
    result = await pipeline._tracked.arun("inert", "inert")
    assert result.text == "known inert success"
    assert pipeline.state.usage.agent_calls == 2
    assert not pipeline._stop_requested


async def test_unattested_real_style_failure_remains_blocking():
    class MissingReceipt:
        calls = 0
        async def arun(self, *args, **kwargs):
            self.calls += 1
            raise AgentError("controlled absent provider receipt")

    runner = MissingReceipt()
    pipeline = Pipeline(ProjectState(id="unknown-receipt-failure", name="Fixture", goal="Local only",
                                     phase=PipelinePhase.BUILD, budget_usd=1), runner)
    with pytest.raises(AgentError, match="absent provider receipt"):
        await pipeline._tracked.arun("inert", "inert")
    assert pipeline.state.usage.unreported_calls == 1
    with pytest.raises(AgentError, match="COST_UNREPORTED"):
        await pipeline._tracked.arun("inert", "inert")
    assert runner.calls == 1
