from uuid import UUID, uuid4
from typing import Any, AsyncGenerator
from models.thread import Thread, Message
from infrastructure.thread_repository import ThreadRepository
from infrastructure.user_repository import UserRepository
from infrastructure.context_repository import ContextRepository
from application.exceptions.quota_exceeded_exception import QuotaExceededException
from context.context_helper_studi import ContextHelperStudi
from models.context import Context
from infrastructure.llm_repository import LlmRepository
from application.content_service import ContentService
from security.jwt_skillforge_payload import JWTSkillForgePayload
from application.user_service import UserService
from models.user import User, School
from envvar import EnvHelper


class ThreadService:
    def __init__(
        self, user_service: UserService, thread_repository: ThreadRepository, user_repository: UserRepository, context_repository: ContextRepository, llm_repository: LlmRepository, content_service: ContentService
    ) -> None:
        self.user_service: UserService = user_service
        self.thread_repository: ThreadRepository = thread_repository
        self.user_repository: UserRepository = user_repository
        self.context_repository: ContextRepository = context_repository
        self.llm_repository: LlmRepository = llm_repository
        self.content_service: ContentService = content_service
        self.max_messages_by_conversation = 100  # TODO: put in env. var

    async def acreate_new_thread(self, token_payload: JWTSkillForgePayload, lms_user_id: str, thread_id: UUID | None = None, context: Any = None) -> Thread:
        user_id = await self.user_repository.aget_user_id_by_lms_user_id(lms_user_id)
        if not user_id:
            user_id = await self._aaction_upon_unfound_user(token_payload)
        if thread_id and await self.thread_repository.adoes_thread_exist(thread_id):
            raise ValueError(f"Thread with id '{thread_id}' already exists")
        context_id = None
        if context:
            context_filter = ContextHelperStudi.get_content_filter_for_studi(context)
            context_full = context.model_dump() if hasattr(context, "model_dump") else context
            context_model = Context(context_filter=context_filter, context_full=context_full)
            context_obj = await self.context_repository.aget_or_create_context(context_model)
            context_id = context_obj.id

        thread = await self.thread_repository.acreate_thread(user_id, thread_id, context_id)
        return thread

    async def aget_threads_ids_by_user_and_context(self, token_payload: JWTSkillForgePayload, lms_user_id: str, context: Any) -> list[UUID]:
        user_id = await self.user_repository.aget_user_id_by_lms_user_id(lms_user_id)
        if not user_id:
            user_id = await self._aaction_upon_unfound_user(token_payload)

        content_filter = ContextHelperStudi.get_content_filter_for_studi(context)
        content_obj = await self.context_repository.aget_context_by_filter(content_filter)

        # If this context doesn't exist, then no thread can exist for this context
        # If no threads exists: still provide a new (not persisted) thread id (which will actually be created upon the first message addition to it.)
        if not content_obj or not content_obj.id:
            threads_ids = [self._generated_new_thread_id()]
        else:
            threads_ids = await self.thread_repository.aget_threads_ids_by_user_and_context(user_id, content_obj.id)
            if not threads_ids or not any(threads_ids):
                threads_ids = [self._generated_new_thread_id()]

        return threads_ids

    def _generated_new_thread_id(self) -> UUID:
        return uuid4()

    async def aget_thread_by_id_or_create(
        self, token_payload: JWTSkillForgePayload, thread_id: UUID, lms_user_id: str, context: Any = None, persist_thread_if_created: bool = True, page_number: int = 0, page_size: int = 0
    ) -> Thread:
        user_id = await self.user_repository.aget_user_id_by_lms_user_id(lms_user_id)
        if not user_id:
            user_id = await self._aaction_upon_unfound_user(token_payload)

        thread = await self.thread_repository.aget_thread_by_id(thread_id, page_number, page_size)
        if thread and thread.user_id != user_id:
            raise ValueError(f"Access denied to thread with id '{thread_id}'. This thread doesn't belongs to logged user with LMS id: '{lms_user_id}'.")

        if not thread:
            if persist_thread_if_created:
                thread = await self.acreate_new_thread(token_payload, lms_user_id, thread_id, context)
            else:
                thread = Thread(id=thread_id, user_id=user_id, messages=[])
        return thread

    async def astream_llm_response_and_persist(self, thread: Thread, context: Any, format_response_to_server_sent_events: bool = False, all_chunks: list[str] = []) -> AsyncGenerator[str, None]:
        """
        Stream LLM response for the given thread and persist the full response.
        This is an async generator that yields response chunks.
        """
        if not thread.id:
            raise ValueError("Thread must have an ID to persist messages")

        # Retrieve context content (from DB else from scraping)
        all_context_info: dict = context.model_dump() if hasattr(context, "model_dump") else context
        # if isinstance(context, CourseContextStudiRequest):
        #     content_info = {
        #         "course_url": context.ressource.ressource_url,
        #         "resource_name": context.ressource.ressource_title,
        #         "parcours_name": context.parcours_name,
        #     }
        content = await self.content_service.aget_content_by_filter(all_context_info)

        # Stream answer to user query
        async_streaming_response = self.llm_repository.aquery(thread, content.content_full, context.ressource.ressource_title, context.parcours_name, False, all_chunks)
        async for response_chunk in async_streaming_response:
            if format_response_to_server_sent_events:
                yield f"data: {response_chunk}\n\n"  # Format as SSE (Server-Sent Events) - required for API streaming
            else:
                yield response_chunk

        # Persist the full answer into the thread after stream ends
        await self.thread_repository.aadd_message_to_thread(thread.id, "".join(all_chunks), "assistant")

    async def aprepare_thread_for_query(self, token_payload: JWTSkillForgePayload, thread_id: UUID, lms_user_id: str, user_query_content: str, context: Any) -> Thread:
        """
        Prepare a thread for a new query by validating access, checking quota, and adding the user message.
        This method should be called BEFORE creating a StreamingResponse so that exceptions
        (like QuotaExceededException) can be caught by middleware.

        Returns:
            Thread: The updated thread with the new user message added

        Raises:
            ValueError: If user not found, thread access denied, or invalid parameters
            QuotaExceededException: If the user has exceeded the message quota
        """
        thread: Thread = await self.aget_thread_by_id_or_create(token_payload, thread_id, lms_user_id, context, persist_thread_if_created=True)
        await self._aadd_user_message_to_thread(thread, user_query_content)

        # Reload full thread with added message
        updated_thread = await self.thread_repository.aget_thread_by_id(thread.id)
        return updated_thread

    async def _aadd_user_message_to_thread(self, thread: Thread, user_query_content: str) -> Message:
        if not thread.id:
            raise ValueError("Thread must have an ID to add messages")

        user_queries = [msg for msg in thread.messages if msg.role.name == "user"]
        if self.max_messages_by_conversation and len(user_queries) >= self.max_messages_by_conversation:
            raise QuotaExceededException("You have reached the maximum number of messages allowed per conversation.")

        return await self.thread_repository.aadd_message_to_thread(thread.id, user_query_content, "user")

    async def aget_thread_messages_count(self, thread_id: UUID) -> int:
        """Get the total count of messages for a thread.

        Args:
            thread_id: Thread's UUID

        Returns:
            Total number of messages in the thread
        """
        return await self.thread_repository.aget_thread_messages_count(thread_id)

    async def _aaction_upon_unfound_user(self, token_payload: JWTSkillForgePayload) -> str:
        if EnvHelper.get_fails_on_unfound_user():
            raise ValueError(f"User not found from its internal LMS id: {token_payload.get_lms_user_id()}")

        # If allowed, create an empty user on the fly, only with its 'LMS user id' and school.
        user = User(
            lms_user_id=token_payload.get_lms_user_id(),
            school=School(name=token_payload.get_school_name()),
            civility="",
            first_name="",
            last_name="",
            email="fake@fake.com",
        )
        user = await self.user_service.acreate_or_update_user(user)
        return user.id
