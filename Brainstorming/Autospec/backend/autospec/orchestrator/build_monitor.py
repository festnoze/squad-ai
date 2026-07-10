"""Build monitor — the persisted JSONL timeline of a pipeline run.

ALWAYS on (the write is cheap and per-project, and the timeline is the primary
after-the-fact diagnostic — a red run whose only trace was a volatile SSE log
line is impossible to debug once the process is gone). Each run appends events
to ``workspace/<project>/build-monitor.jsonl`` and, when ``BUILD_MONITOR_DIR``
is set (e.g. by ``scripts/build_driver.py`` to collect one dir per run), mirrors
them into a single cross-project ``timeline.jsonl`` there too. The goal is to
make *what actually happened* during a headless build legible after the fact:
every agent round-trip (role, item, duration, ok/error), every real test run
(green/red + tail), every narrative pipeline log line, phase transitions and the
final outcome — so the common failure modes can be diagnosed.

This module is intentionally defensive: any I/O error is swallowed so monitoring
never perturbs a build.
"""

from __future__ import annotations

import json
import os
import threading
import time

from ..storage import workspace_dir


def _aggregate_path():
    d = os.environ.get("BUILD_MONITOR_DIR", "").strip()
    return (d and os.path.join(d, "timeline.jsonl")) or ""


class BuildMonitor:
    """Per-pipeline writer. Cheap to construct; every emit is best-effort."""

    _agg_lock = threading.Lock()

    def __init__(self, state):
        self._state = state
        self._lock = threading.Lock()

    # -- event kinds -------------------------------------------------------
    def agent_call(self, role, item_id, duration_ms, ok, error="",
                   in_tokens=0, out_tokens=0, model="", prompt_chars=0):
        self._emit(
            "agent", role=role or "?", item=item_id,
            duration_ms=round(duration_ms), ok=ok,
            error=(error or "")[:400], in_tokens=in_tokens, out_tokens=out_tokens,
            # W0.3: resolved model id per call (tier routing / ladder / scorecard).
            # W0.4: prompt size, for context-budget telemetry.
            model=model or "", prompt_chars=prompt_chars,
        )

    def pytest(self, item_id, ok, summary=""):
        self._emit("pytest", item=item_id, ok=ok, summary=(summary or "")[:600])

    def log(self, source, line):
        """Mirror one narrative pipeline log line (``Pipeline._log``) into the
        timeline. The SSE bus those lines are published on is volatile — without
        this mirror the run's actual story (scope gate decisions, merges,
        reverts, requeues, splits) dies with the process."""
        self._emit("log", source=source or "?", line=(line or "")[:2000])

    def phase(self, name):
        self._emit("phase", name=name)

    def event(self, kind, **fields):
        self._emit(kind, **fields)

    # -- writer ------------------------------------------------------------
    def _emit(self, kind, **fields):
        try:
            phase = self._state.phase.value
        except Exception:
            phase = "?"
        rec = {
            "ts": round(time.time(), 3),
            "kind": kind,
            "project": getattr(self._state, "id", "?"),
            "phase": phase,
            **fields,
        }
        line = json.dumps(rec, ensure_ascii=False)
        try:
            path = workspace_dir(self._state.id) / "build-monitor.jsonl"
            path.parent.mkdir(parents=True, exist_ok=True)
            with self._lock, open(path, "a", encoding="utf-8") as fh:
                fh.write(line + "\n")
        except OSError:
            pass
        agg = _aggregate_path()
        if agg:
            try:
                os.makedirs(os.path.dirname(agg), exist_ok=True)
                with BuildMonitor._agg_lock, open(agg, "a", encoding="utf-8") as fh:
                    fh.write(line + "\n")
            except OSError:
                pass
