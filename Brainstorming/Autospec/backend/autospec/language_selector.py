"""L2: pick the backend language for the generated product from the goal/brief.

Two axes are estimated (1-5): technical *complexity* and *criticality* (cost of a
regression — financial/legal/safety/data). The recommendation:
  • Rust  — high complexity OR high criticality (banking, health, systems…).
  • Python — simple / low-criticality (calculator, landing page, prototype…).
  • Go    — the default, "serious" app of medium complexity/criticality.

This module is the deterministic fallback used when the LLM selector is off or
fails; the agent (see pipeline._aselect_language) may override it.
"""

from __future__ import annotations

# Keyword sets are matched as substrings against a lowercased goal+brief, so
# stems ("banc" → banque/bancaire, "securit" → sécurité/security) catch variants.
CRITICAL_KEYWORDS = (
    "banc", "paiement", "payment", "santé", "sante", "health", "médical",
    "medical", "securit", "sécurit", "finance", "légal", "legal", "rgpd",
    "gdpr", "sûreté", "surete", "safety", "assurance", "trading", "bourse",
    "comptab", "fiscal",
)
COMPLEX_KEYWORDS = (
    "temps réel", "temps reel", "realtime", "concurrent", "distribu",
    "haute perform", "performance", "scalab", "machine learning", "algorithme",
    "système", "systeme", "compilateur", "crypto", "blockchain", "moteur",
    "parsing", "calcul exigeant", "low-level", "embarqu",
)
SIMPLE_KEYWORDS = (
    "calculatrice", "calculator", "démo", "demo", "vitrine", "prototype",
    "todo", "to-do", "exemple", "landing", "blog", "portfolio", "crud",
)


def _clamp(n: int) -> int:
    return max(1, min(5, n))


def _hits(text: str, keywords: tuple[str, ...]) -> int:
    return sum(1 for kw in keywords if kw in text)


def recommend_language(goal: str, brief: str = "") -> dict:
    """Deterministic backend-language recommendation from the goal/brief.

    Returns ``{language, complexity, criticality, rationale}`` — language is one
    of ``"python" | "go" | "rust"``.
    """
    text = f"{goal}\n{brief}".lower()
    simple = _hits(text, SIMPLE_KEYWORDS) > 0
    criticality = _clamp(2 + _hits(text, CRITICAL_KEYWORDS) - (1 if simple else 0))
    complexity = _clamp(2 + _hits(text, COMPLEX_KEYWORDS) - (1 if simple else 0))

    if criticality >= 4 or complexity >= 4:
        language = "rust"
        rationale = (
            "Complexité technique ou criticité élevée : le compilateur Rust "
            "décharge le linter et les tests (exhaustivité, null-safety, erreurs "
            "non gérées, data races) pour une correction maximale par itération."
        )
    elif simple and criticality <= 2 and complexity <= 2:
        language = "python"
        rationale = (
            "Projet simple et peu critique : Python offre la génération la plus "
            "fiable (pas de barrière de compilation), idéal pour un prototype/CLI."
        )
    else:
        language = "go"
        rationale = (
            "Application professionnelle de complexité/criticité moyenne : Go "
            "offre le meilleur compromis (typage, débit de boucle rapide, "
            "déploiement simple)."
        )

    return {
        "language": language,
        "complexity": complexity,
        "criticality": criticality,
        "rationale": rationale,
    }
