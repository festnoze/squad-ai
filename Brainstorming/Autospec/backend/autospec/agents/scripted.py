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

_DEV_FRONTEND_GREEN = json.dumps(
    {
        "status": "green",
        "summary": "Composant React + tests Vitest (mode démo) — suite verte et build OK.",
        "files": ["src/Counter.tsx", "src/Counter.test.tsx"],
        "test_results": [
            {"id": "UT-1", "status": "green", "nodeids": ["src/Counter.test.tsx::affiche le compteur"]}
        ],
    },
    ensure_ascii=False,
)

_ARCHITECT = json.dumps(
    {
        "message": "Design (démo).",
        "design": "## Architecture\nCouche service + repository (mode démo).",
    },
    ensure_ascii=False,
)

# SK-2: the decomposer splits a backend story into layered sub-tasks (built in
# parallel worktrees then aggregated). Two tasks, the façade depending on the service.
_DECOMPOSE = json.dumps(
    {
        "message": "Découpage par couche (mode démo).",
        "tasks": [
            {
                "id": "T-1",
                "layer": "application",
                "skill": "service-search-or-create",
                "title": "Service de calcul",
                "description": "Service qui calcule le résultat.",
                "acceptance_criteria": ["AC-1"],
                "gherkin": "Feature: Service\n  Scenario: Calcul\n    Given deux nombres\n    When le service calcule\n    Then le résultat est correct",
                "depends_on": [],
            },
            {
                "id": "T-2",
                "layer": "facade",
                "skill": "endpoint-search-or-create",
                "title": "Exposition du calcul",
                "description": "Point d'entrée qui appelle le service.",
                "acceptance_criteria": ["AC-1"],
                "gherkin": "Feature: Façade\n  Scenario: Appel\n    Given le service\n    When j'appelle la façade\n    Then le résultat est renvoyé",
                "depends_on": ["T-1"],
            },
        ],
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

_IMPACT = json.dumps(
    {
        "message": "Feedback analysé : nouvelle story créée (mode démo).",
        "action": "new_stories",
        "epic": {"id": "EPIC-FB", "title": "Retours utilisateur", "description": "Changements issus du feedback."},
        "stories": [
            {
                "id": "US-FB-1",
                "title": "Prendre en compte le feedback",
                "description": "En tant qu'utilisateur, je veux que mon retour soit intégré afin d'améliorer le produit.",
                "acceptance_criteria": ["Le feedback est traité."],
                "gherkin": "Feature: Feedback\n  Scenario: Prise en compte\n    Given un feedback utilisateur\n    When il est analysé\n    Then une story est créée",
                "depends_on": [],
                "priority": 1,
            }
        ],
    },
    ensure_ascii=False,
)

# ST-15: stream-aware impact — a feedback that adds a web UI creates the
# `frontend` stream and a front task wired (depends_on) to an existing back US.
_IMPACT_STREAMS = json.dumps(
    {
        "message": "Feedback analysé : ajout d'une UI web (nouveau stream frontend).",
        "action": "new_stories",
        "add_streams": ["frontend"],
        "epic": {"id": "EPIC-UI", "title": "Interface web", "description": "UI ajoutée suite au feedback."},
        "stories": [
            {
                "id": "US-UI-1",
                "title": "Écran web du produit",
                "description": "En tant qu'utilisateur, je veux une UI web afin d'utiliser le produit dans le navigateur.",
                "acceptance_criteria": ["L'écran affiche le résultat de l'API."],
                "gherkin": "Feature: UI web\n  Scenario: Affichage\n    Given l'API back\n    When j'ouvre l'écran\n    Then le résultat s'affiche",
                "depends_on": [],
                "priority": 1,
                "stream": "",
                "tasks": [
                    {
                        "id": "T-UI-1",
                        "stream": "frontend",
                        "title": "Composant React principal",
                        "description": "Écran React qui consomme l'API backend.",
                        "acceptance_criteria": ["Le composant rend le résultat de l'API."],
                        "gherkin": "Feature: Composant\n  Scenario: Rendu\n    Given des données\n    When le composant rend\n    Then le résultat est visible",
                        "depends_on": ["US-1"],
                    }
                ],
            }
        ],
    },
    ensure_ascii=False,
)

# ST-4: the architect picks a backend + frontend stream (demo).
_STREAMS = json.dumps(
    {
        "streams": [
            {"id": "backend", "kind": "backend", "language": "python", "file_root": ""},
            {"id": "frontend", "kind": "frontend", "language": "react", "file_root": "frontend"},
        ],
        "rationale": "Backend API + interface web React (mode démo).",
    },
    ensure_ascii=False,
)

# ST-5: the stream-aware PO plan — one US decomposed into a backend task and a
# frontend task that depends on it (cross-stream dependency).
_PO_PLAN_STREAMS = json.dumps(
    {
        "epics": [
            {
                "id": "EPIC-1",
                "title": "Cœur applicatif",
                "description": "Fonctionnalités de base, réparties par stream.",
                "stories": [
                    {
                        "id": "US-1",
                        "title": "Additionner deux nombres (API + UI)",
                        "description": "En tant qu'utilisateur, je veux additionner deux nombres via une UI web afin d'obtenir leur somme.",
                        "acceptance_criteria": ["La somme de 2 et 3 vaut 5."],
                        "gherkin": "Feature: Addition\n  Scenario: Somme simple\n    Given le nombre 2\n    And le nombre 3\n    When je les additionne\n    Then j'obtiens 5",
                        "depends_on": [],
                        "priority": 1,
                        "stream": "",
                        "tasks": [
                            {
                                "id": "T-1",
                                "stream": "backend",
                                "title": "Exposer l'addition via l'API",
                                "description": "Endpoint de calcul de la somme.",
                                "acceptance_criteria": ["GET /add?a=2&b=3 renvoie 5."],
                                "gherkin": "Feature: API addition\n  Scenario: Somme\n    Given a=2 et b=3\n    When j'appelle l'API\n    Then la réponse est 5",
                                "depends_on": [],
                            },
                            {
                                "id": "T-2",
                                "stream": "frontend",
                                "title": "Écran d'addition",
                                "description": "Formulaire React qui appelle l'API et affiche la somme.",
                                "acceptance_criteria": ["La somme s'affiche à l'écran."],
                                "gherkin": "Feature: UI addition\n  Scenario: Affichage\n    Given deux champs\n    When je valide\n    Then la somme s'affiche",
                                "depends_on": ["T-1"],
                            },
                        ],
                    },
                    {
                        "id": "US-2",
                        "title": "Soustraire deux nombres",
                        "description": "En tant qu'utilisateur, je veux soustraire deux nombres afin d'obtenir leur différence.",
                        "acceptance_criteria": ["La différence de 5 et 3 vaut 2."],
                        "gherkin": "Feature: Soustraction\n  Scenario: Différence simple\n    Given le nombre 5\n    And le nombre 3\n    When je les soustrais\n    Then j'obtiens 2",
                        "depends_on": ["US-1"],
                        "priority": 2,
                        "stream": "backend",
                        "tasks": [],
                    },
                ],
            }
        ]
    }
)

_LANGUAGE = json.dumps(
    {
        "language": "go",
        "complexity": 3,
        "criticality": 2,
        "rationale": "Application de complexité moyenne (mode démo) — Go par défaut.",
    },
    ensure_ascii=False,
)

_COMPONENTS = json.dumps(
    {
        "message": "Stack par défaut proposée (mode démo).",
        "components": [
            {"id": "backend", "kind": "backend", "name": "API backend", "technology": "Python + FastAPI", "rationale": "logique métier et API", "optional": False},
            {"id": "frontend", "kind": "frontend", "name": "Interface web", "technology": "React + Vite", "rationale": "interface utilisateur", "optional": False},
            {"id": "db", "kind": "database", "name": "Base de données", "technology": "PostgreSQL", "rationale": "persistance", "optional": True},
        ],
    },
    ensure_ascii=False,
)

_TECH_WRITER = json.dumps(
    {
        "message": "README généré (mode démo).",
        "readme": "# Projet généré\n\nApplication de démonstration générée par Autospec.\n\n## Lancement\n\n```\nuv run python main.py\n```\n\n## Tests\n\n```\nuv run pytest\n```\n",
    },
    ensure_ascii=False,
)

_EVALUATOR = json.dumps(
    {
        "message": "Produit exercé (mode démo) — un souci d'intégration relevé.",
        "findings": [
            {
                "id": "FND-1",
                "severity": "medium",
                "kind": "integration",
                "title": "Addition et soustraction ne se composent pas",
                "detail": "Le CLI n'enchaîne pas les deux opérations (mode démo).",
            }
        ],
    },
    ensure_ascii=False,
)

_RETRO = json.dumps(
    {
        "message": "Rétrospective (mode démo).",
        "lessons": [
            "Mocker explicitement les collaborateurs directs dans les tests de service.",
            "Câbler chaque nouvelle opération dans main.py dès la story.",
        ],
        "recommendations": ["Conserver le parallélisme à 2 développeurs (mode démo)."],
    },
    ensure_ascii=False,
)

_ASSESS = json.dumps(
    {
        "maturity": "vague",
        "rationale": "Idée ouverte à explorer avant de spécifier (mode démo).",
        "techniques": ["What If Scenarios", "First Principles Thinking"],
    },
    ensure_ascii=False,
)

# brainstorm_auto_answer returns PLAIN text (the AI playing the product owner).
_AUTO_ANSWER = (
    "Cible : usage personnel, MVP minimal en CLI (mode démo) — priorité à l'ajout "
    "et au listing des éléments."
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
        model: str | None = None,
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
        if "PROCESSUS OBLIGATOIRE FRONTEND" in prompt:  # dev_story_frontend (ST-7)
            return _DEV_FRONTEND_GREEN
        if "PROCESSUS OBLIGATOIRE" in prompt:  # dev_story / dev_revise
            return _DEV_GREEN
        if "l'évaluateur d'un pipeline" in prompt:  # evaluator_probe (E6)
            return _EVALUATOR
        if "agent de rétrospective" in prompt:  # retro_review (E7)
            return _RETRO
        if "analyste d'impact" in prompt:  # feedback_impact
            # ST-15: the stream-aware impact adds this marker → grow the product
            # with a new frontend stream + a front task wired to the back.
            if "ÉVOLUTION MULTI-STREAM" in prompt:
                return _IMPACT_STREAMS
            return _IMPACT
        if "MATURITÉ de l'idée" in prompt:  # assess_idea (B-IDEA)
            return _ASSESS
        if "PORTEUR du projet" in prompt:  # brainstorm_auto_answer (B-IDEA)
            return _AUTO_ANSWER
        if "découpe le travail en\nSTREAMS" in prompt or "STREAMS parallélisables" in prompt:
            return _STREAMS  # select_streams (ST-4)
        if "choisit le LANGAGE BACKEND" in prompt:  # language_proposal (L2)
            return _LANGUAGE
        if "agent solutionneur" in prompt:  # components_proposal
            return _COMPONENTS
        if "tech-writer d'un pipeline" in prompt:  # tech_writer
            return _TECH_WRITER
        if "architecte de tests" in prompt:  # qa_test_plan
            match = _QA_STORY_RE.search(prompt)
            return _qa_plan(match.group(1) if match else "US-1")
        if "en SOUS-TÂCHES par COUCHE" in prompt:  # decompose_story (SK-2)
            return _DECOMPOSE
        if "design technique CONCIS" in prompt:  # architect_design
            return _ARCHITECT
        if "PO/Scrum Master" in prompt:  # po_plan / po_revise
            # ST-5: the stream-aware plan adds this marker; branch to the
            # decomposed reply, keeping the flag-off PO reply intact.
            if "DÉCOUPAGE MULTI-STREAM" in prompt:
                return _PO_PLAN_STREAMS
            return _PO_PLAN
        if "analyste/explorateur" in prompt:  # analyst_explore
            return _ANALYST
        # default: PM (interview, brainstorm or brief-for-feature) -> a brief
        return _PM_BRIEF
