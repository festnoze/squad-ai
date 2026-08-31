"""Shared fixtures: a tiny hand-built market and a temp directory seeded with the bundled dataset."""

from __future__ import annotations

from pathlib import Path

import pytest

from pmx.data.bundled import seed_dataset
from pmx.types import Market, PricePoint


@pytest.fixture
def yes_market() -> Market:
    """A market that rises from 40 to 90 cents and resolves YES."""
    prices = tuple(PricePoint(t=f"d{i}", price=p) for i, p in enumerate([40, 45, 55, 60, 72, 85, 90]))
    return Market(
        id="test-yes",
        question="Will the test resolve YES?",
        category="other",
        source="reconstructed",
        resolution=1,
        resolved_date="2020-01-01",
        prices=prices,
    )


@pytest.fixture
def no_market() -> Market:
    """A market that falls from 60 to 5 cents and resolves NO."""
    prices = tuple(PricePoint(t=f"d{i}", price=p) for i, p in enumerate([60, 50, 40, 25, 12, 5]))
    return Market(
        id="test-no",
        question="Will the test resolve NO?",
        category="other",
        source="reconstructed",
        resolution=0,
        resolved_date="2020-02-01",
        prices=prices,
    )


@pytest.fixture
def seeded_data(tmp_path: Path) -> Path:
    """A temp directory holding the full bundled dataset."""
    out = tmp_path / "markets"
    seed_dataset(out)
    return out
