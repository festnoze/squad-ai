"""W7: evaluator delegates to confinement; trusted launcher retains exact ownership.

No generated main.py is executed on the host. Native probes below contain only
source-reviewed factory constants and are NOT presented as a security boundary.
"""
import os
import subprocess
import sys
import time
from types import SimpleNamespace

import pytest

from autospec.agents.runner import FakeRunner, spawn_owned_process, close_owned_process
from autospec.config import settings
from autospec.models import ProjectState
from autospec.orchestrator import bootstrap
from autospec.orchestrator.pipeline import Pipeline, _run_capped_process, _minimal_env
from autospec.storage import workspace_dir
from .test_runner_processes import _assert_dead


@pytest.mark.parametrize('profile', ['cli', 'api'])
@pytest.mark.parametrize('success', [True, False])
async def test_evaluator_delegates_exact_root_timeout_and_preserves_failure(monkeypatch, profile, success):
    monkeypatch.setattr(settings, 'fake_agents', False)
    monkeypatch.setattr(settings, 'evaluator_run_timeout_s', 7)
    state = ProjectState(id='w7-isolated', name='app', goal='g', product_profile=profile)
    pipeline = Pipeline(state, FakeRunner([]))
    calls, events = [], []
    async def verify(actual_state, root, *, timeout_s):
        calls.append((actual_state, root, timeout_s))
        return SimpleNamespace(ok=success, detail='isolated PASS' if success else 'isolated FAIL')
    monkeypatch.setattr(bootstrap, 'verify_runtime', verify)
    monkeypatch.setattr(pipeline.monitor, 'event', lambda kind, **fields: events.append((kind, fields)))
    monkeypatch.setattr(subprocess, 'Popen', lambda *a, **k: pytest.fail('Evaluator cannot launch host product'))
    monkeypatch.setattr(Pipeline, '_kill_workspace_port_holders', staticmethod(lambda *a: pytest.fail('No broad port/path sweep')))
    detail = await pipeline._aexercise_product()
    assert calls == [(state, workspace_dir(state.id), 7)]
    assert detail == ('isolated PASS' if success else 'isolated FAIL')
    assert events == [('evaluator_run', {'ok': success, 'isolated': True})]


async def test_demo_never_calls_a_runtime_or_spawns(monkeypatch):
    monkeypatch.setattr(settings, 'fake_agents', True)
    async def forbidden(*a, **k): pytest.fail('Demo is not real validation')
    monkeypatch.setattr(bootstrap, 'verify_runtime', forbidden)
    monkeypatch.setattr(subprocess, 'Popen', lambda *a, **k: pytest.fail('Demo cannot spawn'))
    pipeline = Pipeline(ProjectState(id='w7-demo', name='app', goal='g'), FakeRunner([]))
    assert 'démo' in await pipeline._aexercise_product()


def test_pid_only_tree_kill_is_refused_without_taskkill(monkeypatch):
    monkeypatch.setattr(subprocess, 'run', lambda *a, **k: pytest.fail('PID guessing/taskkill is not ownership'))
    class Foreign:
        pid = os.getpid()  # even our live test PID is not an owned handle
        def poll(self): return None
    assert Pipeline._kill_tree(Foreign()) is False


@pytest.mark.parametrize('exit_parent', [False, True], ids=['deadline', 'parent-exit-open-pipe'])
def test_trusted_capped_launcher_closes_owned_descendants_only(tmp_path, exit_parent):
    marker = tmp_path/'trusted-child.pid'
    child = f"import os,time,pathlib;pathlib.Path({str(marker)!r}).write_text(str(os.getpid()));time.sleep(60)"
    # Absolute factory marker, reviewed constant program; never a product entrypoint.
    parent = (f"import subprocess,sys,time,pathlib;subprocess.Popen([sys.executable,'-u','-c',{child!r}]);"
              f"p=pathlib.Path({str(marker)!r});deadline=time.monotonic()+15\n"
              "while not p.exists() and time.monotonic()<deadline:time.sleep(.02)\n"
              "print('trusted launcher ready',flush=True)\n" + ("" if exit_parent else "time.sleep(60)\n"))
    sentinel = spawn_owned_process([sys.executable, '-u', '-c', 'import time;time.sleep(60)'],
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        started = time.monotonic()
        result = _run_capped_process([sys.executable,'-u','-c',parent], cwd=tmp_path,
            env=_minimal_env(), timeout=15 if exit_parent else 10, output_cap=4096,
            kill_tree=Pipeline._kill_tree, name='w7-trusted-native')
        assert time.monotonic()-started < 25
        assert marker.exists(), 'A pre-start timeout is not proof of descendant cleanup'
        _assert_dead(int(marker.read_text()))
        assert sentinel.poll() is None, 'An unrelated owned process must not be touched'
        assert 'trusted launcher ready' in result.output and not result.pipe_leaked
        if exit_parent: assert result.returncode == 0 and not result.timed_out
        else: assert result.timed_out and result.killed_tree
    finally:
        close_owned_process(sentinel)
