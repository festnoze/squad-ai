"""Python scanner: AST-based, so symbol and route facts are exact.

Route detection covers the common decorator styles: FastAPI/Starlette
(@app.get, @router.post, ...), Flask (@app.route, @bp.route), and Django
url patterns (path(...) / re_path(...) in urls.py files).
"""

import ast
import re

from .base import Scanner, read_rel

HTTP_METHODS = {"get", "post", "put", "delete", "patch", "head", "options"}


class PythonScanner(Scanner):
    name = "python"
    extensions = (".py",)
    manifest_names = ("pyproject.toml", "requirements.txt", "setup.py")

    def scan_file(self, rel_path, text, result):
        try:
            tree = ast.parse(text)
        except SyntaxError as exc:
            result.notes.append({"file": rel_path,
                                 "note": f"python syntax error at line {exc.lineno}"})
            return

        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                methods = [n.name for n in node.body
                           if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
                result.symbols.append({
                    "name": node.name, "kind": "class", "file": rel_path,
                    "line": node.lineno,
                    "extra": {"methods": methods[:20],
                              "bases": [ast.dump(b)[:40] if not isinstance(b, ast.Name)
                                        else b.id for b in node.bases][:5]},
                })
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                self._check_route(node, rel_path, result)
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    result.imports.append({"file": rel_path,
                                           "target": alias.name.split(".")[0],
                                           "external": None})
            elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                result.imports.append({"file": rel_path,
                                       "target": node.module.split(".")[0],
                                       "external": None})

        # top-level functions only (walk() above already got routes on all)
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                result.symbols.append({
                    "name": node.name, "kind": "function", "file": rel_path,
                    "line": node.lineno,
                    "extra": {"args": [a.arg for a in node.args.args][:10]},
                })

        if rel_path.endswith("urls.py"):
            self._django_urls(rel_path, text, result)

    def _check_route(self, node, rel_path, result):
        for dec in node.decorator_list:
            if not (isinstance(dec, ast.Call) and isinstance(dec.func, ast.Attribute)):
                continue
            attr = dec.func.attr.lower()
            if attr in HTTP_METHODS or attr == "route":
                path = ""
                if dec.args and isinstance(dec.args[0], ast.Constant) \
                        and isinstance(dec.args[0].value, str):
                    path = dec.args[0].value
                result.routes.append({
                    "method": attr.upper() if attr != "route" else "ANY",
                    "path": path, "handler": node.name,
                    "file": rel_path, "line": node.lineno,
                })

    def _django_urls(self, rel_path, text, result):
        for match in re.finditer(r"""(?:re_)?path\(\s*['"]([^'"]*)['"]""", text):
            line = text.count("\n", 0, match.start()) + 1
            result.routes.append({"method": "ANY", "path": match.group(1),
                                  "handler": "(django url)", "file": rel_path,
                                  "line": line})

    def scan_manifests(self, root, all_files, result):
        paths = {f["path"] for f in all_files}
        if "requirements.txt" in paths:
            for i, line in enumerate(read_rel(root, "requirements.txt").splitlines(), 1):
                line = line.strip()
                if not line or line.startswith(("#", "-")):
                    continue
                name = re.split(r"[<>=!~\[; ]", line, maxsplit=1)[0]
                if name:
                    result.deps.append({"ecosystem": "pypi", "name": name,
                                        "version": line[len(name):].strip() or "*",
                                        "file": "requirements.txt"})
        if "pyproject.toml" in paths:
            text = read_rel(root, "pyproject.toml")
            block = re.search(r"dependencies\s*=\s*\[(.*?)\]", text, re.S)
            if block:
                for match in re.finditer(r"""['"]([^'"]+)['"]""", block.group(1)):
                    spec = match.group(1)
                    name = re.split(r"[<>=!~\[; ]", spec, maxsplit=1)[0]
                    result.deps.append({"ecosystem": "pypi", "name": name,
                                        "version": spec[len(name):].strip() or "*",
                                        "file": "pyproject.toml"})
