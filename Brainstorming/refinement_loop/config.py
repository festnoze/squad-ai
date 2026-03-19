"""Configuration for the refinement loop system."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent


@dataclass
class RefinementConfig:
    """Configuration for a refinement loop session.

    Change `subject`, `task_prompt`, and `test_requirements` to swap topics.
    """

    subject: str
    task_prompt: str
    test_requirements: str
    max_iterations: int = 5
    model: str = "claude-sonnet-4-6"
    workspace_dir: Path = field(default_factory=lambda: BASE_DIR / "workspace")
    logs_dir: Path = field(default_factory=lambda: BASE_DIR / "logs" / "iterations")
    max_budget_per_agent: float = 1.0
    max_turns_coder: int = 20
    max_turns_evaluator: int = 30


@dataclass
class CoderResult:
    code: str
    session_id: str | None = None
    cost_usd: float | None = None
    duration_ms: int | None = None


@dataclass
class EvaluatorResult:
    tests_passed: int
    tests_failed: int
    test_output: str
    performance_metrics: list[dict]
    code_quality_issues: list[str]
    improvement_suggestions: list[str]
    overall_assessment: str
    should_continue: bool
    session_id: str | None = None
    cost_usd: float | None = None
    duration_ms: int | None = None


# --- JSON schema the Evaluator must conform to ---

EVALUATOR_OUTPUT_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "tests_passed": {"type": "integer"},
        "tests_failed": {"type": "integer"},
        "test_output": {"type": "string"},
        "performance_metrics": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "n": {"type": "integer"},
                    "duration_seconds": {"type": "number"},
                    "result_count": {"type": "integer"},
                },
                "required": ["n", "duration_seconds"],
            },
        },
        "code_quality_issues": {"type": "array", "items": {"type": "string"}},
        "improvement_suggestions": {"type": "array", "items": {"type": "string"}},
        "overall_assessment": {"type": "string"},
        "should_continue": {"type": "boolean"},
    },
    "required": [
        "tests_passed",
        "tests_failed",
        "test_output",
        "performance_metrics",
        "improvement_suggestions",
        "overall_assessment",
        "should_continue",
    ],
}


# --- Default config: prime-number algorithm ---

def make_prime_config() -> RefinementConfig:
    """Pre-built config for the prime-number search subject."""
    return RefinementConfig(
        subject="Algorithme de recherche des nombres premiers",
        task_prompt=(
            "Ecris un module Python (solution.py) qui expose une fonction "
            "`find_primes(n: int) -> list[int]` retournant les n premiers "
            "nombres premiers.\n"
            "Le code doit etre performant, lisible, et bien documente.\n"
            "Tu ne dois modifier QUE le fichier solution.py."
        ),
        test_requirements=(
            "Ecris des tests pytest dans test_solution.py pour le module solution.py.\n"
            "Les tests doivent verifier :\n"
            "1. Correction : find_primes(0) == [], find_primes(1) == [2], "
            "find_primes(10) retourne les 10 premiers nombres premiers, etc.\n"
            "2. Performance : mesurer le temps d'execution pour N = 100, 1000, "
            "10_000 et 100_000 et reporter les durees.\n"
            "3. Edge cases : n negatif, n tres grand, types invalides.\n\n"
            "Execute les tests avec pytest -v et rapporte les resultats."
        ),
    )
