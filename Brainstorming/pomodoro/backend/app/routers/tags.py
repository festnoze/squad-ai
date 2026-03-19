"""Tags router — list and create custom tags."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session as DBSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models import Tag, User
from app.schemas import TagCreate, TagOut

router = APIRouter(prefix="/api/tags", tags=["tags"])

DEFAULT_TAGS = [
    {"name": "Work", "color": "#FF6B6B"},
    {"name": "Study", "color": "#4ECDC4"},
    {"name": "Creative", "color": "#FFE66D"},
    {"name": "Health", "color": "#95E1D3"},
    {"name": "Side Project", "color": "#A29BFE"},
]


@router.get("", response_model=list[TagOut])
def list_tags(
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[Tag]:
    """List all tags for the current user, creating defaults if none exist."""
    tags = db.query(Tag).filter(Tag.user_id == current_user.id).all()
    if not tags:
        # Seed default tags for this user
        for default in DEFAULT_TAGS:
            tag = Tag(user_id=current_user.id, name=default["name"], color=default["color"])
            db.add(tag)
        db.commit()
        tags = db.query(Tag).filter(Tag.user_id == current_user.id).all()
    return tags


@router.post("", response_model=TagOut, status_code=status.HTTP_201_CREATED)
def create_tag(
    payload: TagCreate,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Tag:
    """Create a custom tag for the current user."""
    existing = (
        db.query(Tag)
        .filter(Tag.user_id == current_user.id, Tag.name == payload.name)
        .first()
    )
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Tag with this name already exists",
        )
    tag = Tag(user_id=current_user.id, name=payload.name, color=payload.color)
    db.add(tag)
    db.commit()
    db.refresh(tag)
    return tag
