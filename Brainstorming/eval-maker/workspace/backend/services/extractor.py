"""Rule extraction service — uses an LLM call to extract atomic rules from a system prompt."""

import json
import logging
from pathlib import Path

from backend.services.llm_client import achat_completion

logger = logging.getLogger(__name__)

_PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"


def _load_prompt(name: str) -> str:
    return (_PROMPTS_DIR / name).read_text(encoding="utf-8")


EXTRACTION_SYSTEM_PROMPT = _load_prompt("extract_rules.txt")
MERGE_SYSTEM_PROMPT_TEMPLATE = _load_prompt("merge_rules.txt")


async def _aextract_raw(prompt_text: str) -> list[dict]:
    """Extract raw rules from a system prompt using an LLM call with structured output.

    This is the first pass — it may return more than 50 rules.

    Args:
        prompt_text: The full text of the system prompt to analyze.

    Returns:
        A list of dicts, each with keys: rule_code, text, source_section, is_explicit.
    """
    user_message = f"Here is the system prompt to analyze. Extract every atomic rule/instruction from it:\n\n---\n{prompt_text}\n---"

    raw = await achat_completion(
        system_prompt=EXTRACTION_SYSTEM_PROMPT,
        user_message=user_message,
        response_format={"type": "json_object"},
    )

    data = json.loads(raw)
    rules = data.get("rules", [])

    logger.info("Extracted %d raw rules from prompt", len(rules))

    # Validate and normalize
    validated = []
    for i, rule in enumerate(rules):
        validated.append({
            "rule_code": rule.get("rule_code", f"R{i+1:02d}"),
            "text": rule.get("text", ""),
            "source_section": rule.get("source_section", ""),
            "is_explicit": rule.get("is_explicit", True),
        })

    return validated


async def _amerge_rules(rules: list[dict], target: int = 45) -> list[dict]:
    """Merge/deduplicate a list of rules down to a target count using an LLM call.

    Args:
        rules: The list of rule dicts to consolidate.
        target: The desired number of rules after merging.

    Returns:
        A consolidated list of rule dicts.
    """
    system_prompt = MERGE_SYSTEM_PROMPT_TEMPLATE.format(target=target)
    user_message = (
        f"Here are {len(rules)} rules to consolidate down to {target}:\n\n"
        + json.dumps(rules, indent=2, ensure_ascii=False)
    )

    raw = await achat_completion(
        system_prompt=system_prompt,
        user_message=user_message,
        response_format={"type": "json_object"},
    )

    data = json.loads(raw)
    merged = data.get("rules", [])

    logger.info("Merge pass: %d rules → %d rules", len(rules), len(merged))

    # Validate and normalize
    validated = []
    for i, rule in enumerate(merged):
        validated.append({
            "rule_code": rule.get("rule_code", f"R{i+1:02d}"),
            "text": rule.get("text", ""),
            "source_section": rule.get("source_section", ""),
            "is_explicit": rule.get("is_explicit", True),
        })

    return validated


async def aextract_rules(prompt_text: str) -> list[dict]:
    """Extract rules from a system prompt, with automatic merging if count exceeds 50.

    Orchestrates a two-pass extraction:
    1. Raw extraction via LLM (may return 80+ rules)
    2. If count > 50, a merge pass consolidates down to ~45 rules

    Args:
        prompt_text: The full text of the system prompt to analyze.

    Returns:
        A list of dicts, each with keys: rule_code, text, source_section, is_explicit.
        Guaranteed to contain at most 50 rules.
    """
    rules = await _aextract_raw(prompt_text)

    if len(rules) > 50:
        logger.info(
            "Extracted %d rules (over 50), running merge pass targeting 45",
            len(rules),
        )
        rules = await _amerge_rules(rules, target=45)

    return rules[:50]  # hard safety cap
