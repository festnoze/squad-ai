from uuid import UUID
from fastapi import APIRouter, HTTPException
from application.available_service import AvailableService
from application.service_exceptions import QuotaOverloadException
from web_services.request_models.conversation_request_model import ConversationRequestModel
from common_tools.models.conversation import Conversation, Message, User
from common_tools.models.device_info import DeviceInfo
from fastapi.responses import JSONResponse, StreamingResponse, Response

from web_services.request_models.query_asking_request_model import QueryAskingRequestModel
from web_services.request_models.user_request_model import UserRequestModel

##########################
#      API Endpoints     #
##########################

inference_router = APIRouter(prefix="/rag/inference", tags=["Inference"])

@inference_router.patch("/user/sync")
async def create_or_retrieve_user(user_request_model: UserRequestModel):
    try:        
        device_info_RM = user_request_model.device_info
        device_info_model = DeviceInfo(user_request_model.IP, device_info_RM.user_agent, device_info_RM.platform, device_info_RM.app_version, device_info_RM.os, device_info_RM.browser, device_info_RM.is_mobile, )
        user_id = await AvailableService.create_or_retrieve_user_async(
                                                    user_request_model.user_id,
                                                    user_request_model.user_name,
                                                    device_info_model)
        return JSONResponse(content={"id": str(user_id)}, status_code=200)
    
    except QuotaOverloadException as e:
        print(f"Failed to create conversation: {e}")
        raise HTTPException(status_code=429, detail=str(e))
    
    except Exception as e:
        print(f"Failed to create conversation: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    

@inference_router.post("/conversation/create")
async def create_new_conversation(conversation: ConversationRequestModel):
    try:
        messages_model = [Message(message.role, message.content) for message in conversation.messages]
        new_conv = await AvailableService.create_new_conversation_async(conversation.user_id, messages_model)
        return JSONResponse(
            content={"id": str(new_conv.id)},
            status_code=200
        )
    
    except QuotaOverloadException as e:
        print(f"Failed to create conversation: {e}")
        raise HTTPException(status_code=429, detail=str(e))
    
    except Exception as e:
        print(f"Failed to create conversation: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    

@inference_router.post("/conversation/message/stream")
async def rag_query_stream_async(user_query_request_model: QueryAskingRequestModel):
    try:
        response_generator = AvailableService.rag_query_stream_async(
                                    user_query_request_model.conversation_id,
                                    user_query_request_model.user_query_content,
                                    user_query_request_model.display_waiting_message,
                                    False)
        return StreamingResponse(response_generator, media_type="text/event-stream")  
    
    except QuotaOverloadException as e:
        print(f"Failed to create conversation: {e}")
        raise HTTPException(status_code=429, detail=str(e))
      
    except Exception as e:
        print(f"Failed to create conversation: {e}")
        raise HTTPException(status_code=500, detail=str(e))