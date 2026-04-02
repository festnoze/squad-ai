"""Rule clustering service — groups rules into thematic clusters using an LLM call."""

import json
import logging
from pathlib import Path

from backend.services.llm_client import achat_completion

logger = logging.getLogger(__name__)

_PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"


def _load_prompt(name: str) -> str:
    return (_PROMPTS_DIR / name).read_text(encoding="utf-8")


CLUSTERING_SYSTEM_PROMPT = _load_prompt("cluster_rules.txt")


async def acluster_rules(rules: list[dict]) -> list[dict]:
    """Cluster rules into thematic groups using an LLM call.

    Args:
        rules: List of rule dicts with at least 'rule_code' and 'text' keys.

    Returns:
        List of cluster dicts: {name, description, rule_codes}.
    """
    rules_text = "\n".join(
        f"- {r['rule_code']}: {r['text']}" for r in rules
    )
    user_message = f"Here are the extracted rules to cluster:\n\n{rules_text}"

    raw = await achat_completion(
        system_prompt=CLUSTERING_SYSTEM_PROMPT,
        user_message=user_message,
        response_format={"type": "json_object"},
    )

    data = json.loads(raw)
    clusters = data.get("clusters", [])

    logger.info("Created %d clusters", len(clusters))

    return clusters
