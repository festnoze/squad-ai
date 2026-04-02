"""SQLAlchemy models package — import all models so Base.metadata knows about them."""

from backend.models.rule import Rule
from backend.models.cluster import Cluster
from backend.models.judge_prompt import JudgePrompt
from backend.models.test_case import TestCase
from backend.models.eval_result import EvalResult

__all__ = ["Rule", "Cluster", "JudgePrompt", "TestCase", "EvalResult"]
