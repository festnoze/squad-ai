import json
import os
from pathlib import Path
from subprocess import CompletedProcess

import pytest

from autospec.orchestrator.environments import CleanEnvironmentManager, EnvironmentError, minimal_environment


class Installer:
    def __init__(self):
        self.calls = []

    def __call__(self, argv, *, cwd, env):
        self.calls.append((argv, env))
        if "sync" in argv:
            root = cwd / ".venv"
            root.mkdir()
            (root / "pyvenv.cfg").write_text("include-system-site-packages = false\n", encoding="utf-8")
            (root / "package.py").write_text("installed = True\n", encoding="utf-8")
        elif "ci" in argv:
            (cwd / "node_modules").mkdir()
            (cwd / "node_modules/pkg.js").write_text("export default true;", encoding="utf-8")
        return CompletedProcess(argv, 0, "", "")


def project(tmp_path, ecosystem="python"):
    root = tmp_path / "product"
    root.mkdir()
    names = ("pyproject.toml", "uv.lock") if ecosystem == "python" else ("package.json", "package-lock.json")
    for name in names:
        (root / name).write_text('[project]\nname="fixture"\nversion="0.1.0"\n' if name == "pyproject.toml" else "fixture", encoding="utf-8")
    (root / "main.py").write_text("print('hello')", encoding="utf-8")
    return root


VERSIONS = {"uv": "uv 1", "python": "Python 3.12"}


def test_cache_identity_includes_lock_tool_platform_and_mode(tmp_path):
    root = project(tmp_path)
    installer = Installer()
    manager = CleanEnvironmentManager(tmp_path / "supervisor", installer)
    a = manager.prepare(root, "python", tool_versions=VERSIONS, platform_id="windows-x64")
    b = manager.prepare(root, "python", tool_versions=VERSIONS, platform_id="windows-x64")
    assert not a.reused and b.reused
    assert len(installer.calls) == 1
    (root / "uv.lock").write_text("changed lock", encoding="utf-8")
    c = manager.prepare(root, "python", tool_versions=VERSIONS, platform_id="windows-x64")
    d = manager.prepare(root, "python", "runtime", tool_versions=VERSIONS, platform_id="windows-x64")
    e = manager.prepare(root, "python", tool_versions=VERSIONS | {"uv": "uv 2"}, platform_id="windows-x64")
    f = manager.prepare(root, "python", tool_versions=VERSIONS, platform_id="linux-x64")
    assert len({a.fingerprint, c.fingerprint, d.fingerprint, e.fingerprint, f.fingerprint}) == 5
    assert "--locked" in installer.calls[0][0]
    assert "--no-install-project" in installer.calls[0][0]
    assert "--no-dev" in installer.calls[2][0]
    with pytest.raises(EnvironmentError, match="runtime"):
        d.test_command("report.json")


def test_enriched_product_venv_and_secrets_never_copied(tmp_path):
    root = project(tmp_path)
    (root / ".venv").mkdir()
    (root / ".venv/argon2.py").write_text("accidentally installed", encoding="utf-8")
    (root / ".env").write_text("TOKEN=secret", encoding="utf-8")
    (root / ".claude").mkdir()
    (root / ".claude/auth.json").write_text("credential", encoding="utf-8")
    (root / ".npmrc").write_text("authToken=secret", encoding="utf-8")
    for name in ("autospec-state.json", "build-monitor.jsonl", "autospec-interactions.jsonl", "acceptance-contract.json", "contract-baseline.json", ".env.example"):
        (root / name).write_text("supervisor metadata", encoding="utf-8")
    (root / ".autospec").mkdir()
    (root / ".autospec/oracle.json").write_text("independent oracle", encoding="utf-8")
    installer = Installer()
    clean = CleanEnvironmentManager(tmp_path / "supervisor", installer).prepare(root, "python", tool_versions=VERSIONS)
    staged = clean.stage_project(root, tmp_path / "run")
    assert not (staged / ".venv").exists() and not (staged / ".env").exists()
    assert not (staged / ".claude").exists() and not (staged / ".npmrc").exists()
    assert not (staged / ".autospec").exists()
    assert not (staged / "acceptance-contract.json").exists()
    assert not (staged / "contract-baseline.json").exists()
    assert not (staged / "autospec-state.json").exists()
    assert not (staged / "build-monitor.jsonl").exists()
    assert not (staged / "autospec-interactions.jsonl").exists()
    assert not (staged / ".env.example").exists()
    assert (staged / "main.py").exists()
    assert "uv" not in clean.test_command("report.json")
    assert "-m" in clean.test_command("report.json")
    assert installer.calls[0][1]["UV_PROJECT_ENVIRONMENT"] != str(root / ".venv")


def test_source_hardlink_is_rejected_before_copy(tmp_path):
    root = project(tmp_path)
    source = tmp_path / "outside-secret"
    source.write_text("secret", encoding="utf-8")
    os.link(source, root / "disguised.txt")
    clean = CleanEnvironmentManager(tmp_path / "supervisor", Installer()).prepare(root, "python", tool_versions=VERSIONS)
    with pytest.raises(EnvironmentError, match="hardlink"):
        clean.stage_project(root, tmp_path / "run")
    assert not (tmp_path / "run").exists()


def test_cache_drift_is_not_reused_or_silently_repaired(tmp_path):
    root = project(tmp_path)
    manager = CleanEnvironmentManager(tmp_path / "supervisor", Installer())
    clean = manager.prepare(root, "python", tool_versions=VERSIONS)
    (clean.cache_path / ".venv/argon2.py").write_text("manual injection", encoding="utf-8")
    with pytest.raises(EnvironmentError, match="ENVIRONMENT_DRIFT"):
        manager.prepare(root, "python", tool_versions=VERSIONS)
    with pytest.raises(EnvironmentError, match="ENVIRONMENT_DRIFT"):
        clean.stage_project(root, tmp_path / "run")


def test_input_change_after_prepare_refuses_execution(tmp_path):
    root = project(tmp_path)
    clean = CleanEnvironmentManager(tmp_path / "supervisor", Installer()).prepare(root, "python", tool_versions=VERSIONS)
    (root / "uv.lock").write_text("changed", encoding="utf-8")
    with pytest.raises(EnvironmentError, match="INPUT_CHANGED"):
        clean.stage_project(root, tmp_path / "run")


def test_failed_clean_install_never_gets_attestation(tmp_path):
    root = project(tmp_path)
    manager = CleanEnvironmentManager(tmp_path / "supervisor", lambda argv, **kw: CompletedProcess(argv, 1, "lock mismatch", ""))
    with pytest.raises(EnvironmentError, match="CLEAN_INSTALL_FAILED"):
        manager.prepare(root, "python", tool_versions=VERSIONS)
    assert not list((tmp_path / "supervisor").rglob("attestation.json"))
    with pytest.raises(EnvironmentError, match="CACHE_INCOMPLETE"):
        manager.prepare(root, "python", tool_versions=VERSIONS)


def test_node_clean_ci_and_runtime_separation(tmp_path):
    root = project(tmp_path, "node")
    (root / "node_modules").mkdir()
    (root / "node_modules/poison.js").write_text("false", encoding="utf-8")
    installer = Installer()
    manager = CleanEnvironmentManager(tmp_path / "supervisor", installer)
    clean = manager.prepare(root, "node", tool_versions={"node": "22", "npm": "10"})
    staged = clean.stage_project(root, tmp_path / "run")
    assert "--ignore-scripts" in installer.calls[0][0]
    assert "--include=dev" in installer.calls[0][0]
    assert not (staged / "node_modules/poison.js").exists()
    assert (staged / "node_modules/pkg.js").exists()
    assert clean.test_command("r.json", frontend=True)[1] == "node_modules/vitest/vitest.mjs"


def test_cache_and_environment_vars_are_supervisor_owned(tmp_path, monkeypatch):
    root = project(tmp_path)
    with pytest.raises(EnvironmentError, match="outside"):
        CleanEnvironmentManager(root / "cache", Installer()).prepare(root, "python", tool_versions=VERSIONS)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "private")
    monkeypatch.setenv("PYTHONPATH", "poison")
    env = minimal_environment()
    assert "ANTHROPIC_API_KEY" not in env and "PYTHONPATH" not in env
    (root / "uv.lock").unlink()
    with pytest.raises(EnvironmentError, match="DECLARATION_MISSING"):
        CleanEnvironmentManager(tmp_path / "cache", Installer()).prepare(root, "python", tool_versions=VERSIONS)
