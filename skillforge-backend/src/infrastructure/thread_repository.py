import logging
from uuid import UUID
from sqlalchemy import select
from common_tools.database.generic_datacontext import GenericDataContext  # type: ignore[import-untyped]
from infrastructure.entities import Base
from infrastructure.entities.thread_entity import ThreadEntity
from infrastructure.entities.message_entity import MessageEntity
from infrastructure.converters.thread_converters import ThreadConverters
from infrastructure.converters.message_converters import MessageConverters
from models.thread import Thread
from models.message import Message
from envvar import EnvHelper
from infrastructure.caching.cache_service import CacheService
from infrastructure.caching.caching_decorator import cache_retrieval_or_caching
from infrastructure.role_repository import RoleRepository
from infrastructure.helpers.database_helper import DatabaseHelper


class ThreadRepository:
    def __init__(self, db_path_or_url: str | None = None) -> None:
        self.logger = logging.getLogger(__name__)
        self.db_path_or_url = DatabaseHelper.build_postgres_connection_url(db_path_or_url)
        self.data_context = GenericDataContext(Base, self.db_path_or_url)
        self.role_repository = RoleRepository(db_path_or_url=self.db_path_or_url)
        host = EnvHelper.get_postgres_host()
        dbname = EnvHelper.get_postgres_database_name()
        self.logger.debug(f"ThreadRepository initialized with database: {host}/{dbname}")

    async def acreate_thread(self, user_id: UUID, thread_id: UUID | None = None, context_id: UUID | None = None) -> Thread:
        """Create a new empty thread for a user.

        Args:
            user_id: UUID of the user
            thread_id: Optional UUID to use for the thread
            context_id: Optional UUID of the context to associate with the thread

        Returns:
            Thread model instance

        Raises:
            ValueError: If user does not exist
            Exception: If thread creation fails
        """
        try:
            thread_entity = ThreadEntity(user_id=user_id, context_id=context_id, messages=[])
            if thread_id:
                thread_entity.id = thread_id
            thread_entity = await self.data_context.add_entity_async(thread_entity)
            return ThreadConverters.convert_thread_entity_to_model(thread_entity)

        except (ValueError, RuntimeError) as e:
            # GenericDataContext wraps ValueError in RuntimeError - handle both
            raise ValueError(f"User with id {user_id} does not exist") from e
        except Exception as e:
            self.logger.error(f"Failed to create thread: {e}")
            raise

    async def aadd_message_to_thread(self, thread_id: UUID, content: str, role_name: str) -> Message:
        """Add a message to an existing thread.

        Args:
            thread_id: UUID of the thread
            content: Message content
            role_name: Message role name (e.g., 'user', 'assistant')

        Returns:
            Message model instance

        Raises:
            ValueError: If thread does not exist or role not found
            Exception: If message addition fails
        """
        try:
            if not content:
                raise ValueError("Content is required. Message cannot be added to thread without content")

            # Check if thread exists - get_entity_by_id will raise ValueError if not found
            if not await self.aget_thread_by_id(thread_id):
                raise ValueError(f"Cannot add messages because thread with id {thread_id} does not exist")

            # Lookup role by name using RoleRepository
            role = await self.role_repository.aget_by_name(role_name)
            if not role:
                raise ValueError(f"Role '{role_name}' not found.")

            # Create and add message
            async with self.data_context.get_session_async() as session:
                message_entity = MessageEntity(thread_id=thread_id, role_id=role.id, content=content)
                session.add(message_entity)
                await session.commit()
                await session.refresh(message_entity)

            # Fetch the message with joined role for conversion
            message_entity_with_role = await self.data_context.get_entity_by_id_async(MessageEntity, message_entity.id)

            # Invalidate all cached versions of this thread (all pagination variants)
            invalidated_count = await CacheService.adelete_pattern(f"thread:{thread_id}:*")
            if invalidated_count > 0:
                self.logger.debug(f"Invalidated {invalidated_count} cached entries for thread {thread_id}")

            return MessageConverters.convert_message_entity_to_model(message_entity_with_role)

        except (ValueError, RuntimeError, Exception):
            raise

    @cache_retrieval_or_caching("thread:{thread_id}:page:{page_number}:size:{page_size}", ttl=600)
    async def aget_thread_by_id(self, thread_id: UUID, page_number: int = 0, page_size: int = 0) -> Thread | None:
        """Retrieve a thread by its UUID with optional message pagination.

        Args:
            thread_id: Thread's UUID
            page_number: Page number for messages (1-indexed). 0 means load all messages.
            page_size: Number of messages per page. 0 means load all messages.

        Returns:
            Thread model if found, None otherwise
        """
        try:
            # If pagination parameters are provided and valid, use custom query
            if page_number > 0 and page_size > 0:
                # Get total count of messages for this thread
                total_messages = await self.aget_thread_messages_count(thread_id)

                # Calculate offset from the END of the list (reverse pagination)
                # Page 1 = last page_size messages, Page 2 = previous page_size messages, etc.
                offset = max(0, total_messages - (page_number * page_size))

                async with self.data_context.get_session_async() as session:
                    # Load messages with pagination (ordered chronologically, but offset from the end)
                    # Use joinedload to eager-load the role relationship
                    from sqlalchemy.orm import joinedload

                    messages_stmt = select(MessageEntity).options(joinedload(MessageEntity.role)).where(MessageEntity.thread_id == thread_id).order_by(MessageEntity.created_at).offset(offset).limit(page_size)
                    messages_result = await session.execute(messages_stmt)
                    paginated_messages = list(messages_result.scalars().unique().all())

                # Now load the thread with user and context, and manually assign the messages
                thread_entity: ThreadEntity = await self.data_context.get_entity_by_id_async(ThreadEntity, thread_id)

                if not thread_entity:
                    return None

                # Replace the messages collection with our paginated subset
                thread_entity.messages = paginated_messages

                return ThreadConverters.convert_thread_entity_to_model(thread_entity)
            else:
                # Default behavior: load all messages (eager loading via relationship)
                thread_entity_default: ThreadEntity | None = await self.data_context.get_entity_by_id_async(ThreadEntity, thread_id)
                return ThreadConverters.convert_thread_entity_to_model(thread_entity_default) if thread_entity_default else None

        except Exception as e:
            self.logger.error(f"Failed to get thread by id: {e}")
            return None

    async def adoes_thread_exist(self, thread_id: UUID) -> bool:
        """Check if a thread exists by its UUID.

        Args:
            thread_id: Thread's UUID

        Returns:
            True if thread exists, False otherwise
        """
        try:
            retrieved_thread_id: UUID | None = await self.data_context.get_entity_by_id_async(ThreadEntity, thread_id, [ThreadEntity.id], fails_if_not_found=False)
            return True if retrieved_thread_id else False
        except Exception as e:
            self.logger.error(f"Failed to check if thread exists: {e}")
            return False

    async def aget_threads_ids_by_user_and_context(self, user_id: UUID, context_id: UUID) -> list[UUID]:
        """Retrieve all threads ids for a user and context.

        Args:
            user_id: User's UUID
            context_id: Context's UUID

        Returns:
            List of Thread ids
        """
        try:
            async with self.data_context.get_session_async() as session:
                stmt = select(ThreadEntity.id).where(ThreadEntity.user_id == user_id).where(ThreadEntity.context_id == context_id).order_by(ThreadEntity.created_at.desc())
                result = await session.execute(stmt)
                thread_ids: list[UUID] = list(result.scalars().all())
                return thread_ids
        except Exception as e:
            self.logger.error(f"Failed to get user threads: {e}")
            return []

    async def aget_thread_messages_count(self, thread_id: UUID) -> int:
        """Get the total count of messages for a thread.

        Args:
            thread_id: Thread's UUID

        Returns:
            Total number of messages in the thread
        """
        try:
            from sqlalchemy import func

            async with self.data_context.get_session_async() as session:
                count_stmt = select(func.count()).select_from(MessageEntity).where(MessageEntity.thread_id == thread_id)
                count_result = await session.execute(count_stmt)
                total_messages: int = count_result.scalar() or 0
                return total_messages
        except Exception as e:
            self.logger.error(f"Failed to get thread messages count: {e}")
            return 0
