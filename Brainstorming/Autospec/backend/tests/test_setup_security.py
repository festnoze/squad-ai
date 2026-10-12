"""Setup delegates dependency preparation; legacy host argv cannot execute."""
from types import SimpleNamespace

import pytest

from autospec.agents.runner import AgentError
from autospec.config import settings
from autospec.orchestrator import setup_exec, validation_environment


@pytest.mark.parametrize('ecosystem', ['python', 'node'])
def test_install_delegates_to_clean_linux_without_host_argv_env(tmp_path, monkeypatch, ecosystem):
    manifest = 'pyproject.toml' if ecosystem == 'python' else 'package.json'
    (tmp_path/manifest).write_text('[project]\nname="setup-proof"\nversion="1.0.0"\n' if ecosystem == 'python' else '{}')
    for key in ('ANTHROPIC_API_KEY', 'DATABASE_URL', 'NODE_OPTIONS'):
        monkeypatch.setenv(key, 'must-not-forward-to-product')
    calls = []
    class CleanManager:
        def __init__(self, cache_root, *, docker, timeout):
            assert not cache_root.resolve().is_relative_to(tmp_path.resolve())
            assert docker == settings.docker_cmd and timeout <= 180
        def ensure_lock(self, root, kind): calls.append(('lock', root, kind))
        def prepare(self, root, kind, mode):
            calls.append(('prepare', root, kind, mode))
            return SimpleNamespace(fingerprint='attested-linux')
    monkeypatch.setattr(validation_environment, 'LinuxEnvironmentManager', CleanManager)
    monkeypatch.setattr('subprocess.Popen', lambda *a, **k: pytest.fail('Setup must not launch legacy host commands'))
    ok, output = setup_exec._run_install(['host-shell', 'malicious-never-executed'], tmp_path)
    assert ok and 'attested-linux' in output
    assert calls == [('lock', tmp_path, ecosystem), ('prepare', tmp_path, ecosystem, 'test')]


@pytest.mark.parametrize('stage', ['lock', 'prepare'])
def test_install_isolation_error_has_no_host_fallback(tmp_path, monkeypatch, stage):
    (tmp_path/'pyproject.toml').write_text('[project]\nname="setup-proof"\nversion="1.0.0"\n')
    monkeypatch.setattr(settings, 'agent_timeout_s', .2)
    class Unavailable:
        def __init__(self, cache_root, *, docker, timeout): assert timeout == .2
        def ensure_lock(self, *args):
            if stage == 'lock': raise AgentError('ISOLATION_UNAVAILABLE: offline timeout', code='ISOLATION_UNAVAILABLE')
        def prepare(self, *args): raise AgentError('ISOLATION_UNAVAILABLE: offline timeout', code='ISOLATION_UNAVAILABLE')
    monkeypatch.setattr(validation_environment, 'LinuxEnvironmentManager', Unavailable)
    monkeypatch.setattr('subprocess.Popen', lambda *a, **k: pytest.fail('Isolation failure must not execute host fallback'))
    ok, output = setup_exec._run_install(['host-python', '-c', 'never-execute'], tmp_path)
    assert not ok and 'ISOLATION_UNAVAILABLE' in output
