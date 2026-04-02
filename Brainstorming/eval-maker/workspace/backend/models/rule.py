"""Rule model — an atomic instruction extracted from the system prompt."""

from sqlalchemy import Boolean, Column, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from backend.database import Base


class Rule(Base):
    __tablename__ = "rules"

    id = Column(Integer, primary_key=True, autoincrement=True)
    rule_code = Column(String(10), unique=True, nullable=False)
    text = Column(Text, nullable=False)
    source_section = Column(String(200), nullable=True)
    is_explicit = Column(Boolean, default=True, nullable=False)
    cluster_id = Column(Integer, ForeignKey("clusters.id"), nullable=True)

    cluster = relationship("Cluster", back_populates="rules")
    eval_results = relationship("EvalResult", back_populates="rule")
