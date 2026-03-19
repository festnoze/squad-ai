"""Profile router — view profile, update settings."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session as DBSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models import User
from app.schemas import REALM_THRESHOLDS, ProfileOut, SettingsUpdate
from app.utils import calculate_level

router = APIRouter(prefix="/api/profile", tags=["profile"])


@router.get("", response_model=ProfileOut)
def get_profile(
    current_user: User = Depends(get_current_user),
) -> ProfileOut:
    """Return the full user profile including XP, level, realms."""
    return ProfileOut(
        id=current_user.id,
        email=current_user.email,
        xp=current_user.xp,
        level=calculate_level(current_user.xp),
        current_streak=current_user.current_streak,
        longest_streak=current_user.longest_streak,
        last_session_date=current_user.last_session_date,
        unlocked_realms=current_user.get_unlocked_realms(),
        active_realm=current_user.active_realm,
        focus_duration=current_user.focus_duration,
        short_break_duration=current_user.short_break_duration,
        long_break_duration=current_user.long_break_duration,
        sessions_before_long_break=current_user.sessions_before_long_break,
        auto_advance=current_user.auto_advance,
    )


@router.put("/settings", response_model=ProfileOut)
def update_settings(
    payload: SettingsUpdate,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ProfileOut:
    """Update timer settings and/or active realm."""
    if payload.active_realm is not None:
        unlocked = current_user.get_unlocked_realms()
        if payload.active_realm not in unlocked:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Realm '{payload.active_realm}' is not unlocked",
            )
        current_user.active_realm = payload.active_realm

    if payload.focus_duration is not None:
        current_user.focus_duration = payload.focus_duration
    if payload.short_break_duration is not None:
        current_user.short_break_duration = payload.short_break_duration
    if payload.long_break_duration is not None:
        current_user.long_break_duration = payload.long_break_duration
    if payload.sessions_before_long_break is not None:
        current_user.sessions_before_long_break = payload.sessions_before_long_break
    if payload.auto_advance is not None:
        current_user.auto_advance = payload.auto_advance

    db.commit()
    db.refresh(current_user)

    return ProfileOut(
        id=current_user.id,
        email=current_user.email,
        xp=current_user.xp,
        level=calculate_level(current_user.xp),
        current_streak=current_user.current_streak,
        longest_streak=current_user.longest_streak,
        last_session_date=current_user.last_session_date,
        unlocked_realms=current_user.get_unlocked_realms(),
        active_realm=current_user.active_realm,
        focus_duration=current_user.focus_duration,
        short_break_duration=current_user.short_break_duration,
        long_break_duration=current_user.long_break_duration,
        sessions_before_long_break=current_user.sessions_before_long_break,
        auto_advance=current_user.auto_advance,
    )
