"""SQLAlchemy ORM models for Deep Focus."""

import json
from datetime import datetime, date

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import relationship

from app.database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    email = Column(String, unique=True, index=True, nullable=False)
    password_hash = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    # XP & Progression
    xp = Column(Integer, default=0)
    current_streak = Column(Integer, default=0)
    longest_streak = Column(Integer, default=0)
    last_session_date = Column(Date, nullable=True)

    # Timer settings
    focus_duration = Column(Integer, default=25)
    short_break_duration = Column(Integer, default=5)
    long_break_duration = Column(Integer, default=15)
    sessions_before_long_break = Column(Integer, default=4)
    auto_advance = Column(Boolean, default=False)

    # Realms
    unlocked_realms = Column(Text, default='["void", "ember"]')
    active_realm = Column(String, default="void")

    # Relationships
    sessions = relationship("Session", back_populates="user", cascade="all, delete-orphan")
    distractions = relationship("Distraction", back_populates="user", cascade="all, delete-orphan")
    tags = relationship("Tag", back_populates="user", cascade="all, delete-orphan")

    def get_unlocked_realms(self) -> list[str]:
        return json.loads(self.unlocked_realms) if self.unlocked_realms else ["void", "ember"]

    def set_unlocked_realms(self, realms: list[str]) -> None:
        self.unlocked_realms = json.dumps(realms)


class Session(Base):
    __tablename__ = "sessions"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    tag = Column(String, nullable=True)
    intention = Column(Text, nullable=True)
    duration_minutes = Column(Integer, nullable=False)
    completed = Column(Boolean, default=True)
    started_at = Column(DateTime, nullable=False)
    ended_at = Column(DateTime, nullable=False)
    session_type = Column(String, default="focus")  # "focus", "short_break", "long_break"

    user = relationship("User", back_populates="sessions")


class Distraction(Base):
    __tablename__ = "distractions"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    session_id = Column(Integer, ForeignKey("sessions.id"), nullable=True)
    category = Column(String, nullable=False)
    note = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="distractions")


class Tag(Base):
    __tablename__ = "tags"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    name = Column(String, nullable=False)
    color = Column(String, default="#FFFFFF")

    user = relationship("User", back_populates="tags")
