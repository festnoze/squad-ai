"""Validated public request surface for the local MVP API."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from pmx.agents.registry import DEFAULT_ROSTER


class RunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dataset: str = Field(default="mvp2026", pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]{0,79}$")
    provider: Literal["kalshi", "manifold", "polymarket"]
    fold: Literal["train", "validation"] = "validation"
    agent_ids: list[str] = Field(default_factory=lambda: [row[0] for row in DEFAULT_ROSTER])
    seed: int = Field(default=7, ge=0, le=2_147_483_647, strict=True)
    bankroll_cents: int = Field(default=100_000, ge=10_000, le=1_000_000_000, strict=True)
    max_markets: int = Field(default=12, ge=1, le=30, strict=True)

    @field_validator("agent_ids")
    @classmethod
    def valid_agents(cls, value: list[str]) -> list[str]:
        available = {row[0] for row in DEFAULT_ROSTER}
        if not value or len(value) != len(set(value)) or not set(value) <= available:
            raise ValueError("Choisissez des stratégies connues, distinctes, et au moins une stratégie.")
        return sorted(value)


class CampaignRequest(BaseModel):
    """A bounded search on internal training windows; no public sealed-fold selector."""

    model_config = ConfigDict(extra="forbid")

    dataset: str = Field(default="mvp2026", pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]{0,79}$")
    provider: Literal["kalshi", "manifold", "polymarket"]
    seed: int = Field(default=7, ge=0, le=2_147_483_647, strict=True)
    n_trials: int = Field(default=30, ge=1, le=100, strict=True)
    max_markets: int = Field(default=60, ge=6, le=200, strict=True)
    bankroll_cents: int = Field(default=100_000, ge=10_000, le=100_000_000, strict=True)
    n_splits: int = Field(default=3, ge=2, le=5, strict=True)
    finalists: int = Field(default=3, ge=1, le=5, strict=True)


class AnalysisSettingsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool = Field(strict=True)


class SignalRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    dataset: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]{0,79}$")
