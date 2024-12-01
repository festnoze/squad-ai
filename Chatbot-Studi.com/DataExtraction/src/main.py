import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse, JSONResponse
from contextlib import asynccontextmanager
import logging
from application.available_service import AvailableService
from web_services.request_models.conversation_request_model import ConversationRequestModel

from common_tools.models.conversation import Conversation

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
async def rag_query_stream_async(conversation_history_request_model: ConversationRequestModel):
    conversation_history = Conversation(conversation_history_request_model.messages)
    response_generator = AvailableService.rag_query_retrieval_and_augmented_generation_streaming_async(conversation_history)
    return StreamingResponse(response_generator, media_type="text/event-stream")
    #TODO: miss this (doable when conversation are identified w/ id and saved/cache on API) : conversation.last_message.content = AvailableService.get_summarized_answer(st.session_state.conversation.last_message.content)

if __name__ == "__main__":
    uvicorn.run("main:app", host="127.0.0.1", port=8000, timeout_keep_alive=180, reload=True)