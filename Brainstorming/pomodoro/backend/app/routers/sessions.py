"""Sessions router — create, list, stats with XP/streak logic."""

from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func
from sqlalchemy.orm import Session as DBSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models import Session, User
from app.schemas import (
    REALM_THRESHOLDS,
    PausePenaltyOut,
    SessionCreate,
    SessionOut,
    SessionStats,
)
from app.utils import calculate_level

router = APIRouter(prefix="/api/sessions", tags=["sessions"])

# ── Constants ────────────────────────────────────────────────────

FULL_CYCLE_BONUS_XP = 25
PAUSE_PENALTY_XP = 2

# Realms that are always unlocked regardless of level (default realms).
_DEFAULT_REALMS = {"void", "ember"}


# ── Helper functions ─────────────────────────────────────────────


def _streak_multiplier(streak_days: int) -> float:
    """Return the XP multiplier based on current streak length."""
    if streak_days >= 14:
        return 3.0
    if streak_days >= 7:
        return 2.0
    if streak_days >= 3:
        return 1.5
    return 1.0


def _update_streak(user: User, session_date: date) -> None:
    """Update the user's streak based on the session date.

    Streak death: Missing a day resets streak to 1.
    Note on realm locking: A streak reset alone cannot cause realm locks
    because it does not reduce XP (level never drops from a streak reset).
    However, XP *can* decrease via the pause-penalty endpoint, so realm
    locks are handled separately by ``_lock_realms``.
    """
    if user.last_session_date is None:
        # First ever session
        user.current_streak = 1
    elif session_date == user.last_session_date:
        # Same day — no streak change
        pass
    elif session_date == user.last_session_date + timedelta(days=1):
        # Consecutive day
        user.current_streak += 1
    elif session_date > user.last_session_date + timedelta(days=1):
        # Missed day(s) — reset streak
        user.current_streak = 1
    else:
        # Session date is before last_session_date (backfill) — no change
        pass

    if user.current_streak > user.longest_streak:
        user.longest_streak = user.current_streak

    user.last_session_date = session_date


def _unlock_realms(user: User) -> None:
    """Unlock realms based on current level."""
    level = calculate_level(user.xp)
    current_realms = user.get_unlocked_realms()
    changed = False
    for realm, required_level in REALM_THRESHOLDS.items():
        if realm not in current_realms and level >= required_level:
            current_realms.append(realm)
            changed = True
    if changed:
        user.set_unlocked_realms(current_realms)


def _lock_realms(user: User) -> None:
    """Lock (remove) realms the user's level no longer qualifies for.

    This is relevant when XP decreases (e.g. via the pause-penalty endpoint).
    Default realms ("void" and "ember") are never locked.
    If the user's ``active_realm`` gets locked, it resets to "void".
    """
    level = calculate_level(user.xp)
    current_realms = user.get_unlocked_realms()
    locked_realms: list[str] = []
    remaining_realms: list[str] = []

    for realm in current_realms:
        required_level = REALM_THRESHOLDS.get(realm, 0)
        if realm in _DEFAULT_REALMS or level >= required_level:
            remaining_realms.append(realm)
        else:
            locked_realms.append(realm)

    if locked_realms:
        user.set_unlocked_realms(remaining_realms)
        # If the active realm was locked, reset to "void"
        if user.active_realm in locked_realms:
            user.active_realm = "void"


def _calculate_xp(session: SessionCreate, user: User) -> int:
    """Calculate XP earned for a session."""
    if session.session_type != "focus" or not session.completed:
        return 0

    base_xp = 10
    streak_bonus = 5 if user.current_streak >= 1 else 0
    raw_xp = base_xp + streak_bonus

    multiplier = _streak_multiplier(user.current_streak)
    return int(raw_xp * multiplier)


def _count_completed_focus_sessions_on_date(
    db: DBSession, user_id: int, session_date: date
) -> int:
    """Count completed focus sessions for a user on a given date."""
    day_start = datetime.combine(session_date, datetime.min.time())
    day_end = datetime.combine(session_date, datetime.max.time())

    count = (
        db.query(func.count(Session.id))
        .filter(
            Session.user_id == user_id,
            Session.session_type == "focus",
            Session.completed == True,  # noqa: E712
            Session.ended_at >= day_start,
            Session.ended_at <= day_end,
        )
        .scalar()
    )
    return count or 0


# ── Endpoints ────────────────────────────────────────────────────


@router.post("", response_model=SessionOut, status_code=status.HTTP_201_CREATED)
def create_session(
    payload: SessionCreate,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Log a completed session and update XP, streak, and realms."""
    session = Session(
        user_id=current_user.id,
        tag=payload.tag,
        intention=payload.intention,
        duration_minutes=payload.duration_minutes,
        completed=payload.completed,
        started_at=payload.started_at,
        ended_at=payload.ended_at,
        session_type=payload.session_type,
    )
    db.add(session)
    db.flush()  # get session.id

    xp_earned = 0
    if payload.session_type == "focus" and payload.completed:
        session_date = payload.ended_at.date()
        _update_streak(current_user, session_date)
        xp_earned = _calculate_xp(payload, current_user)
        current_user.xp += xp_earned

        # B1: Full-cycle XP bonus — +25 XP for completing a full cycle.
        # A full cycle is N focus sessions (where N = sessions_before_long_break,
        # default 4).  We check if the total completed focus sessions today is
        # a non-zero multiple of that setting.
        sessions_before_long_break = current_user.sessions_before_long_break or 4
        completed_today = _count_completed_focus_sessions_on_date(
            db, current_user.id, session_date
        )
        if completed_today > 0 and completed_today % sessions_before_long_break == 0:
            current_user.xp += FULL_CYCLE_BONUS_XP
            xp_earned += FULL_CYCLE_BONUS_XP

        _unlock_realms(current_user)

    db.commit()
    db.refresh(session)

    return {
        "id": session.id,
        "user_id": session.user_id,
        "tag": session.tag,
        "intention": session.intention,
        "duration_minutes": session.duration_minutes,
        "completed": session.completed,
        "started_at": session.started_at,
        "ended_at": session.ended_at,
        "session_type": session.session_type,
        "xp_earned": xp_earned,
    }


@router.post(
    "/pause-penalty",
    response_model=PausePenaltyOut,
    status_code=status.HTTP_200_OK,
)
def pause_penalty(
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> PausePenaltyOut:
    """Deduct 2 XP for pausing a session (minimum 0 XP).

    After the deduction, realm locks are re-evaluated: any realm whose
    required level exceeds the user's new level is removed (except the
    default realms "void" and "ember").
    """
    old_xp = current_user.xp
    current_user.xp = max(0, current_user.xp - PAUSE_PENALTY_XP)
    actual_deduction = old_xp - current_user.xp

    # Re-check realm locks since XP decreased
    _lock_realms(current_user)

    db.commit()
    db.refresh(current_user)

    return PausePenaltyOut(
        xp_deducted=actual_deduction,
        new_xp=current_user.xp,
    )


@router.get("", response_model=list[SessionOut])
def list_sessions(
    tag: str | None = Query(None),
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
    limit: int | None = Query(None),
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[Session]:
    """List sessions with optional tag, date, and limit filters."""
    query = db.query(Session).filter(Session.user_id == current_user.id)

    if tag:
        query = query.filter(Session.tag == tag)
    if date_from:
        query = query.filter(Session.started_at >= datetime.combine(date_from, datetime.min.time()))
    if date_to:
        query = query.filter(
            Session.started_at <= datetime.combine(date_to, datetime.max.time())
        )

    query = query.order_by(Session.started_at.desc())

    if limit is not None:
        query = query.limit(limit)

    return query.all()


@router.get("/stats", response_model=SessionStats)
def get_session_stats(
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
    period: str | None = Query(None),
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> SessionStats:
    """Aggregated session statistics."""
    # If period is provided and date_from/date_to are not, compute date range
    if period and date_from is None and date_to is None:
        today = date.today()
        if period == "daily":
            date_from = today
            date_to = today
        elif period == "weekly":
            date_from = today - timedelta(days=7)
            date_to = today
        elif period == "monthly":
            date_from = today - timedelta(days=30)
            date_to = today

    query = db.query(Session).filter(
        Session.user_id == current_user.id,
        Session.session_type == "focus",
    )

    if date_from:
        query = query.filter(Session.started_at >= datetime.combine(date_from, datetime.min.time()))
    if date_to:
        query = query.filter(
            Session.started_at <= datetime.combine(date_to, datetime.max.time())
        )

    sessions = query.all()

    total_focus_minutes = sum(s.duration_minutes for s in sessions)
    total_sessions = len(sessions)
    completed_sessions = sum(1 for s in sessions if s.completed)

    # Average duration
    avg_duration = (
        total_focus_minutes / completed_sessions if completed_sessions > 0 else 0
    )

    # Daily breakdown
    daily: dict[str, int] = {}
    for s in sessions:
        day_key = s.started_at.date().isoformat()
        daily[day_key] = daily.get(day_key, 0) + s.duration_minutes

    daily_breakdown = [{"date": k, "minutes": v} for k, v in sorted(daily.items())]

    # Tag breakdown
    tag_breakdown: dict[str, int] = {}
    for s in sessions:
        tag_name = s.tag or "Untagged"
        tag_breakdown[tag_name] = tag_breakdown.get(tag_name, 0) + s.duration_minutes

    return SessionStats(
        total_focus_minutes=total_focus_minutes,
        total_sessions=total_sessions,
        completed_sessions=completed_sessions,
        avg_duration=avg_duration,
        current_streak=current_user.current_streak,
        longest_streak=current_user.longest_streak,
        daily_breakdown=daily_breakdown,
        tag_breakdown=tag_breakdown,
    )
