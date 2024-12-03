from fastapi import APIRouter, HTTPException
from application.available_service import AvailableService
from web_services.request_models.conversation_request_model import ConversationRequestModel
from common_tools.models.conversation import Conversation
from fastapi.responses import JSONResponse, StreamingResponse, Response

from web_services.request_models.user_query_asking_request_model import UserQueryAskingRequestModel

router = APIRouter()

##########################
#      API Endpoints     #
##########################

@router.post("/data/vector_db")
async def create_vector_db():
    output_dir = AvailableService.out_dir
    return AvailableService.create_vector_db_from_generated_embeded_documents(output_dir)

@router.get("/rag/query/create")
async def create_new_conversation(user_name: str = None):
    try:
        #AvailableService.create_and_fill_retrieved_data_sqlLite_database()
        new_conv = await AvailableService.create_new_conversation_async(user_name)
        return JSONResponse(
            content={"id": str(new_conv.id)},  # Convert UUID to string for JSON serialization
            status_code=200
        )
    except Exception as e:
        print(f"Failed to create conversation: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/rag/query/stream")
async def rag_query_stream_async(user_query_request_model: UserQueryAskingRequestModel):
    response_generator = AvailableService.rag_query_stream_async(user_query_request_model)
    return StreamingResponse(response_generator, media_type="text/event-stream")