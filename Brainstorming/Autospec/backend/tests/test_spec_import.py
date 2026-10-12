"""Tests of spec import (I3): an imported brief seeds the project and skips the
PM interview, going straight to planning."""

import asyncio
import json
import os
from pathlib import Path, PureWindowsPath

import httpx
import pytest

from autospec.agents.runner import FakeRunner
from autospec.api import server
from autospec.models import PipelinePhase, ProjectState
from autospec.orchestrator.pipeline import Pipeline
from autospec.orchestrator import workspace
from autospec.spec_import import MAX_BRIEF_CHARS, parse_spec_import

from .conftest import wait_until

PO = json.dumps({"epics": [{"id": "EPIC-1", "title": "E", "stories": [
    {"id": "US-1", "title": "S", "description": "d", "acceptance_criteria": ["c"],
     "gherkin": "Feature: F Scenario s Given a When b Then c", "depends_on": []}]}]})
QA = json.dumps({"message": "Trivial.", "tests": []})
DEV = json.dumps({"status": "green", "summary": "ok", "files": []})


def test_parse_spec_import_trims_and_caps():
    assert parse_spec_import("  hello  ") == "hello"
    assert parse_spec_import(None) == ""
    assert len(parse_spec_import("x" * (MAX_BRIEF_CHARS + 100))) == MAX_BRIEF_CHARS


async def test_imported_brief_skips_interview(green_pytest):
    state = ProjectState(id="p-i3", name="m", goal="g", brief="# Imported brief")
    pipeline = Pipeline(state, FakeRunner([PO, QA, DEV]))  # no PM interview reply queued
    pipeline.start()
    await wait_until(lambda: pipeline.state.phase in (PipelinePhase.DONE, PipelinePhase.ERROR, PipelinePhase.NEEDS_ATTENTION))
    assert pipeline.state.phase == PipelinePhase.DONE, pipeline.state.error
    assert pipeline.state.brief == "# Imported brief"
    assert any(s.status.value == "done" for s in pipeline.state.stories)


@pytest.mark.skipif(os.name != "nt", reason="Windows extended path representation")
@pytest.mark.parametrize("prefix_on", ["root", "child"])
def test_scaffold_accepts_equivalent_windows_resolved_prefixes(tmp_path, monkeypatch, prefix_on):
    """Reproduce the two spellings observed during concurrent ws creation.

    Real files stay under tmp_path. Only the Windows path spelling returned by
    resolve is controlled, so containment must hold for both equivalent forms.
    """
    root = tmp_path / "new-workspace"
    target = root / "application"
    original_resolve = Path.resolve
    root.mkdir()
    def resolve_with_observed_prefix(path, *args, **kwargs):
        resolved = original_resolve(path, *args, **kwargs)
        plain = str(resolved).removeprefix("\\\\?\\")
        expected = str(root if prefix_on == "root" else target)
        return Path("\\\\?\\" + plain) if plain == expected else Path(plain)
    monkeypatch.setattr(Path, "resolve", resolve_with_observed_prefix)
    assert workspace._inside(root, target) == target
    workspace._mkdir(root, target)
    assert target.is_dir()


@pytest.mark.parametrize("outside", [False, True])
def test_scaffold_extended_unc_comparison_still_rejects_outside_paths(tmp_path, monkeypatch, outside):
    """Compare Windows UNC spellings on every platform, without a network share."""
    root = tmp_path / "workspace"
    target = root / "application"
    class ResolvedUNC(PureWindowsPath):
        def resolve(self):
            location = "outside" if outside else "workspace"
            return PureWindowsPath(f"\\\\?\\UNC\\server\\share\\{location}\\application")
    monkeypatch.setattr(Path, "resolve", lambda self: ResolvedUNC("\\\\server\\share\\workspace"))
    if outside:
        with pytest.raises(ValueError, match="hors du projet"):
            workspace._inside(root, target)
    else:
        assert workspace._inside(root, target) == target


async def test_create_endpoint_with_imported_brief(green_pytest):
    server.pipelines.clear()
    server.set_runner(FakeRunner([PO, QA, DEV]))
    transport = httpx.ASGITransport(app=server.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.post(
            "/api/projects", json={"goal": "g", "name": "imp", "brief": "# Spec doc"}
        )
        pid = r.json()["id"]
        assert r.json()["state"]["brief"] == "# Spec doc"

        async def done():
            rr = await client.get(f"/api/projects/{pid}")
            return rr.json()["phase"] == "done"

        for _ in range(2000):
            if await done():
                break
            await asyncio.sleep(0.01)
        assert await done()
