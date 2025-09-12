"""Chart data API endpoints."""

from typing import List
from fastapi import APIRouter, HTTPException, Query

from app.models.chart import ChartData, ChartDataRequest, ChartDataResponse
from app.services.chart_service import ChartService

router = APIRouter()
chart_service = ChartService()


@router.get("/", response_model=List[str])
async def list_chart_files():
    """List available chart files."""
    try:
        files = await chart_service.list_chart_files()
        return files
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{filename}", response_model=ChartData)
async def get_chart_data(filename: str):
    """Get chart data from file."""
    try:
        chart_data = await chart_service.load_chart_data(filename)
        if not chart_data:
            raise HTTPException(status_code=404, detail="Chart file not found")
        return chart_data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/download", response_model=ChartDataResponse)
async def download_chart_data(request: ChartDataRequest):
    """Download new chart data."""
    try:
        result = await chart_service.download_chart_data(request)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/resample")
async def resample_chart_data(
    filename: str,
    target_period: str = Query(..., description="Target period (e.g., '1h', '4h', '1d')")
):
    """Resample chart data to different timeframe."""
    try:
        result = await chart_service.resample_chart_data(filename, target_period)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{filename}")
async def delete_chart_file(filename: str):
    """Delete a chart file."""
    try:
        success = await chart_service.delete_chart_file(filename)
        if not success:
            raise HTTPException(status_code=404, detail="Chart file not found")
        return {"message": "Chart file deleted successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/metadata/{filename}")
async def get_chart_metadata(filename: str):
    """Get chart metadata without loading full data."""
    try:
        metadata = await chart_service.get_chart_metadata(filename)
        if not metadata:
            raise HTTPException(status_code=404, detail="Chart file not found")
        return metadata
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))