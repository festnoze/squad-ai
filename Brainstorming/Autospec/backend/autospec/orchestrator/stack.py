"""Resolve the technical contract before any generated source is written."""

from __future__ import annotations

import re
from pathlib import PurePosixPath, PureWindowsPath

from ..models import ProjectState

BACKENDS = {"python": "fastapi", "go": "net/http", "rust": "axum", "node": "node:http"}


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


def explicit_backend(text: str) -> str:
    """Respect an unambiguous requested language (never substring-match 'go')."""
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
    # Ambiguous comparisons are left to the architect instead of picking the
    # first language mentioned in a discussion of alternatives.
    return found[0] if len(found) == 1 else ""


def resolve(state: ProjectState) -> dict[str, str]:
    """Use explicit choices first, otherwise a small documented template catalog.

    No unsupported request is silently replaced with another framework/database.
    The API may supply a partial technical_stack; once persisted, the complete
    decision is stable on resume.
    """
    requested = dict(state.technical_stack)
    _validate_stream_roots(state)
    text = f"{state.goal}\n{state.brief}".lower()
    affirmative = _affirmative_constraints(text)
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
    explicit = requested.get("backend") or framework_backend or explicit_backend(text)
    backend = explicit or state.backend_language.value
    if backend not in BACKENDS:
        raise ValueError(f"Backend {backend!r} sans template : choisir python, go, rust ou node.")
    framework = requested.get("framework") or BACKENDS[backend]
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
        "source": requested.get("source") or ("explicit" if explicit else "inferred"),
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
