"""Skill library: registry, prompt catalog, and per-workspace seeding (SK-1).

Skills are small, progressively-disclosed capability files (``SKILL.md`` +
``references/``) the QA/Dev agents load on demand instead of inlining every
convention in the prompt. Two delivery paths (hybrid):

- **native** — the bundled library is copied into each workspace's
  ``.claude/skills/`` so the headless ``claude`` CLI auto-discovers them (its
  native Skill tool, progressive disclosure → the body/references load only when
  the agent decides a skill is relevant, keeping the base prompt small);
- **catalog** — a compact name/description block is injected into the QA/Dev
  prompt for EVERY provider (so OpenAI/Ollama backends, which have no native
  Skill tool, still know what is available and how the generated app is shaped).

OFF by default; gated by the pipeline's effective profile/settings plus role flag.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from ..config import settings

# Curated skill set. ``name`` MUST match the SKILL.md folder under the bundled
# library (``settings.skills_dir``). ``roles`` controls which agent sees a skill
# in its catalog; ``summary``/``when`` build the compact prompt block.
SKILL_REGISTRY: list[dict] = [
    {
        "name": "architecture",
        "roles": ("qa", "dev"),
        "summary": "Architecture backend en 3 couches (façade → application → "
        "infrastructure), conventions de nommage (préfixe async `a`), "
        "enregistrement des composants.",
        "when": "placer une classe dans la bonne couche, nommer/enregistrer un composant",
    },
    {
        "name": "db-entity-change",
        "roles": ("dev",),
        "summary": "Créer/modifier une entité de persistance + sa migration "
        "(couche infrastructure).",
        "when": "ajouter une table/entité/colonne, changer le schéma de données",
    },
    {
        "name": "repo-search-or-create",
        "roles": ("dev",),
        "summary": "Réutiliser ou créer une méthode de repository (accès données, DRY).",
        "when": "lire/écrire en base : get/create/update/delete sur une entité",
    },
    {
        "name": "service-search-or-create",
        "roles": ("dev",),
        "summary": "Réutiliser ou créer une méthode de service (cas d'usage, "
        "couche application).",
        "when": "implémenter une règle métier / orchestrer des repositories",
    },
    {
        "name": "endpoint-search-or-create",
        "roles": ("dev",),
        "summary": "Réutiliser ou créer un endpoint FastAPI + modèles "
        "request/response (couche façade).",
        "when": "exposer un cas d'usage en HTTP / ajouter une route",
    },
    {
        "name": "error-code-management",
        "roles": ("dev",),
        "summary": "Codes d'erreur centralisés + classes d'exception + catalogue "
        "de messages.",
        "when": "lever/ajouter une erreur métier, gérer un cas d'échec",
    },
    {
        "name": "test-generator",
        "roles": ("qa", "dev"),
        "summary": "Générer des tests unitaires/intégration/e2e par couche selon "
        "les conventions (`test_a{action}_{entity}_{scenario}`).",
        "when": "écrire des tests pour un router/service/repository ou un flux complet",
    },
    {
        "name": "bdd-gherkin",
        "roles": ("qa",),
        "summary": "Décomposer une acceptance Gherkin en tests unitaires "
        "outside-in/London-school par couche + câblage pytest-bdd + liaison nodeids.",
        "when": "transformer un scénario Gherkin en plan de tests par couche",
    },
    {
        "name": "skill-creator",
        "roles": ("qa", "dev"),
        "summary": "Créer une nouvelle skill (SKILL.md + references) pour étendre l'usine.",
        "when": "un savoir-faire récurrent mérite d'être capitalisé en skill",
    },
    {
        # P4: used by the independence-judge agent, NOT injected into qa/dev
        # catalogs (its own `independence` role keeps their prompts unchanged).
        "name": "task-independence",
        "roles": ("independence",),
        "summary": "Certifier quelles tâches décomposées peuvent se construire en "
        "parallèle (fichiers disjoints) et sérialiser/fusionner les autres avant "
        "le scheduler de streams.",
        "when": "décider si deux tâches d'un même stream peuvent tourner en parallèle",
    },
]


def skills_for_role(role: str) -> list[dict]:
    """Curated skills visible to an agent role ('qa' / 'dev')."""
    return [s for s in SKILL_REGISTRY if role in s["roles"]]


def catalog_block(role: str) -> str:
    """Compact "available skills" block injected into the QA/Dev prompt. Empty
    string when no skill targets the role (so the prompt stays byte-identical)."""
    skills = skills_for_role(role)
    if not skills:
        return ""
    lines = [
        "\nCOMPÉTENCES DISPONIBLES (skills) — obligatoires quand applicables.",
        "Chaque skill est un mode d'emploi réutilisable : charge-la À LA DEMANDE "
        "(outil Skill, ou lis `.claude/skills/<nom>/SKILL.md`) au lieu de tout "
        "réinventer. Si une story touche un déclencheur listé, applique la skill "
        "correspondante et mentionne son nom dans ton résumé ou tes fichiers de "
        "test. Ne charge que celles utiles à cette story :",
    ]
    for s in skills:
        lines.append(
            f"- `{s['name']}` — {s['summary']} "
            f"(OBLIGATOIRE si : {s['when']})."
        )
    return "\n".join(lines) + "\n"


def seed_skills(ws: Path) -> int:
    """Copy the bundled skill library into ``ws/.claude/skills`` (incl. any
    ``skill-rules.json`` / activation hook at its root, so the claude CLI can
    surface skills natively). Idempotent — existing files are left untouched —
    and best-effort: a missing source library is a silent no-op. Returns the
    number of files written. Blocking (file IO); call via :func:`aseed_skills`."""
    src = settings.skills_dir
    if not src.exists() or not src.is_dir():
        return 0
    dest_root = ws / ".claude" / "skills"
    written = 0
    for path in src.rglob("*"):
        if path.is_dir() or "__pycache__" in path.parts or path.suffix == ".pyc":
            continue
        target = dest_root / path.relative_to(src)
        if target.exists():
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(path.read_bytes())
        written += 1
    return written


async def aseed_skills(ws: Path) -> int:
    """Async wrapper around :func:`seed_skills` (stay off the event loop)."""
    return await asyncio.to_thread(seed_skills, ws)
