import os
import unittest

from atlas.config import DEFAULT_EXCLUDE_DIRS
from atlas.intake import walk_repo
from atlas.scanners import scan_repo

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")


def scan(fixture):
    root = os.path.join(FIXTURES, fixture)
    return scan_repo(root, walk_repo(root, DEFAULT_EXCLUDE_DIRS))


class PythonScannerTests(unittest.TestCase):
    def setUp(self):
        self.result = scan("pyapp")

    def test_routes(self):
        routes = {(r["method"], r["path"]) for r in self.result.routes}
        self.assertIn(("GET", "/invoices"), routes)
        self.assertIn(("POST", "/invoices/{invoice_id}/retry"), routes)

    def test_symbols(self):
        classes = {s["name"] for s in self.result.symbols if s["kind"] == "class"}
        self.assertIn("InvoiceEngine", classes)
        functions = {s["name"] for s in self.result.symbols if s["kind"] == "function"}
        self.assertIn("suspend_subscription", functions)

    def test_deps_from_pyproject(self):
        deps = {d["name"] for d in self.result.deps}
        self.assertIn("fastapi", deps)
        self.assertIn("sqlalchemy", deps)

    def test_imports(self):
        targets = {i["target"] for i in self.result.imports}
        self.assertIn("fastapi", targets)
        self.assertIn("billingcore", targets)


class CSharpScannerTests(unittest.TestCase):
    def setUp(self):
        self.result = scan("csapp")

    def test_types_and_methods(self):
        names = {(s["kind"], s["name"]) for s in self.result.symbols}
        self.assertIn(("class", "InvoiceController"), names)
        self.assertIn(("class", "InvoiceService"), names)
        self.assertIn(("method", "ListAll"), names)
        self.assertIn(("method", "Retry"), names)
        self.assertIn(("namespace", "Billing.Api.Services"), names)
        self.assertIn(("assembly", "Billing.Api"), names)

    def test_controller_routes(self):
        routes = {(r["method"], r["path"]) for r in self.result.routes}
        self.assertIn(("GET", "/api/invoice"), routes)
        self.assertIn(("POST", "/api/invoice/retry/{id}"), routes)

    def test_nuget_deps(self):
        deps = {d["name"]: d["version"] for d in self.result.deps}
        self.assertEqual(deps.get("Newtonsoft.Json"), "13.0.3")


class ReactScannerTests(unittest.TestCase):
    def setUp(self):
        self.result = scan("reactapp")

    def test_components_and_hooks(self):
        components = {s["name"]: s for s in self.result.symbols
                      if s["kind"] == "react_component"}
        self.assertIn("App", components)
        self.assertIn("InvoiceTable", components)
        self.assertIn("useState", components["InvoiceTable"]["extra"]["hooks"])

    def test_frontend_routes(self):
        paths = {r["path"] for r in self.result.routes}
        self.assertIn("/dashboard", paths)
        self.assertIn("/settings", paths)

    def test_npm_deps_and_package_identity(self):
        deps = {d["name"] for d in self.result.deps}
        self.assertIn("react-router-dom", deps)
        packages = {s["name"] for s in self.result.symbols if s["kind"] == "package"}
        self.assertIn("billing-dashboard", packages)


class AngularScannerTests(unittest.TestCase):
    def setUp(self):
        self.result = scan("ngapp")

    def test_decorated_symbols(self):
        by_kind = {}
        for s in self.result.symbols:
            by_kind.setdefault(s["kind"], set()).add(s["name"])
        self.assertIn("InvoiceListComponent", by_kind.get("angular_component", set()))
        self.assertIn("InvoiceService", by_kind.get("angular_injectable", set()))
        self.assertIn("AppRoutingModule", by_kind.get("angular_ngmodule", set()))

    def test_selector_extracted(self):
        component = next(s for s in self.result.symbols
                         if s["kind"] == "angular_component")
        self.assertEqual(component["extra"]["selector"], "app-invoice-list")

    def test_angular_routes(self):
        paths = {r["path"] for r in self.result.routes}
        self.assertIn("invoices", paths)
        self.assertIn("admin", paths)


if __name__ == "__main__":
    unittest.main()
