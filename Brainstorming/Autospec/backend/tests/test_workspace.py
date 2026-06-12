from autospec.models import ProjectState
from autospec.orchestrator import workspace
from autospec.storage import workspace_dir


def make_state() -> ProjectState:
    return ProjectState(id="proj-1", name="Demo App", goal="ship something")


def test_scaffold_writes_gitignore_protecting_venv():
    state = make_state()
    workspace.scaffold(state)

    gitignore = workspace_dir(state.id) / ".gitignore"
    assert gitignore.exists()
    assert ".venv/" in gitignore.read_text(encoding="utf-8")
