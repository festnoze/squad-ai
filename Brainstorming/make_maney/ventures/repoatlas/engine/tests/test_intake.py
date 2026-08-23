import os
import tempfile
import unittest

from atlas.config import DEFAULT_EXCLUDE_DIRS
from atlas.intake import detect_stacks, summarize, walk_repo

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")


class IntakeTests(unittest.TestCase):
    def test_walk_and_meters(self):
        files = walk_repo(os.path.join(FIXTURES, "pyapp"), DEFAULT_EXCLUDE_DIRS)
        paths = {f["path"] for f in files}
        self.assertIn("src/billingcore/api.py", paths)
        self.assertIn("pyproject.toml", paths)
        meters = summarize(files)
        self.assertGreater(meters["code_kloc"], 0)
        self.assertGreaterEqual(meters["code_file_count"], 3)

    def test_vendored_dirs_are_excluded(self):
        with tempfile.TemporaryDirectory() as tmp:
            os.makedirs(os.path.join(tmp, "node_modules", "lib"))
            os.makedirs(os.path.join(tmp, "src"))
            with open(os.path.join(tmp, "node_modules", "lib", "big.js"), "w") as fh:
                fh.write("x\n" * 5000)
            with open(os.path.join(tmp, "src", "app.js"), "w") as fh:
                fh.write("export const a = 1;\n")
            with open(os.path.join(tmp, "package-lock.json"), "w") as fh:
                fh.write("{}\n" * 100)
            files = walk_repo(tmp, DEFAULT_EXCLUDE_DIRS)
            paths = {f["path"] for f in files}
            self.assertEqual(paths, {"src/app.js"})

    def test_stack_detection(self):
        cases = {
            "pyapp": "python",
            "reactapp": "react",
            "ngapp": "angular",
            "csapp": "csharp",
        }
        for fixture, expected in cases.items():
            root = os.path.join(FIXTURES, fixture)
            files = walk_repo(root, DEFAULT_EXCLUDE_DIRS)
            self.assertIn(expected, detect_stacks(root, files),
                          msg=f"fixture {fixture}")


if __name__ == "__main__":
    unittest.main()
