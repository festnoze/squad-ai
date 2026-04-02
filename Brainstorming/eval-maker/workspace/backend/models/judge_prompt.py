"""JudgePrompt model — LLM-as-judge prompt and rubric for a cluster."""

from sqlalchemy import Column, ForeignKey, Integer, Text
from sqlalchemy import JSON
from sqlalchemy.orm import relationship

from backend.database import Base


class JudgePrompt(Base):
    __tablename__ = "judge_prompts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    cluster_id = Column(Integer, ForeignKey("clusters.id"), unique=True, nullable=False)
    system_prompt = Column(Text, nullable=False)
    rubric_json = Column(JSON, nullable=False)

    cluster = relationship("Cluster", back_populates="judge_prompt")
