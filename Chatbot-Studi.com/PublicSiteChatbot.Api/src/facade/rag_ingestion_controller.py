from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from data_retrieval.website_scraping_retrieval import WebsiteScrapingRetrieval
from application.available_service import AvailableService

ingestion_router = APIRouter(prefix="/rag/ingestion", tags=["Ingestion"])

@ingestion_router.post("/drupal/data/retrieve")
async def retrieve_drupal_data():
    AvailableService.retrieve_all_data()
    return {"message": "Drupal data retrieved successfully"}

@ingestion_router.post("/website/scrape")
async def scrape_website():
    scraper = WebsiteScrapingRetrieval()
    scraper.scrape_all_trainings()
    return {"message": "Website data scraped successfully"}

@ingestion_router.post("/vectorstore/create/full")
async def create_vectorstore():
    await AvailableService.create_vector_db_after_generate_chunk_and_embed_documents_summaries_and_questions_async(
                            AvailableService.out_dir, 
                            load_existing_embeddings_from_file_if_exists= False
                        )
    return {"message": "Vector store created successfully"}
