"""POST /cluster — Cluster all extracted rules into thematic groups."""

import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import aget_session
from backend.models.cluster import Cluster
from backend.models.judge_prompt import JudgePrompt
from backend.models.rule import Rule
from backend.schemas.cluster import ClusterOut, ClusterResponse
from backend.services.clusterer import acluster_rules

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/cluster", response_model=ClusterResponse)
async def cluster_rules(
    session: AsyncSession = Depends(aget_session),
):
    """Cluster all extracted rules into thematic groups."""
    # Fetch all rules
    result = await session.execute(select(Rule).order_by(Rule.id))
    rules = result.scalars().all()

    if not rules:
        raise HTTPException(status_code=404, detail="No rules found. Run /extract first.")

    # Clear existing clusters (cascade deletes judge prompts)
    await session.execute(delete(JudgePrompt))
    await session.execute(delete(Cluster))
    # Reset cluster_id on all rules
    for rule in rules:
        rule.cluster_id = None
    await session.flush()

    # Build rule dicts for LLM
    rule_dicts = [
        {"rule_code": r.rule_code, "text": r.text, "id": r.id}
        for r in rules
    ]

    try:
        clusters_data = await acluster_rules(rule_dicts)
    except Exception as exc:
        logger.exception("Clustering LLM call failed")
        raise HTTPException(status_code=500, detail=f"Clustering failed: {exc}")

    if not clusters_data:
        raise HTTPException(status_code=500, detail="LLM returned no clusters")

    # Build a rule_code -> rule mapping
    code_to_rule = {r.rule_code: r for r in rules}

    # Create clusters and assign rules
    clusters_out = []
    for cdata in clusters_data:
        cluster = Cluster(
            name=cdata.get("name", "Unnamed"),
            description=cdata.get("description", ""),
        )
        session.add(cluster)
        await session.flush()
        await session.refresh(cluster)

        rule_count = 0
        for rc in cdata.get("rule_codes", []):
            rule = code_to_rule.get(rc)
            if rule:
                rule.cluster_id = cluster.id
                rule_count += 1
            else:
                logger.warning("Rule code %s from LLM not found in DB", rc)

        clusters_out.append(
            ClusterOut(
                id=cluster.id,
                name=cluster.name,
                description=cluster.description,
                rule_count=rule_count,
            )
        )

    # BUG-003 fix: assign any unmatched rules to a "Miscellaneous" cluster
    unassigned = [r for r in rules if r.cluster_id is None]
    if unassigned:
        logger.warning(
            "%d rule(s) were not matched by the LLM clustering output — assigning to 'Miscellaneous'",
            len(unassigned),
        )
        misc_cluster = Cluster(
            name="Miscellaneous",
            description="Rules that were not matched to any LLM-generated cluster.",
        )
        session.add(misc_cluster)
        await session.flush()
        await session.refresh(misc_cluster)

        for r in unassigned:
            r.cluster_id = misc_cluster.id

        clusters_out.append(
            ClusterOut(
                id=misc_cluster.id,
                name=misc_cluster.name,
                description=misc_cluster.description,
                rule_count=len(unassigned),
            )
        )

    await session.commit()

    return ClusterResponse(clusters=clusters_out)
