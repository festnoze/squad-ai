"""C# scanner: regex heuristics, documented and conservative.

Without a Roslyn dependency we cannot fully parse C#; these heuristics are
tuned for the common shapes (ASP.NET controllers, services, EF entities).
Anything ambiguous becomes a note, never a guessed fact.
"""

import os
import re

from .base import Scanner, read_rel

NAMESPACE_RE = re.compile(r"^\s*namespace\s+([\w.]+)", re.M)
USING_RE = re.compile(r"^\s*using\s+(?:static\s+)?([\w.]+)\s*;", re.M)
TYPE_RE = re.compile(
    r"^\s*(?:\[[^\]]*\]\s*)*"
    r"(?:public|internal|protected|private)?\s*"
    r"(?:static\s+|sealed\s+|abstract\s+|partial\s+)*"
    r"(class|interface|record|struct|enum)\s+(\w+)", re.M)
METHOD_RE = re.compile(
    r"^\s*(?:public|internal|protected)\s+"
    r"(?:static\s+|async\s+|virtual\s+|override\s+|sealed\s+|partial\s+)*"
    r"[\w<>\[\],\s.?]+?\s+(\w+)\s*\(", re.M)
ROUTE_ATTR_RE = re.compile(r"\[\s*Route\(\s*\"([^\"]*)\"\s*\)\s*\]")
HTTP_ATTR_RE = re.compile(r"\[\s*Http(Get|Post|Put|Delete|Patch)(?:\(\s*\"([^\"]*)\"\s*\))?\s*\]")
PACKAGE_REF_RE = re.compile(r"<PackageReference\s+Include=\"([^\"]+)\"(?:\s+Version=\"([^\"]+)\")?", re.I)

KEYWORD_FALSE_METHODS = {"if", "for", "foreach", "while", "switch", "using",
                         "return", "new", "catch", "lock", "throw", "await"}


class CSharpScanner(Scanner):
    name = "csharp"
    extensions = (".cs",)
    manifest_names = ("*.csproj",)

    def scan_file(self, rel_path, text, result):
        for match in NAMESPACE_RE.finditer(text):
            line = text.count("\n", 0, match.start()) + 1
            result.symbols.append({"name": match.group(1), "kind": "namespace",
                                   "file": rel_path, "line": line, "extra": {}})

        for match in TYPE_RE.finditer(text):
            kind, name = match.group(1), match.group(2)
            line = text.count("\n", 0, match.start()) + 1
            result.symbols.append({"name": name, "kind": kind,
                                   "file": rel_path, "line": line, "extra": {}})

        for match in METHOD_RE.finditer(text):
            name = match.group(1)
            if name in KEYWORD_FALSE_METHODS:
                continue
            line = text.count("\n", 0, match.start()) + 1
            result.symbols.append({"name": name, "kind": "method",
                                   "file": rel_path, "line": line, "extra": {}})

        for match in USING_RE.finditer(text):
            result.imports.append({"file": rel_path,
                                   "target": match.group(1).split(".")[0],
                                   "external": None})

        self._routes(rel_path, text, result)

    def _routes(self, rel_path, text, result):
        base_match = ROUTE_ATTR_RE.search(text)
        base = base_match.group(1) if base_match else ""
        controller = ""
        type_match = TYPE_RE.search(text)
        if type_match:
            controller = type_match.group(2)
        base = base.replace("[controller]",
                            controller.replace("Controller", "").lower())
        for match in HTTP_ATTR_RE.finditer(text):
            method = match.group(1).upper()
            sub = match.group(2) or ""
            path = "/".join(p for p in (base.strip("/"), sub.strip("/")) if p)
            line = text.count("\n", 0, match.start()) + 1
            result.routes.append({"method": method, "path": "/" + path,
                                  "handler": controller or "(unknown)",
                                  "file": rel_path, "line": line})

    def scan_manifests(self, root, all_files, result):
        for f in all_files:
            if not f["path"].endswith(".csproj"):
                continue
            text = read_rel(root, f["path"])
            for match in PACKAGE_REF_RE.finditer(text):
                result.deps.append({"ecosystem": "nuget", "name": match.group(1),
                                    "version": match.group(2) or "*",
                                    "file": f["path"]})
            asm = re.search(r"<(?:AssemblyName|RootNamespace)>([^<]+)<", text)
            if asm:
                result.symbols.append({
                    "name": asm.group(1), "kind": "assembly",
                    "file": f["path"], "line": 1, "extra": {}})
            else:
                result.symbols.append({
                    "name": os.path.splitext(os.path.basename(f["path"]))[0],
                    "kind": "assembly", "file": f["path"], "line": 1, "extra": {}})
