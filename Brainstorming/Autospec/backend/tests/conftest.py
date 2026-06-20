import pytest

from autospec.config import settings
from autospec.orchestrator.pipeline import Pipeline, _PERSIST_EXECUTOR


@pytest.fixture(scope="session", autouse=True)
def _isolate_real_workspace(tmp_path_factory):
    """Guarantee the real ``Autospec/workspace`` is NEVER written by the suite.

    The per-test ``tmp_workspace`` fixture redirects ``workspace_root`` to a
    per-test dir, but state persistence runs on a background thread
    (``_PERSIST_EXECUTOR``) — a pipeline bg task can flush a state write AFTER
    its test finished, once the per-test ``monkeypatch`` has already reverted
    ``workspace_root`` to the real value. Pinning the session-wide default to a
    temp dir means any such late write lands here, not in the developer's real
    workspace (that's why deterministic-id test projects used to pile up there).
    """
    session_root = tmp_path_factory.mktemp("autospec-test-workspace")
    original = settings.workspace_root
    settings.workspace_root = session_root
    yield
    # Drain any state writes still queued on the shared executor before we
    # restore the real path, so none escapes to the real workspace at shutdown.
    _PERSIST_EXECUTOR.shutdown(wait=True)
    settings.workspace_root = original


@pytest.fixture(autouse=True)
def tmp_workspace(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "workspace_root", tmp_path / "workspace")
    monkeypatch.setattr(settings, "max_parallel_devs", 2)
    monkeypatch.setattr(settings, "dev_max_attempts", 2)
    # Hermetic tests: a developer's backend/.env (loaded by config at import) must
    # not change pipeline flow. Pin the flags that add agent calls / phases to
    # their safe defaults; a test exercising one re-enables it via monkeypatch.
    monkeypatch.setattr(settings, "brainstorm_assist_enabled", False)
    monkeypatch.setattr(settings, "streams_enabled", False)
    return tmp_path


@pytest.fixture
def green_pytest(monkeypatch):
    async def _arun_pytest(self):
        return True, "all green", {}

    monkeypatch.setattr(Pipeline, "_arun_pytest", _arun_pytest)


async def wait_until(predicate, timeout=20.0, interval=0.01):
    import asyncio

    deadline = asyncio.get_event_loop().time() + timeout
    while not predicate():
        if asyncio.get_event_loop().time() > deadline:
            raise TimeoutError("condition not met in time")
        await asyncio.sleep(interval)
