"""Tests for the heatmap schema."""

from backend.schemas.heatmap import HeatmapResponse, HeatmapRule, HeatmapScenario, HeatmapCluster


def test_heatmap_response_schema():
    """Test that HeatmapResponse can be constructed with valid data."""
    response = HeatmapResponse(
        rules=[
            HeatmapRule(id=1, rule_code="R01", text="Test rule", cluster_name="C1")
        ],
        scenarios=[
            HeatmapScenario(test_case_id=1, scenario_type="baseline", user_input_preview="Hello")
        ],
        matrix=[[4]],
        clusters=[
            HeatmapCluster(id=1, name="C1", rule_ids=[1])
        ],
    )
    assert len(response.rules) == 1
    assert response.matrix[0][0] == 4


def test_heatmap_response_with_null_scores():
    """Test that HeatmapResponse handles null scores."""
    response = HeatmapResponse(
        rules=[
            HeatmapRule(id=1, rule_code="R01", text="Test", cluster_name="C1")
        ],
        scenarios=[
            HeatmapScenario(test_case_id=1, scenario_type="edge", user_input_preview="Test")
        ],
        matrix=[[None]],
        clusters=[],
    )
    assert response.matrix[0][0] is None
