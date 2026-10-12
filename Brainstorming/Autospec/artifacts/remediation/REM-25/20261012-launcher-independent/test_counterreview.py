"""Independent REM-25 counter-tests. Every OS process and HTTP call is inert."""
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
import ctypes
import pytest

ROOT = Path('C:/Users/e.millerioux/.codex/worktrees/autospec-remediation-integration/squad-ai/Brainstorming/Autospec')
spec = importlib.util.spec_from_file_location('independent_campaign', ROOT / 'tools/support_benchmark_campaign.py')
c = importlib.util.module_from_spec(spec)
spec.loader.exec_module(c)

def test_actual_interpreter_handle_retained_until_supervisor_cleanup(monkeypatch):
    from autospec.agents import runner
    closed = []
    class Function:
        def __init__(self, fn): self.fn = fn
        def __call__(self, *args): return self.fn(*args)
    def member(handle, job, out):
        out._obj.value = True
        return True
    api = SimpleNamespace(OpenProcess=Function(lambda *a: 99),
        IsProcessInJob=Function(member), CloseHandle=Function(closed.append))
    monkeypatch.setattr(ctypes, 'WinDLL', lambda *a, **k: api)
    monkeypatch.setattr(runner, '_process_identity', lambda p: 'created-at')
    c.job_member_identity(SimpleNamespace(handle=77), 42)
    assert closed == [], 'actual interpreter handle closed before admission POST'

def supervisor_fixture(tmp_path, monkeypatch, *, assignment_failure=False, states=None):
    from autospec.agents import runner
    campaign = tmp_path / 'relais-support-rem25-independent'
    campaign.mkdir()
    (campaign / 'projects').mkdir()
    (campaign / 'factory-identity.json').write_text(json.dumps(dict(pid=42, started_at=123, source_stamp='sha')))
    events = []
    class Process:
        pid = 42
        def poll(self): return None
        def terminate(self): events.append('owned-child-terminated')
        def kill(self): events.append('owned-child-killed')
        def wait(self, timeout): events.append('wait')
    class Job:
        def assign_and_resume(self, p):
            if assignment_failure: raise OSError('inert assignment failure')
            events.append('assigned')
        def close(self): events.append('closed')
    monkeypatch.setattr(runner, '_WindowsJob', Job)
    monkeypatch.setattr(runner, '_process_identity', lambda p: 'owned-handle')
    monkeypatch.setattr(c, 'trusted_imports', lambda *a: None)
    monkeypatch.setattr(c, 'job_member_identity', lambda *a: 'owned-interpreter')
    monkeypatch.setattr(c.subprocess, 'Popen', lambda *a, **kw: Process())
    monkeypatch.setattr(c, 'payload', lambda *a: {})
    monkeypatch.setattr(c, 'create_once', lambda *a: 'p')
    state_iter = iter(states or [])
    def request(method, url, body=None):
        if url.endswith('/api/health'):
            return dict(ok=True, started_at=123, source_stamp='sha', source_stamp_now='sha')
        return next(state_iter)
    monkeypatch.setattr(c, 'http', request)
    count = [0]
    def sleep(seconds):
        count[0] += 1
        if count[0] >= len(states or [None]): raise KeyboardInterrupt()
    monkeypatch.setattr(c.time, 'sleep', sleep)
    env = c.environment({}, campaign, 8130)
    return campaign, env, dict(factory_commit='a' * 40), events

def test_assignment_failure_terminates_owned_suspended_child(tmp_path, monkeypatch):
    campaign, env, receipt, events = supervisor_fixture(tmp_path, monkeypatch, assignment_failure=True)
    with pytest.raises(OSError): c.supervise(ROOT, campaign, 8130, env, receipt)
    assert any(e.startswith('owned-child-') for e in events), events

def test_real_project_state_cost_pause_error_and_verdict_are_monitored(tmp_path, monkeypatch):
    from autospec.models import ProjectState
    first = ProjectState(id='p', name='inert', goal='offline monitor probe', budget_usd=40)
    first.usage.cost_usd = 1
    second = first.model_copy(deep=True)
    second.usage.cost_usd = 7
    second.paused = True
    second.error = 'COST_UNREPORTED'
    second.acceptance_result = {'verdict': 'NOT_VERIFIED'}
    campaign, env, receipt, events = supervisor_fixture(tmp_path, monkeypatch,
        states=[first.model_dump(mode='json'), second.model_dump(mode='json')])
    with pytest.raises(KeyboardInterrupt): c.supervise(ROOT, campaign, 8130, env, receipt)
    records = [json.loads(line) for line in (campaign / 'supervisor.jsonl').read_text().splitlines()]
    observed = [r['state'] for r in records if r['event'] == 'STATE']
    assert len(observed) == 2, 'cost/paused/error/verdict change silently dropped'
    assert observed[-1]['cost_usd'] == 7
    assert observed[-1]['paused'] is True
    assert observed[-1]['error'] == 'COST_UNREPORTED'
    assert observed[-1]['acceptance_result']['verdict'] == 'NOT_VERIFIED'
