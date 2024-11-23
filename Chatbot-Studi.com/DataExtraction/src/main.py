from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse, JSONResponse
from contextlib import asynccontextmanager
import logging

from common_tools.models.conversation import Conversation
from available_service import AvailableService

from request_models.conversation_request_model import ConversationRequestModel

@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        AvailableService.init(activate_print=True)
        yield
    finally:
        await app.state.shutdown()

app = FastAPI(lifespan=lifespan)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@app.middleware("http")
async def log_validation_errors(request: Request, call_next):
    try:
        return await call_next(request)
    except Exception as exc:
        # Log the error
        logger.error("Validation error: %s", exc)
        # Return the default response
        return JSONResponse(
            status_code=422,
            content={"detail": str(exc)}
        )

@app.post("/data/vector_db")
async def create_vector_db():
    output_dir = AvailableService.out_dir
    return AvailableService.create_vector_db_from_generated_embeded_documents(output_dir)

@app.post("/rag/query/stream")
async def rag_query_stream(conversation_history_request_model: ConversationRequestModel):
    conversation_history = Conversation(conversation_history_request_model.messages)
    async def generate_chunks_full_pipeline_streaming():
        async for chunk in AvailableService.rag_query_dynamic_pipeline_streaming_async(conversation_history):
            yield chunk
    return StreamingResponse(generate_chunks_full_pipeline_streaming(), media_type="text/event-stream")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
