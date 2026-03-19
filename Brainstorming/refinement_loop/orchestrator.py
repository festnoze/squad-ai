"""Orchestrator — runs the Coder <-> Evaluator refinement loop."""

from __future__ import annotations

import asyncio
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

# Allow launching Claude Code SDK from within a Claude Code session.
os.environ.pop("CLAUDECODE", None)

# Force UTF-8 output on Windows to avoid cp1252 encoding errors.
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# Ensure the project root is on sys.path so `config` and `agents` resolve.
_PROJECT_ROOT = Path(__file__).resolve().parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

# Monkey-patch the SDK message parser to gracefully skip unknown message types
# (e.g. rate_limit_event) instead of raising MessageParseError.
import claude_agent_sdk._internal.message_parser as _mp
import claude_agent_sdk._internal.client as _client

_original_parse_message = _mp.parse_message


def _patched_parse_message(data):
    try:
        return _original_parse_message(data)
    except _mp.MessageParseError:
        # Return a SystemMessage so the stream continues uninterrupted.
        return _mp.SystemMessage(
            subtype=data.get("type", "unknown"),
            data=data,
        )


# Patch both the module-level function AND the already-imported reference in client.
_mp.parse_message = _patched_parse_message
_client.parse_message = _patched_parse_message

from agents.coder import arun_coder
from agents.evaluator import arun_evaluator
from config import CoderResult, EvaluatorResult, RefinementConfig, make_prime_config


def _ensure_workspace(config: RefinementConfig) -> None:
    config.workspace_dir.mkdir(parents=True, exist_ok=True)
    config.logs_dir.mkdir(parents=True, exist_ok=True)


def _save_iteration(
    config: RefinementConfig,
    iteration: int,
    coder: CoderResult,
    evaluator: EvaluatorResult,
) -> None:
    data = {
        "iteration": iteration,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "coder": {
            "code_length": len(coder.code),
            "session_id": coder.session_id,
            "cost_usd": coder.cost_usd,
            "duration_ms": coder.duration_ms,
        },
        "evaluator": {
            "tests_passed": evaluator.tests_passed,
            "tests_failed": evaluator.tests_failed,
            "test_output": evaluator.test_output,
            "performance_metrics": evaluator.performance_metrics,
            "code_quality_issues": evaluator.code_quality_issues,
            "improvement_suggestions": evaluator.improvement_suggestions,
            "overall_assessment": evaluator.overall_assessment,
            "should_continue": evaluator.should_continue,
            "session_id": evaluator.session_id,
            "cost_usd": evaluator.cost_usd,
            "duration_ms": evaluator.duration_ms,
        },
    }
    path = config.logs_dir / f"iter_{iteration:03d}.json"
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"  -> Log saved: {path}")


def _format_feedback(evaluator: EvaluatorResult) -> str:
    lines = [
        f"Tests passed: {evaluator.tests_passed}",
        f"Tests failed: {evaluator.tests_failed}",
        "",
        "## Test output (truncated)",
        evaluator.test_output[:2000],
        "",
    ]
    if evaluator.performance_metrics:
        lines.append("## Performance metrics")
        for m in evaluator.performance_metrics:
            lines.append(f"  N={m.get('n', '?')} -> {m.get('duration_seconds', '?')}s")
        lines.append("")
    if evaluator.code_quality_issues:
        lines.append("## Code quality issues")
        for issue in evaluator.code_quality_issues:
            lines.append(f"  - {issue}")
        lines.append("")
    if evaluator.improvement_suggestions:
        lines.append("## Improvement suggestions")
        for s in evaluator.improvement_suggestions:
            lines.append(f"  - {s}")
        lines.append("")
    lines.append(f"## Overall assessment\n{evaluator.overall_assessment}")
    return "\n".join(lines)


def _print_iteration_summary(iteration: int, evaluator: EvaluatorResult) -> None:
    status = "PASS" if evaluator.tests_failed == 0 else "FAIL"
    print(f"\n  [{status}] Iteration {iteration}: "
          f"{evaluator.tests_passed} passed, {evaluator.tests_failed} failed")
    if evaluator.performance_metrics:
        for m in evaluator.performance_metrics:
            print(f"    N={m.get('n', '?'):>7} -> {m.get('duration_seconds', '?'):.4f}s")
    print(f"  Assessment: {evaluator.overall_assessment[:200]}")
    eval_cost = evaluator.cost_usd or 0.0
    print(f"  Evaluator cost: ${eval_cost:.4f}")


def _print_final_summary(
    config: RefinementConfig,
    total_iterations: int,
    total_cost: float,
) -> None:
    print(f"\n{'='*60}")
    print(f"  REFINEMENT COMPLETE")
    print(f"{'='*60}")
    print(f"  Subject: {config.subject}")
    print(f"  Iterations: {total_iterations}/{config.max_iterations}")
    print(f"  Total cost: ${total_cost:.4f}")
    print(f"  Workspace: {config.workspace_dir}")
    print(f"  Logs: {config.logs_dir}")
    print(f"{'='*60}\n")


async def arun_refinement_loop(config: RefinementConfig) -> None:
    """Main refinement loop: Coder <-> Evaluator."""

    _ensure_workspace(config)
    previous_feedback: str | None = None
    total_cost = 0.0
    final_iteration = 0

    for iteration in range(1, config.max_iterations + 1):
        final_iteration = iteration
        print(f"\n{'='*60}")
        print(f"  ITERATION {iteration}/{config.max_iterations}")
        print(f"{'='*60}")

        # --- Coder ---
        print(f"\n  >> Running Coder Agent (iteration {iteration})...")
        coder_result = await arun_coder(config, iteration, previous_feedback)
        total_cost += coder_result.cost_usd or 0.0
        print(f"  Coder done. Cost: ${coder_result.cost_usd or 0:.4f}")

        # --- Evaluator ---
        print(f"\n  >> Running Evaluator Agent (iteration {iteration})...")
        eval_result = await arun_evaluator(config, iteration)
        total_cost += eval_result.cost_usd or 0.0

        # --- Save & report ---
        _save_iteration(config, iteration, coder_result, eval_result)
        _print_iteration_summary(iteration, eval_result)

        # --- Convergence check ---
        if eval_result.tests_failed == 0 and not eval_result.should_continue:
            print(f"\n  >> Convergence reached at iteration {iteration}!")
            break

        # --- Prepare feedback for next iteration ---
        previous_feedback = _format_feedback(eval_result)

    _print_final_summary(config, final_iteration, total_cost)


def main() -> None:
    config = make_prime_config()
    asyncio.run(arun_refinement_loop(config))


if __name__ == "__main__":
    main()
