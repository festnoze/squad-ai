"""Resolve the technical contract before any generated source is written."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import PurePosixPath, PureWindowsPath

from ..models import ProjectState

BACKENDS = {"python": "fastapi", "go": "net/http", "rust": "axum", "node": "node:http"}
# Greenfield creation is supported only when the entire initialization chain is
# implemented: scaffold + lock resolution + isolated tests + runtime preflight.
# Go/Rust templates exist, but their locked Linux validation profile does not.
INITIALIZATION_CAPABILITIES = {
    "python": frozenset({"scaffold", "lock", "isolated_tests", "runtime_preflight"}),
    "node": frozenset({"scaffold", "lock", "isolated_tests", "runtime_preflight"}),
    "go": frozenset({"scaffold"}),
    "rust": frozenset({"scaffold"}),
}
REQUIRED_INITIALIZATION_CAPABILITIES = frozenset(
    {"scaffold", "lock", "isolated_tests", "runtime_preflight"}
)
SUPPORTED_INITIAL_BACKENDS = frozenset(
    backend for backend, capabilities in INITIALIZATION_CAPABILITIES.items()
    if REQUIRED_INITIALIZATION_CAPABILITIES <= capabilities
)
_DECISION_FIELDS = ("backend", "framework", "frontend", "database", "kind")


def supports_initialization(backend: str) -> bool:
    """Whether a backend can pass every deterministic greenfield foundation gate."""
    capabilities = INITIALIZATION_CAPABILITIES.get(str(backend or "").lower(), frozenset())
    return REQUIRED_INITIALIZATION_CAPABILITIES <= capabilities


def unsupported_initialization_message(backend: str) -> str:
    return (
        f"Stack backend {backend!r} explicitement demandée, mais son initialisation complète "
        "(aucun profil Linux complet attesté : verrou de dépendances, tests isolés et préflight runtime) "
        "n'est pas encore validée. "
        "Aucune substitution automatique ne sera faite : choisir Python/FastAPI ou Node.js, "
        "ou importer un projet existant (brownfield)."
    )


def explicit_unsupported_initial_backend(state: ProjectState) -> str:
    """Return an explicitly requested Go/Rust backend before any analysis call.

    ``backend_language`` alone is not explicit intent: it can be an old or
    context-derived recommendation.
    """
    requested = dict(getattr(state, "technical_stack", {}) or {})
    if requested.get("kind") == "frontend":
        return ""
    backend = str(requested.get("backend") or "").strip().lower()
    framework_backend = next(
        (language for language, framework in BACKENDS.items()
         if framework == requested.get("framework")),
        "",
    )
    if backend in {"go", "rust"} and requested.get("source") != "inferred":
        return backend
    if framework_backend in {"go", "rust"} and requested.get("source") != "inferred":
        return framework_backend
    prose_backend = explicit_backend(f"{state.goal}\n{state.brief}")
    return prose_backend if prose_backend in {"go", "rust"} else ""


def supported_default_backend(backend: str) -> str:
    """Clamp a context/model recommendation to the attested bootstrap catalog."""
    normalized = str(backend or "").strip().lower()
    return normalized if supports_initialization(normalized) else "python"


def freeze(decision: dict[str, str], *, rationale: str = "") -> dict[str, str]:
    """Seal the already validated architect decision, separately from prose."""
    result = dict(decision)
    payload = {key: result[key] for key in _DECISION_FIELDS}
    result["version"] = "1"
    result["decision_sha256"] = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    result["rationale"] = rationale or result.get("rationale") or (
        "Contraintes explicites prioritaires ; catalogue de templates validés."
        if result.get("source") == "explicit" else
        "Choix de l'architecte ; Python simple ou backend typé, React pour interface."
    )
    result["template_catalog_version"] = "1"
    return result


def _sealed(requested: dict[str, str]) -> dict[str, str] | None:
    if not requested.get("decision_sha256"):
        return None
    if requested.get("version") != "1" or any(key not in requested for key in _DECISION_FIELDS):
        raise ValueError("Décision de stack persistée incomplète ou de version inconnue.")
    if requested.get("template_catalog_version", "1") != "1":
        raise ValueError("Version du catalogue de templates inconnue.")
    if freeze(requested)["decision_sha256"] != requested["decision_sha256"]:
        raise ValueError("Décision de stack modifiée : résoudre explicitement un nouveau contrat avant bootstrap.")
    backend, kind = requested["backend"], requested["kind"]
    if kind != "frontend" and not supports_initialization(backend):
        # A frozen context recommendation may predate the current capability
        # catalog. Let resolve() migrate that inferred decision as one unit;
        # an explicitly requested unsupported stack must still fail closed.
        if requested.get("source") != "inferred":
            raise ValueError(unsupported_initialization_message(backend))
        return None
    supported = (
        kind == "frontend" and backend == requested["framework"] == requested["database"] == "none"
        and requested["frontend"] == "react"
    ) or (
        kind in {"api", "fullstack", "cli", "library"} and backend in BACKENDS
        and requested["framework"] == BACKENDS[backend]
        and requested["frontend"] in {"none", "react"}
        and requested["database"] in {"none", "sqlite"}
        and (requested["database"] != "sqlite" or backend == "python")
        and (kind != "fullstack" or requested["frontend"] == "react")
    )
    if not supported:
        raise ValueError("Décision de stack persistée hors du catalogue pris en charge.")
    return dict(requested)


def _affirmative_constraints(text: str) -> str:
    """Do not turn an explicitly excluded technology into a stack requirement.

    This deliberately handles only direct negations, not general prose intent.
    Keep the original text for frontend-only intent ("sans backend").
    """
    technology = (
        r"(?:python|fastapi|golang|go|rust|axum|node(?:\.js|js)?|django|flask|"
        r"vue(?:\.js)?|angular|svelte|next\.js|express(?:\.js)?|sqlite|postgres(?:ql)?|"
        r"mysql|mariadb|mongodb|redis|java|javascript|c\#|c\+\+|\.net|dotnet|php|ruby|typescript|"
        r"base de données|database|persistance|persistence)"
    )
    return re.sub(
        r"\b(?:sans|without|no|not|pas|aucun|aucune|ni)\s+"
        r"(?:(?:de|du|la|le|une?|a|an|any|utiliser|use|using)\s+){0,3}"
        + technology + r"(?!\w)",
        " ", text, flags=re.I,
    )


def _unsupported_backend_language(text: str) -> str:
    """Recognize explicit backend languages without rejecting React TypeScript.

    Restrict proximity to one clause and stop at a frontend role transition;
    an API mentioned before 'frontend React en TypeScript' is not a TS backend.
    """
    scope = r"(?:back[- ]?end|api|service|cli|serveur|server|command[- ]line)"
    frontend = r"(?:front[- ]?end|react|interface|ui)"
    # Only stack connectors, not arbitrary intervening nouns (e.g. a Python API
    # serving a catalogue of Java courses is not implemented in Java).
    words = (
        r"(?:(?:en|in|using|avec|with|écrit|écrite|développé|développée|written|"
        r"implemented|built|rest|restful|web|backend|back-end|api|langage|language|"
        r"dans|le|the|du|de|a|an|un|une|pour|for|as|principal)\s+){0,6}"
    )
    technologies = r"(?<!\w)(?:java|c\#|c\+\+|\.net|dotnet|php|ruby|typescript)(?!\w)"
    for match in re.finditer(technologies, text, re.I):
        before, after = text[:match.start()], text[match.end():]
        if re.search(r"\b" + scope + r"\b\s*[:=]?\s*" + words + r"$", before, re.I):
            return match[0]
        if re.match(r"\s+" + words + scope + r"\b", after, re.I):
            return match[0]
        language_marker = re.search(
            r"\b(?:langage|language)\s+(?:(?:en|in|backend|principal)\s+){0,3}$", before, re.I,
        )
        clause = re.split(r"[,;\n]", before)[-1] + match[0] + re.split(r"[,;\n]", after)[0]
        if language_marker and not (match[0].lower() == "typescript" and re.search(r"\b" + frontend + r"\b", clause, re.I)):
            return match[0]
    return ""


def _unsupported_framework(text: str) -> str:
    """Keep the unsupported-stack gate without treating French views as Vue.

    Only unambiguous prose constructions exempt the bare word ``vue``;
    Vue.js and otherwise unexplained Vue mentions remain explicit constraints.
    Match each occurrence independently so prose cannot hide a later choice.
    """
    pattern = r"\b(?:django|flask|vue(?:\.js)?|angular|svelte|next\.js|express(?:\.js)?)\b"
    for match in re.finditer(pattern, text, re.I):
        if match[0].lower() == "vue":
            before, after = text[:match.start()], text[match.end():]
            prose_prefix = re.search(
                r"\b(?:chaque|une|la|cette|notre|votre|leur|sa|ma|ta|point de)\s+$", before, re.I,
            )
            prose_suffix = re.match(r"\s+d[’']ensemble\b", after, re.I)
            purpose = re.search(r"\ben\s+$", before, re.I) and re.match(r"\s+de\b", after, re.I)
            if prose_prefix or prose_suffix or purpose:
                continue
        return match[0]
    return ""


def _validate_stream_roots(state: ProjectState) -> None:
    """Reject escapes before workspace.scaffold can write a declared stream."""
    for stream in state.streams:
        root = stream.file_root or ""
        portable = root.replace("\\", "/")
        if "\x00" in root or ":" in portable or PureWindowsPath(root).drive or PurePosixPath(portable).is_absolute() or ".." in portable.split("/"):
            raise ValueError(f"Chemin du stream {stream.id!r} hors du projet : {root!r}")


def _backend_candidates(text: str) -> list[str]:
    patterns = {
        "python": r"\b(?:python|fastapi)\b",
        "go": r"\bgolang\b|\b(?:en|in|using|avec|langage|language|backend|stack)\s+go\b|\bgo\s+(?:backend|api|language|langage)\b",
        "rust": r"\b(?:rust|axum)\b",
        "node": r"\b(?:node(?:\.js|js)?|express(?:\.js)?)\b",
    }
    text = _affirmative_constraints(text)
    found = [lang for lang, pattern in patterns.items() if re.search(pattern, text, re.I)]
    # JavaScript identifies Node only when assigned to the backend; a React UI
    # written in JavaScript must not override an independently chosen backend.
    scope = r"(?:back[- ]?end|api|service|cli|serveur|server)"
    glue = r"(?:(?:en|in|using|avec|with|written|implemented|rest|web|backend|api|pour|for|the|le)\s+){0,4}"
    javascript_backend = re.search(
        r"\b" + scope + r"\b\s*[:=]?\s*" + glue + r"javascript\b"
        r"|\bjavascript\s+" + glue + scope + r"\b", text, re.I,
    )
    if javascript_backend and "node" not in found:
        found.append("node")
    return found


def explicit_backend(text: str) -> str:
    """Respect an unambiguous requested language (never substring-match 'go')."""
    found = _backend_candidates(text)
    return found[0] if len(found) == 1 else ""


def resolve(state: ProjectState) -> dict[str, str]:
    """Use explicit choices first, otherwise a small documented template catalog.

    No unsupported request is silently replaced with another framework/database.
    The API may supply a partial technical_stack; once persisted, the complete
    decision is stable on resume.
    """
    requested = dict(state.technical_stack)
    _validate_stream_roots(state)
    # A completed pre-analysis is immutable across resume and new prose. Only
    # an explicit new decision may change the scaffold, never another parse.
    sealed = _sealed(requested)
    if sealed is not None:
        return sealed
    text = f"{state.goal}\n{state.brief}".lower()
    affirmative = _affirmative_constraints(text)
    candidates = _backend_candidates(text)
    technology = r"(?:python|fastapi|rust|axum|golang|go|node(?:\.js|js)?)"
    assignment = r"\b(?:back[- ]?end|api|serveur|server|langage|language)\s*[:=]?\s*(?:(?:en|in|using|avec|with|écrit|written)\s+){0,3}(" + technology + r")\b"
    assigned = _backend_candidates("\n".join(m[0] for m in re.finditer(assignment, affirmative, re.I)))
    alternatives = re.search(r"\b" + technology + r"\s+(?:(?:ou|or|versus|vs)(?:\s+bien)?)\s+" + technology + r"\b", affirmative, re.I)
    if len(candidates) > 1 and len(assigned) > 1 and not alternatives:
        raise ValueError("Contraintes de backend contradictoires : plusieurs langages exigés sans choix d'alternative.")
    prose_backend = explicit_backend(text)
    if requested.get("backend") and prose_backend and requested["backend"] != prose_backend:
        raise ValueError("Contraintes de stack contradictoires entre le brief et le choix structuré.")
    unsupported_language = _unsupported_backend_language(affirmative)
    if unsupported_language:
        raise ValueError(
            f"Langage backend explicite {unsupported_language!r} sans template initial validé. "
            "Importer un projet existant (brownfield) ou choisir Python, Go, Rust ou Node.js."
        )
    # A partial contract must not hide an unsupported explicit choice in the
    # brief (nor may the frontend-only early return silently turn Vue into React).
    unsupported = _unsupported_framework(affirmative)
    if unsupported:
        raise ValueError(
            f"Stack explicite {unsupported!r} sans template initial validé. "
            "Importer un projet existant (brownfield) ou choisir un template du catalogue."
        )
    kind = requested.get("kind", "")
    if not kind:
        profile = state.product_profile
        frontend_only = re.search(
            r"\bfront[- ]?end[- ]only\b|\bfront[- ]?end\s+(?:seul|uniquement|only)\b"
            r"|\b(?:uniquement|only)\s+(?:(?:un|a)\s+)?front[- ]?end\b"
            r"|\breact\s+(?:uniquement|only)\b",
            text,
        ) or (
            re.search(r"\b(?:react|frontend|front.end|interface|web|site|dashboard|spa)\b", text)
            and re.search(r"\b(?:sans|without|no)\s+(?:(?:un|a|de)\s+)?back[- ]?end\b", text)
        )
        if frontend_only:
            kind = "frontend"
        elif profile in ("cli", "library-fast"):
            kind = "library" if profile == "library-fast" else "cli"
        elif profile in ("fullstack", "web-ssr"):
            kind = "fullstack"
        elif profile == "api":
            kind = "api"
        elif re.search(r"\b(?:cli|command.line|ligne de commande)\b", text):
            kind = "cli"
        elif re.search(r"\b(?:librairie|bibliothèque|library|sdk)\b", text):
            kind = "library"
        elif re.search(r"\b(?:react|frontend|front.end|interface|web|site|dashboard|spa)\b", text):
            kind = "fullstack"
        elif re.search(r"\b(?:api|backend|back.end|fastapi|service http)\b", text):
            kind = "api"
        else:
            kind = "cli"
    if kind not in ("api", "fullstack", "frontend", "cli", "library"):
        raise ValueError(f"Type de projet non pris en charge : {kind}")

    if kind == "frontend":
        if requested.get("frontend", "react") != "react":
            raise ValueError("Le template frontend pris en charge est React.")
        if requested.get("database", "none") != "none" or re.search(
            r"\b(?:sqlite|postgres(?:ql)?|mysql|mariadb|mongodb|redis)\b", affirmative
        ):
            raise ValueError("Un frontend seul ne peut pas héberger une base de données serveur.")
        return {"backend": "none", "framework": "none", "frontend": "react",
                "database": "none", "kind": kind, "source": requested.get("source", "explicit")}

    framework_backend = next((language for language, framework in BACKENDS.items() if framework == requested.get("framework")), "")
    explicit_text = explicit_backend(text)
    if requested.get("source") == "inferred":
        if explicit_text:
            if not supports_initialization(explicit_text):
                raise ValueError(unsupported_initialization_message(explicit_text))
            backend = explicit_text
            framework = BACKENDS[backend]
            source = "explicit"
        else:
            candidate = requested.get("backend") or framework_backend or state.backend_language.value
            backend = supported_default_backend(candidate)
            framework = (requested.get("framework") or BACKENDS[backend]) if backend == candidate else BACKENDS[backend]
            source = "inferred"
        explicit = explicit_text
    else:
        explicit = requested.get("backend") or framework_backend or explicit_text
        if explicit and not supports_initialization(explicit):
            raise ValueError(unsupported_initialization_message(explicit))
        backend = explicit or supported_default_backend(state.backend_language.value)
        framework = requested.get("framework") or BACKENDS.get(backend, "")
        source = requested.get("source") or ("explicit" if explicit else "inferred")
    if backend not in BACKENDS:
        raise ValueError(f"Backend {backend!r} sans template : choisir python, go, rust ou node.")
    frontend = requested.get("frontend") or ("react" if kind in ("fullstack", "frontend") else "none")
    database = requested.get("database")
    if database is None:
        if re.search(r"\b(?:postgres(?:ql)?|mysql|mariadb|mongodb|redis)\b", affirmative):
            database = re.search(r"\b(?:postgres(?:ql)?|mysql|mariadb|mongodb|redis)\b", affirmative)[0]
        else:
            database = "sqlite" if re.search(r"\b(?:sqlite|base de données|database|persist\w*|crud)\b", affirmative) else "none"
    if framework != BACKENDS[backend] or frontend not in ("react", "none"):
        raise ValueError(f"Template non pris en charge : {backend}/{framework}/{frontend}.")
    if database not in ("sqlite", "none"):
        raise ValueError(f"Base {database!r} sans adaptateur de pré-vérification ; sqlite et none sont pris en charge.")
    if database == "sqlite" and not explicit and backend != "python":
        backend, framework = "python", "fastapi"
    if database == "sqlite" and backend != "python":
        raise ValueError("Le prévol SQLite est actuellement pris en charge avec Python/FastAPI uniquement.")
    if kind == "fullstack" and frontend == "none":
        raise ValueError("Un projet fullstack nécessite un frontend.")
    return {
        "backend": backend, "framework": framework, "frontend": frontend,
        "database": database, "kind": kind,
        "source": source,
    }


def contract(state: ProjectState) -> str:
    if not state.technical_stack:
        return ""
    fields = ", ".join(f"{k}={v}" for k, v in state.technical_stack.items())
    api = state.technical_stack.get("kind") in ("api", "fullstack")
    return (
        f"Socle technique déterministe : {fields}. "
        + ("Le bootstrap et /api/health existent déjà. " if api else "Le bootstrap et ses tests existent déjà. ")
        + "Étendre le socle existant, "
        "préserver son point d'entrée, sa configuration et ses tests. "
        "Ne pas recréer le projet ni changer sa stack."
    )
