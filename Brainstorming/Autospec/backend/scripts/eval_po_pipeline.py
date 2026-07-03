"""Éval A/B du pipeline PO (RFC po-pipeline-v2 §6) — mono-passe vs multi-étapes.

Produit, pour chaque brief de référence, le plan dans les DEUX modes
(`AUTOSPEC_PO_PIPELINE=off` puis `on`) et compare la FORME des plans :
granularité des feuilles vs budget, taxonomie des critères (happy/edge/error/
boundary), présence/alignement du Gherkin, largeur de parallélisme du DAG,
Technical Stories — plus les compteurs de calibration (dégradations…).

C'est le critère d'activation du RFC : le pipeline ne mérite `on` par défaut
que si ses plans sont mesurablement mieux dimensionnés.

Usage (depuis backend/, venv actif) :
    uv run python scripts/eval_po_pipeline.py                 # scripted (démo, gratuit)
    AUTOSPEC_EVAL_PROVIDER=claude uv run python scripts/eval_po_pipeline.py   # agents réels
"""

from __future__ import annotations

import asyncio
import os
import sys
import tempfile
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")  # console Windows cp1252

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from autospec.agents.providers import make_runner  # noqa: E402
from autospec.agents.scripted import ScriptedRunner  # noqa: E402
from autospec.config import settings  # noqa: E402
from autospec.models import ProjectState  # noqa: E402
from autospec.orchestrator import streams as work_streams  # noqa: E402
from autospec.orchestrator.pipeline import Pipeline  # noqa: E402

BRIEFS = {
    "todo": (
        "Une application de todo-list : créer/terminer/supprimer des tâches, "
        "les lister par priorité, persistance locale JSON."
    ),
    "biblio": (
        "Un gestionnaire de bibliothèque : catalogue de livres, emprunts avec "
        "dates de retour, pénalités de retard, recherche par auteur/titre, "
        "import CSV et statistiques de lecture."
    ),
    "fullstack": (
        "Un tableau de bord de suivi de dépenses : API backend (comptes, "
        "transactions, catégories, budgets mensuels), calculs d'agrégats, "
        "et interface web (graphiques, filtres, alertes de dépassement)."
    ),
}


def _plan_metrics(state: ProjectState) -> dict:
    stories = [s for s in state.stories if not s.technical]
    ts = [s for s in state.stories if s.technical]
    tasks = [t for s in state.stories for t in s.tasks]
    leaves = tasks or stories
    budget = settings.task_file_budget

    def within_budget(item) -> bool:
        declared = len(getattr(item, "files_hint", []) or [])
        estimated = getattr(item, "estimated_files", 0)
        sized = declared or estimated
        return 0 < sized <= budget

    crits = [c for s in state.stories for c in s.acceptance_criteria]
    kinds = {getattr(c, "kind", "") for c in crits if getattr(c, "kind", "")}
    with_kind = sum(1 for c in crits if getattr(c, "kind", ""))
    gherkins = [s for s in stories if s.gherkin.strip()]

    graph = work_streams.build_work_graph(state)
    roots = sum(1 for item in graph if not item.depends_on)
    calib = state.calibration_for()
    return {
        "epics": len(state.epics),
        "stories": len(stories),
        "technical_stories": len(ts),
        "tasks": len(tasks),
        "feuilles ≤ budget (dimensionnées)": f"{sum(1 for l in leaves if within_budget(l))}/{len(leaves)}",
        "critères": len(crits),
        "critères taxonomisés": f"{with_kind}/{len(crits)}",
        "kinds couverts": ",".join(sorted(kinds)) or "—",
        "stories avec gherkin": f"{len(gherkins)}/{len(stories)}",
        "largeur DAG (racines //)": roots,
        "warnings graphe": len(work_streams.validate(state)),
        "dégradations pipeline": calib.degradations,
        "revue: points signalés": len(state.plan_review_issues),
    }


async def _arun_one(brief_slug: str, brief: str, mode: str, provider: str) -> dict:
    settings.po_pipeline = mode
    state = ProjectState(id=f"eval-{brief_slug}-{mode}", name=f"eval-{brief_slug}", goal=brief)
    state.brief = brief
    runner = ScriptedRunner() if provider == "scripted" else make_runner(provider)
    pipeline = Pipeline(state, runner)
    await pipeline._aplan_phase()
    return _plan_metrics(state)


async def amain() -> None:
    provider = os.environ.get("AUTOSPEC_EVAL_PROVIDER", "scripted").strip().lower()
    settings.workspace_root = Path(tempfile.mkdtemp(prefix="autospec-eval-"))
    settings.streams_enabled = True
    settings.fake_agents = provider == "scripted"

    print(f"# Éval A/B pipeline PO — provider={provider}")
    print(f"# budget fichiers/feuille = {settings.task_file_budget}\n")
    for slug, brief in BRIEFS.items():
        results = {}
        for mode in ("off", "on"):
            try:
                results[mode] = await _arun_one(slug, brief, mode, provider)
            except Exception as exc:  # un brief qui casse ne doit pas stopper l'éval
                results[mode] = {"ERREUR": str(exc)[:120]}
        keys = [k for k in results.get("on", results["off"]) if k != "ERREUR"] or ["ERREUR"]
        width = max(len(k) for k in keys) + 2
        print(f"## Brief « {slug} »")
        print(f"{'métrique'.ljust(width)}| mono-passe (off) | pipeline (on)")
        print(f"{'-' * width}|{'-' * 18}|{'-' * 14}")
        for k in keys:
            off_v = results["off"].get(k, results["off"].get("ERREUR", "—"))
            on_v = results["on"].get(k, results["on"].get("ERREUR", "—"))
            print(f"{k.ljust(width)}| {str(off_v).ljust(16)} | {on_v}")
        print()
    print(
        "Verdict attendu (RFC v2 §6) : le pipeline mérite `on` par défaut si les\n"
        "feuilles sont mieux dimensionnées, les critères taxonomisés et le DAG\n"
        "plus large, sans dégradations — à confirmer sur provider réel avec les\n"
        "compteurs de calibration post-build (splits réactifs, over-budget)."
    )


if __name__ == "__main__":
    asyncio.run(amain())
