from available_service import AvailableService
from common_tools.models.conversation import Conversation
from fastapi import FastAPI, BackgroundTasks
from contextlib import asynccontextmanager
from fastapi.responses import StreamingResponse

@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        AvailableService.init()
        yield
    finally:
        await app.state.shutdown()

app = FastAPI(lifespan=lifespan)

@app.post("/data/vector_db")
async def create_vector_db():
    output_dir = AvailableService.out_dir
    return AvailableService.create_vector_db_from_generated_embeded_documents(output_dir)

@app.post("/rag/query/stream")
async def rag_query_stream(conversation_history: Conversation):
    def generate_chunks():
        for chunk in AvailableService.rag_query_full_pipeline_streaming(conversation_history):
            yield chunk
    return StreamingResponse(generate_chunks(), media_type="text/event-stream")
