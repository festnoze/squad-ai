"""Test configuration and fixtures."""

import pytest
import sys
from pathlib import Path

# Add the project root to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

@pytest.fixture
def sample_trade_data():
    """Sample trade data for testing."""
    return {
        "symbol": "AAPL",
        "quantity": 100,
        "entry_price": 150.0,
        "stop_loss": 140.0,
        "take_profit": 170.0
    }

@pytest.fixture
def sample_candle_data():
    """Sample candle data for testing."""
    return {
        "open": 100.0,
        "high": 110.0,
        "low": 95.0,
        "close": 105.0,
        "volume": 1000000.0
    }