"""Proactive Technical Stories: the PO (and its critic via po_revise) can emit a
Technical Story directly in the plan — not only the reactive split-on-failure."""

import json

from autospec.config import settings
from autospec.orchestrator import streams as work_streams

from tests.test_pipeline import make_pipeline


def _plan_with_ts() -> str:
    return json.dumps({
        "epics": [{
            "id": "EPIC-1", "title": "E", "description": "",
            "stories": [
                {
                    "id": "US-1", "title": "Feature",
                    "description": "En tant qu'utilisateur, je veux la feature.",
                    "acceptance_criteria": ["c"],
                    "gherkin": "Feature: F\n  Scenario: S\n    Given a\n    When b\n    Then c",
                    "stream": "backend", "depends_on": ["TS-1"],
                },
                {
                    "id": "TS-1", "title": "Socle données", "technical": True,
                    "contract": "Le repository expose aget_x/acreate_x testés.",
                    "depends_on": [],
                    "tasks": [
                        {"id": "T-a", "stream": "backend", "title": "entité",
                         "file_globs": ["pkg/entity.py"]},
                        {"id": "T-b", "stream": "backend", "title": "repository",
                         "file_globs": ["pkg/repo.py"], "depends_on": ["T-a"]},
                    ],
                },
            ],
        }]
    })


async def test_po_plan_emits_technical_story(monkeypatch):
    monkeypatch.setattr(settings, "streams_enabled", True)
    pipeline, _ = make_pipeline([_plan_with_ts()])
    pipeline.state.brief = "brief"
    await pipeline._aplan_phase()

    ts = pipeline.state.story("TS-1")
    assert ts.technical is True
    assert ts.contract.startswith("Le repository")
    assert ts.gherkin == ""                      # no functional Gherkin
    assert [t.id for t in ts.tasks] == ["T-a", "T-b"]

    us1 = pipeline.state.story("US-1")
    assert us1.technical is False                # the functional US stays functional

    # US-1 depends on the TS → the work-graph resolves to the TS's leaf tasks.
    graph = work_streams.build_work_graph(pipeline.state)
    assert set(graph.items["US-1"].depends_on) >= {"T-a", "T-b"}


async def test_technical_flag_ignored_without_streams(monkeypatch):
    # Without streams a TS can't carry tasks → the flag is dropped (legacy-safe).
    monkeypatch.setattr(settings, "streams_enabled", False)
    pipeline, _ = make_pipeline([_plan_with_ts()])
    pipeline.state.brief = "brief"
    await pipeline._aplan_phase()
    assert pipeline.state.story("TS-1").technical is False


def test_plan_criteria_mentions_technical_stories():
    from autospec.agents import prompts

    c = prompts.PLAN_CRITERIA.lower()
    assert "technical stor" in c and "contract" in c
