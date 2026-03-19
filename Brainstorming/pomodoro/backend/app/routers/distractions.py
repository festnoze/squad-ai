"""Distractions router — log distractions and get analytics."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session as DBSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models import Distraction, User
from app.schemas import (
    VALID_DISTRACTION_CATEGORIES,
    DistractionCreate,
    DistractionOut,
    DistractionStats,
)

router = APIRouter(prefix="/api/distractions", tags=["distractions"])


@router.post("", response_model=DistractionOut, status_code=status.HTTP_201_CREATED)
def create_distraction(
    payload: DistractionCreate,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Distraction:
    """Log a distraction event."""
    if payload.category not in VALID_DISTRACTION_CATEGORIES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid category. Must be one of: {VALID_DISTRACTION_CATEGORIES}",
        )
    distraction = Distraction(
        user_id=current_user.id,
        session_id=payload.session_id,
        category=payload.category,
        note=payload.note,
    )
    db.add(distraction)
    db.commit()
    db.refresh(distraction)
    return distraction


@router.get("/stats", response_model=DistractionStats)
def get_distraction_stats(
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> DistractionStats:
    """Return distraction analytics grouped by category."""
    distractions = (
        db.query(Distraction).filter(Distraction.user_id == current_user.id).all()
    )
    categories: dict[str, int] = {}
    for d in distractions:
        categories[d.category] = categories.get(d.category, 0) + 1

    return DistractionStats(
        total_distractions=len(distractions),
        categories=categories,
    )
