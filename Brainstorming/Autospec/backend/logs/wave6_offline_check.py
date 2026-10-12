"""Offline check of the wave 6 traceability fix against the REAL supervised run.

Loads drv-p3-9ae648a7's persisted state, rescans its tests/ and frontend/src the
way the pipeline does, and prints the report BEFORE (story-qualified ids only)
and AFTER (story + task ids folded onto canonical criteria). Temporary tool,
lives in logs/ and is not part of the repo's test suite.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from autospec.orchestrator import traceability  # noqa: E402

WS = Path(r"C:\Dev\squad-ai\Brainstorming\Autospec\workspace\drv-p3-9ae648a7")


def load_stories() -> list[dict]:
    state = json.loads((WS / "autospec-state.json").read_text(encoding="utf-8"))
    return state.get("stories", [])


def collect_sources() -> dict[str, str]:
    out: dict[str, str] = {}
    for p in WS.rglob("*.py"):
        if "node_modules" in p.parts or "__pycache__" in p.parts or ".venv" in p.parts:
            continue
        rel = p.relative_to(WS).as_posix()
        if "test" not in Path(rel).name and "/tests/" not in "/" + rel:
            continue
        out[rel] = p.read_text(encoding="utf-8", errors="replace")
    root = WS / "frontend" / "src"
    if root.is_dir():
        for pattern in ("*.test.ts", "*.test.tsx", "*.spec.ts", "*.spec.tsx"):
            for p in root.rglob(pattern):
                if "node_modules" in p.parts:
                    continue
                out[p.relative_to(WS).as_posix()] = p.read_text(
                    encoding="utf-8", errors="replace"
                )
    return out


def build_aliases(stories: list[dict]) -> dict[str, str]:
    aliases: dict[str, str] = {}
    for s in stories:
        bare = {c["id"] for c in s.get("acceptance_criteria", [])}
        for c in s.get("acceptance_criteria", []):
            qualified = f"{s['id']}.{c['id']}"
            aliases[qualified] = qualified
        for t in s.get("tasks", []):
            for c in t.get("acceptance_criteria", []):
                aliases[f"{t['id']}.{c['id']}"] = (
                    f"{s['id']}.{c['id']}" if c["id"] in bare else f"{t['id']}.{c['id']}"
                )
    return aliases


def main() -> None:
    stories = load_stories()
    sources = collect_sources()
    markers: set[str] = set()
    for src in sources.values():
        markers |= traceability.ac_ids_in_source(src)

    print(f"stories        : {len(stories)}")
    print(f"tasks          : {sum(len(s.get('tasks', [])) for s in stories)}")
    print(f"test files     : {len(sources)}")
    print(f"distinct markers: {len(markers)} -> {sorted(markers)}")

    story_only = {
        f"{s['id']}.{c['id']}" for s in stories for c in s.get("acceptance_criteria", [])
    }
    before = traceability.coverage_report(story_only, sources)
    declared_bare_before = {
        c["id"] for s in stories for c in s.get("acceptance_criteria", [])
    }
    orphans_before = [o for o in before["orphans"] if o not in declared_bare_before]
    print("\nBEFORE (story-qualified ids only)")
    print(f"  declared : {len(story_only)}")
    print(f"  covered  : {len(before['covered'])}")
    print(f"  uncovered: {len(before['uncovered'])} {before['uncovered']}")
    print(f"  orphans  : {len(orphans_before)} {orphans_before}")

    aliases = build_aliases(stories)
    after = traceability.fold_aliases(
        traceability.coverage_report(set(aliases), sources), aliases
    )
    declared_bare = set(declared_bare_before) | {
        c["id"]
        for s in stories
        for t in s.get("tasks", [])
        for c in t.get("acceptance_criteria", [])
    }
    orphans_after = [o for o in after["orphans"] if o not in declared_bare]
    canonical = set(aliases.values())
    print("\nAFTER (story + task ids, aliases folded)")
    print(f"  declared ids : {len(aliases)} (canonical criteria: {len(canonical)})")
    print(f"  covered  : {len(after['covered'])}")
    print(f"  uncovered: {len(after['uncovered'])} {after['uncovered']}")
    print(f"  orphans  : {len(orphans_after)} {orphans_after}")

    unexplained = sorted(m for m in markers if m not in aliases and m not in declared_bare)
    print(f"\nmarkers neither declared nor bare: {len(unexplained)} {unexplained}")


if __name__ == "__main__":
    main()
