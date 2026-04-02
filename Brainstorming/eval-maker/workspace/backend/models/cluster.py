"""Cluster model — a thematic group of related rules."""

from sqlalchemy import Column, Integer, String, Text
from sqlalchemy.orm import relationship

from backend.database import Base


class Cluster(Base):
    __tablename__ = "clusters"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)

    rules = relationship("Rule", back_populates="cluster")
    judge_prompt = relationship(
        "JudgePrompt", back_populates="cluster", uselist=False, cascade="all, delete-orphan"
    )
