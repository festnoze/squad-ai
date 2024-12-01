from fastapi import APIRouter
from application.available_service import AvailableService
from web_services.request_models.conversation_request_model import ConversationRequestModel
from common_tools.models.conversation import Conversation
from fastapi.responses import StreamingResponse

router = APIRouter()

##########################
#      API Endpoints     #
##########################

@router.post("/data/vector_db")
async def create_vector_db():
    output_dir = AvailableService.out_dir
    return AvailableService.create_vector_db_from_generated_embeded_documents(output_dir)

@router.post("/rag/query/stream")
async def rag_query_stream_async(conversation_history_request_model: ConversationRequestModel):
    conversation_history = Conversation(conversation_history_request_model.messages)
    response_generator = AvailableService.rag_query_retrieval_and_augmented_generation_streaming_async(conversation_history)
    return StreamingResponse(response_generator, media_type="text/event-stream")
    #TODO: miss this (doable when conversation are identified w/ id and saved/cache on API) : conversation.last_message.content = AvailableService.get_summarized_answer(st.session_state.conversation.last_message.content)

# Launch the API with Uvicorn server:
# if __name__ == "__rag_query_controller__":
#     uvicorn.run(
#         "web_services.rag_query_controller:app", 
#         host="127.0.0.1", 
#         port=8000, 
#         timeout_keep_alive=180, 
#         reload=True, 
#         log_level="error",  # Set log level to error
#         access_log=False    # Disable access logs
#     )