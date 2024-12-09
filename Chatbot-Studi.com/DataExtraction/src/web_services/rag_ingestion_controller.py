from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from data_retrieval.website_scraping_retrieval import WebsiteScrapingRetrieval
from application.available_service import AvailableService

ingestion_router = APIRouter(prefix="/rag/ingestion", tags=["Ingestion"])

@ingestion_router.post("/drupal/data/retrieve")
async def retrieve_drupal_data():
    try:
        AvailableService.retrieve_all_data()
        return JSONResponse(content={"status": "success"}, status_code=200)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@ingestion_router.post("/website/scrape")
async def scrape_website():
    try:
        scraper = WebsiteScrapingRetrieval()
        scraper.scrape_all_trainings()
        return JSONResponse(content={"status": "success"}, status_code=200)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@ingestion_router.post("/vectorstore/create/full")
async def create_vectorstore():
    try:
        AvailableService.create_vector_db_from_generated_embeded_documents(AvailableService.out_dir)
        return JSONResponse(content={"status": "success"}, status_code=200)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@ingestion_router.post("/vectorstore/create/from-summaries")
async def create_vectorstore_summary():
    try:
        AvailableService.create_summary_vector_db_from_generated_embeded_documents(AvailableService.out_dir)
        return JSONResponse(content={"status": "success"}, status_code=200)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@ingestion_router.post("/groundtruth/generate")
async def generate_ground_truth():
    try:
        AvailableService.generate_ground_truth()
        return JSONResponse(content={"status": "success"}, status_code=200)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
