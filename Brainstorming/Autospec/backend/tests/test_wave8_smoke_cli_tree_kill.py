"""W8: CLI/help always delegate to isolated captured streams, no host argv/env.

Real container timeout/baked-source probes live in captured_and_baked_validation.
Real native descendant probes are trusted factory constants in W7/runner tests.
"""
import subprocess
import sys

import pytest

from autospec.agents.runner import AgentError, FakeRunner
from autospec.config import settings
from autospec.models import ProjectState
from autospec.orchestrator import isolated_validation, runtime_acceptance
from autospec.orchestrator.pipeline import Pipeline, _run_capped_process, _minimal_env


def _pipeline(tmp_path, monkeypatch, replies, *, help_enabled=True):
    calls = []
    product = tmp_path/'product'; product.mkdir()
    class Validator:
        def __init__(self, cache, *, docker, timeout):
            assert not cache.resolve().is_relative_to(product.resolve())
            assert docker == settings.docker_cmd and timeout == settings.smoke_run_timeout_s
        def run_captured(self, root, ecosystem, argv, *, mode):
            calls.append((root, ecosystem, argv, mode))
            response = replies.pop(0)
            if isinstance(response, BaseException): raise response
            return (*response, object())
    monkeypatch.setattr(isolated_validation, 'IsolatedValidator', Validator)
    monkeypatch.setattr(settings, 'smoke_cli_help', help_enabled)
    monkeypatch.setattr(runtime_acceptance, '_backend_web_candidate', lambda _: False)
    monkeypatch.setattr(subprocess, 'Popen', lambda *a, **k: pytest.fail('A generated CLI must not execute on host'))
    state = ProjectState(id='w8-isolated', name='app', goal='g', product_profile='cli')
    pipeline = Pipeline(state, FakeRunner([]))
    monkeypatch.setattr(pipeline, '_expects_web_app', lambda: False)
    return pipeline, calls, product


@pytest.mark.parametrize('failure', [
    subprocess.TimeoutExpired('owned-container', 1),
    AgentError('ISOLATION_UNAVAILABLE: no Linux engine', code='ISOLATION_UNAVAILABLE'),
    OSError('engine unreachable'),
])
def test_cli_timeout_or_infra_cannot_fallback_to_host(tmp_path, monkeypatch, failure):
    pipeline, calls, product = _pipeline(tmp_path, monkeypatch, [failure])
    ok, detail = pipeline._smoke_run_python(product)
    assert not ok and 'ISOLATION_UNAVAILABLE' in detail
    assert calls == [(product, 'python', ['/opt/venv/bin/python', 'main.py'], 'runtime')]


def test_help_timeout_is_not_green_after_successful_run(tmp_path, monkeypatch):
    pipeline, calls, product = _pipeline(tmp_path, monkeypatch, [(0, 'nominal', ''), subprocess.TimeoutExpired('owned-container', 1)])
    ok, detail = pipeline._smoke_run_python(product)
    assert not ok and 'ISOLATION_UNAVAILABLE' in detail
    assert [call[2] for call in calls] == [['/opt/venv/bin/python', 'main.py'], ['/opt/venv/bin/python', 'main.py', '--help']]


@pytest.mark.parametrize('help_response,success', [
    ((0, 'usage: source-reviewed CLI --help', ''), True),
    ((0, '', 'usage: launcher diagnostic on stderr only'), False),
    ((2, 'usage: invalid invocation', 'error'), False),
])
def test_help_requires_actual_stdout_and_success(tmp_path, monkeypatch, help_response, success):
    pipeline, calls, product = _pipeline(tmp_path, monkeypatch, [(0, '', ''), help_response])
    events = []
    monkeypatch.setattr(pipeline.monitor, 'event', lambda kind, **fields: events.append((kind, fields)))
    ok, detail = pipeline._smoke_run_python(product)
    assert ok is success
    if help_response[1] == '': assert 'muet' in detail
    assert len(calls) == 2 and calls[1][2][-1] == '--help'
    assert events == [('smoke_cli', {'probe': 'help', 'ok': success, 'isolated': True})]


def test_help_compatibility_arguments_never_forward_host_command_or_secret(tmp_path, monkeypatch):
    calls = []
    class Trusted:
        def run_captured(self, *args, **kwargs):
            calls.append((args, kwargs))
            return 0, 'usage: confined help', '', object()
    monkeypatch.setattr(subprocess, 'Popen', lambda *a, **k: pytest.fail('Legacy host argv must be ignored'))
    ok, _ = Pipeline._smoke_cli_help_run(tmp_path, ['host-shell', 'never-execute'],
        {'ANTHROPIC_API_KEY': 'never-forward'}, 3, validator=Trusted())
    assert ok and calls == [((tmp_path, 'python', ['/opt/venv/bin/python', 'main.py', '--help']), {'mode': 'runtime'})]


def test_web_sync_gate_refuses_without_running_a_cli(tmp_path, monkeypatch):
    pipeline, calls, product = _pipeline(tmp_path, monkeypatch, [])
    monkeypatch.setattr(pipeline, '_expects_web_app', lambda: True)
    ok, detail = pipeline._smoke_run_python(product)
    assert not ok and 'asynchronous isolated runtime' in detail and not calls


def test_successful_nonhelp_cli_uses_only_isolated_entrypoint(tmp_path, monkeypatch):
    pipeline, calls, product = _pipeline(tmp_path, monkeypatch, [(0, 'real output', '')], help_enabled=False)
    ok, detail = pipeline._smoke_run_python(product)
    assert ok and detail == 'CLI exécuté (code 0)'
    assert calls == [(product, 'python', ['/opt/venv/bin/python', 'main.py'], 'runtime')]


def test_trusted_native_capped_launcher_drains_both_bounded_streams(tmp_path):
    # Reviewed factory program, not code read from generated main.py. Native
    # ownership is lifecycle cleanup only, never product confinement.
    program = "import sys;sys.stdout.write('x'*100000);sys.stdout.flush();sys.stderr.write('e'*100000);sys.stderr.flush()"
    result = _run_capped_process([sys.executable, '-u', '-c', program], cwd=tmp_path,
        env=_minimal_env(), timeout=15, output_cap=4096, kill_tree=Pipeline._kill_tree,
        stderr=subprocess.PIPE, name='w8-trusted-streams')
    assert result.returncode == 0 and not result.timed_out and not result.pipe_leaked
    assert result.output == 'x'*4096 and result.stderr_output == 'e'*4096 and result.truncated
