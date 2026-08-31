"""Load and validate historical markets from JSON on disk.

A market file is the single source of truth for one backtest. Loading validates it with pydantic so a
malformed file fails loudly here rather than deep in the engine, and normalises prices into the frozen
:class:`~pmx.types.Market` the engine consumes.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field, field_validator

from pmx.types import PRICE_MAX, PRICE_MIN, Market, PricePoint


class PricePointModel(BaseModel):
    t: str
    price: int = Field(ge=PRICE_MIN, le=PRICE_MAX)


class MarketModel(BaseModel):
    """The on-disk schema. ``source`` and ``resolution`` are constrained so a demo path can never be
    mistaken for imported data and an outcome is always a clean 0 or 1."""

    id: str
    question: str
    category: str = "other"
    source: str = "reconstructed"
    resolution: int = Field(ge=0, le=1)
    resolved_date: str
    notes: str = ""
    prices: list[PricePointModel]

    @field_validator("source")
    @classmethod
    def _known_source(cls, v: str) -> str:
        if v not in ("imported", "reconstructed"):
            raise ValueError("source must be 'imported' or 'reconstructed'")
        return v

    @field_validator("prices")
    @classmethod
    def _non_empty(cls, v: list[PricePointModel]) -> list[PricePointModel]:
        if len(v) < 2:
            raise ValueError("a market needs at least two price points")
        return v

    def to_market(self) -> Market:
        return Market(
            id=self.id,
            question=self.question,
            category=self.category,
            source=self.source,
            resolution=self.resolution,
            resolved_date=self.resolved_date,
            notes=self.notes,
            prices=tuple(PricePoint(t=p.t, price=p.price) for p in self.prices),
        )


def load_market(path: Path) -> Market:
    """Load and validate one market JSON file."""
    return MarketModel.model_validate_json(path.read_text(encoding="utf-8")).to_market()


def load_markets(data_dir: Path) -> list[Market]:
    """Load every ``*.json`` market under ``data_dir``, sorted by resolved date then id for a stable
    order (which matters for walk-forward splits)."""
    markets = [load_market(p) for p in sorted(data_dir.glob("*.json"))]
    markets.sort(key=lambda m: (m.resolved_date, m.id))
    return markets
