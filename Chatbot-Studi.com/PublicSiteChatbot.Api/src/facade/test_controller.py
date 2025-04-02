import json
import uuid
from uuid import UUID
from fastapi import APIRouter, HTTPException
from application.available_service import AvailableService
from src.infrastructure.user_repository import UserRepository
from application.service_exceptions import QuotaOverloadException
from common_tools.RAG.rag_service import RagService
from common_tools.RAG.rag_service_factory import RagServiceFactory
from facade.request_models.conversation_request_model import ConversationRequestModel
from fastapi.responses import JSONResponse, StreamingResponse, Response

from facade.request_models.query_asking_request_model import QueryAskingRequestModel, QueryNoConversationRequestModel
from facade.request_models.user_request_model import UserRequestModel

from common_tools.models.conversation import Conversation, Message, User
from common_tools.models.device_info import DeviceInfo

##########################
#      API Endpoints     #
##########################

test_router = APIRouter(prefix="/tests", tags=["Tests"])
    
@test_router.get("/models/all")
async def test_all_models_querying():
    try:
        models_tests_results:list[str] = await AvailableService.test_all_llms_from_env_config_async()
        success = all(['SUCCESS' in model_test_result for model_test_result in models_tests_results])

    except Exception as e:
        success = False
        models_tests_results = [str(e)]

    response_content = {}
    response_content["result"] = "success" if success else "failure"
    if not success:
        response_content["errors"] = models_tests_results
        
    return JSONResponse(content= response_content, status_code= 200)
    
@test_router.get("/models/{model_index}")
async def test_model_querying(model_index:int = 0):
    try:
        model_test_result:str = await AvailableService.test_single_llm_from_env_config_async(model_index)
        return JSONResponse(content={"result": "success"}, status_code=200)
    except Exception as e:
        print(f"Failed to test user retrieval from local SQL database: {e}")
        return JSONResponse(content={"result": "failure", "error": str(e)}, status_code=200)
    
@test_router.get("/databases/conversations/read")
async def test_conversations_database_read():
    try:
        user_repository = UserRepository() 
        users = await user_repository.get_all_users_async()
        assert any(users)
        return JSONResponse(content={"result": "success"}, status_code=200)
    except Exception as e:
        print(f"Failed to test user retrieval from local SQL database: {e}")
        return JSONResponse(content={"result": "failure", "error": str(e)}, status_code=200)
    
@test_router.get("/databases/conversations/write")
async def test_conversations_database_write():
    try:
        device_info_model = DeviceInfo("fake test IP", "user_agent", "platform", "app_version", "os", "browser", False)
        user_id = uuid.uuid4()
        repo = UserRepository() 
        user_id = await repo.create_or_update_user_async(User(
                                                    "user_name",
                                                    device_info_model,
                                                    user_id,))
        repo.delete_user_by_id_async(user_id)
        return JSONResponse(content={"result": "success"}, status_code=200)
    except Exception as e:
        print(f"Failed to test user creation in local SQL database: {e}")
        return JSONResponse(content={"result": "failure", "error": str(e)}, status_code=200)
    
@test_router.get("/vector-databases/rag/read")
async def test_RAG_vector_database_access():
    try:
        rag_service: RagService = RagServiceFactory.build_from_env_config(vector_db_base_path=None)
        chunks = rag_service.vectorstore.similarity_search("quels BTS en RH ?", k=3)
        assert any(chunks)
        return JSONResponse(content={"result": "success"}, status_code=200)
    except Exception as e:
        print(f"Failed to test retrieval from RAG vector database: {e}")
        return JSONResponse(content={"result": "failure", "error": str(e)}, status_code=200)
    
@test_router.get("/all")
async def test_all() -> JSONResponse:
    errors: dict = {}
    r1: JSONResponse = await test_model_querying(model_index=0)
    r1_dict: dict = json.loads(r1.body.decode("utf-8"))
    if r1_dict.get("result") != "success":
        errors["model_querying"] = r1_dict.get("error", "failure")
    r2: JSONResponse = await test_conversations_database_read()
    r2_dict: dict = json.loads(r2.body.decode("utf-8"))
    if r2_dict.get("result") != "success":
        errors["conversations_read"] = "failure"
    r3: JSONResponse = await test_conversations_database_write()
    r3_dict: dict = json.loads(r3.body.decode("utf-8"))
    if r3_dict.get("result") != "success":
        errors["conversations_write"] = "failure"
    r4: JSONResponse = await test_RAG_vector_database_access()
    r4_dict: dict = json.loads(r4.body.decode("utf-8"))
    if r4_dict.get("result") != "success":
        errors["rag_vector_access"] = r4_dict.get("error", "failure")
    if errors:
        return JSONResponse(content={"result": "failure", "errors": errors}, status_code=200)
    return JSONResponse(content={"result": "success"}, status_code=200)