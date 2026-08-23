"""RepoAtlas engine CLI.

  python run_atlas.py intake  --config atlas.json
  python run_atlas.py survey  --config atlas.json
  python run_atlas.py pack    --config atlas.json [--repo NAME] [--no-llm]
  python run_atlas.py diff    --config atlas.json --repo NAME

intake: meters per repo (the pricing basis).
survey: estate triage across every repo (coupling, mini-scores, quotes).
pack:   full pipeline per repo: scan -> map -> read -> write -> verify.
diff:   drift between the two most recent fact-graph snapshots of a repo.
"""

import argparse
import json
import os
import sys

from atlas import estate, gitstats, intake, mapping, readers, synthesis, verify
from atlas.claude_client import ClaudeClient
from atlas.config import load_engagement
from atlas.factgraph import FactGraph
from atlas.scanners import scan_repo


def cmd_intake(engagement, args):
    for repo in engagement.repos:
        info = intake.run_intake(repo, engagement.exclude_dirs, engagement.work_dir)
        meters = info["meters"]
        print(f"{repo.name:24s} stacks={','.join(info['stacks']) or '?':18s} "
              f"code={meters['code_kloc']:>8.1f}k LOC  "
              f"files={meters['code_file_count']}")


def cmd_survey(engagement, args):
    result = estate.run_survey(engagement)
    print(f"Survey written: {os.path.join(engagement.out_dir, 'survey.md')}")
    for repo in result["repos"]:
        quote = f"  pack {repo['pack_quote_eur']} EUR" if "pack_quote_eur" in repo else ""
        print(f"  {repo['repo']:24s} -> {repo['triage']['level']:10s}{quote}")
    print(f"Totals: {result['totals']['repos']} repos, "
          f"{result['totals']['code_kloc']}k LOC, survey basis "
          f"{result['totals']['survey_price_eur']} EUR")


def cmd_pack(engagement, args):
    targets = [engagement.repo(args.repo)] if args.repo else engagement.repos
    llm_on = engagement.llm_enabled and not args.no_llm
    failures = 0
    for repo in targets:
        ok = build_pack(engagement, repo, llm_on)
        failures += 0 if ok else 1
    sys.exit(1 if failures else 0)


def build_pack(engagement, repo, llm_on):
    print(f"== {repo.name} ==")
    info = intake.run_intake(repo, engagement.exclude_dirs, engagement.work_dir)
    files = info["files"]
    scan = scan_repo(repo.path, files)
    git_stats = gitstats.collect(repo.path)
    modules = mapping.detect_modules(files, engagement.max_modules)
    edges = mapping.internal_edges(modules, scan, files)
    sizes = {f["path"]: f["lines"] for f in files}
    hotspots = gitstats.hotspots(git_stats, sizes)

    work = os.path.join(engagement.work_dir, repo.name)
    client = ClaudeClient(os.path.join(work, "logs"),
                          model=engagement.llm_model) if llm_on else None
    if llm_on and (client is None or not client.available):
        print("  claude CLI not found: falling back to facts-only mode")
        client = None

    # fact graph snapshot (scanner facts)
    graph = FactGraph(repo.name)
    for s in scan.symbols:
        graph.add("symbol", {k: s[k] for k in ("name", "kind", "file")},
                  evidence=[{"path": s["file"], "line": s["line"]}],
                  source="scanner", verified=True)
    for r in scan.routes:
        graph.add("route", {k: r[k] for k in ("method", "path", "file")},
                  evidence=[{"path": r["file"], "line": r["line"]}],
                  source="scanner", verified=True)
    for d in scan.deps:
        graph.add("dependency", d, evidence=[{"path": d["file"]}],
                  source="scanner", verified=True)
    for src, dst in edges:
        graph.add("module_edge", {"from": src, "to": dst}, source="scanner",
                  verified=True)

    summaries, git_by_module = [], {}
    for module in modules:
        digest = readers.build_digest(module, scan, git_stats, edges, repo.path)
        git_by_module[module["name"]] = digest["git"]
        summary = readers.read_module(digest, info["stacks"], client) if client else None
        summaries.append(summary or readers.facts_only_summary(digest))
    readers.summaries_to_facts(graph, summaries)

    snap_dir = os.path.join(work, "snapshots")
    os.makedirs(snap_dir, exist_ok=True)
    snap_index = len(os.listdir(snap_dir)) + 1
    graph.save(os.path.join(snap_dir, f"{snap_index:03d}.json"),
               meta={"modules": [m["name"] for m in modules]})

    manifests = [{"file": d["file"], "note": f"{d['ecosystem']} manifest"}
                 for d in {d["file"]: d for d in scan.deps}.values()]
    context = {
        "repo": repo.name, "stacks": info["stacks"], "meters": info["meters"],
        "modules": modules, "summaries": summaries, "edges": edges,
        "hotspots": hotspots, "deps": scan.deps, "manifests": manifests,
        "notes": scan.notes, "git_by_module": git_by_module,
    }
    pack_dir = os.path.join(engagement.out_dir, repo.name, "pack")
    written = synthesis.write_pack(pack_dir, context, client,
                                   language=engagement.language)

    known = {f["path"] for f in files}
    passed, details = verify.run_gates(pack_dir, repo.path, known, summaries,
                                       [m["name"] for m in modules])
    status = "PASS" if passed else "FAIL"
    print(f"  {len(written)} docs -> {pack_dir}")
    print(f"  verification: {status} "
          f"(dead paths: {len(details['dead_paths'])}, "
          f"missing symbols: {len(details['missing_symbols'])})")
    return passed


def cmd_diff(engagement, args):
    repo = engagement.repo(args.repo)
    snap_dir = os.path.join(engagement.work_dir, repo.name, "snapshots")
    snaps = sorted(os.listdir(snap_dir)) if os.path.isdir(snap_dir) else []
    if len(snaps) < 2:
        raise SystemExit("need at least two snapshots; run `pack` twice")
    old = FactGraph.load(os.path.join(snap_dir, snaps[-2]))
    new = FactGraph.load(os.path.join(snap_dir, snaps[-1]))
    delta = new.diff(old)
    print(f"Drift {snaps[-2]} -> {snaps[-1]}: "
          f"+{len(delta['added'])} facts, -{len(delta['removed'])} facts")
    for fact in delta["added"][:20]:
        print(f"  + {fact['kind']}: {json.dumps(fact['data'])}")
    for fact in delta["removed"][:20]:
        print(f"  - {fact['kind']}: {json.dumps(fact['data'])}")


def main():
    parser = argparse.ArgumentParser(description="RepoAtlas engine")
    parser.add_argument("command", choices=["intake", "survey", "pack", "diff"])
    parser.add_argument("--config", required=True)
    parser.add_argument("--repo")
    parser.add_argument("--no-llm", action="store_true")
    args = parser.parse_args()
    engagement = load_engagement(args.config)
    {"intake": cmd_intake, "survey": cmd_survey,
     "pack": cmd_pack, "diff": cmd_diff}[args.command](engagement, args)


if __name__ == "__main__":
    main()
