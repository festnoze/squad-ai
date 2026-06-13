"""Deterministic scripted agent backend for demo / e2e (no Claude CLI).

The runner recognises which BMAD agent is being driven from the task prompt and
returns canned JSON, so the whole pipeline (PM -> PO -> QA -> Dev) runs end to
end without any LLM. Used when AUTOSPEC_FAKE_AGENTS is set; pytest verification
is short-circuited separately in the pipeline.
"""

from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path

from ..config import settings
from .runner import AgentResult

_PM_BRIEF = json.dumps(
    {
        "type": "brief",
        "message": "Brief généré (mode démo).",
        "brief": "# Brief (démo)\nUne petite application de démonstration générée par Autospec.",
    }
)

_PO_PLAN = json.dumps(
    {
        "epics": [
            {
                "id": "EPIC-1",
                "title": "Cœur applicatif",
                "description": "Les fonctionnalités de base.",
                "stories": [
                    {
                        "id": "US-1",
                        "title": "Additionner deux nombres",
                        "description": "En tant qu'utilisateur, je veux additionner deux nombres afin d'obtenir leur somme.",
                        "acceptance_criteria": [
                            "La somme de 2 et 3 vaut 5.",
                            "L'addition est commutative.",
                        ],
                        "gherkin": "Feature: Addition\n  Scenario: Somme simple\n    Given le nombre 2\n    And le nombre 3\n    When je les additionne\n    Then j'obtiens 5",
                        "depends_on": [],
                        "priority": 1,
                    },
                    {
                        "id": "US-2",
                        "title": "Soustraire deux nombres",
                        "description": "En tant qu'utilisateur, je veux soustraire deux nombres afin d'obtenir leur différence.",
                        "acceptance_criteria": ["La différence de 5 et 3 vaut 2."],
                        "gherkin": "Feature: Soustraction\n  Scenario: Différence simple\n    Given le nombre 5\n    And le nombre 3\n    When je les soustrais\n    Then j'obtiens 2",
                        "depends_on": ["US-1"],
                        "priority": 2,
                    },
                ],
            }
        ]
    }
)


def _qa_plan(story_id: str) -> str:
    return json.dumps(
        {
            "message": "Décomposition outside-in (mode démo).",
            "tests": [
                {
                    "id": "UT-1",
                    "layer": "service",
                    "description": "le service calcule correctement le résultat",
                    "mocks": [],
                    "file_hint": f"tests/unit/test_{story_id.lower().replace('-', '_')}_service.py",
                    "criteria": ["AC-1"],
                }
            ],
        }
    )


_DEV_GREEN = json.dumps(
    {
        "status": "green",
        "summary": "Implémentation et tests (mode démo) — suite verte.",
        "files": ["app/core.py", "tests/unit/test_service.py"],
        "test_results": [
            {"id": "UT-1", "status": "green", "nodeids": ["tests/unit/test_us1_service.py::test_service"]}
        ],
    }
)

_ARCHITECT = json.dumps(
    {
        "message": "Design (démo).",
        "design": "## Architecture\nCouche service + repository (mode démo).",
    },
    ensure_ascii=False,
)

_ANALYST = json.dumps(
    {
        "message": "Prochaine feature priorisée : la multiplication (mode démo).",
        "hypotheses": [
            {"id": "FH-1", "title": "Multiplier deux nombres", "rationale": "valeur élevée, simple", "value": 4, "complexity": 2},
            {"id": "FH-2", "title": "Diviser deux nombres", "rationale": "utile ensuite", "value": 3, "complexity": 3},
        ],
        "selected": "FH-1",
    }
)

_JUDGE = json.dumps(
    {"score": 90, "verdict": "Qualité suffisante (mode démo).", "reasons": ["ok"]},
    ensure_ascii=False,
)

_CRITIC = json.dumps(
    {"reflection": "Analyse (mode démo).", "issues": [], "suggestions": []},
    ensure_ascii=False,
)

# "User story à couvrir : US-3 — titre" in the QA prompt (prompts.qa_test_plan).
_QA_STORY_RE = re.compile(r"User story à couvrir : (\S+)")


class ScriptedRunner:
    """Returns canned JSON per agent, recognised from the task prompt."""

    async def arun(
        self,
        prompt: str,
        system_prompt: str,
        cwd: Path | None = None,
        session_id: str | None = None,
    ) -> AgentResult:
        if settings.demo_delay_s:
            await asyncio.sleep(settings.demo_delay_s)
        text = self._reply_for(prompt)
        return AgentResult(text=text, session_id="scripted-session")

    @staticmethod
    def _reply_for(prompt: str) -> str:
        # Judge/critic first: their prompts embed an arbitrary artifact (a plan,
        # a critique, an agent reply) that could quote other agents' markers.
        if "juge qualité d'une boucle de raffinement" in prompt:
            return _JUDGE
        if "à critiquer dans une boucle de raffinement" in prompt:
            return _CRITIC
        if "PROCESSUS OBLIGATOIRE" in prompt:  # dev_story / dev_revise
            return _DEV_GREEN
        if "architecte de tests" in prompt:  # qa_test_plan
            match = _QA_STORY_RE.search(prompt)
            return _qa_plan(match.group(1) if match else "US-1")
        if "design technique CONCIS" in prompt:  # architect_design
            return _ARCHITECT
        if "PO/Scrum Master" in prompt:  # po_plan / po_revise
            return _PO_PLAN
        if "analyste/explorateur" in prompt:  # analyst_explore
            return _ANALYST
        # default: PM (interview, brainstorm or brief-for-feature) -> a brief
        return _PM_BRIEF
