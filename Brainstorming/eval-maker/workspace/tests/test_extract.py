"""Tests for the extract endpoint."""

import pytest
from unittest.mock import AsyncMock, patch


@pytest.mark.asyncio
async def test_aextract_rules_returns_list():
    """Test that aextract_rules returns a list of rule dicts."""
    mock_response = '{"rules": [{"rule_code": "R01", "text": "Test rule", "source_section": "Test", "is_explicit": true}]}'

    with patch("backend.services.extractor.achat_completion", new_callable=AsyncMock, return_value=mock_response):
        from backend.services.extractor import aextract_rules
        result = await aextract_rules("Some prompt text")

        assert isinstance(result, list)
        assert len(result) == 1
        assert result[0]["rule_code"] == "R01"
        assert result[0]["text"] == "Test rule"
