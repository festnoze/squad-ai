"""Module mapping: split a repo into 5-20 units a developer learns as one.

Deterministic heuristic first (path-segment grouping under source roots);
an optional agent pass can refine names and merges when the LLM is enabled,
but the heuristic result is always the fallback and the test baseline.
"""

from .config import CODE_LANGS

SOURCE_ROOTS = {"src", "app", "apps", "lib", "libs", "source", "packages", "services"}
MIN_FILES_PER_MODULE = 3


def _segment(path):
    parts = path.split("/")
    if len(parts) == 1:
        return "(root)"
    if parts[0].lower() in SOURCE_ROOTS and len(parts) > 2:
        return parts[0] + "/" + parts[1]
    return parts[0]


def detect_modules(files, max_modules=20):
    """files: intake entries. Returns [{name, prefix, files, loc}] sorted by loc."""
    code_files = [f for f in files if f["lang"] in CODE_LANGS]
    groups = {}
    for f in code_files:
        groups.setdefault(_segment(f["path"]), []).append(f)

    modules, small = [], []
    for prefix, members in groups.items():
        entry = {
            "name": prefix.replace("/", "-").strip("-.") or "root",
            "prefix": prefix,
            "files": [m["path"] for m in members],
            "loc": sum(m["lines"] for m in members),
        }
        (modules if len(members) >= MIN_FILES_PER_MODULE else small).append(entry)

    if small:
        modules.append({
            "name": "misc", "prefix": "(misc)",
            "files": sorted(p for e in small for p in e["files"]),
            "loc": sum(e["loc"] for e in small),
        })

    modules.sort(key=lambda m: -m["loc"])
    if len(modules) > max_modules:
        overflow = modules[max_modules - 1:]
        modules = modules[:max_modules - 1]
        modules.append({
            "name": "other", "prefix": "(other)",
            "files": sorted(p for e in overflow for p in e["files"]),
            "loc": sum(e["loc"] for e in overflow),
        })
    return modules


def module_of(path, modules):
    for module in modules:
        if module["prefix"] in ("(misc)", "(other)"):
            continue
        if module["prefix"] == "(root)":
            if "/" not in path:
                return module["name"]
        elif path == module["prefix"] or path.startswith(module["prefix"] + "/"):
            return module["name"]
    for module in modules:
        if path in module["files"]:
            return module["name"]
    return None


def internal_edges(modules, scan, files):
    """Module-to-module dependency edges derived from import facts.

    Python: absolute imports whose top package matches a module's top dir.
    JS/TS: relative imports resolved against the importing file's directory.
    C#: using directives whose root matches a namespace declared elsewhere.
    """
    known_paths = {f["path"] for f in files}
    # python top-package -> module, and C# namespace-root -> module
    py_package_of = {}
    cs_namespace_of = {}
    for symbol in scan.symbols:
        module = module_of(symbol["file"], modules)
        if module is None:
            continue
        if symbol["kind"] == "namespace":
            cs_namespace_of.setdefault(symbol["name"].split(".")[0], module)
    for path in known_paths:
        if path.endswith("__init__.py"):
            parts = path.split("/")
            if len(parts) >= 2:
                module = module_of(path, modules)
                if module:
                    py_package_of.setdefault(parts[-2], module)

    edges = set()
    for imp in scan.imports:
        src = module_of(imp["file"], modules)
        if src is None:
            continue
        dst = None
        target = imp["target"]
        if target.startswith("."):  # relative JS import
            base_dir = "/".join(imp["file"].split("/")[:-1])
            resolved = _resolve_relative(base_dir, target)
            for candidate in (resolved, resolved + ".ts", resolved + ".tsx",
                              resolved + ".js", resolved + ".jsx",
                              resolved + "/index.ts", resolved + "/index.js"):
                if candidate in known_paths:
                    dst = module_of(candidate, modules)
                    break
        else:
            dst = py_package_of.get(target) or cs_namespace_of.get(target)
        if dst and dst != src:
            edges.add((src, dst))
    return sorted(edges)


def _resolve_relative(base_dir, target):
    parts = base_dir.split("/") if base_dir else []
    for piece in target.split("/"):
        if piece == "..":
            parts = parts[:-1]
        elif piece not in (".", ""):
            parts.append(piece)
    return "/".join(parts)
