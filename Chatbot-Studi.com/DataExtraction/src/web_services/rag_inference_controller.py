from fastapi import APIRouter, HTTPException
from application.available_service import AvailableService
from web_services.request_models.conversation_request_model import ConversationRequestModel
from common_tools.models.conversation import Conversation
from fastapi.responses import JSONResponse, StreamingResponse, Response

from web_services.request_models.query_asking_request_model import QueryAskingRequestModel
from web_services.request_models.user_request_model import UserRequestModel

##########################
#      API Endpoints     #
##########################

inference_router = APIRouter(prefix="/rag/inference", tags=["Inference"])

@inference_router.post("/user/sync")
async def create_or_retrieve_user(user_request_model: UserRequestModel):
    try:
        user_id = await AvailableService.create_or_retrieve_user_async(
                                                    user_request_model.user_id,
                                                    user_request_model.user_name,
                                                    user_request_model.IP,
                                                    user_request_model.device_info)
        
        return JSONResponse(
            content={"id": str(user_id)},
            status_code=200
        )
    except Exception as e:
        print(f"Failed to create conversation: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@inference_router.get("/query/create")
async def create_new_conversation(user_name: str = None):
    try:
        new_conv = await AvailableService.create_new_conversation_async(user_name)
        return JSONResponse(
            content={"id": str(new_conv.id)},
            status_code=200
        )
    except Exception as e:
        print(f"Failed to create conversation: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@inference_router.post("/query/stream")
async def rag_query_stream_async(user_query_request_model: QueryAskingRequestModel):
    response_generator = AvailableService.rag_query_stream_async(
                                user_query_request_model.conversation_id,
                                user_query_request_model.user_query_content,
                                user_query_request_model.display_waiting_message,
                                False)
    return StreamingResponse(response_generator, media_type="text/event-stream")