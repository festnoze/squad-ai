from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from uuid import UUID
from application.thread_service import ThreadService
from common_tools.helpers.validation_helper import Validate  # type: ignore[import-untyped]
from dependency_injection_config import deps
from facade.request_models.user_query_request import UserAskNewQueryRequest
from facade.request_models.context_request import CourseContextStudiRequest
from facade.response_models.thread_response import ThreadIdsResponse, ThreadMessagesResponse
from facade.converters.thread_response_converter import ThreadResponseConverter
from models.thread import Thread
from security.auth_dependency import authentication_required
from security.jwt_skillforge_payload import JWTSkillForgePayload

thread_router = APIRouter(prefix="/thread", tags=["Thread"])


# @thread_router.post(
#     "/new",
#     description="Create a new conversation thread for a user",
#     response_model=ThreadCreatedResponse,
#     status_code=200,
# )
# async def acreate_new_thread(token_payload: JWTSkillForgePayload = Depends(authentication_required), thread_service: ThreadService = deps.depends(ThreadService)) -> ThreadCreatedResponse:
#     user_internal_id = token_payload.get_user_id()
#     if not Validate.is_int(user_internal_id):
#         raise ValueError(f"Provided user id value: '{user_external_id}' isn't a valid integer.")

#     thread = await thread_service.acreate_new_thread(user_internal_id)
#     return ThreadResponseConverter.convert_thread_to_created_response(thread)


@thread_router.post(
    "/get-all/ids",
    description="Get the all existing threads ids for the specified user and context, return new thread id if none exists",
    response_model=ThreadIdsResponse,
    status_code=200,
)
async def aget_all_threads_ids_or_create_new(
    body: CourseContextStudiRequest, token_payload: JWTSkillForgePayload = Depends(authentication_required), thread_service: ThreadService = deps.depends(ThreadService)
) -> ThreadIdsResponse:
    lms_user_id = token_payload.get_lms_user_id()
    if not lms_user_id or not Validate.is_int(lms_user_id):
        raise ValueError(f"Provided user LMS id value: '{lms_user_id}' isn't a valid integer.")

    threads_ids = await thread_service.aget_threads_ids_by_user_and_context(token_payload, lms_user_id, body)
    return ThreadResponseConverter.convert_thread_ids_to_response(threads_ids)


@thread_router.get(
    "/{thread_id}/messages",
    description="Get messages for the specified thread with optional pagination. Page 1 returns the most recent messages.",
    response_model=ThreadMessagesResponse,
    status_code=200,
)
async def aget_thread_messages(
    thread_id: str, page_number: int = 0, page_size: int = 0, token_payload: JWTSkillForgePayload = Depends(authentication_required), thread_service: ThreadService = deps.depends(ThreadService)
) -> ThreadMessagesResponse:
    if not Validate.is_uuid(thread_id):
        raise ValueError(f"Provided thread id value: '{thread_id}' isn't a valid UUID.")

    lms_user_id = token_payload.get_lms_user_id()
    if not lms_user_id:
        raise ValueError("User LMS ID not found in token")

    # Pass pagination parameters to the service/repository layer for database-level pagination
    thread: Thread = await thread_service.aget_thread_by_id_or_create(UUID(thread_id), lms_user_id, persist_thread_if_created=False, page_number=page_number, page_size=page_size)

    # Get total count of messages for proper pagination metadata
    total_messages_count = await thread_service.aget_thread_messages_count(UUID(thread_id))

    # No need for in-memory pagination - messages are already paginated at the database level
    return ThreadResponseConverter.convert_thread_to_messages_response(thread, 0, len(thread.messages), total_messages_count)


@thread_router.post(
    "/{thread_id}/query",
    description="Add a new user query to a existing thread, generate AI response and return it as a stream",
    status_code=200,
)
async def aanswer_user_query_into_thread(
    thread_id: str, body: UserAskNewQueryRequest, token_payload: JWTSkillForgePayload = Depends(authentication_required), thread_service: ThreadService = deps.depends(ThreadService)
) -> StreamingResponse:
    if not Validate.is_uuid(thread_id):
        raise ValueError(f"Provided thread id value: '{thread_id}' isn't a valid UUID.")

    lms_user_id = token_payload.get_lms_user_id()
    if not lms_user_id or not Validate.is_int(lms_user_id):
        raise ValueError(f"Provided user LMS id value: '{lms_user_id}' isn't a valid integer.")

    # Prepare the thread and add user message BEFORE creating StreamingResponse
    # This allows exceptions (like QuotaExceededException) to be caught by middleware
    updated_thread = await thread_service.aprepare_thread_for_query(token_payload, UUID(thread_id), lms_user_id, body.query.query_text_content, body.course_context)

    # Now stream the LLM response
    response_generator = thread_service.astream_llm_response_and_persist(updated_thread, body.course_context, True)
    return StreamingResponse(response_generator, media_type="text/event-stream")
