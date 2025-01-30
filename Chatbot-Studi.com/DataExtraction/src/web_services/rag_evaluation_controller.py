from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from data_retrieval.website_scraping_retrieval import WebsiteScrapingRetrieval
from application.available_service import AvailableService

evaluation_router = APIRouter(prefix="/rag/evaluation", tags=["Evaluation"])

@evaluation_router.post("/groundtruth/generate")
async def generate_ground_truth():
    await AvailableService.generate_ground_truth_async()
    return {"message": "Ground truth generated successfully"}
