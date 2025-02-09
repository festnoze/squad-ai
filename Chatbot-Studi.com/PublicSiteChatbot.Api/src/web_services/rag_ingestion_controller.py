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
    AvailableService.create_vector_after_chunking_and_embedding_documents(
        AvailableService.out_dir,
        BM25_storage_in_database_sparse_vectors=True)
    return {"message": "Full vector store created successfully"}

@ingestion_router.post("/vectorstore/create/from-summaries")
async def create_vectorstore_summary():
    await AvailableService.create_vector_db_after_generate_chunk_and_embed_documents_summaries_and_questions_async(AvailableService.out_dir)
    return {"message": "Vector store created successfully from summaries"}
