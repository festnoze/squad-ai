"""Unit tests for ThreadService"""

import pytest
from uuid import uuid4, UUID
from unittest.mock import Mock, AsyncMock

from application.thread_service import ThreadService
from application.exceptions.quota_exceeded_exception import QuotaExceededException
from models.thread import Thread
from models.message import Message
from models.role import Role
from models.context import Context
from security.jwt_skillforge_payload import JWTSkillForgePayload


class TestThreadService:
    """Unit tests for ThreadService class"""

    @pytest.fixture
    def mock_token_payload(self) -> JWTSkillForgePayload:
        """Fixture providing a mock JWT token payload"""
        return JWTSkillForgePayload(
            iss="test-issuer", exp=9999999999, nbf=0, sid="test-session-id", sub="test-user-id", school_name="Test School", civility="Mr", first_name="Test", last_name="User", email="test@example.com"
        )

    @pytest.fixture
    def mock_context_repository(self) -> Mock:
        """Fixture providing a mocked ContextRepository"""
        repo = Mock()
        repo.aget_or_create_context = AsyncMock()
        repo.aget_context_by_filter = AsyncMock()
        return repo

    @pytest.fixture
    def mock_llm_service(self) -> Mock:
        """Fixture providing a mocked LlmRepository"""
        repo = Mock()
        repo.aquery = AsyncMock()
        return repo

    @pytest.fixture
    def mock_user_service(self) -> Mock:
        """Fixture providing a mocked UserService"""
        service = Mock()
        service.aget_user_by_lms_user_id = AsyncMock()
        return service

    # @pytest.fixture
    # def mock_course(self) -> Course:
    #     """Fixture providing a mocked CourseHierarchy"""
    #     from models.course_hierarchy import CourseHierarchy
    #     return CourseHierarchy(parcours_id="9999", content_summary_full="Test full summary")

    @pytest.fixture
    def mock_course_hierarchy_repository(self) -> Mock:
        """Fixture providing a mocked CourseRepository"""
        from models.course_hierarchy import CourseHierarchy

        repo = Mock()
        mock_course_hierarchy = Mock(spec=CourseHierarchy)

        mock_course_hierarchy.course_hierarchy = {"parcours_id": "9999", "content_summary_full": "Test full summary"}
        repo.aget_course_hierarchy_by_partial_filter = AsyncMock(return_value=mock_course_hierarchy)
        return repo

    @pytest.fixture
    def service(
        self, mock_user_service: Mock, mock_thread_repository: Mock, mock_user_repository: Mock, mock_context_repository: Mock, mock_llm_service: Mock, test_content_service: Mock, mock_course_hierarchy_repository: Mock
    ) -> ThreadService:
        """Fixture providing ThreadService with mocked repositories"""
        return ThreadService(
            user_service=mock_user_service,
            thread_repository=mock_thread_repository,
            user_repository=mock_user_repository,
            context_repository=mock_context_repository,
            llm_service=mock_llm_service,
            content_service=test_content_service,
            course_hierarchy_repository=mock_course_hierarchy_repository,
        )

    async def test_acreate_new_thread_success_async(self, service: ThreadService, mock_token_payload: JWTSkillForgePayload, mock_thread_repository: Mock, mock_user_repository: Mock, mock_thread: Thread):
        """Test successfully creating a new thread"""
        # Arrange
        lms_user_id = "lms_123"
        user_id = uuid4()
        mock_user_repository.aget_user_id_by_lms_user_id = AsyncMock(return_value=user_id)
        mock_thread_repository.adoes_thread_exist = AsyncMock(return_value=False)
        mock_thread_repository.acreate_thread = AsyncMock(return_value=mock_thread)

        # Act
        result = await service.acreate_new_thread(mock_token_payload, lms_user_id)

        # Assert
        assert result == mock_thread
        mock_user_repository.aget_user_id_by_lms_user_id.assert_called_once_with(lms_user_id)
        mock_thread_repository.acreate_thread.assert_called_once_with(user_id, None, None)

    async def test_acreate_new_thread_user_not_exists_async(self, service: ThreadService, mock_token_payload: JWTSkillForgePayload, mock_user_repository: Mock, mock_user_service: Mock, mock_thread_repository: Mock):
        """Test creating thread when user doesn't exist - should create user from token"""
        # Arrange
        lms_user_id = "lms_456"
        new_user_id = uuid4()
        mock_user_repository.aget_user_id_by_lms_user_id = AsyncMock(return_value=None)
        mock_user_repository.acreate_user = AsyncMock()
        mock_user_service.acreate_or_update_user = AsyncMock()
        # Mock aaction_upon_unfound_user to return new user id
        service.aaction_upon_unfound_user = AsyncMock(return_value=new_user_id)
        mock_thread_repository.adoes_thread_exist = AsyncMock(return_value=False)
        mock_thread = Mock()
        mock_thread_repository.acreate_thread = AsyncMock(return_value=mock_thread)

        # Act
        result = await service.acreate_new_thread(mock_token_payload, lms_user_id)

        # Assert
        assert result == mock_thread
        service.aaction_upon_unfound_user.assert_called_once_with(mock_token_payload)
        mock_thread_repository.acreate_thread.assert_called_once()

    async def test_acreate_new_thread_with_context_async(
        self, service: ThreadService, mock_token_payload: JWTSkillForgePayload, mock_thread_repository: Mock, mock_user_repository: Mock, mock_context_repository: Mock, mock_thread: Thread
    ):
        """Test creating thread with context"""
        # Arrange
        lms_user_id = "lms_789"
        user_id = uuid4()
        context_data = {"theme_id": "theme_001", "module_id": "module_001"}
        context_obj = Context(id=uuid4(), context_filter=context_data, context_full=context_data)

        mock_user_repository.aget_user_id_by_lms_user_id = AsyncMock(return_value=user_id)
        mock_thread_repository.adoes_thread_exist = AsyncMock(return_value=False)
        mock_context_repository.aget_or_create_context = AsyncMock(return_value=context_obj)
        mock_thread_repository.acreate_thread = AsyncMock(return_value=mock_thread)

        # Act
        result = await service.acreate_new_thread(mock_token_payload, lms_user_id, context=context_data)

        # Assert
        assert result == mock_thread
        mock_context_repository.aget_or_create_context.assert_called_once()
        mock_thread_repository.acreate_thread.assert_called_once_with(user_id, None, context_obj.id)

    async def test_acreate_new_thread_already_exists_async(self, service: ThreadService, mock_token_payload: JWTSkillForgePayload, mock_thread_repository: Mock, mock_user_repository: Mock):
        """Test creating thread when thread_id already exists"""
        # Arrange
        lms_user_id = "lms_999"
        user_id = uuid4()
        thread_id = uuid4()
        mock_user_repository.aget_user_id_by_lms_user_id = AsyncMock(return_value=user_id)
        mock_thread_repository.adoes_thread_exist = AsyncMock(return_value=True)

        # Act & Assert
        with pytest.raises(ValueError, match="already exists"):
            await service.acreate_new_thread(mock_token_payload, lms_user_id, thread_id=thread_id)

        # Verify thread creation was not attempted
        mock_thread_repository.acreate_thread.assert_not_called()

    async def test_aget_threads_ids_by_user_and_context_no_threads_async(
        self, service: ThreadService, mock_token_payload: JWTSkillForgePayload, mock_thread_repository: Mock, mock_user_repository: Mock, mock_context_repository: Mock
    ):
        """Test getting thread IDs when user has no threads - should return new UUID"""
        # Arrange
        lms_user_id = "lms_001"
        user_id = uuid4()
        context_data = {"theme_id": "theme_001"}
        context_obj = Context(id=uuid4(), context_filter=context_data, context_full=context_data)

        mock_user_repository.aget_user_id_by_lms_user_id = AsyncMock(return_value=user_id)
        mock_context_repository.aget_context_by_filter = AsyncMock(return_value=context_obj)
        mock_thread_repository.aget_threads_ids_by_user_and_context = AsyncMock(return_value=[])

        # Act
        result = await service.aget_threads_ids_by_user_and_context(mock_token_payload, lms_user_id, context_data)

        # Assert
        assert isinstance(result, list)
        assert len(result) == 1
        assert isinstance(result[0], UUID)

    async def test_aget_threads_ids_by_user_and_context_with_threads_async(
        self, service: ThreadService, mock_token_payload: JWTSkillForgePayload, mock_thread_repository: Mock, mock_user_repository: Mock, mock_context_repository: Mock
    ):
        """Test getting thread IDs when user has existing threads"""
        # Arrange
        lms_user_id = "lms_002"
        user_id = uuid4()
        context_data = {"theme_id": "theme_002"}
        context_obj = Context(id=uuid4(), context_filter=context_data, context_full=context_data)
        existing_thread_ids = [uuid4(), uuid4()]

        mock_user_repository.aget_user_id_by_lms_user_id = AsyncMock(return_value=user_id)
        mock_context_repository.aget_context_by_filter = AsyncMock(return_value=context_obj)
        mock_thread_repository.aget_threads_ids_by_user_and_context = AsyncMock(return_value=existing_thread_ids)

        # Act
        result = await service.aget_threads_ids_by_user_and_context(mock_token_payload, lms_user_id, context_data)

        # Assert
        assert result == existing_thread_ids

    async def test_aget_thread_by_id_or_create_existing_thread_async(self, service: ThreadService, mock_token_payload: JWTSkillForgePayload, mock_thread_repository: Mock, mock_user_repository: Mock, mock_thread: Thread):
        """Test getting an existing thread"""
        # Arrange
        lms_user_id = "lms_003"
        thread_id = uuid4()
        mock_user_repository.aget_user_id_by_lms_user_id = AsyncMock(return_value=mock_thread.user_id)
        mock_thread_repository.aget_thread_by_id = AsyncMock(return_value=mock_thread)

        # Act
        result = await service.aget_thread_by_id_or_create(mock_token_payload, thread_id, lms_user_id, persist_thread_if_created=False)

        # Assert
        assert result == mock_thread
        mock_thread_repository.aget_thread_by_id.assert_called_once_with(thread_id, 0, 0)

    async def test_aget_thread_by_id_or_create_thread_not_exists_persist_async(
        self, service: ThreadService, mock_token_payload: JWTSkillForgePayload, mock_thread_repository: Mock, mock_user_repository: Mock, mock_thread: Thread
    ):
        """Test creating a thread when it doesn't exist and persist=True"""
        # Arrange
        lms_user_id = "lms_004"
        user_id = uuid4()
        thread_id = uuid4()
        context_data = {"theme_id": "theme_004"}

        mock_user_repository.aget_user_id_by_lms_user_id = AsyncMock(return_value=user_id)
        mock_thread_repository.aget_thread_by_id = AsyncMock(return_value=None)
        mock_thread_repository.adoes_thread_exist = AsyncMock(return_value=False)
        mock_thread_repository.acreate_thread = AsyncMock(return_value=mock_thread)

        # Act
        result = await service.aget_thread_by_id_or_create(mock_token_payload, thread_id, lms_user_id, context=context_data, persist_thread_if_created=True)

        # Assert
        assert result == mock_thread

    async def test_aget_thread_by_id_or_create_thread_not_exists_no_persist_async(self, service: ThreadService, mock_token_payload: JWTSkillForgePayload, mock_thread_repository: Mock, mock_user_repository: Mock):
        """Test creating a thread when it doesn't exist and persist=False"""
        # Arrange
        lms_user_id = "lms_005"
        user_id = uuid4()
        thread_id = uuid4()

        mock_user_repository.aget_user_id_by_lms_user_id = AsyncMock(return_value=user_id)
        mock_thread_repository.aget_thread_by_id = AsyncMock(return_value=None)

        # Act
        result = await service.aget_thread_by_id_or_create(mock_token_payload, thread_id, lms_user_id, persist_thread_if_created=False)

        # Assert
        assert isinstance(result, Thread)
        assert result.id == thread_id
        assert result.user_id == user_id
        assert result.messages == []
        # Verify thread was NOT persisted
        mock_thread_repository.acreate_thread.assert_not_called()

    async def test_aget_thread_by_id_or_create_wrong_user_async(self, service: ThreadService, mock_token_payload: JWTSkillForgePayload, mock_thread_repository: Mock, mock_user_repository: Mock, mock_thread: Thread):
        """Test accessing thread owned by different user"""
        # Arrange
        lms_user_id = "lms_006"
        thread_id = uuid4()
        wrong_user_id = uuid4()

        mock_user_repository.aget_user_id_by_lms_user_id = AsyncMock(return_value=wrong_user_id)
        mock_thread_repository.aget_thread_by_id = AsyncMock(return_value=mock_thread)

        # Act & Assert
        with pytest.raises(ValueError, match="Access denied"):
            await service.aget_thread_by_id_or_create(mock_token_payload, thread_id, lms_user_id, persist_thread_if_created=False)

    async def test_aadd_user_query_to_thread_success_async(self, service: ThreadService, mock_thread_repository: Mock, mock_thread: Thread):
        """Test successfully adding a user query to a thread"""
        # Arrange
        user_role = Role(id=uuid4(), name="user")
        thread_with_messages = Thread(
            id=mock_thread.id,
            user_id=mock_thread.user_id,
            created_at=mock_thread.created_at,
            messages=[Message(id=uuid4(), thread_id=mock_thread.id, role=user_role, content="Previous query", created_at=mock_thread.created_at)],
        )

        new_message = Message(id=uuid4(), thread_id=mock_thread.id, role=user_role, content="New query", created_at=mock_thread.created_at)

        mock_thread_repository.aadd_message_to_thread = AsyncMock(return_value=new_message)

        # Act
        result = await service._aadd_user_message_to_thread(thread_with_messages, "New query")

        # Assert
        assert result == new_message
        mock_thread_repository.aadd_message_to_thread.assert_called_once_with(mock_thread.id, "New query", "user")

    async def test_aadd_user_query_to_thread_quota_exceeded_async(self, service: ThreadService, mock_thread_repository: Mock, mock_thread: Thread):
        """Test adding query when quota is exceeded"""
        # Arrange
        user_role = Role(id=uuid4(), name="user")
        messages = [Message(id=uuid4(), thread_id=mock_thread.id, role=user_role, content=f"Query {i}", created_at=mock_thread.created_at) for i in range(service.max_messages_by_conversation)]

        thread_at_limit = Thread(id=mock_thread.id, user_id=mock_thread.user_id, created_at=mock_thread.created_at, messages=messages)

        # Act & Assert
        with pytest.raises(QuotaExceededException, match="maximum number of messages"):
            await service._aadd_user_message_to_thread(thread_at_limit, "One more query")

        # Verify message was not added
        mock_thread_repository.aadd_message_to_thread.assert_not_called()

    async def test_astream_answer_to_user_query_and_add_to_thread_async(
        self, service: ThreadService, mock_token_payload: JWTSkillForgePayload, mock_thread_repository: Mock, mock_llm_service: Mock, mock_user_repository: Mock, mock_thread: Thread, test_content_service: Mock
    ):
        """Test streaming answer method using the new two-phase approach"""
        # Arrange
        lms_user_id = "lms_007"
        user_role = Role(id=uuid4(), name="user")
        thread_with_query = Thread(
            id=mock_thread.id,
            user_id=mock_thread.user_id,
            created_at=mock_thread.created_at,
            messages=[Message(id=uuid4(), thread_id=mock_thread.id, role=user_role, content="User query", created_at=mock_thread.created_at)],
        )

        # Mock the LLM repository to return an async generator
        async def mock_llm_response():
            yield "Response "
            yield "chunk "
            yield "1"

        mock_llm_service.aquery = Mock(side_effect=lambda thread, content, title, parcours, use_rag, chunks: mock_llm_response())
        mock_user_repository.aget_user_id_by_lms_user_id = AsyncMock(return_value=mock_thread.user_id)
        mock_thread_repository.aget_thread_by_id = AsyncMock(return_value=thread_with_query)
        mock_thread_repository.aadd_message_to_thread = AsyncMock()

        # Update service to use test_content_service from conftest
        service.content_service = test_content_service

        # Mock context
        context_mock = Mock()
        context_mock.ressource = Mock()
        context_mock.ressource.ressource_title = "Test Title"
        context_mock.parcours_name = "Test Parcours"
        context_mock.model_dump = Mock(return_value={"parcour_id": "9999"})

        # Act - Phase 1: Prepare thread (validates and adds user message)
        prepared_thread = await service.aprepare_thread_for_query(mock_token_payload, thread_with_query.id, lms_user_id, "User query", context_mock)

        # Verify user message was added
        assert mock_thread_repository.aadd_message_to_thread.call_count == 1

        # Act - Phase 2: Stream LLM response
        chunks = []
        async for chunk in service.astream_llm_response_and_persist(prepared_thread, context_mock):
            chunks.append(chunk)

        # Assert
        assert len(chunks) == 3
        assert chunks == ["Response ", "chunk ", "1"]
        # Verify assistant message was added (called once for user message, once for assistant response)
        assert mock_thread_repository.aadd_message_to_thread.call_count == 2

    async def test_max_messages_by_conversation_configuration_async(
        self, mock_user_service: Mock, mock_thread_repository: Mock, mock_user_repository: Mock, mock_context_repository: Mock, mock_llm_service: Mock, test_content_service: Mock, mock_course_hierarchy_repository: Mock
    ):
        """Test that max_messages_by_conversation is configurable"""
        # Act
        service = ThreadService(
            user_service=mock_user_service,
            thread_repository=mock_thread_repository,
            user_repository=mock_user_repository,
            context_repository=mock_context_repository,
            llm_service=mock_llm_service,
            content_service=test_content_service,
            course_hierarchy_repository=mock_course_hierarchy_repository,
        )

        # Assert
        assert service.max_messages_by_conversation == 100
