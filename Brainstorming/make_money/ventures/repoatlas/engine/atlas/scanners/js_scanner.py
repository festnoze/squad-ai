"""JavaScript/TypeScript scanner covering React and Angular idioms.

Heuristics, documented:
- React components: exported Capitalized function/const/class in .jsx/.tsx
  (or .js/.ts whose text contains JSX-ish markup), plus hooks used.
- React routes: <Route path="..."> and router config objects {path: "..."}.
- Angular: @Component/@Injectable/@NgModule/@Directive/@Pipe decorators
  (selector extracted when present) and route arrays
  {path: '...', component|loadChildren|loadComponent}.
- Imports: ES import/require targets; relative targets are internal.
"""

import json
import re

from .base import Scanner, read_rel

IMPORT_RE = re.compile(
    r"""(?:import\s+(?:[\w{},*\s]+\s+from\s+)?|require\(\s*)['"]([^'"]+)['"]""")
EXPORT_COMPONENT_RE = re.compile(
    r"export\s+(?:default\s+)?(?:async\s+)?(?:function|const|class)\s+([A-Z]\w+)")
EXPORT_CLASS_RE = re.compile(r"export\s+(?:abstract\s+)?class\s+(\w+)")
HOOK_RE = re.compile(r"\buse[A-Z]\w+\b")
REACT_ROUTE_RE = re.compile(r"""<Route\s[^>]*path\s*=\s*["']([^"']+)["']""")
ROUTE_OBJ_RE = re.compile(
    r"""path:\s*['"]([^'"]*)['"]\s*,\s*(?:element|component|loadChildren|loadComponent|children)""")
NG_DECORATOR_RE = re.compile(r"@(Component|Injectable|NgModule|Directive|Pipe)\s*\(")
NG_SELECTOR_RE = re.compile(r"""selector:\s*['"]([^'"]+)['"]""")


class JsScanner(Scanner):
    name = "js"
    extensions = (".ts", ".tsx", ".js", ".jsx", ".mjs")
    manifest_names = ("package.json",)

    def scan_file(self, rel_path, text, result):
        for match in IMPORT_RE.finditer(text):
            target = match.group(1)
            result.imports.append({
                "file": rel_path,
                "target": target,
                "external": not target.startswith("."),
            })

        for match in NG_DECORATOR_RE.finditer(text):
            kind = "angular_" + match.group(1).lower()
            window = text[match.end():match.end() + 600]
            selector = NG_SELECTOR_RE.search(window)
            name_match = EXPORT_CLASS_RE.search(text[match.end():])
            name = name_match.group(1) if name_match else "(anonymous)"
            line = text.count("\n", 0, match.start()) + 1
            result.symbols.append({
                "name": name, "kind": kind, "file": rel_path, "line": line,
                "extra": {"selector": selector.group(1) if selector else ""}})

        is_reactish = rel_path.endswith((".jsx", ".tsx")) or "</" in text \
            or "React" in text
        if is_reactish and not NG_DECORATOR_RE.search(text):
            for match in EXPORT_COMPONENT_RE.finditer(text):
                line = text.count("\n", 0, match.start()) + 1
                hooks = sorted(set(HOOK_RE.findall(text)))[:8]
                result.symbols.append({
                    "name": match.group(1), "kind": "react_component",
                    "file": rel_path, "line": line, "extra": {"hooks": hooks}})

        for regex in (REACT_ROUTE_RE, ROUTE_OBJ_RE):
            for match in regex.finditer(text):
                line = text.count("\n", 0, match.start()) + 1
                result.routes.append({"method": "VIEW", "path": match.group(1),
                                      "handler": "(frontend route)",
                                      "file": rel_path, "line": line})

        if not NG_DECORATOR_RE.search(text) and not is_reactish:
            for match in EXPORT_CLASS_RE.finditer(text):
                line = text.count("\n", 0, match.start()) + 1
                result.symbols.append({"name": match.group(1), "kind": "class",
                                       "file": rel_path, "line": line, "extra": {}})

    def scan_manifests(self, root, all_files, result):
        for f in all_files:
            if f["path"].split("/")[-1] != "package.json":
                continue
            if "/" in f["path"]:  # only root manifests (workspaces: note it)
                result.notes.append({"file": f["path"],
                                     "note": "nested package.json (workspace?)"})
                continue
            try:
                pkg = json.loads(read_rel(root, f["path"]))
            except ValueError:
                result.notes.append({"file": f["path"], "note": "invalid JSON"})
                continue
            for section in ("dependencies", "devDependencies"):
                for name, version in pkg.get(section, {}).items():
                    result.deps.append({"ecosystem": "npm", "name": name,
                                        "version": version, "file": f["path"]})
            if pkg.get("name"):
                result.symbols.append({"name": pkg["name"], "kind": "package",
                                       "file": f["path"], "line": 1, "extra": {}})
