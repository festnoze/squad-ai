from dataclasses import dataclass


@dataclass
class ChartMetadata:
    """Metadata for chart data including asset information"""
    asset_name: str
    currency: str
    period_duration: str = "1min"