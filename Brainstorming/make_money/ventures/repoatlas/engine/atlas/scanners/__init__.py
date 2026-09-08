"""Scanner registry: pick deterministic extractors for a repo's stacks."""

from .base import ScanResult, merge_results
from .python_scanner import PythonScanner
from .csharp_scanner import CSharpScanner
from .js_scanner import JsScanner

SCANNERS = [PythonScanner(), CSharpScanner(), JsScanner()]


def scan_repo(root, files):
    """Run every applicable scanner over the repo's files, merge results."""
    results = []
    for scanner in SCANNERS:
        subset = [f for f in files if f["ext"] in scanner.extensions]
        if subset or scanner.manifest_names:
            results.append(scanner.scan(root, subset, files))
    return merge_results(results)
