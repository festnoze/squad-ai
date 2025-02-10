from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from services.available_actions import AvailableActions
from webservices.request_models.analyse_files import AnalyseFilesRequestModel
from webservices.request_models.generate_summaries import GenerateSummariesRequestModel
from webservices.request_models.rag_query import RagQueryRequestModel

all_router = APIRouter(prefix="", tags=["All Controller"])

@all_router.post("/rag/query")
async def rag_query_no_streaming_endpoint(rag_query: RagQueryRequestModel) -> str:
    answer: str = await AvailableActions.rag_query_no_streaming_async(rag_query.query, rag_query.include_bm25_retrieval)
    return answer

@all_router.post("/rag/query/stream")
async def rag_query_streaming_endpoint(rag_query: RagQueryRequestModel) -> StreamingResponse:
    response_generator = AvailableActions.rag_query_streaming_async(rag_query.query, rag_query.include_bm25_retrieval)
    return StreamingResponse(response_generator, media_type="text/event-stream")

@all_router.post("/rebuild_vectorstore")
async def rebuild_vectorstore_endpoint() -> dict:
    AvailableActions.rebuild_vectorstore()
    return {"status": "vectorstore rebuilt"}

@all_router.post("/analyse_files")
async def analyse_files_endpoint(analyse_files: AnalyseFilesRequestModel) -> dict:
    AvailableActions.analyse_files_code_structures(analyse_files.files_batch_size, analyse_files.code_folder_path)
    return {"status": "analysis done"}

@all_router.post("/generate_all_summaries")
async def generate_all_summaries_endpoint(generate_summaries: GenerateSummariesRequestModel) -> dict:
    AvailableActions.generate_all_summaries(generate_summaries.files_batch_size, generate_summaries.llm_batch_size, generate_summaries.code_folder_path)
    return {"status": "summaries generated"}