"""Estate mode: survey many repositories, find coupling, triage depth.

The survey answers three questions the client cannot answer themselves:
1. What do we actually have? (per-repo meters and mini risk scores)
2. How do the repos depend on each other? (coupling edges)
3. Where does deep work pay off? (triage: deep / docs-only / inventory)

Triage thresholds are code, documented here, so every recommendation is
reproducible and defensible.
"""

import datetime
import json
import os

from . import gitstats, intake
from .scanners import scan_repo

# Pack pricing meters (kept in sync with PRD.md section 3)
PACK_BASE_PER_REPO = 290.0
PACK_TRANCHES = [(50.0, 14.0), (200.0, 6.0), (float("inf"), 2.5)]
MULTI_REPO_DISCOUNT = 0.15  # on per-repo totals beyond the 5th repo


def pack_price(code_kloc, repo_index=0):
    price = PACK_BASE_PER_REPO
    remaining = code_kloc
    for width, rate in PACK_TRANCHES:
        take = min(remaining, width)
        price += take * rate
        remaining -= take
        if remaining <= 0:
            break
    if repo_index >= 5:
        price *= (1.0 - MULTI_REPO_DISCOUNT)
    return round(price)


# Names too generic to identify a repo: matching on these would create
# false coupling edges between unrelated repos.
GENERIC_IDENTITIES = {
    "tests", "test", "src", "app", "apps", "lib", "libs", "utils", "scripts",
    "docs", "examples", "core", "common", "main", "shared", "tools", "api",
    "web", "server", "client", "backend", "frontend",
}


def survey_repo(repo_cfg, exclude_dirs, work_dir):
    """Metadata-level pass over one repo: meters, git health, identities."""
    info = intake.run_intake(repo_cfg, exclude_dirs, work_dir)
    stats = gitstats.collect(repo_cfg.path)
    scan = scan_repo(repo_cfg.path, info["files"])

    identities = {repo_cfg.name.lower()}
    for symbol in scan.symbols:
        if symbol["kind"] in ("package", "assembly"):
            identities.add(symbol["name"].lower())
        if symbol["kind"] == "namespace":
            identities.add(symbol["name"].split(".")[0].lower())
    for f in info["files"]:
        if f["path"].endswith("__init__.py"):
            parts = f["path"].split("/")
            if len(parts) >= 2:
                identities.add(parts[-2].lower())
    identities -= GENERIC_IDENTITIES

    external_refs = set()
    for dep in scan.deps:
        external_refs.add(dep["name"].lower())
    for imp in scan.imports:
        if imp["external"] is not False and not imp["target"].startswith("."):
            external_refs.add(imp["target"].lower())

    all_authors = {}
    commits_last_year = 0
    last_commit = ""
    if stats:
        cutoff = (datetime.date.today() - datetime.timedelta(days=365)).isoformat()
        commits_last_year = sum(1 for d in stats["commit_dates"] if d >= cutoff)
        last_commit = stats["commit_dates"][-1] if stats["commit_dates"] else ""
        for entry in stats["files"].values():
            for author, n in entry["authors"].items():
                all_authors[author] = all_authors.get(author, 0) + n

    from collections import Counter
    bus = gitstats.bus_factor(Counter(all_authors)) if all_authors else None

    return {
        "repo": repo_cfg.name,
        "stacks": info["stacks"],
        "meters": info["meters"],
        "routes": len(scan.routes),
        "symbols": len(scan.symbols),
        "identities": sorted(identities),
        "external_refs": sorted(external_refs),
        "git": {"available": stats is not None,
                "commits_last_year": commits_last_year,
                "last_commit": last_commit,
                "bus_factor": bus},
    }


def coupling_edges(surveys):
    """repo A -> repo B when A's external refs name one of B's identities."""
    edges = []
    for a in surveys:
        for b in surveys:
            if a["repo"] == b["repo"]:
                continue
            hits = sorted(set(a["external_refs"]) & set(b["identities"]))
            if hits:
                edges.append({"from": a["repo"], "to": b["repo"], "via": hits})
    return edges


def triage(survey, in_degree):
    """Documented thresholds -> deep / docs-only / inventory."""
    kloc = survey["meters"]["code_kloc"]
    git = survey["git"]
    active = git["commits_last_year"] >= 12 if git["available"] else None
    dormant = git["available"] and git["commits_last_year"] == 0
    risky_knowledge = git["bus_factor"] is not None and git["bus_factor"] <= 2
    load_bearing = in_degree > 0 or survey["routes"] >= 5

    if dormant and in_degree == 0:
        level, why = "inventory", "no commits in 12 months and nothing depends on it"
    elif (active or active is None) and (load_bearing or kloc >= 50) \
            and (risky_knowledge or not git["available"]):
        level, why = "deep", "actively changed, load-bearing, and knowledge is concentrated"
    elif load_bearing or kloc >= 20:
        level, why = "docs-only", "worth documenting; risk does not justify deeper work yet"
    else:
        level, why = "inventory", "small and quiet; keep it on the map, spend nothing more"
    return {"level": level, "why": why}


def run_survey(engagement):
    surveys = [survey_repo(r, engagement.exclude_dirs, engagement.work_dir)
               for r in engagement.repos]
    edges = coupling_edges(surveys)
    in_degree = {s["repo"]: 0 for s in surveys}
    for edge in edges:
        in_degree[edge["to"]] += 1

    deep_rank = 0
    for survey in sorted(surveys, key=lambda s: -s["meters"]["code_kloc"]):
        survey["triage"] = triage(survey, in_degree[survey["repo"]])
        survey["in_degree"] = in_degree[survey["repo"]]
        if survey["triage"]["level"] in ("deep", "docs-only"):
            survey["pack_quote_eur"] = pack_price(
                survey["meters"]["code_kloc"], repo_index=deep_rank)
            deep_rank += 1

    result = {"engagement": engagement.name, "repos": surveys,
              "coupling": edges,
              "totals": {
                  "repos": len(surveys),
                  "code_kloc": round(sum(s["meters"]["code_kloc"] for s in surveys), 1),
                  "survey_price_eur": 2900 + 90 * len(surveys),
              }}

    os.makedirs(engagement.out_dir, exist_ok=True)
    with open(os.path.join(engagement.out_dir, "survey.json"), "w",
              encoding="utf-8") as fh:
        json.dump(result, fh, indent=1)
    with open(os.path.join(engagement.out_dir, "survey.md"), "w",
              encoding="utf-8") as fh:
        fh.write(render_survey_md(result))
    return result


def render_survey_md(result):
    lines = [f"# Estate Survey: {result['engagement']}", ""]
    totals = result["totals"]
    lines.append(f"{totals['repos']} repositories, {totals['code_kloc']}k lines of "
                 f"code (vendored and generated excluded). "
                 f"Survey price basis: {totals['survey_price_eur']} EUR.")
    lines.append("")
    lines.append("| Repo | Stacks | kLOC | Routes | Commits/yr | Bus factor | Depended on by | Triage | Pack quote |")
    lines.append("|---|---|---|---|---|---|---|---|---|")
    for s in sorted(result["repos"], key=lambda r: -r["meters"]["code_kloc"]):
        git = s["git"]
        lines.append("| {repo} | {stacks} | {kloc} | {routes} | {commits} | {bus} | {deg} | **{triage}** | {quote} |".format(
            repo=s["repo"], stacks=",".join(s["stacks"]) or "?",
            kloc=s["meters"]["code_kloc"], routes=s["routes"],
            commits=git["commits_last_year"] if git["available"] else "no git",
            bus=git["bus_factor"] if git["bus_factor"] is not None else "-",
            deg=s["in_degree"], triage=s["triage"]["level"],
            quote=f"{s['pack_quote_eur']} EUR" if "pack_quote_eur" in s else "-"))
    lines.append("")
    lines.append("## Why each repo landed where it did")
    lines.append("")
    for s in result["repos"]:
        lines.append(f"- **{s['repo']}** -> {s['triage']['level']}: {s['triage']['why']}")
    lines.append("")
    lines.append("## Coupling between repositories")
    lines.append("")
    if result["coupling"]:
        lines.append("```mermaid")
        lines.append("graph LR")
        for edge in result["coupling"]:
            lines.append(f"  {edge['from']} --> {edge['to']}")
        lines.append("```")
        lines.append("")
        for edge in result["coupling"]:
            lines.append(f"- `{edge['from']}` depends on `{edge['to']}` via: "
                         + ", ".join(edge["via"]))
    else:
        lines.append("No cross-repo dependencies detected by identity matching. "
                     "(Runtime coupling via HTTP is only detectable with deeper scans.)")
    lines.append("")
    return "\n".join(lines)
