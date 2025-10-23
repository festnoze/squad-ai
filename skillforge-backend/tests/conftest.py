"""Shared test fixtures and configuration for SkillForge API tests"""

import pytest
from uuid import uuid4
from datetime import datetime
from unittest.mock import Mock, AsyncMock, MagicMock
from fastapi import FastAPI
from fastapi.testclient import TestClient

from lagom import Container
from lagom.integrations.fast_api import FastApiIntegration

from dependency_injection_config import deps
from api_config import ApiConfig

from models.user import User
from models.thread import Thread
from models.message import Message

from application.thread_service import ThreadService
from application.user_service import UserService

from infrastructure.thread_repository import ThreadRepository
from infrastructure.user_repository import UserRepository
from infrastructure.school_repository import SchoolRepository
from infrastructure.context_repository import ContextRepository
from infrastructure.fill_static_data_in_database_repository import DatabaseAdministrationRepository
from infrastructure.llm_repository import LlmRepository


# Import all entities to ensure SQLAlchemy relationships are registered
from infrastructure.entities.user_entity import UserEntity  # noqa: F401
from infrastructure.entities.thread_entity import ThreadEntity  # noqa: F401
from infrastructure.entities.message_entity import MessageEntity  # noqa: F401


@pytest.fixture
def mock_user() -> User:
    """Fixture providing a mock User model"""
    return User(
        id=uuid4(),
        lms_user_id="test_lms_123",
        civility="Mr",
        first_name="John",
        last_name="Doe",
        email="john.doe@example.com",
        created_at=datetime.now(),
        updated_at=None,
        deleted_at=None,
    )


@pytest.fixture
def mock_user_request() -> dict:
    return {
        "lms_user_id": "8888",
        "school_name": "Test School",
        "civility": "Mr",
        "first_name": "Error",
        "last_name": "Test",
        "email": "error@example.com",
    }


@pytest.fixture
def mock_thread(mock_user: User) -> Thread:
    """Fixture providing a mock Thread model"""
    return Thread(
        id=uuid4(),
        user_id=mock_user.id,
        created_at=datetime.now(),
        messages=[],
    )


@pytest.fixture
def mock_context_filter_request() -> dict:
    """Default context filter request fixture (text resource)"""
    return {
        "ressource": {"ressource_id": "res_001", "ressource_type": "text", "ressource_code": "code_001", "ressource_title": "Test Resource", "ressource_url": "http://example.com", "ressource_path": "/path/to/resource"},
        "theme_id": "theme_001",
        "module_id": "module_001",
        "matiere_id": "matiere_001",
        "parcour_id": "parcour_001",
    }


@pytest.fixture
def mock_context_filter_video() -> dict:
    """Context filter request fixture for video resource"""
    return {
        "ressource": {
            "ressource_id": "res_video_001",
            "ressource_type": "video",
            "ressource_code": "code_video_001",
            "ressource_title": "Test Video",
            "ressource_url": "http://example.com/video",
            "ressource_path": "/path/to/video",
        },
        "theme_id": "theme_video_001",
        "module_id": "module_video_001",
        "matiere_id": "matiere_video_001",
        "parcour_id": "parcour_video_001",
    }


@pytest.fixture
def mock_context_filter_pdf() -> dict:
    """Context filter request fixture for PDF resource"""
    return {
        "ressource": {"ressource_id": "res_pdf_001", "ressource_type": "pdf", "ressource_code": "code_pdf_001", "ressource_title": "Test PDF", "ressource_url": "http://example.com/pdf", "ressource_path": "/path/to/pdf"},
        "theme_id": "theme_pdf_001",
        "module_id": "module_pdf_001",
        "matiere_id": "matiere_pdf_001",
        "parcour_id": "parcour_pdf_001",
    }


@pytest.fixture
def mock_message(mock_thread: Thread) -> Message:
    """Fixture providing a mock Message model"""
    from models.role import Role

    mock_role = Role(id=uuid4(), name="user")
    return Message(
        id=uuid4(),
        thread_id=mock_thread.id,
        role=mock_role,
        content="Test message content",
        created_at=datetime.now(),
    )


@pytest.fixture
def test_container() -> Container:
    """Fixture providing a fresh test container"""
    return Container()


@pytest.fixture
def test_deps(test_container: Container) -> FastApiIntegration:
    """Fixture providing FastApiIntegration for testing"""
    return FastApiIntegration(test_container)


@pytest.fixture
def mock_user_repository() -> Mock:
    """Fixture providing a mocked UserRepository"""
    repo = Mock()
    repo.acreate = AsyncMock()
    repo.aupdate = AsyncMock()
    repo.acreate_or_update = AsyncMock()
    repo.aget_user_by_id = AsyncMock()
    repo.aget_user_by_lms_user_id = AsyncMock()
    repo.adoes_user_exists = AsyncMock()
    repo.aget_user_by_internal_lms_id = AsyncMock()
    return repo


@pytest.fixture
def mock_school_repository() -> Mock:
    """Fixture providing a mocked SchoolRepository"""
    repo = Mock()
    repo.acreate_or_get_by_name = AsyncMock()
    return repo


@pytest.fixture
def mock_thread_repository() -> Mock:
    """Fixture providing a mocked ThreadRepository"""
    repo = Mock()
    repo.acreate_thread = AsyncMock()
    repo.aadd_message_to_thread = AsyncMock()
    repo.aget_thread_by_id = AsyncMock()
    repo.aget_user_all_threads_async = AsyncMock()
    return repo


@pytest.fixture
def mock_user_service() -> Mock:
    """Fixture providing a mocked UserService"""
    service = Mock()
    service.acreate_or_update_user = AsyncMock()
    service.aget_user_by_lms_user_id = AsyncMock()
    service.aget_user_by_id = AsyncMock()
    return service


@pytest.fixture
def mock_thread_service() -> Mock:
    """Fixture providing a mocked ThreadService"""
    service = Mock()
    service.acreate_new_thread = AsyncMock()
    service.aget_thread_with_added_query = AsyncMock()
    service.astreaming_answer_to_user_query = AsyncMock()
    return service


def create_mock_async_session():
    """Helper function to create a properly mocked async session"""
    mock_session = MagicMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=None)
    mock_session.execute = AsyncMock()
    return mock_session


@pytest.fixture
def mock_generic_datacontext() -> Mock:
    """Fixture providing a mocked GenericDataContext"""
    context = Mock()
    context.add_entity_async = AsyncMock()
    context.get_entity_by_id_async = AsyncMock()
    context.update_entity_async = AsyncMock()

    # Mock async context manager for get_session_async
    context.get_session_async = MagicMock(side_effect=lambda: create_mock_async_session())
    return context


@pytest.fixture
async def test_fill_static_data_in_database_repository() -> DatabaseAdministrationRepository:
    """Fixture providing DatabaseAdministrationRepository with temporary SQLite database"""
    import tempfile

    # Create a temporary database file
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        db_path = tmp.name

    repo: DatabaseAdministrationRepository = DatabaseAdministrationRepository(db_path_or_url=db_path)
    # Create tables asynchronously for async SQLite
    await repo.data_context.create_database_async()
    # Fill static data (roles)
    await repo.afill_all_static_data()
    return repo


@pytest.fixture
async def test_user_repository(test_fill_static_data_in_database_repository: DatabaseAdministrationRepository) -> UserRepository:
    """Fixture providing UserRepository with temporary SQLite database"""
    repo = UserRepository(db_path_or_url=test_fill_static_data_in_database_repository.db_path_or_url)
    return repo


@pytest.fixture
async def test_school_repository(test_fill_static_data_in_database_repository: DatabaseAdministrationRepository) -> SchoolRepository:
    """Fixture providing SchoolRepository sharing same database"""
    repo = SchoolRepository(db_path_or_url=test_fill_static_data_in_database_repository.db_path_or_url)
    return repo


@pytest.fixture
async def test_thread_repository(test_fill_static_data_in_database_repository: DatabaseAdministrationRepository) -> ThreadRepository:
    """Fixture providing ThreadRepository sharing same database as UserRepository"""
    repo = ThreadRepository(db_path_or_url=test_fill_static_data_in_database_repository.db_path_or_url)
    return repo


@pytest.fixture
async def test_context_repository(test_fill_static_data_in_database_repository: DatabaseAdministrationRepository) -> ContextRepository:
    """Fixture providing ContextRepository sharing same database"""
    repo = ContextRepository(db_path_or_url=test_fill_static_data_in_database_repository.db_path_or_url)
    return repo


@pytest.fixture
def test_user_service(test_user_repository: UserRepository, test_school_repository: SchoolRepository) -> UserService:
    """Fixture providing UserService with test repository"""
    return UserService(user_repository=test_user_repository, school_repository=test_school_repository)


@pytest.fixture
def test_llm_repository() -> LlmRepository:
    """Fixture providing a mocked LlmRepository for integration tests"""
    mock_repo = Mock()

    # Mock the aquery method to return an async generator
    async def mock_llm_response():
        yield "This is a test response "
        yield "from the LLM."

    mock_repo.aquery = Mock(side_effect=lambda thread: mock_llm_response())
    return mock_repo


@pytest.fixture
def test_thread_service(test_thread_repository: ThreadRepository, test_user_repository: UserRepository, test_context_repository: ContextRepository, test_llm_repository) -> ThreadService:
    """Fixture providing ThreadService with test repositories"""
    return ThreadService(thread_repository=test_thread_repository, user_repository=test_user_repository, context_repository=test_context_repository, llm_repository=test_llm_repository)


@pytest.fixture
def app() -> FastAPI:
    """Fixture providing FastAPI app with full middleware configuration"""
    app = ApiConfig.create_app()
    return app


@pytest.fixture
def client(
    app: FastAPI,
    test_user_repository: UserRepository,
    test_school_repository: SchoolRepository,
    test_thread_repository: ThreadRepository,
    test_context_repository: ContextRepository,
    test_user_service: UserService,
    test_thread_service: ThreadService,
) -> TestClient:
    """Fixture providing test client with full dependency chain

    Note: Authentication is overridden per test using app.dependency_overrides
    """
    with deps.override_for_test() as test_container:
        test_container[UserRepository] = test_user_repository
        test_container[SchoolRepository] = test_school_repository
        test_container[ThreadRepository] = test_thread_repository
        test_container[ContextRepository] = test_context_repository
        test_container[UserService] = test_user_service
        test_container[ThreadService] = test_thread_service
        yield TestClient(app)
