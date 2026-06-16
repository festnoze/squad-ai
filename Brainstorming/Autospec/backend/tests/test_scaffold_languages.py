"""L2g-2: per-language workspace scaffolding."""

from autospec.models import BackendLanguage, ProjectState
from autospec.orchestrator import workspace


def test_scaffold_python_is_default():
    state = ProjectState(id="py1", name="My App", goal="g")
    ws = workspace.scaffold(state)
    assert (ws / "pyproject.toml").exists()
    assert (ws / "main.py").exists()
    assert not (ws / "go.mod").exists()


def test_scaffold_go_module():
    state = ProjectState(id="go1", name="My App", goal="g", backend_language=BackendLanguage.GO)
    ws = workspace.scaffold(state)
    assert (ws / "go.mod").exists()
    assert "module my_app" in (ws / "go.mod").read_text(encoding="utf-8")
    assert (ws / "main.go").exists()
    assert "package main" in (ws / "main.go").read_text(encoding="utf-8")
    # no Python artifacts leak into a Go workspace
    assert not (ws / "pyproject.toml").exists()


def test_scaffold_rust_crate():
    state = ProjectState(id="rs1", name="My App", goal="g", backend_language=BackendLanguage.RUST)
    ws = workspace.scaffold(state)
    assert (ws / "Cargo.toml").exists()
    assert 'name = "my_app"' in (ws / "Cargo.toml").read_text(encoding="utf-8")
    assert (ws / "src" / "main.rs").exists()
    assert not (ws / "pyproject.toml").exists()


def test_scaffold_is_idempotent():
    state = ProjectState(id="go2", name="App", goal="g", backend_language=BackendLanguage.GO)
    ws = workspace.scaffold(state)
    (ws / "go.mod").write_text("module custom\n\ngo 1.21\n", encoding="utf-8")
    workspace.scaffold(state)  # must not overwrite existing files
    assert "module custom" in (ws / "go.mod").read_text(encoding="utf-8")
