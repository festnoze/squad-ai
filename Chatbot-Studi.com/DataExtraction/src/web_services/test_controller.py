from uuid import UUID
from fastapi import APIRouter, HTTPException
from application.available_service import AvailableService
from application.service_exceptions import QuotaOverloadException
from web_services.request_models.conversation_request_model import ConversationRequestModel
from fastapi.responses import JSONResponse, StreamingResponse, Response

from web_services.request_models.query_asking_request_model import QueryAskingRequestModel, QueryNoConversationRequestModel
from web_services.request_models.user_request_model import UserRequestModel

##########################
#      API Endpoints     #
##########################

test_router = APIRouter(prefix="/tests", tags=["Tests"])

@test_router.get("/models/{model_index}")
async def test_model_querying(model_index:int = 0):
    try:
        model_test_result:str = await AvailableService.test_single_llm_from_env_config_async(model_index)
        success = 'SUCCESS' in model_test_result
        return JSONResponse(content={"model_test_result": model_test_result}, status_code= 200 if success else 417) # 417 HTTP Code: Expectation Failed 

    except Exception as e:
        print(f"Failed to test all models. Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    
@test_router.get("/databases/conversations/read")
async def test_conversations_database_read():
    try:
        success = False
        
        return JSONResponse(content={"result": "OK"}, status_code= 200 if success else 417) # 417 HTTP Code: Expectation Failed 

    except Exception as e:
        print(f"Failed to test all models. Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    
@test_router.get("/models/all")
async def test_all_models_querying():
    try:
        models_tests_results:list[str] = await AvailableService.test_all_llms_from_env_config_async()
        success = all(['SUCCESS' in model_test_result for model_test_result in models_tests_results])
        return JSONResponse(content={"models_tests_results": models_tests_results}, status_code= 200 if success else 417) # 417 HTTP Code: Expectation Failed 

    except Exception as e:
        print(f"Failed to test all models. Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))