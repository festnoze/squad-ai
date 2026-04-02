"""Tests for the cluster service."""

import pytest
from unittest.mock import AsyncMock, patch


@pytest.mark.asyncio
async def test_acluster_rules_returns_clusters():
    """Test that acluster_rules returns a list of cluster dicts."""
    mock_response = '{"clusters": [{"name": "Test Cluster", "description": "A test", "rule_codes": ["R01"]}]}'

    with patch("backend.services.clusterer.achat_completion", new_callable=AsyncMock, return_value=mock_response):
        from backend.services.clusterer import acluster_rules
        result = await acluster_rules([{"rule_code": "R01", "text": "Test"}])

        assert isinstance(result, list)
        assert len(result) == 1
        assert result[0]["name"] == "Test Cluster"
