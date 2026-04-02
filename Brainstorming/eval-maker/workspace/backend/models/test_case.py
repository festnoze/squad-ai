"""TestCase model — a test scenario targeting one or more rules."""

from sqlalchemy import Column, Integer, String, Text, JSON
from sqlalchemy.orm import relationship

from backend.database import Base


class TestCase(Base):
    __tablename__ = "test_cases"

    id = Column(Integer, primary_key=True, autoincrement=True)
    rule_ids = Column(JSON, nullable=False)
    scenario_type = Column(String(20), nullable=False)
    user_input = Column(Text, nullable=False)
    expected_behavior = Column(Text, nullable=False)
    tags = Column(JSON, default=list)
    langfuse_item_id = Column(String(100), nullable=True)

    eval_results = relationship("EvalResult", back_populates="test_case")
