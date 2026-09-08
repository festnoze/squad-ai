"""Verification gates: no deliverable ships with claims the repo can't back.

G1 path gate: every path-looking token cited in generated markdown must
   exist in the scanned repo. 100% required.
G2 symbol gate: every public_api symbol must be findable in its claimed
   file. 98% required.
G3 structure gate: the pack contains every required file, non-trivially.

The report itself ships inside the pack: it is the product's honesty.
"""

import os
import re

PATH_TOKEN_RE = re.compile(r"`([\w\-./\\]+?\.[A-Za-z0-9]{1,6})(?::\d+)?`")
REQUIRED_DOCS = ("01_overview.md", "02_architecture.md", "06_dependencies.md",
                 "07_onboarding.md", "08_debt_register.md")
NON_PATH_HINTS = ("http://", "https://", "*.")


def check_paths(pack_dir, repo_root, known_files):
    """G1: verify every cited path. Returns (checked, dead:[{doc, path}])."""
    checked, dead = 0, []
    basenames = {p.split("/")[-1] for p in known_files}
    for doc_dir, _, names in os.walk(pack_dir):
        for name in names:
            if not name.endswith(".md") or name == "verification_report.md":
                continue
            doc = os.path.join(doc_dir, name)
            with open(doc, "r", encoding="utf-8") as fh:
                text = fh.read()
            for match in PATH_TOKEN_RE.finditer(text):
                token = match.group(1).replace("\\", "/")
                if any(h in token for h in NON_PATH_HINTS):
                    continue
                checked += 1
                if token in known_files or token.split("/")[-1] in basenames \
                        or os.path.exists(os.path.join(repo_root, token)):
                    continue
                dead.append({"doc": os.path.relpath(doc, pack_dir), "path": token})
    return checked, dead


def check_symbols(repo_root, summaries):
    """G2: grep every public_api symbol in its claimed file."""
    checked, missing = 0, []
    for summary in summaries:
        for api in summary.get("public_api", []):
            symbol, rel = api.get("symbol"), api.get("file")
            if not symbol or not rel:
                continue
            checked += 1
            full = os.path.join(repo_root, rel)
            try:
                with open(full, "r", encoding="utf-8", errors="ignore") as fh:
                    if symbol not in fh.read():
                        missing.append({"module": summary["module"],
                                        "symbol": symbol, "file": rel})
            except OSError:
                missing.append({"module": summary["module"],
                                "symbol": symbol, "file": rel})
    return checked, missing


def check_structure(pack_dir, module_names):
    problems = []
    for name in REQUIRED_DOCS:
        path = os.path.join(pack_dir, name)
        if not os.path.exists(path):
            problems.append(f"missing {name}")
        elif os.path.getsize(path) < 200:
            problems.append(f"{name} is suspiciously small")
    for module in module_names:
        if not os.path.exists(os.path.join(pack_dir, "03_modules", f"{module}.md")):
            problems.append(f"missing module doc for {module}")
    return problems


def run_gates(pack_dir, repo_root, known_files, summaries, module_names):
    checked_paths, dead = check_paths(pack_dir, repo_root, known_files)
    checked_syms, missing = check_symbols(repo_root, summaries)
    structure = check_structure(pack_dir, module_names)

    path_rate = 1.0 if checked_paths == 0 else 1 - len(dead) / checked_paths
    sym_rate = 1.0 if checked_syms == 0 else 1 - len(missing) / checked_syms
    passed = (not dead) and sym_rate >= 0.98 and not structure

    lines = ["# Verification report", "",
             f"**Result: {'PASS' if passed else 'FAIL'}**", "",
             f"- G1 paths: {checked_paths} cited paths checked, "
             f"{len(dead)} dead ({path_rate:.1%} valid; required 100%)",
             f"- G2 symbols: {checked_syms} symbols checked, "
             f"{len(missing)} not found ({sym_rate:.1%} valid; required 98%)",
             f"- G3 structure: {'complete' if not structure else '; '.join(structure)}",
             ""]
    if dead:
        lines += ["## Dead paths", ""]
        lines += [f"- {d['doc']}: `{d['path']}`" for d in dead]
    if missing:
        lines += ["", "## Missing symbols", ""]
        lines += [f"- {m['module']}: {m['symbol']} not found in `{m['file']}`"
                  for m in missing]
    lines.append("")

    with open(os.path.join(pack_dir, "verification_report.md"), "w",
              encoding="utf-8") as fh:
        fh.write("\n".join(lines))
    return passed, {"dead_paths": dead, "missing_symbols": missing,
                    "structure": structure}
