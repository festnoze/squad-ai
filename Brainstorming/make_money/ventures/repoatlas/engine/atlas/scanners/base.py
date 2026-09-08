"""Scanner contract.

A scanner extracts FACTS a compiler-less heuristic can defend:
- symbols:  {name, kind, file, line, extra?}      (class, function, component, ...)
- routes:   {method, path, handler, file, line}   (HTTP surface)
- imports:  {file, target, external}              (dependency edges)
- deps:     {ecosystem, name, version, file}      (declared external packages)
- notes:    {file, note}                          (parse failures, oddities)

Scanners never guess intent. Anything that needs judgment goes to the agent
layer, which receives these facts as its ground truth.
"""

import os


class ScanResult:
    def __init__(self):
        self.symbols = []
        self.routes = []
        self.imports = []
        self.deps = []
        self.notes = []


def merge_results(results):
    merged = ScanResult()
    for r in results:
        merged.symbols += r.symbols
        merged.routes += r.routes
        merged.imports += r.imports
        merged.deps += r.deps
        merged.notes += r.notes
    return merged


class Scanner:
    name = "base"
    extensions = ()
    manifest_names = ()

    def scan(self, root, files, all_files):
        result = ScanResult()
        for f in files:
            try:
                with open(os.path.join(root, f["path"]), "r",
                          encoding="utf-8", errors="ignore") as fh:
                    text = fh.read()
            except OSError as exc:
                result.notes.append({"file": f["path"], "note": f"unreadable: {exc}"})
                continue
            self.scan_file(f["path"], text, result)
        self.scan_manifests(root, all_files, result)
        return result

    def scan_file(self, rel_path, text, result):
        raise NotImplementedError

    def scan_manifests(self, root, all_files, result):
        """Optional: extract declared dependencies from manifest files."""


def read_rel(root, rel_path):
    with open(os.path.join(root, rel_path), "r", encoding="utf-8",
              errors="ignore") as fh:
        return fh.read()
