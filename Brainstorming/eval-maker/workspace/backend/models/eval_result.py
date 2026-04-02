"""EvalResult model — a single score from running a test case through a judge."""

from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, Integer, Text
from sqlalchemy.orm import relationship

from backend.database import Base


class EvalResult(Base):
    __tablename__ = "eval_results"

    id = Column(Integer, primary_key=True, autoincrement=True)
    test_case_id = Column(Integer, ForeignKey("test_cases.id"), nullable=False)
    rule_id = Column(Integer, ForeignKey("rules.id"), nullable=False)
    score = Column(Integer, nullable=False)
    reasoning = Column(Text, nullable=True)
    system_response = Column(Text, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    test_case = relationship("TestCase", back_populates="eval_results")
    rule = relationship("Rule", back_populates="eval_results")
