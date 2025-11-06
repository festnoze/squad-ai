import asyncio
import logging
from uuid import UUID, uuid4
from typing import Any, AsyncGenerator
from models.thread import Thread, Message
from infrastructure.thread_repository import ThreadRepository
from infrastructure.user_repository import UserRepository
from infrastructure.context_repository import ContextRepository
from infrastructure.course_hierarchy_repository import CourseHierarchyRepository
from application.exceptions.quota_exceeded_exception import QuotaExceededException
from helpers.context_helper_studi import ContextHelperStudi
from models.context import Context
from infrastructure.llm_service import LlmService
from application.content_service import ContentService
from security.jwt_skillforge_payload import JWTSkillForgePayload
from application.user_service import UserService
from models.user import User
from models.school import School
from models.course_hierarchy import CourseHierarchy
from envvar import EnvHelper


class ThreadService:
    def __init__(
        self,
        user_service: UserService,
        thread_repository: ThreadRepository,
        user_repository: UserRepository,
        context_repository: ContextRepository,
        llm_service: LlmService,
        content_service: ContentService,
        course_hierarchy_repository: CourseHierarchyRepository,
    ) -> None:
        self.logger = logging.getLogger(__name__)
        self.user_service: UserService = user_service
        self.thread_repository: ThreadRepository = thread_repository
        self.user_repository: UserRepository = user_repository
        self.context_repository: ContextRepository = context_repository
        self.llm_service: LlmService = llm_service
        self.content_service: ContentService = content_service
        self.course_hierarchy_repository: CourseHierarchyRepository = course_hierarchy_repository
        self.max_messages_by_conversation = 100  # TODO: put in env. var

    async def acreate_new_thread(self, token_payload: JWTSkillForgePayload, lms_user_id: str, thread_id: UUID | None = None, context: Any = None) -> Thread:
        user_id_or_none = await self.user_repository.aget_user_id_by_lms_user_id(lms_user_id)
        if not user_id_or_none:
            user_id_or_none = await self.aaction_upon_unfound_user(token_payload)
        user_id: UUID = user_id_or_none  # At this point we know it's not None
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
        user_id_or_none = await self.user_repository.aget_user_id_by_lms_user_id(lms_user_id)
        if not user_id_or_none:
            user_id_or_none = await self.aaction_upon_unfound_user(token_payload)
        user_id: UUID = user_id_or_none  # At this point we know it's not None

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
        user_id_or_none = await self.user_repository.aget_user_id_by_lms_user_id(lms_user_id)
        if not user_id_or_none:
            user_id_or_none = await self.aaction_upon_unfound_user(token_payload)
        user_id: UUID = user_id_or_none  # At this point we know it's not None

        thread: Thread | None = await self.thread_repository.aget_thread_by_id(thread_id, page_number, page_size)
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

        if any(all_chunks):
            all_chunks = []

        try:
            # Retrieve context content (from DB else from scraping)
            context_dict: dict = context.model_dump() if hasattr(context, "model_dump") else context
            content = await self.content_service.aget_content_by_filter(context_dict)
            course_hierarchy = await self._aget_course_hierarchy_for_query(context_dict)
            ressource_name = context.ressource.ressource_title
            breadcrumb = self._build_breadcrumb(course_hierarchy, context_dict, ressource_name, "\n")
            parcours_name = context_dict.get("parcours_name") or "-- nom de parcours non trouvé --"
            academic_level = self._get_academic_level(parcours_name)
            if not academic_level:
                academic_level = "-- niveau académique non trouvé --"
            lesson_content = content.content_summary_full or content.content_full or "-- pas de contenu de cours trouvé --"
            # Stream answer to user query
            async_streaming_response = self.llm_service.aquery(thread, academic_level, breadcrumb, lesson_content, False, all_chunks)
            async for response_chunk in async_streaming_response:
                # Format chunks as SSE (Server-Sent Events) - required for API streaming
                if format_response_to_server_sent_events:
                    yield f"data: {response_chunk}\n\n"
                else:
                    yield response_chunk

            # Persist the full answer into the thread before ending stream
            await self.thread_repository.aadd_message_to_thread(thread.id, "".join(all_chunks), "assistant")

            # End marker (Optional - follow OpenAI conventions)
            if format_response_to_server_sent_events:
                yield "data: [DONE]\n\n"

        except asyncio.CancelledError:
            # Request was cancelled (client disconnected or server shutting down)
            self.logger.info(f"Stream cancelled for thread {thread.id}. Saving partial response.")

            # Try to save partial response if we have any chunks
            if all_chunks:
                try:
                    await self.thread_repository.aadd_message_to_thread(thread.id, "".join(all_chunks) + "\n\n[Response interrupted]", "assistant")
                except Exception as e:
                    # If saving fails during shutdown, log but don't raise
                    self.logger.warning(f"Failed to save partial response during cancellation: {e}")

            # Don't re-raise - return gracefully to prevent cascading errors
            # The middleware will handle the cancellation appropriately
            return

        except (ConnectionResetError, ConnectionAbortedError, BrokenPipeError) as e:
            # Client connection errors - common on Windows with Python 3.13
            self.logger.warning(f"Connection error during streaming for thread {thread.id}: {type(e).__name__}")

            # Try to save partial response
            if all_chunks:
                try:
                    await self.thread_repository.aadd_message_to_thread(thread.id, "".join(all_chunks) + "\n\n[Response interrupted due to connection error]", "assistant")
                except Exception as save_error:
                    self.logger.warning(f"Failed to save partial response after connection error: {save_error}")

            # Don't raise - return gracefully
            return

        except Exception as e:
            self.logger.error(f"Error during LLM streaming for thread {thread.id}: {e}")
            raise

    def _get_academic_level(self, parcours_name: str) -> str | None:
        academic_levels = {
            "CAP": "Bac-",
            "Brevet Pro": "Bac-",
            "Bac Pro": "Bac",
            "Pré-Graduate": "Bac",
            "BTS": "Bac+2",
            "Bachelor": "Bac+3",
            "Global BBA": "Bac+3",
            "DCG": "Bac+3",
            "Licence": "Bac+3",
            "Mastère": "Bac+5",
            "Master": "Bac+5",
            "MBA": "Bac+5",
            "Global MBA": "Bac+5",
            "Graduate": "Bac+5",
            "Maitrise": "Bac+5",
            "DSCG": "Bac+7",
        }
        words = parcours_name.strip().split()
        for num_words in [2, 1]:  # Essaie d'abord avec 2 mots, puis 1 mot
            key = " ".join(words[:num_words])
            if key in academic_levels:
                return academic_levels[key]
        return None

    async def _aget_course_hierarchy_for_query(self, context: dict) -> CourseHierarchy | None:
        """Build content for query"""
        partial_filter = {"parcours_id": context["parcour_id"]}
        course: CourseHierarchy | None = await self.course_hierarchy_repository.aget_course_hierarchy_by_partial_filter(partial_filter)
        if not course:
            if EnvHelper.get_fails_on_not_found_course_hierarchy():
                raise ValueError(f"Course with parcours_id {context['parcour_id']} not found")
            else:
                return None
        return course

    def _build_breadcrumb(self, course: CourseHierarchy | None, context: dict, ressource_name: str | None = None, separator: str = " / ") -> str:
        """Build breadcrumb trail from course hierarchy using context IDs.

        Args:
            course_hierarchy: The course hierarchy dictionary
            context: Dictionary containing matiere_id, module_id, and theme_id

        Returns:
            Breadcrumb string with format: "Matiere Name / Module Name / Theme Name"
        """
        breadcrumb_parts = []
        if not course:
            course_hierarchy = {}
        else:
            course_hierarchy = course.course_hierarchy
        # Naming proposal for hierarchical levels: Program (Course) / Area (SkillBlock) / Unit (Skill) / Section / Lesson.

        # Extract IDs from context
        parcours_id = context.get("parcour_id")
        if course_hierarchy and str(course_hierarchy.get("parcours_id")) != parcours_id:
            raise ValueError(f"Parcours ID mismatch: {course_hierarchy.get('parcours_id')} != {parcours_id}")

        parcours_name = context.get("parcours_name")
        matiere_id = context.get("matiere_id")
        module_id = context.get("module_id")
        theme_id = context.get("theme_id")

        breadcrumb_parts.append("Parcours : " + (parcours_name or ""))

        # Find matiere name
        if matiere_id and "matieres" in course_hierarchy:
            for matiere in course_hierarchy["matieres"]:
                if str(matiere.get("matiere_id")) == matiere_id:
                    breadcrumb_parts.append("Matière : " + matiere.get("name", ""))
                    break

        # Find module name
        if module_id and "modules" in course_hierarchy:
            for module in course_hierarchy["modules"]:
                if str(module.get("module_id")) == module_id:
                    breadcrumb_parts.append("Module : " + module.get("name", ""))
                    break

        # Find theme name
        if theme_id and "themes" in course_hierarchy:
            for theme in course_hierarchy["themes"]:
                if str(theme.get("theme_id")) == theme_id:
                    breadcrumb_parts.append("Thème : " + theme.get("name", ""))
                    break

        if ressource_name:
            breadcrumb_parts.append("Cours (Ressource) : " + ressource_name)

        return separator.join(breadcrumb_parts)

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
        updated_thread: Thread | None = await self.thread_repository.aget_thread_by_id(thread.id)
        if not updated_thread:
            raise ValueError(f"Failed to reload thread {thread.id} after adding message")
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

    async def aaction_upon_unfound_user(self, token_payload: JWTSkillForgePayload) -> UUID:
        if EnvHelper.get_fails_on_not_found_user():
            raise ValueError(f"User not found from its internal LMS id: {token_payload.get_lms_user_id()}")

        # If allowed, create an empty user on the fly, only with its 'LMS user id' and school.
        user = User(
            lms_user_id=token_payload.get_lms_user_id() or "",
            school=School(name=token_payload.get_school_name() or ""),
            civility="",
            first_name="",
            last_name="",
            email="fake@fake.com",
        )
        user = await self.user_service.acreate_or_update_user(user)
        if not user.id:
            raise ValueError("Failed to create user - user ID is None")
        return user.id
