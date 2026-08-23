"""Module readers: build fact digests per module, optionally enrich via LLM.

The digest is the contract: scanners and git stats produce it; the agent
receives ONLY it (plus bounded source excerpts). Digest size is capped so a
1M-LOC estate costs the same per module as a small repo.
"""

import json
import os

from . import gitstats, prompts

EXCERPT_FILE_LIMIT = 6
EXCERPT_CHARS_PER_FILE = 2500
SYMBOL_CAP = 60


def build_digest(module, scan, git_stats, edges, repo_root):
    files_set = set(module["files"])
    symbols = [s for s in scan.symbols if s["file"] in files_set][:SYMBOL_CAP]
    routes = [r for r in scan.routes if r["file"] in files_set]
    internal = sorted({dst for src, dst in edges if src == module["name"]})
    git = gitstats.rollup(git_stats, module["files"]) if git_stats else None

    # excerpt priority: route handlers first, then largest files
    priority = [r["file"] for r in routes]
    priority += sorted(files_set - set(priority), key=lambda p: -_size(repo_root, p))
    excerpts = []
    for path in priority[:EXCERPT_FILE_LIMIT]:
        try:
            with open(os.path.join(repo_root, path), "r", encoding="utf-8",
                      errors="ignore") as fh:
                text = fh.read(EXCERPT_CHARS_PER_FILE)
        except OSError:
            continue
        excerpts.append(f"----- {path} -----\n{text}")

    return {
        "module": module["name"],
        "metrics": {"files": len(module["files"]), "loc": module["loc"]},
        "symbols": symbols,
        "routes": routes,
        "internal_deps": internal,
        "git": git,
        "excerpts": "\n".join(excerpts),
    }


def _size(root, rel):
    try:
        return os.path.getsize(os.path.join(root, rel))
    except OSError:
        return 0


def read_module(digest, stacks, client):
    """LLM pass. Returns the summary dict, or None (caller falls back)."""
    hints = "\n".join(prompts.STACK_HINTS.get(s, "") for s in stacks if s in prompts.STACK_HINTS)
    prompt = prompts.MODULE_READER.format(
        module=digest["module"],
        stacks=", ".join(stacks) or "unknown",
        stack_hints=hints,
        metrics=json.dumps(digest["metrics"]),
        symbols=json.dumps(digest["symbols"], indent=0),
        routes=json.dumps(digest["routes"], indent=0),
        internal_deps=json.dumps(digest["internal_deps"]),
        git=json.dumps(digest["git"]),
        excerpts=digest["excerpts"],
    )
    summary = client.run(prompt, expect_json=True, label=f"read_{digest['module']}")
    if not isinstance(summary, dict) or "purpose" not in summary:
        return None
    summary["module"] = digest["module"]
    return summary


def facts_only_summary(digest):
    """Deterministic fallback: an honest summary built purely from facts."""
    return {
        "module": digest["module"],
        "purpose": "(facts-only mode: purpose not interpreted; see symbols and routes)",
        "entry_points": [{"file": r["file"], "symbol": r["handler"],
                          "role": f"{r['method']} {r['path']}"}
                         for r in digest["routes"][:10]],
        "public_api": [{"symbol": s["name"], "kind": s["kind"],
                        "file": s["file"],
                        "summary": f"declared at line {s['line']}"}
                       for s in digest["symbols"][:30]],
        "data": [],
        "risks": [],
        "key_files": [{"path": f"{digest['excerpts'].splitlines()[0][6:-6].strip()}" if digest["excerpts"] else "",
                       "role": "largest or most routed file"}] if digest["excerpts"] else [],
        "open_questions": ["LLM enrichment was disabled; purpose, data flows and "
                           "risks need the agent pass or a human read."],
    }


def summaries_to_facts(graph, summaries):
    for summary in summaries:
        for api in summary.get("public_api", []):
            graph.add("public_api",
                      {"module": summary["module"], "symbol": api.get("symbol"),
                       "kind": api.get("kind"), "summary": api.get("summary")},
                      evidence=[{"path": api.get("file")}],
                      source="agent:reader")
        for risk in summary.get("risks", []):
            graph.add("risk", {"module": summary["module"],
                               "claim": risk.get("claim")},
                      evidence=[{"path": risk.get("evidence")}],
                      source="agent:reader")
