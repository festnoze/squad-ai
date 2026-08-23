import types
import unittest

from atlas.factgraph import FactGraph
from atlas.mapping import detect_modules, internal_edges, module_of


def fake_files(spec):
    """spec: {path: lines}"""
    def lang(path):
        return "python" if path.endswith(".py") else "typescript"
    return [{"path": p, "ext": "." + p.rsplit(".", 1)[-1], "lang": lang(p),
             "lines": n} for p, n in spec.items()]


class MappingTests(unittest.TestCase):
    def test_modules_grouped_and_small_ones_merged(self):
        files = fake_files({
            "src/alpha/__init__.py": 1, "src/alpha/a1.py": 100,
            "src/alpha/a2.py": 80,
            "src/beta/__init__.py": 1, "src/beta/b1.py": 60, "src/beta/b2.py": 40,
            "tools/one_off.py": 10,
        })
        modules = detect_modules(files)
        names = {m["name"] for m in modules}
        self.assertIn("src-alpha", names)
        self.assertIn("src-beta", names)
        self.assertIn("misc", names)  # tools has < 3 files
        self.assertEqual(module_of("src/alpha/a1.py", modules), "src-alpha")

    def test_module_cap_produces_other(self):
        spec = {}
        for i in range(30):
            for j in range(3):
                spec[f"pkg{i:02d}/f{j}.py"] = 50
        modules = detect_modules(fake_files(spec), max_modules=10)
        self.assertEqual(len(modules), 10)
        self.assertEqual(modules[-1]["name"], "other")

    def test_internal_edges_python_and_relative_js(self):
        files = fake_files({
            "src/alpha/__init__.py": 1, "src/alpha/a1.py": 100, "src/alpha/a2.py": 10,
            "src/beta/__init__.py": 1, "src/beta/b1.py": 60, "src/beta/b2.py": 10,
            "src/ui/x.ts": 30, "src/ui/y.ts": 30, "src/ui/parts/z.ts": 30,
        })
        modules = detect_modules(files)
        scan = types.SimpleNamespace(symbols=[], imports=[
            {"file": "src/beta/b1.py", "target": "alpha", "external": None},
            {"file": "src/ui/x.ts", "target": "./parts/z", "external": False},
        ])
        edges = internal_edges(modules, scan, files)
        self.assertIn(("src-beta", "src-alpha"), edges)
        # relative import stays inside src/ui: no self-edge
        self.assertNotIn(("src-ui", "src-ui"), edges)


class FactGraphTests(unittest.TestCase):
    def test_add_query_save_load_diff(self):
        import os
        import tempfile
        graph = FactGraph("demo")
        graph.add("symbol", {"name": "A", "kind": "class", "file": "a.py"},
                  evidence=[{"path": "a.py", "line": 3}], source="scanner",
                  verified=True)
        graph.add("route", {"method": "GET", "path": "/x", "file": "a.py"})
        self.assertEqual(len(graph.query("symbol")), 1)
        self.assertEqual(len(graph.query("symbol", name="A")), 1)
        self.assertEqual(len(graph.query("symbol", name="B")), 0)

        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "snap.json")
            graph.save(path)
            loaded = FactGraph.load(path)
        self.assertEqual(len(loaded.facts), 2)

        newer = FactGraph("demo")
        newer.add("symbol", {"name": "A", "kind": "class", "file": "a.py"})
        newer.add("symbol", {"name": "B", "kind": "class", "file": "b.py"})
        delta = newer.diff(graph)
        added = {f["data"].get("name") for f in delta["added"]}
        removed = {f["kind"] for f in delta["removed"]}
        self.assertIn("B", added)
        self.assertIn("route", removed)


if __name__ == "__main__":
    unittest.main()
