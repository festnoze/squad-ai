import pytest

from autospec.config import settings
from autospec.orchestrator.pipeline import Pipeline


@pytest.fixture(autouse=True)
def tmp_workspace(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "workspace_root", tmp_path / "workspace")
    monkeypatch.setattr(settings, "max_parallel_devs", 2)
    monkeypatch.setattr(settings, "dev_max_attempts", 2)
    return tmp_path


@pytest.fixture
def green_pytest(monkeypatch):
    async def _arun_pytest(self):
        return True, "all green"

    monkeypatch.setattr(Pipeline, "_arun_pytest", _arun_pytest)


async def wait_until(predicate, timeout=5.0, interval=0.01):
    import asyncio

    deadline = asyncio.get_event_loop().time() + timeout
    while not predicate():
        if asyncio.get_event_loop().time() > deadline:
            raise TimeoutError("condition not met in time")
        await asyncio.sleep(interval)
