"""Pydantic v2 schemas for Deep Focus API."""

from datetime import datetime, date
from pydantic import BaseModel, EmailStr, Field


# ── Auth ──────────────────────────────────────────────────────────

class UserRegister(BaseModel):
    email: EmailStr
    password: str = Field(min_length=6, max_length=128)


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserOut(BaseModel):
    id: int
    email: str
    created_at: datetime
    xp: int
    current_streak: int
    longest_streak: int

    model_config = {"from_attributes": True}


# ── Sessions ──────────────────────────────────────────────────────

class SessionCreate(BaseModel):
    tag: str | None = None
    intention: str | None = None
    duration_minutes: int = Field(ge=1, le=90)
    completed: bool = True
    started_at: datetime
    ended_at: datetime
    session_type: str = "focus"  # "focus", "short_break", "long_break"


class SessionOut(BaseModel):
    id: int
    user_id: int
    tag: str | None
    intention: str | None
    duration_minutes: int
    completed: bool
    started_at: datetime
    ended_at: datetime
    session_type: str
    xp_earned: int | None = None

    model_config = {"from_attributes": True}


class SessionStats(BaseModel):
    total_focus_minutes: int
    total_sessions: int
    completed_sessions: int
    avg_duration: float = 0
    current_streak: int
    longest_streak: int
    daily_breakdown: list[dict]
    tag_breakdown: dict[str, int] = {}


class PausePenaltyOut(BaseModel):
    """Response schema for the pause XP penalty endpoint."""
    xp_deducted: int
    new_xp: int


# ── Tags ──────────────────────────────────────────────────────────

class TagCreate(BaseModel):
    name: str = Field(min_length=1, max_length=50)
    color: str = Field(default="#FFFFFF", pattern=r"^#[0-9A-Fa-f]{6}$")


class TagOut(BaseModel):
    id: int
    name: str
    color: str
    user_id: int

    model_config = {"from_attributes": True}


# ── Distractions ──────────────────────────────────────────────────

VALID_DISTRACTION_CATEGORIES = [
    "Phone",
    "Social Media",
    "Noise",
    "Hunger",
    "Wandering Mind",
    "Other",
]


class DistractionCreate(BaseModel):
    session_id: int | None = None
    category: str
    note: str | None = None


class DistractionOut(BaseModel):
    id: int
    user_id: int
    session_id: int | None
    category: str
    note: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class DistractionStats(BaseModel):
    total_distractions: int
    categories: dict[str, int]


# ── Profile ───────────────────────────────────────────────────────

REALM_THRESHOLDS: dict[str, int] = {
    "void": 0,
    "ember": 0,
    "glacier": 5,
    "neon": 10,
    "forest": 15,
    "cosmos": 25,
}


class ProfileOut(BaseModel):
    id: int
    email: str
    xp: int
    level: int
    current_streak: int
    longest_streak: int
    last_session_date: date | None
    unlocked_realms: list[str]
    active_realm: str
    focus_duration: int
    short_break_duration: int
    long_break_duration: int
    sessions_before_long_break: int
    auto_advance: bool


class SettingsUpdate(BaseModel):
    focus_duration: int | None = Field(default=None, ge=1, le=90)
    short_break_duration: int | None = Field(default=None, ge=1, le=30)
    long_break_duration: int | None = Field(default=None, ge=1, le=60)
    sessions_before_long_break: int | None = Field(default=None, ge=1, le=10)
    auto_advance: bool | None = None
    active_realm: str | None = None
