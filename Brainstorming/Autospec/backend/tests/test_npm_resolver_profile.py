"""Pinned supervisor npm profile; native probes never execute source on host."""
import hashlib
import json
import os
from pathlib import Path

import pytest

from autospec.orchestrator import validation_environment as module
from autospec.orchestrator.validation_environment import LinuxEnvironmentManager


def test_npm_profile_checks_primary_integrity_before_extraction_or_execution():
    script = module._npm_profile_script()
    assert module.NPM_VERSION == "11.6.4"
    assert module.NPM_INTEGRITY.startswith("sha512-")
    assert json.dumps(module.NPM_VERSION) in script
    assert json.dumps(module.NPM_INTEGRITY) in script
    assert "redirect:'error'" in script and "size>20000000" in script
    assert script.index("integrity mismatch") < script.index("writeFileSync") < script.index("spawnSync('/bin/tar'")
    assert script.index("version mismatch") < script.index("spawnSync(process.execPath")
    assert "--force" not in script and "--legacy-peer-deps" not in script


def test_profile_argv_stays_literal_and_rejects_non_npm_dispatch():
    literal = "fixture@1.0.0; must-never-be-a-shell-command"
    args = module._node_npm_command(["npm", "install", "--ignore-scripts", literal])
    assert args[:3] == ["/usr/local/bin/node", "--input-type=commonjs", "-e"]
    assert args[4:] == ["--", "install", "--ignore-scripts", literal]
    assert literal not in args[3]
    with pytest.raises(RuntimeError, match="literal factory npm"):
        module._node_npm_command(["sh", "-c", "anything"])


@pytest.mark.parametrize("mode", ["test", "runtime"])
def test_node_recipe_provisions_trusted_tool_before_product_manifest(tmp_path, mode):
    manifest = tmp_path / "package.json"
    manifest.write_text("{}")
    recipe = LinuxEnvironmentManager._recipe("node@sha256:" + "a" * 64, "node", mode, "b" * 64, manifest)
    assert module.RECIPE_VERSION >= 5
    assert recipe.index("__autospec_provision_only__") < recipe.index("COPY package.json")
    assert 'ENV PATH="/opt/autospec-npm/bin:$PATH"' in recipe
    assert "RUN npm ci --ignore-scripts --no-audit --no-fund --userconfig=/dev/null" in recipe
    assert "--force" not in recipe and "--legacy-peer-deps" not in recipe
    assert "COPY ." not in recipe and "USER 65532:65532" in recipe
    first_run = next(line[4:] for line in recipe.splitlines() if line.startswith("RUN ["))
    assert json.loads(first_run)[-2:] == ["--", "__autospec_provision_only__"]
    assert "--omit=dev" in recipe if mode == "runtime" else "--include=dev" in recipe


@pytest.mark.parametrize("name,value", [("NPM_VERSION", "11.6.3"), ("NPM_INTEGRITY", "sha512-wrong")])
def test_changed_tool_identity_changes_recipe_template_hash(tmp_path, monkeypatch, name, value):
    manifest = tmp_path / "package.json"
    manifest.write_text("{}")
    original = LinuxEnvironmentManager._recipe("node@sha256:" + "a" * 64, "node", "test", "FINGERPRINT", manifest)
    monkeypatch.setattr(module, name, value)
    changed = LinuxEnvironmentManager._recipe("node@sha256:" + "a" * 64, "node", "test", "FINGERPRINT", manifest)
    assert hashlib.sha256(original.encode()).hexdigest() != hashlib.sha256(changed.encode()).hexdigest()


def manifests(root):
    data = {"name": "npm-profile-proof", "version": "1.0.0", "private": True,
            "scripts": {"postinstall": "node -e \"require('fs').writeFileSync('hook-ran.txt','unsafe')\""},
            "devDependencies": {"vite": "6.4.4", "vitest": "4.1.11"}}
    (root / "package.json").write_text(json.dumps(data))
    (root / "main.js").write_text("throw Error('must never execute during resolution')")
    (root / ".env").write_text("SECRET=fixture-not-copied")
    (root / ".npmrc").write_text("registry=http://127.0.0.1:1/\n")
    return (root / "package.json").read_bytes()


native = pytest.mark.skipif(os.environ.get("AUTOSPEC_NATIVE_NPM_PROFILE") != "1",
                            reason="explicit owned Linux npm resolver/build profile opt-in")


@native
def test_real_pinned_npm_resolves_vitest4_and_runs_version_netnone(tmp_path):
    from autospec.orchestrator.sandbox import run_isolated
    original = manifests(tmp_path)
    manager = LinuxEnvironmentManager(tmp_path.parent / "npm-profile-cache", timeout=300)
    lock = manager.ensure_lock(tmp_path, "node")
    parsed = json.loads(lock.read_bytes())
    assert parsed["packages"]["node_modules/vitest"]["version"] == "4.1.11"
    assert (tmp_path / "package.json").read_bytes() == original
    assert not (tmp_path / "hook-ran.txt").exists()
    receipt = {}
    environment = manager.prepare(tmp_path, "node", receipt=receipt)
    assert receipt["status"] in {"cache_attested", "build_attested"}
    assert receipt["inputs"]["version"] == module.RECIPE_VERSION
    stage = module.snapshot_product(tmp_path, tmp_path.parent / (tmp_path.name + "-version-stage"))
    rc, out, err = run_isolated(["npm", "--version"], str(stage), environment.image, timeout=30)
    assert rc == 0, err
    assert out.strip() == "11.6.4"
    evidence = os.environ.get("AUTOSPEC_NPM_PROFILE_EVIDENCE")
    if evidence:
        target = Path(evidence)
        target.mkdir(parents=True, exist_ok=True)
        (target / "native-profile.json").write_text(json.dumps({"scope": "actual supervisor npm profile, not product acceptance",
            "npm_version": out.strip(), "npm_integrity": module.NPM_INTEGRITY,
            "manifest_sha256": hashlib.sha256(original).hexdigest(), "lock_sha256": hashlib.sha256(lock.read_bytes()).hexdigest(),
            "version_probe_return_code": rc, "netnone_version_probe": True, "environment": receipt}, indent=2))
        (target / "native-profile-package.json").write_bytes(original)
        (target / "native-profile-package-lock.json").write_bytes(lock.read_bytes())


@native
def test_real_wrong_supervisor_npm_integrity_never_exports_lock(tmp_path, monkeypatch):
    original = manifests(tmp_path)
    lock = tmp_path / "package-lock.json"
    retained = b'{"lockfileVersion":3,"packages":{}}'
    lock.write_bytes(retained)
    monkeypatch.setattr(module, "NPM_INTEGRITY", "sha512-" + "A" * 86 + "==")
    manager = LinuxEnvironmentManager(tmp_path.parent / "npm-profile-negative-cache", timeout=60)
    with pytest.raises(RuntimeError, match="Factory npm integrity mismatch"):
        manager.regenerate_lock(tmp_path, "node")
    assert lock.read_bytes() == retained
    assert (tmp_path / "package.json").read_bytes() == original
    assert not (tmp_path / "hook-ran.txt").exists()
