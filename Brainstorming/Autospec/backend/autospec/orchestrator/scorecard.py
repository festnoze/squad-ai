"""W0.2 — retrospective reliability KPIs from a ``build-monitor.jsonl`` timeline.

The build monitor (always on, ``orchestrator/build_monitor.py``) appends one JSON
event per line: agent calls (role, item, model, tokens, ok), pytest runs
(item, ok), phase transitions and narrative logs. This module turns that raw
timeline into the reliability metrics the Verified Swarm Upgrade waves are
measured against — green-on-first-attempt, attempts per story, stories failed,
tokens per green story, wall-clock — plus a per-model breakdown that later feeds
the model scorecard (W5.2) and judge calibration (W5.5).

Deliberately pure stdlib with no pipeline imports: it reads a file (or a list of
event dicts) so it runs as a CLI (``python -m autospec.orchestrator.scorecard
<path-or-project-id>``) and is trivially unit-tested against a fixture. This is
the yardstick every later wave is compared against; a wave that does not move a
KPI here gets reverted behind its flag rather than accreted.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class ModelStats:
    calls: int = 0
    ok: int = 0
    errors: int = 0
    in_tokens: int = 0
    out_tokens: int = 0

    @property
    def tokens(self) -> int:
        return self.in_tokens + self.out_tokens


@dataclass
class RunKPIs:
    """Reliability KPIs for a single build timeline."""

    wall_clock_s: float = 0.0
    agent_calls: int = 0
    agent_errors: int = 0
    in_tokens: int = 0
    out_tokens: int = 0
    # Buildable items that ran at least one test suite.
    items_tested: int = 0
    green_at_first_attempt: int = 0
    green_eventually: int = 0
    items_failed: int = 0
    total_attempts: int = 0  # pytest runs across tested items
    context_budget_warnings: int = 0
    by_role: dict[str, int] = field(default_factory=dict)
    by_model: dict[str, ModelStats] = field(default_factory=dict)
    # Per-item pytest ok-sequence (ts order), for drill-down / debugging.
    item_attempts: dict[str, list[bool]] = field(default_factory=dict)

    @property
    def total_tokens(self) -> int:
        return self.in_tokens + self.out_tokens

    @property
    def green_at_1_rate(self) -> float:
        return self.green_at_first_attempt / self.items_tested if self.items_tested else 0.0

    @property
    def failure_rate(self) -> float:
        return self.items_failed / self.items_tested if self.items_tested else 0.0

    @property
    def avg_attempts_to_green(self) -> float:
        greens = [
            len(seq) for seq in self.item_attempts.values() if any(seq)
        ]
        return sum(greens) / len(greens) if greens else 0.0

    @property
    def tokens_per_green_story(self) -> float:
        return self.total_tokens / self.green_eventually if self.green_eventually else 0.0


def load_events(source: str | Path) -> list[dict]:
    """Parse a ``build-monitor.jsonl`` file into a list of event dicts.

    Malformed lines are skipped (the timeline is best-effort append-only and may
    be truncated if a run was killed mid-write)."""
    path = Path(source)
    events: list[dict] = []
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return events
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            events.append(obj)
    return events


def compute(events: list[dict]) -> RunKPIs:
    """Compute reliability KPIs from an ordered list of timeline events."""
    k = RunKPIs()
    timestamps: list[float] = []

    for ev in events:
        ts = ev.get("ts")
        if isinstance(ts, (int, float)):
            timestamps.append(float(ts))
        kind = ev.get("kind")

        if kind == "agent":
            k.agent_calls += 1
            role = str(ev.get("role") or "?")
            k.by_role[role] = k.by_role.get(role, 0) + 1
            ok = bool(ev.get("ok", True))
            it = int(ev.get("in_tokens", 0) or 0)
            ot = int(ev.get("out_tokens", 0) or 0)
            k.in_tokens += it
            k.out_tokens += ot
            if not ok:
                k.agent_errors += 1
            model = str(ev.get("model") or "?")
            ms = k.by_model.setdefault(model, ModelStats())
            ms.calls += 1
            ms.in_tokens += it
            ms.out_tokens += ot
            if ok:
                ms.ok += 1
            else:
                ms.errors += 1

        elif kind == "pytest":
            item = str(ev.get("item") or "?")
            if item.startswith("phase:"):
                continue  # phase-level checks are not buildable stories
            k.item_attempts.setdefault(item, []).append(bool(ev.get("ok", False)))

        elif kind == "context_budget":
            k.context_budget_warnings += 1

    # Derive per-item outcomes from the pytest ok-sequences.
    for seq in k.item_attempts.values():
        if not seq:
            continue
        k.items_tested += 1
        k.total_attempts += len(seq)
        if seq[0]:
            k.green_at_first_attempt += 1
        if any(seq):
            k.green_eventually += 1
        else:
            k.items_failed += 1

    if timestamps:
        k.wall_clock_s = max(timestamps) - min(timestamps)
    return k


def format_report(k: RunKPIs) -> str:
    """Human-readable one-screen KPI summary."""
    lines = [
        "== Verified Swarm — run KPIs ==",
        f"wall-clock:            {k.wall_clock_s:.0f}s",
        f"agent calls:           {k.agent_calls} ({k.agent_errors} errors)",
        f"tokens:                {k.total_tokens:,} (in {k.in_tokens:,} / out {k.out_tokens:,})",
        f"items tested:          {k.items_tested}",
        f"green @ first attempt: {k.green_at_first_attempt} ({k.green_at_1_rate:.0%})",
        f"green eventually:      {k.green_eventually}",
        f"items failed:          {k.items_failed} ({k.failure_rate:.0%})",
        f"avg attempts→green:    {k.avg_attempts_to_green:.2f}",
        f"tokens / green story:  {k.tokens_per_green_story:,.0f}",
        f"context warnings:      {k.context_budget_warnings}",
        "",
        "by role:  " + ", ".join(f"{r}={n}" for r, n in sorted(k.by_role.items())),
        "by model:",
    ]
    for model, ms in sorted(k.by_model.items()):
        lines.append(
            f"  {model:32} calls={ms.calls:4} ok={ms.ok:4} err={ms.errors:3} "
            f"tokens={ms.tokens:,}"
        )
    return "\n".join(lines)


def _resolve_path(arg: str) -> Path:
    """Accept either a direct path to a build-monitor.jsonl or a project id
    (resolved against the workspace). The storage import is lazy so the module
    stays pure for unit tests."""
    p = Path(arg)
    if p.exists():
        return p
    try:
        from ..storage import workspace_dir  # lazy: avoid import cost in tests

        candidate = workspace_dir(arg) / "build-monitor.jsonl"
        if candidate.exists():
            return candidate
    except Exception:
        pass
    return p


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv:
        print("usage: python -m autospec.orchestrator.scorecard <path-or-project-id>")
        return 2
    path = _resolve_path(argv[0])
    events = load_events(path)
    if not events:
        print(f"no timeline events found at {path}")
        return 1
    print(format_report(compute(events)))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
