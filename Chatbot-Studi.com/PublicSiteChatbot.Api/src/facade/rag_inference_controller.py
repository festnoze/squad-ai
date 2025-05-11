from uuid import UUID
from fastapi import APIRouter, HTTPException
from application.available_service import AvailableService
from application.service_exceptions import QuotaOverloadException
from facade.request_models.conversation_request_model import ConversationRequestModel
from common_tools.models.conversation import Conversation, Message, User
from common_tools.models.device_info import DeviceInfo
from fastapi.responses import JSONResponse, StreamingResponse, Response

from facade.request_models.query_asking_request_model import QueryAskingRequestModel, QueryNoConversationRequestModel
from facade.request_models.user_request_model import UserRequestModel

##########################
#      API Endpoints     #
##########################

inference_router = APIRouter(prefix="/rag/inference", tags=["Inference"])

@inference_router.post("/reinitialize", response_class=Response)
def reinitialize():
    try:
        AvailableService.re_init()
        return Response(status_code=204)
    
    except Exception as e:
        print(f"Failed to create conversation: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    
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
            status_code=200)
    
    except Exception as e:
        print(f"Failed to create conversation: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    

@inference_router.post("/conversation/ask-question/stream")
async def rag_query_stream_async(user_query_request_model: QueryAskingRequestModel):
    try:
        conversation = await AvailableService.prepare_conversation_for_user_query_answer_async(
                                                    user_query_request_model.conversation_id,
                                                    user_query_request_model.user_query_content
                                                )        
        response_generator = AvailableService.streaming_answer_to_user_query_with_RAG_async(
                                                    conversation,
                                                    user_query_request_model.display_waiting_message,
                                                    False
                                                )
        return StreamingResponse(response_generator, media_type="text/event-stream")
        
    except QuotaOverloadException as e:
        raise HTTPException(status_code=429, detail=str(e))
    except Exception as e:
        print(f"Failed to handle query stream: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")
    
@inference_router.post("/conversation/add-external-message")
async def conversation_add_external_assistant_message_async(external_question_request_model: QueryAskingRequestModel):
    try:
        conversation = await AvailableService.add_external_message_to_conversation_async(
            external_question_request_model.conversation_id, 
            external_question_request_model.user_query_content,
            "assistant"
        )
        return JSONResponse(content=conversation.get_all_messages_as_json(), status_code=200)
    
    except ValueError as e:
        print(f"Failed to handle query stream: {e}")
        raise HTTPException(status_code=400, detail="Bad request")    
    except Exception as e:
        print(f"Failed to handle query stream: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")
    
@inference_router.post("/no-conversation/ask-question")
async def rag_query_no_conversation_async(user_query_request_model: QueryNoConversationRequestModel):
    try:
        device_info = DeviceInfo(platform=user_query_request_model.type, ip="0.0.0.0", user_agent='', app_version='', os='', browser='', is_mobile=False)
        
        user_id = await AvailableService.create_or_retrieve_user_async(user_id= None, user_name= user_query_request_model.user_name, user_device_info= device_info)
        
        conversation = await AvailableService.add_message_to_user_last_conversation_or_create_one_async(user_id, user_query_request_model.query)
        
        response = await AvailableService.answer_to_user_query_with_RAG_no_streaming_async(conversation, False, True)
        
        return JSONResponse(content=response, status_code=200)
    
    except QuotaOverloadException as e:
        raise HTTPException(status_code=429, detail=str(e))
    except Exception as e:
        print(f"Failed to handle query: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")
    
@inference_router.post("/no-conversation/ask-question/stream")
async def rag_query_no_conversation_streaming_async(user_query_request_model: QueryNoConversationRequestModel):
    try:
        device_info = DeviceInfo(platform=user_query_request_model.type, ip="0.0.0.0", user_agent='', app_version='', os='', browser='', is_mobile=False)
        
        user_id = await AvailableService.create_or_retrieve_user_async(user_id= None, user_name= user_query_request_model.user_name, user_device_info= device_info)
        
        conversation = await AvailableService.add_message_to_user_last_conversation_or_create_one_async(user_id, user_query_request_model.query)
        
        response_generator = AvailableService.streaming_answer_to_user_query_with_RAG_async(conversation, False, False)
        
        return StreamingResponse(response_generator, media_type="text/event-stream")
        
    except QuotaOverloadException as e:
        raise HTTPException(status_code=429, detail=str(e))
    except Exception as e:
        print(f"Failed to handle query stream: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")