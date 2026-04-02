"""Eval execution service — call the system under test, then judge each response."""

import asyncio
import json
import logging

from backend.services.llm_client import achat_completion

logger = logging.getLogger(__name__)


async def arun_eval(
    test_case: dict,
    system_prompt: str,
    judge_prompt: dict,
) -> list[dict]:
    """Run a single eval: call the system under test, then judge the response.

    Args:
        test_case: Dict with user_input, rule_ids, expected_behavior, and optional context.
        system_prompt: The full SkillForge system prompt to use for the system under test.
        judge_prompt: Dict with 'system_prompt' and 'rubric_json' for the judge.

    Returns:
        List of dicts, each with rule_id, score, reasoning, and system_response.
    """
    # 1. Build the user message for the system under test
    context = test_case.get("context", {})
    user_message_parts = []

    if context.get("course_content"):
        user_message_parts.append(f"# Contenu du cours\n{context['course_content']}")
    if context.get("selected_text"):
        user_message_parts.append(f"# Texte selectionne\n{context['selected_text']}")
    if context.get("lesson_breadcrumb"):
        user_message_parts.append(f"# Fil d'Ariane\n{context['lesson_breadcrumb']}")
    if context.get("academic_level"):
        user_message_parts.append(f"# Niveau academique\n{context['academic_level']}")
    if context.get("personalization_instructions"):
        user_message_parts.append(f"# Instructions de personnalisation\n{context['personalization_instructions']}")

    user_message_parts.append(f"# Requete utilisateur (question a laquelle tu dois repondre):\n{test_case['user_input']}")
    full_user_message = "\n\n".join(user_message_parts)

    # 2. Call the system under test
    system_response = await achat_completion(
        system_prompt=system_prompt,
        user_message=full_user_message,
    )

    # 3. Build the judge input
    rubric_text = json.dumps(judge_prompt.get("rubric_json", []), indent=2)
    judge_user_message = (
        f"## System Prompt (given to the assistant)\n"
        f"```\n{system_prompt[:2000]}...\n```\n\n"
        f"## Test Input (user message sent to the assistant)\n"
        f"```\n{full_user_message}\n```\n\n"
        f"## Assistant Response\n"
        f"```\n{system_response}\n```\n\n"
        f"## Rules to Evaluate (with rubric)\n"
        f"```json\n{rubric_text}\n```\n\n"
        f"Score each rule listed above. Return your evaluation as JSON."
    )

    # 4. Call the judge
    judge_raw = await achat_completion(
        system_prompt=judge_prompt.get("system_prompt", "You are an expert evaluator. Score the assistant response on each rule."),
        user_message=judge_user_message,
        response_format={"type": "json_object"},
    )

    # 5. Parse judge output
    try:
        judge_data = json.loads(judge_raw)
        evaluations = judge_data.get("evaluations", [])
    except json.JSONDecodeError:
        logger.error("Judge returned invalid JSON: %s", judge_raw[:500])
        evaluations = []

    # 6. Build results
    results = []
    for ev in evaluations:
        results.append({
            "rule_id": ev.get("rule_id", ""),
            "score": max(1, min(5, int(ev.get("score", 3)))),
            "reasoning": ev.get("reasoning", ""),
            "system_response": system_response,
        })

    return results


async def arun_evals_batch(
    test_cases: list[dict],
    system_prompt: str,
    judge_prompts_by_cluster: dict[int, dict],
    rule_to_cluster: dict[int, int],
    concurrency: int = 5,
) -> list[dict]:
    """Run evaluations for multiple test cases with concurrency control.

    Args:
        test_cases: List of test case dicts.
        system_prompt: The full SkillForge system prompt.
        judge_prompts_by_cluster: Map of cluster_id -> judge_prompt dict.
        rule_to_cluster: Map of rule_id -> cluster_id.
        concurrency: Max concurrent LLM calls.

    Returns:
        Flat list of result dicts (rule_id, score, reasoning, system_response, test_case_id).
    """
    semaphore = asyncio.Semaphore(concurrency)
    all_results = []

    async def _run_single(tc: dict) -> list[dict]:
        async with semaphore:
            # Find the appropriate judge for this test case
            rule_ids = tc.get("rule_ids", [])
            if not rule_ids:
                return []

            # Use the cluster of the first rule to pick the judge
            first_rule_id = rule_ids[0]
            cluster_id = rule_to_cluster.get(first_rule_id)
            if cluster_id is None:
                logger.warning("No cluster found for rule %s, skipping", first_rule_id)
                return []

            judge = judge_prompts_by_cluster.get(cluster_id)
            if judge is None:
                logger.warning("No judge prompt for cluster %d, skipping", cluster_id)
                return []

            results = await arun_eval(tc, system_prompt, judge)
            for r in results:
                r["test_case_id"] = tc.get("id")
            return results

    tasks = [_run_single(tc) for tc in test_cases]
    batch_results = await asyncio.gather(*tasks, return_exceptions=True)

    for result in batch_results:
        if isinstance(result, BaseException):
            logger.error("Eval task failed: %s", result)
            continue
        all_results.extend(result)

    return all_results
