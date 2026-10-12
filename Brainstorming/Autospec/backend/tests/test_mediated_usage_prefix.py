"""Known paid prefixes survive unknown rounds and file/coordinator failures.

All providers are offline scripted turns; no model, shell or generated code runs.
"""
import asyncio
import json
import threading

import pytest

from autospec.agents import runner
from autospec.agents.file_broker import active_dependency_handler


def paid(text, cost=.2, *, complete=True):
    return runner.AgentResult(text, cost_usd=cost, input_tokens=10, output_tokens=2, usage_reported=complete)


def install_turns(monkeypatch, client, replies):
    async def turn(*args):
        result = replies.pop(0)
        if isinstance(result, BaseException): raise result
        return result
    monkeypatch.setattr(client, '_turn', turn)
    monkeypatch.setattr(runner, '_run_tracked', lambda *a, **k: pytest.fail('Offline accounting must not call a paid CLI'))


@pytest.mark.parametrize('last_usage,expected_cost,complete', [
    (None, .2, False),
    (paid('', .03, complete=False), .23, False),
    (paid('', .03, complete=True), .23, True),
])
async def test_later_failed_turn_keeps_every_known_prefix(monkeypatch, tmp_path, last_usage, expected_cost, complete):
    client = runner.ClaudeCliRunner()
    first = paid(json.dumps({'tool':'list_files'}))
    failure = runner.AgentError('offline provider timeout/failure', usage=last_usage)
    install_turns(monkeypatch, client, [first, failure])
    with pytest.raises(runner.AgentError) as result:
        await client.arun('p', 's', cwd=tmp_path)
    usage=result.value.usage
    assert usage.cost_usd == pytest.approx(expected_cost) and usage.usage_reported is complete
    assert usage.input_tokens == (10 if last_usage is None else 20)
    assert usage.output_tokens == (2 if last_usage is None else 4)
    assert usage is not first and usage is not last_usage


@pytest.mark.parametrize('failure', [runner.AgentError('offline dependency refused', code='DEPENDENCY_REFUSED'), OSError('offline write failure')])
async def test_tool_failure_keeps_already_complete_model_cost_without_new_unknown_turn(monkeypatch, tmp_path, failure):
    client = runner.ClaudeCliRunner()
    install_turns(monkeypatch, client, [paid(json.dumps({'tool':'dependency_request','ecosystem':'python'}))])
    def coordinator(*args): raise failure
    token=active_dependency_handler.set(coordinator)
    try:
        with pytest.raises(runner.AgentError) as result:
            await client.arun('p','s',cwd=tmp_path)
        assert result.value.usage.cost_usd == .2 and result.value.usage.usage_reported
        assert result.value.code == ('DEPENDENCY_REFUSED' if isinstance(failure,runner.AgentError) else 'MEDIATED_TOOL_FAILED')
    finally:
        active_dependency_handler.reset(token)


async def test_cancel_in_unknown_paid_turn_attaches_partial_cost(monkeypatch,tmp_path):
    client=runner.ClaudeCliRunner(); entered=asyncio.Event();calls=0
    async def turn(*args):
        nonlocal calls
        calls += 1
        if calls == 1:return paid(json.dumps({'tool':'list_files'}))
        entered.set();await asyncio.Event().wait()
    monkeypatch.setattr(client,'_turn',turn)
    task=asyncio.create_task(client.arun('p','s',cwd=tmp_path))
    await asyncio.wait_for(entered.wait(),3)
    task.cancel()
    with pytest.raises(asyncio.CancelledError) as result:await task
    assert result.value.usage.cost_usd == .2 and not result.value.usage.usage_reported


async def test_cancel_while_tool_waits_preserves_known_final_inference_cost(monkeypatch,tmp_path):
    client=runner.ClaudeCliRunner();entered=threading.Event();release=threading.Event()
    install_turns(monkeypatch,client,[paid(json.dumps({'tool':'dependency_request','ecosystem':'python'}))])
    def coordinator(*args):
        entered.set();assert release.wait(5);return {'status':'pending'}
    token=active_dependency_handler.set(coordinator)
    task=asyncio.create_task(client.arun('p','s',cwd=tmp_path))
    try:
        assert await asyncio.to_thread(entered.wait,3)
        task.cancel()
        with pytest.raises(asyncio.CancelledError) as result:await task
        assert result.value.usage.cost_usd == .2 and result.value.usage.usage_reported
    finally:
        release.set();active_dependency_handler.reset(token)
        await asyncio.gather(task,return_exceptions=True)


async def test_post_turn_observer_failure_cannot_erase_paid_receipt(monkeypatch):
    client=runner.ClaudeCliRunner()
    install_turns(monkeypatch,client,[paid('complete answer')])
    async def observer(active):
        if not active:raise runner.AgentError('offline post-turn persistence error')
    token=runner.active_provider_observer.set(observer)
    try:
        with pytest.raises(runner.AgentError) as result:await client.arun('p','s')
        assert result.value.usage.cost_usd == .2 and result.value.usage.usage_reported
    finally:runner.active_provider_observer.reset(token)
