"""POST /generate-dataset — Generate test cases for all rules."""

import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import aget_session
from backend.models.rule import Rule
from backend.models.test_case import TestCase
from backend.schemas.test_case import DatasetRequest, DatasetResponse
from backend.services.dataset_generator import agenerate_test_cases

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/generate-dataset", response_model=DatasetResponse)
async def generate_dataset(
    request: DatasetRequest | None = None,
    session: AsyncSession = Depends(aget_session),
):
    """Generate test cases for all rules across all scenario types."""
    if request is None:
        request = DatasetRequest()

    # Fetch all rules
    result = await session.execute(select(Rule).order_by(Rule.id))
    rules = result.scalars().all()

    if not rules:
        raise HTTPException(status_code=404, detail="No rules found. Run /extract first.")

    # Clear existing test cases for idempotency
    await session.execute(delete(TestCase))
    await session.flush()

    by_type: dict[str, int] = {}
    total_count = 0

    # Build all (rule_dict, scenario_type) combinations
    combinations: list[tuple[dict, str]] = []
    for rule in rules:
        rule_dict = {
            "id": rule.id,
            "rule_code": rule.rule_code,
            "text": rule.text,
            "source_section": rule.source_section,
        }
        for scenario_type in request.scenario_types:
            combinations.append((rule_dict, scenario_type))

    # Concurrent generation with semaphore
    semaphore = asyncio.Semaphore(request.concurrency)

    async def _generate_one(rule_dict: dict, scenario_type: str) -> list[dict]:
        async with semaphore:
            return await agenerate_test_cases(
                rule=rule_dict,
                scenario_type=scenario_type,
                count=request.cases_per_rule_per_type,
            )

    tasks = [_generate_one(rd, st) for rd, st in combinations]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    # Collect successful results, log failures
    for (rule_dict, scenario_type), result in zip(combinations, results):
        if isinstance(result, BaseException):
            logger.error(
                "Test case generation failed for rule %s / %s: %s",
                rule_dict["rule_code"], scenario_type, result,
            )
            continue

        for tc_data in result:
            tc = TestCase(
                rule_ids=tc_data.get("rule_ids", [rule_dict["id"]]),
                scenario_type=scenario_type,
                user_input=tc_data.get("user_input", ""),
                expected_behavior=tc_data.get("expected_behavior", ""),
                tags=tc_data.get("tags", []),
            )
            session.add(tc)
            total_count += 1
            by_type[scenario_type] = by_type.get(scenario_type, 0) + 1

    await session.commit()

    return DatasetResponse(test_cases_count=total_count, by_type=by_type)
