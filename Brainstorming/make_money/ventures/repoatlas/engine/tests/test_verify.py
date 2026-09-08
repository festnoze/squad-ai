import os
import tempfile
import unittest

from atlas.config import DEFAULT_EXCLUDE_DIRS
from atlas.intake import walk_repo
from atlas.verify import check_paths, check_symbols, run_gates

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")
PYAPP = os.path.join(FIXTURES, "pyapp")

FILLER = " lorem" * 60  # keeps docs above the structure gate's size floor


def write(pack_dir, name, text):
    path = os.path.join(pack_dir, name)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


def full_pack(pack_dir, extra=""):
    for name in ("01_overview.md", "02_architecture.md", "06_dependencies.md",
                 "07_onboarding.md", "08_debt_register.md"):
        write(pack_dir, name,
              f"# {name}\nSee `src/billingcore/api.py`.{FILLER}{extra}")


class VerifyTests(unittest.TestCase):
    def setUp(self):
        self.known = {f["path"] for f in walk_repo(PYAPP, DEFAULT_EXCLUDE_DIRS)}

    def test_dead_path_fails_the_gate(self):
        with tempfile.TemporaryDirectory() as pack:
            full_pack(pack)
            write(pack, "08_debt_register.md",
                  f"# debt\nBroken ref `src/billingcore/ghost.py`.{FILLER}")
            passed, details = run_gates(pack, PYAPP, self.known,
                                        summaries=[], module_names=[])
            self.assertFalse(passed)
            self.assertEqual(len(details["dead_paths"]), 1)
            self.assertEqual(details["dead_paths"][0]["path"],
                             "src/billingcore/ghost.py")

    def test_clean_pack_passes(self):
        with tempfile.TemporaryDirectory() as pack:
            full_pack(pack)
            passed, details = run_gates(pack, PYAPP, self.known,
                                        summaries=[], module_names=[])
            self.assertTrue(passed, details)
            self.assertTrue(os.path.exists(
                os.path.join(pack, "verification_report.md")))

    def test_symbol_gate(self):
        summaries = [{
            "module": "core",
            "public_api": [
                {"symbol": "InvoiceEngine", "file": "src/billingcore/core.py"},
                {"symbol": "GhostClass", "file": "src/billingcore/core.py"},
            ],
        }]
        checked, missing = check_symbols(PYAPP, summaries)
        self.assertEqual(checked, 2)
        self.assertEqual([m["symbol"] for m in missing], ["GhostClass"])

    def test_urls_are_not_treated_as_paths(self):
        with tempfile.TemporaryDirectory() as pack:
            write(pack, "01_overview.md",
                  f"# o\nDocs at `https://example.com/a.py`.{FILLER}")
            checked, dead = check_paths(pack, PYAPP, self.known)
            self.assertEqual(dead, [])


if __name__ == "__main__":
    unittest.main()
