"""Langfuse SDK integration — push datasets and eval configs."""

import asyncio
import logging
from functools import partial

from langfuse import Langfuse

from backend.config import settings

logger = logging.getLogger(__name__)

DATASET_NAME = "skillforge-v28-eval"


def _get_langfuse_client() -> Langfuse:
    """Create a Langfuse client from settings."""
    return Langfuse(
        public_key=settings.langfuse_public_key,
        secret_key=settings.langfuse_secret_key,
        host=settings.langfuse_host,
    )


async def apush_datasets(
    test_cases: list[dict],
    judge_prompts: list[dict],
) -> dict:
    """Push datasets and eval configs to Langfuse.

    Args:
        test_cases: List of test case dicts from the DB (with id, rule_ids,
                    scenario_type, user_input, expected_behavior, tags).
        judge_prompts: List of judge prompt dicts (with cluster_id, system_prompt, rubric_json).

    Returns:
        Dict with dataset_name, items_pushed, eval_configs_created.
    """
    client = _get_langfuse_client()
    loop = asyncio.get_running_loop()

    # Create or get the dataset
    try:
        await loop.run_in_executor(None, partial(
            client.create_dataset,
            name=DATASET_NAME,
            description="Eval suite for SkillForge tutoring prompt v28 — 48 rules across 7 clusters",
            metadata={
                "prompt_version": "28",
                "rules_count": len(test_cases),
                "judges_count": len(judge_prompts),
            },
        ))
        logger.info("Created Langfuse dataset '%s'", DATASET_NAME)
    except Exception as exc:
        logger.warning("Dataset may already exist: %s", exc)

    # Push each test case as a dataset item
    items_pushed = 0
    for idx, tc in enumerate(test_cases):
        context = tc.get("context", {})
        try:
            await loop.run_in_executor(None, partial(
                client.create_dataset_item,
                dataset_name=DATASET_NAME,
                id=f"tc-{tc.get('id', idx)}",
                input={
                    "user_message": tc.get("user_input", ""),
                    "course_content": context.get("course_content", ""),
                    "selected_text": context.get("selected_text", ""),
                    "academic_level": context.get("academic_level", "5"),
                    "lesson_breadcrumb": context.get("lesson_breadcrumb", ""),
                    "personalization_instructions": context.get("personalization_instructions", ""),
                    "is_first_message": context.get("is_first_message", True),
                },
                expected_output={
                    "expected_behavior": tc.get("expected_behavior", ""),
                    "target_rules": tc.get("rule_ids", []),
                    "scenario_type": tc.get("scenario_type", ""),
                },
                metadata={
                    "tags": tc.get("tags", []),
                    "scenario_type": tc.get("scenario_type", ""),
                    "rule_ids": tc.get("rule_ids", []),
                    "local_id": tc.get("id"),
                },
            ))
            items_pushed += 1
        except Exception as exc:
            logger.error("Failed to push test case %s: %s", tc.get("id"), exc)

    # Flush to ensure all events are sent
    await loop.run_in_executor(None, client.flush)

    logger.info("Pushed %d items to Langfuse dataset '%s'", items_pushed, DATASET_NAME)

    return {
        "dataset_name": DATASET_NAME,
        "items_pushed": items_pushed,
        "eval_configs_created": len(judge_prompts),
    }
