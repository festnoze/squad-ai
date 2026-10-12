"""Merged manifests get fresh Linux locks, never unsafe/stale partial exports."""
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from autospec.orchestrator import validation_environment as module
from autospec.orchestrator.validation_environment import LinuxEnvironmentManager


def manifests(root, ecosystem):
    if ecosystem == 'python':
        manifest, lock = root / 'pyproject.toml', root / 'uv.lock'
        manifest.write_text('[project]\nname="lock-regeneration-proof"\nversion="0.1.0"\nrequires-python=">=3.12"\ndependencies=[]\n')
        new = b'version = 1\nrevision = 3\n'
    else:
        manifest, lock = root / 'package.json', root / 'package-lock.json'
        manifest.write_text(json.dumps({'name': 'lock-regeneration-proof', 'version': '1.0.0', 'scripts': {'postinstall': 'exit 99'}}))
        new = b'{"lockfileVersion":3,"packages":{}}'
    lock.write_bytes(b'old-lock-even-if-stale-or-malformed')
    return manifest, lock, new


@pytest.mark.parametrize('ecosystem', ['python', 'node'])
@pytest.mark.parametrize('outcome', ['success', 'exit-failure', 'unsafe-lock', 'source-race', 'lock-race', 'builder-manifest-change'])
def test_regenerate_admits_before_atomic_replace_and_preserves_failure(tmp_path, monkeypatch, ecosystem, outcome):
    manifest, lock, new = manifests(tmp_path, ecosystem)
    old = lock.read_bytes()
    (tmp_path / '.env').write_text('must-not-enter-builder')
    (tmp_path / 'main.py').write_text('must-never-execute')
    manager = LinuxEnvironmentManager(tmp_path / 'outside-cache')
    monkeypatch.setattr(manager, '_base', lambda _: {'Id': 'attested-linux-image'})
    from autospec.orchestrator import sandbox
    cleaned = []
    monkeypatch.setattr(sandbox, '_cleanup_container', lambda *args: cleaned.append(args))
    def resolve(argv, stdin, cwd, timeout):
        stage = Path(cwd)
        assert {path.name for path in stage.iterdir()} == {manifest.name}
        assert lock.read_bytes() == old
        assert argv[argv.index('--network') + 1] == 'bridge'
        assert '--no-build' in argv if ecosystem == 'python' else '--ignore-scripts' in argv
        if outcome == 'exit-failure':
            return 1, '', 'resolver failure'
        if outcome == 'unsafe-lock':
            data = (b'version=1\n[[package]]\nname="bad"\nversion="1"\n[package.source]\nregistry="https://localhost/private"\n'
                    if ecosystem == 'python' else b'{"packages":{"node_modules/bad":{"resolved":"https://localhost/private.tgz"}}}')
        else:
            data = new
        (stage / lock.name).write_bytes(data)
        if outcome == 'source-race':
            manifest.write_bytes(manifest.read_bytes() + b'\n')
        if outcome == 'lock-race':
            lock.write_bytes(b'concurrent-owner-lock')
        if outcome == 'builder-manifest-change':
            staged_manifest = stage / manifest.name
            staged_manifest.write_bytes(staged_manifest.read_bytes() + b'\n')
        return 0, 'resolved', ''
    monkeypatch.setattr(module, '_run_tracked', resolve)
    if outcome == 'success':
        assert manager.regenerate_lock(tmp_path, ecosystem) == lock
        assert lock.read_bytes() == new
    else:
        with pytest.raises(RuntimeError, match='ISOLATION_UNAVAILABLE'):
            manager.regenerate_lock(tmp_path, ecosystem)
        assert lock.read_bytes() == (b'concurrent-owner-lock' if outcome == 'lock-race' else old)
    assert len(cleaned) == 1
    assert (tmp_path / 'main.py').read_text() == 'must-never-execute'
    assert (tmp_path / '.env').read_text() == 'must-not-enter-builder'


def test_regenerate_forbids_direct_url_manifest_before_docker(tmp_path, monkeypatch):
    (tmp_path / 'pyproject.toml').write_text('[project]\nname="bad"\nversion="1"\ndependencies=["bad @ https://localhost/private.whl"]\n')
    lock = tmp_path / 'uv.lock'; lock.write_bytes(b'original')
    manager = LinuxEnvironmentManager(tmp_path / 'cache')
    monkeypatch.setattr(manager, '_base', lambda *_: pytest.fail('must fail before Docker'))
    with pytest.raises(RuntimeError, match='Direct URL'):
        manager.regenerate_lock(tmp_path, 'python')
    assert lock.read_bytes() == b'original'


@pytest.mark.parametrize('uv', [
    'override-dependencies=["bad @ https://localhost/private.whl"]',
    'constraint-dependencies=["bad @ https://localhost/private.whl"]',
    'keyring-provider="subprocess"',
    'allow-insecure-host=["localhost"]',
])
def test_uv_hidden_resolution_config_cannot_bypass_public_registry_admission(tmp_path, uv):
    (tmp_path / 'pyproject.toml').write_text('[project]\nname="bad"\nversion="1"\ndependencies=[]\n[tool.uv]\n' + uv + '\n')
    with pytest.raises(RuntimeError, match='ISOLATION_UNAVAILABLE'):
        module.admit_manifest(tmp_path, 'python', require_lock=False)


def test_npm_overrides_and_legacy_lock_cannot_hide_external_resolved_urls(tmp_path):
    manifest = tmp_path / 'package.json'
    manifest.write_text(json.dumps({'overrides': {'react': 'https://localhost/private.tgz'}}))
    with pytest.raises(RuntimeError, match='overrides'):
        module.admit_manifest(tmp_path, 'node', require_lock=False)
    manifest.write_text('{}')
    (tmp_path / 'package-lock.json').write_text(json.dumps({'lockfileVersion': 1, 'dependencies': {'bad': {'resolved': 'https://localhost/private.tgz'}}}))
    with pytest.raises(RuntimeError, match='v2/v3'):
        module.admit_manifest(tmp_path, 'node')


def test_atomic_publish_failure_does_not_remove_old_lock(tmp_path, monkeypatch):
    _, lock, new = manifests(tmp_path, 'python')
    previous = lock.read_bytes()
    manager = LinuxEnvironmentManager(tmp_path / 'external-cache')
    monkeypatch.setattr(manager, '_base', lambda _: {'Id': 'attested'})
    from autospec.orchestrator import dependencies, sandbox
    monkeypatch.setattr(sandbox, '_cleanup_container', lambda *args: None)
    def resolve(argv, stdin, cwd, timeout):
        (Path(cwd) / 'uv.lock').write_bytes(new)
        return 0, '', ''
    monkeypatch.setattr(module, '_run_tracked', resolve)
    def unavailable(*args):
        raise PermissionError('simulated atomic replace failure')
    monkeypatch.setattr(dependencies.os, 'replace', unavailable)
    with pytest.raises(PermissionError, match='atomic replace'):
        manager.regenerate_lock(tmp_path, 'python')
    assert lock.read_bytes() == previous
    assert not list(tmp_path.glob('.uv.lock-*'))


@pytest.mark.skipif(os.environ.get('AUTOSPEC_REAL_LINUX_VALIDATION') != '1', reason='Opt-in real Linux uv/npm merged-manifest lock regeneration')
@pytest.mark.parametrize('ecosystem', ['python', 'node'])
def test_real_regenerated_lock_matches_merged_manifest_and_failure_preserves_previous(tmp_path, ecosystem):
    manifest, lock, _ = manifests(tmp_path, ecosystem)
    manager = LinuxEnvironmentManager(tmp_path / 'external-cache')
    (tmp_path / 'source.py').write_text('raise RuntimeError("must not run in builder")')
    (tmp_path / '.env').write_text('SECRET=not-in-builder')
    manager.regenerate_lock(tmp_path, ecosystem)
    first = lock.read_bytes()
    if ecosystem == 'python':
        manifest.write_text(manifest.read_text().replace('dependencies=[]', 'dependencies=["idna==3.11"]'))
    else:
        data = json.loads(manifest.read_text()); data['dependencies'] = {'react': '18.3.1'}
        manifest.write_text(json.dumps(data))
    manager.regenerate_lock(tmp_path, ecosystem)
    assert lock.read_bytes() != first
    if ecosystem == 'python':
        import tomllib
        data = tomllib.loads(lock.read_text())
        assert any(package['name'] == 'idna' and package['version'] == '3.11' for package in data['package'])
        manifest.write_text(manifest.read_text().replace('idna==3.11', 'idna==0.0.999999'))
    else:
        data = json.loads(lock.read_text())
        assert data['packages']['node_modules/react']['version'] == '18.3.1'
        data = json.loads(manifest.read_text()); data['dependencies']['react'] = '0.0.999999'
        manifest.write_text(json.dumps(data))
    admitted_previous = lock.read_bytes()
    with pytest.raises(RuntimeError, match='Dependency lock resolution failed'):
        manager.regenerate_lock(tmp_path, ecosystem)
    assert lock.read_bytes() == admitted_previous
    assert {path.name for path in tmp_path.iterdir()} == {manifest.name, lock.name, 'source.py', '.env'}
