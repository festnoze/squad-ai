"""Test case generation service — creates test scenarios for rules."""

import json
import logging
from pathlib import Path

from backend.services.llm_client import achat_completion

logger = logging.getLogger(__name__)

_PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"


def _load_prompt(name: str) -> str:
    return (_PROMPTS_DIR / name).read_text(encoding="utf-8")


DATASET_GENERATION_SYSTEM_PROMPT = _load_prompt("generate_dataset.txt")


async def agenerate_test_cases(
    rule: dict,
    scenario_type: str,
    count: int = 2,
) -> list[dict]:
    """Generate test cases for a given rule and scenario type.

    Args:
        rule: Dict with rule_code, text, source_section, and id.
        scenario_type: One of 'baseline', 'edge', 'adversarial'.
        count: Number of test cases to generate per call.

    Returns:
        List of test case dicts with user_input, expected_behavior, tags, and context.
    """
    user_message = (
        f"Generate exactly {count} {scenario_type} test cases for the following rule:\n\n"
        f"**Rule code**: {rule['rule_code']}\n"
        f"**Rule text**: {rule['text']}\n"
        f"**Source section**: {rule.get('source_section', 'N/A')}\n\n"
        f"Scenario type: {scenario_type}\n"
        f"Remember: {scenario_type} scenarios should be "
        + {
            "baseline": "straightforward happy-path tests where a compliant system should easily pass.",
            "edge": "unusual boundary conditions that test edge cases and ambiguity.",
            "adversarial": "deliberately crafted inputs designed to trick the system into violating this specific rule.",
        }.get(scenario_type, "well-crafted tests.")
    )

    raw = await achat_completion(
        system_prompt=DATASET_GENERATION_SYSTEM_PROMPT,
        user_message=user_message,
        response_format={"type": "json_object"},
    )

    data = json.loads(raw)
    test_cases = data.get("test_cases", [])

    logger.info(
        "Generated %d %s test cases for rule %s",
        len(test_cases), scenario_type, rule['rule_code']
    )

    # Normalize: ensure rule_ids is present
    for tc in test_cases:
        tc["rule_ids"] = [rule["id"]]
        tc["scenario_type"] = scenario_type
        if "tags" not in tc:
            tc["tags"] = []

    return test_cases
