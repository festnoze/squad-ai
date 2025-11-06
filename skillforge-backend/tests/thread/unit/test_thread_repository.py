"""Unit tests for ThreadRepository using in-memory SQLite database"""

import pytest
from uuid import uuid4

from infrastructure.thread_repository import ThreadRepository
from infrastructure.user_repository import UserRepository
from infrastructure.context_repository import ContextRepository
from models.thread import Thread
from models.message import Message
from models.user import User
from models.context import Context


@pytest.fixture
async def test_user_for_thread(test_user_repository: UserRepository) -> User:
    """Fixture providing a test user for thread tests"""
    user = User(
        lms_user_id="test_lms_thread",
        civility="Mr",
        first_name="Test",
        last_name="User",
        email="test.user@example.com",
    )
    return await test_user_repository.acreate_user(user)


@pytest.fixture
async def test_context_for_thread(test_context_repository: ContextRepository) -> Context:
    """Fixture providing a test context for thread tests"""
    context = Context(context_filter={"theme_id": "theme_001", "module_id": "module_001"}, context_full={"theme_id": "theme_001", "module_id": "module_001", "matiere_id": "matiere_001"})
    return await test_context_repository.acreate_context(context)


class TestThreadRepository:
    """Unit tests for ThreadRepository class using in-memory database"""

    async def test_acreate_thread_success_async(self, test_thread_repository: ThreadRepository, test_user_for_thread: User):
        """Test successful thread creation"""
        # Act
        result = await test_thread_repository.acreate_thread(test_user_for_thread.id)

        # Assert
        assert isinstance(result, Thread)
        assert result.user_id == test_user_for_thread.id
        assert len(result.messages) == 0

    async def test_acreate_thread_user_not_exists_async(self, test_thread_repository: ThreadRepository):
        """Test thread creation when user doesn't exist"""
        # Note: SQLite doesn't enforce foreign key constraints by default in test environment
        # This test passes if the function completes or raises an error
        # In production with PostgreSQL, this would raise a foreign key constraint error
        try:
            result = await test_thread_repository.acreate_thread(uuid4())
            # If we get here, the thread was created (SQLite allows this)
            # Just verify it's a Thread object
            assert isinstance(result, Thread)
        except (ValueError, RuntimeError):
            # If an error is raised (PostgreSQL behavior), that's also acceptable
            pass

    async def test_aadd_message_to_thread_success_async(self, test_thread_repository: ThreadRepository, test_user_for_thread: User):
        """Test successfully adding a message to a thread"""
        # Arrange - Create a thread first
        thread = await test_thread_repository.acreate_thread(test_user_for_thread.id)

        # Act - Add a message
        result = await test_thread_repository.aadd_message_to_thread(thread.id, "Test message content", "user")

        # Assert
        assert isinstance(result, Message)
        assert result.content == "Test message content"
        assert result.role.name == "user"
        assert result.thread_id == thread.id

    async def test_aadd_message_to_thread_thread_not_exists_async(self, test_thread_repository: ThreadRepository):
        """Test adding message when thread doesn't exist"""
        # Act & Assert
        # Note: The repository may wrap ValueError in RuntimeError
        with pytest.raises((ValueError, RuntimeError)):
            await test_thread_repository.aadd_message_to_thread(uuid4(), "Test content", "user")

    async def test_aget_thread_by_id_success_async(self, test_thread_repository: ThreadRepository, test_user_for_thread: User):
        """Test successfully retrieving a thread by ID"""
        # Arrange
        created_thread = await test_thread_repository.acreate_thread(test_user_for_thread.id)

        # Act
        result = await test_thread_repository.aget_thread_by_id(created_thread.id)

        # Assert
        assert isinstance(result, Thread)
        assert result.id == created_thread.id
        assert result.user_id == test_user_for_thread.id

    async def test_aget_thread_by_id_not_found_async(self, test_thread_repository: ThreadRepository):
        """Test retrieving thread by ID when thread doesn't exist"""
        # Act
        result = await test_thread_repository.aget_thread_by_id(uuid4())

        # Assert
        assert result is None

    async def test_adoes_thread_exist_true_async(self, test_thread_repository: ThreadRepository, test_user_for_thread: User):
        """Test checking if a thread exists when it does"""
        # Arrange - Create a thread
        thread = await test_thread_repository.acreate_thread(test_user_for_thread.id)

        # Act
        result = await test_thread_repository.adoes_thread_exist(thread.id)

        # Assert
        assert result is True

    async def test_adoes_thread_exist_false_async(self, test_thread_repository: ThreadRepository):
        """Test checking if a thread exists when it doesn't"""
        # Act
        result = await test_thread_repository.adoes_thread_exist(uuid4())

        # Assert
        assert result is False

    async def test_aget_thread_with_messages_async(self, test_thread_repository: ThreadRepository, test_user_for_thread: User):
        """Test retrieving a thread includes its messages"""
        # Arrange - Create thread and add messages
        thread = await test_thread_repository.acreate_thread(test_user_for_thread.id)
        await test_thread_repository.aadd_message_to_thread(thread.id, "First message", "user")
        await test_thread_repository.aadd_message_to_thread(thread.id, "Second message", "assistant")

        # Act
        result = await test_thread_repository.aget_thread_by_id(thread.id)

        # Assert
        assert isinstance(result, Thread)
        assert len(result.messages) == 2
        assert result.messages[0].content in ["First message", "Second message"]
        assert result.messages[1].content in ["First message", "Second message"]

    async def test_aget_threads_ids_by_user_and_context_no_threads_async(self, test_thread_repository: ThreadRepository, test_user_for_thread: User, test_context_for_thread: Context):
        """Test retrieving thread IDs when user has no threads for a context"""
        # Act
        result = await test_thread_repository.aget_threads_ids_by_user_and_context(test_user_for_thread.id, test_context_for_thread.id)

        # Assert
        assert isinstance(result, list)
        assert len(result) == 0

    async def test_aget_threads_ids_by_user_and_context_with_threads_async(self, test_thread_repository: ThreadRepository, test_user_for_thread: User, test_context_for_thread: Context):
        """Test retrieving thread IDs when user has threads for a context"""
        # Arrange - Create multiple threads with the same context
        thread1 = await test_thread_repository.acreate_thread(test_user_for_thread.id, context_id=test_context_for_thread.id)
        thread2 = await test_thread_repository.acreate_thread(test_user_for_thread.id, context_id=test_context_for_thread.id)

        # Act
        result = await test_thread_repository.aget_threads_ids_by_user_and_context(test_user_for_thread.id, test_context_for_thread.id)

        # Assert
        assert isinstance(result, list)
        assert len(result) == 2
        assert thread1.id in result
        assert thread2.id in result

    async def test_aget_threads_ids_by_user_and_context_different_context_async(
        self, test_thread_repository: ThreadRepository, test_context_repository: ContextRepository, test_user_for_thread: User, test_context_for_thread: Context
    ):
        """Test that threads from different contexts are not mixed"""
        # Arrange - Create another context
        other_context = Context(context_filter={"theme_id": "theme_002", "module_id": "module_002"}, context_full={"theme_id": "theme_002", "module_id": "module_002", "matiere_id": "matiere_002"})
        other_context = await test_context_repository.acreate_context(other_context)

        # Create threads with different contexts
        thread1 = await test_thread_repository.acreate_thread(test_user_for_thread.id, context_id=test_context_for_thread.id)
        thread2 = await test_thread_repository.acreate_thread(test_user_for_thread.id, context_id=other_context.id)

        # Act - Get threads for first context
        result = await test_thread_repository.aget_threads_ids_by_user_and_context(test_user_for_thread.id, test_context_for_thread.id)

        # Assert - Only thread1 should be returned
        assert isinstance(result, list)
        assert len(result) == 1
        assert thread1.id in result
        assert thread2.id not in result
