"""Judge prompt generation service — creates LLM-as-judge prompts with scoring rubrics."""

import json
import logging
from pathlib import Path

from backend.services.llm_client import achat_completion

logger = logging.getLogger(__name__)

_PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"


def _load_prompt(name: str) -> str:
    return (_PROMPTS_DIR / name).read_text(encoding="utf-8")


JUDGE_GENERATION_SYSTEM_PROMPT = _load_prompt("generate_judge.txt")


async def agenerate_judge_prompt(
    cluster_name: str,
    cluster_description: str,
    rules: list[dict],
) -> dict:
    """Generate a judge system prompt and scoring rubric for a cluster.

    Args:
        cluster_name: Name of the cluster.
        cluster_description: Description of the cluster.
        rules: List of rule dicts in this cluster (with rule_code and text).

    Returns:
        Dict with 'system_prompt' (str) and 'rubric_json' (list of rubric entries).
    """
    rules_text = "\n".join(
        f"- {r['rule_code']}: {r['text']}" for r in rules
    )

    user_message = (
        f"Generate a judge prompt and rubric for the following cluster:\n\n"
        f"**Cluster name**: {cluster_name}\n"
        f"**Cluster description**: {cluster_description}\n\n"
        f"**Rules in this cluster**:\n{rules_text}\n\n"
        f"Create a comprehensive judge system prompt and a detailed 5-level rubric for each rule."
    )

    raw = await achat_completion(
        system_prompt=JUDGE_GENERATION_SYSTEM_PROMPT,
        user_message=user_message,
        response_format={"type": "json_object"},
    )

    data = json.loads(raw)

    logger.info(
        "Generated judge prompt for cluster '%s' with %d rubric entries",
        cluster_name, len(data.get("rubric", []))
    )

    return {
        "system_prompt": data.get("system_prompt", ""),
        "rubric_json": data.get("rubric", []),
    }
