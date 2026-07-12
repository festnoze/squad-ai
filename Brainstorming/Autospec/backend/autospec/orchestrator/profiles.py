"""Product profiles for Autospec delivery modes.

The historical configuration exposed many low-level flags. Profiles group the
high-impact ones by product shape so an operator can ask for "api", "cli" or
"fullstack" without memorizing which gates and skills should be active.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..models import ProjectState

PROFILE_NAMES = (
    "auto",
    "library-fast",
    "cli",
    "api",
    "web-ssr",
    "fullstack",
    "brownfield",
)


@dataclass(frozen=True)
class ProductProfile:
    name: str
    description: str
    overrides: dict[str, bool]


PROFILES: dict[str, ProductProfile] = {
    "library-fast": ProductProfile(
        name="library-fast",
        description="Small library/module: fastest loop, no runtime app gate.",
        overrides={
            "architecture_enabled": False,
            "components_enabled": False,
            "streams_enabled": False,
            "skills_enabled": True,
            "decompose_enabled": False,
            "smoke_run": False,
            "runtime_acceptance_enabled": False,
            "ui_tests_enabled": False,
            "docker_delivery": False,
        },
    ),
    "cli": ProductProfile(
        name="cli",
        description="Command-line product: tests plus CLI smoke execution.",
        overrides={
            "architecture_enabled": False,
            "components_enabled": False,
            "streams_enabled": False,
            "skills_enabled": True,
            "decompose_enabled": False,
            "smoke_run": True,
            "runtime_acceptance_enabled": False,
            "ui_tests_enabled": False,
            "docker_delivery": False,
        },
    ),
    "api": ProductProfile(
        name="api",
        description="Backend/API product: architecture, skills and app boot gate.",
        overrides={
            "architecture_enabled": True,
            "components_enabled": False,
            "streams_enabled": False,
            "skills_enabled": True,
            "decompose_enabled": True,
            "smoke_run": True,
            "runtime_acceptance_enabled": False,
            "ui_tests_enabled": False,
            "docker_delivery": True,
        },
    ),
    "web-ssr": ProductProfile(
        name="web-ssr",
        description="Server-rendered web app: backend smoke plus UI evidence.",
        overrides={
            "architecture_enabled": True,
            "components_enabled": False,
            "streams_enabled": False,
            "skills_enabled": True,
            "decompose_enabled": True,
            "smoke_run": True,
            "runtime_acceptance_enabled": True,
            "ui_tests_enabled": True,
            "docker_delivery": True,
            # Finding 5 : le chemin d'écriture (POST→DB) doit être exercé de bout
            # en bout — la définition-de-fini stricte force la vérification des
            # critères d'acceptation par le gate, pas seulement des tests unitaires.
            "definition_of_done_strict_criteria": True,
        },
    ),
    "fullstack": ProductProfile(
        name="fullstack",
        description="Backend plus frontend streams with runtime browser acceptance.",
        overrides={
            "architecture_enabled": True,
            "components_enabled": True,
            "streams_enabled": True,
            "skills_enabled": True,
            "decompose_enabled": True,
            "smoke_run": True,
            "runtime_acceptance_enabled": True,
            # Finding 12 : PAS d'exigence pytest-playwright PAR STORY en fullstack.
            # La preuve UI est fournie de bout en bout par le gate runtime
            # acceptance (navigateur réel sur l'app INTÉGRÉE) ; les stories UI y
            # sont implémentées par le STREAM FRONTEND (React/Vitest), dont le
            # prompt ne peut pas produire de tests pytest-playwright à la racine
            # du workspace — l'exiger bloquait la DoD de TOUT projet fullstack.
            # web-ssr garde ui_tests_enabled=True (pages rendues côté serveur :
            # le dev backend écrit naturellement du pytest-playwright).
            "ui_tests_enabled": False,
            "docker_delivery": True,
            # Finding 5 : idem — exercer le parcours d'écriture réel sur fullstack.
            "definition_of_done_strict_criteria": True,
        },
    ),
    "brownfield": ProductProfile(
        name="brownfield",
        description="Existing codebase extension: preserve shape, add analysis and gates.",
        overrides={
            "architecture_enabled": True,
            "components_enabled": False,
            "streams_enabled": False,
            "skills_enabled": True,
            "decompose_enabled": False,
            "smoke_run": True,
            "runtime_acceptance_enabled": False,
            "ui_tests_enabled": False,
            "docker_delivery": False,
        },
    ),
}


def normalize_name(name: str | None, *, brownfield_path: str = "") -> str:
    value = (name or "auto").strip().lower()
    if not value or value == "auto":
        return "brownfield" if brownfield_path.strip() else "auto"
    aliases = {
        "library": "library-fast",
        "lib": "library-fast",
        "web": "web-ssr",
        "frontend": "fullstack",
        "full-stack": "fullstack",
    }
    value = aliases.get(value, value)
    if value not in PROFILE_NAMES:
        raise ValueError(
            f"profil produit inconnu : {name!r} "
            f"(attendu : {', '.join(PROFILE_NAMES)})"
        )
    return value


def resolve_overrides(state: ProjectState) -> dict[str, bool]:
    """Resolve a state's explicit profile without mutating process settings.

    ``auto`` intentionally leaves the existing flag-driven behaviour untouched.
    Returns the per-pipeline overrides to apply at read time.
    """
    profile_name = normalize_name(state.product_profile, brownfield_path=state.brownfield_path)
    state.product_profile = profile_name
    if profile_name == "auto":
        return {}
    return dict(PROFILES[profile_name].overrides)


def apply_to_settings(state: ProjectState) -> dict[str, bool]:
    """Backward-compatible alias for tests/callers.

    Historically this mutated the global ``settings`` singleton. It now returns
    the same override map for a Pipeline instance to carry locally.
    """
    return resolve_overrides(state)
