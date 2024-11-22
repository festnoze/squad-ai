from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from common_tools.models.conversation import Conversation
from available_service import AvailableService
from contextlib import asynccontextmanager

from request_models.conversation_request_model import ConversationRequestModel

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
async def rag_query_stream(conversation_history_request_model: ConversationRequestModel):
    conversation_history = Conversation(conversation_history_request_model.messages)
    async def generate_chunks_full_pipeline_streaming():
        async for chunk in AvailableService.rag_query_dynamic_pipeline_streaming_async(conversation_history):
            yield chunk
    return StreamingResponse(generate_chunks_full_pipeline_streaming(), media_type="text/event-stream")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
