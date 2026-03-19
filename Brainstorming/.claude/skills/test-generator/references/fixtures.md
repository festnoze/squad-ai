# Common Pytest Fixtures Reference

All available fixtures for SkillForge API tests, organized by category.

Location: `tests/conftest.py`

---

## Event Loop Configuration

```python
@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for each test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()
```

---

## Role Fixtures

```python
@pytest.fixture
def user_role() -> Role:
    """Create a user role fixture."""
    return Role(id=uuid4(), name="user")

@pytest.fixture
def assistant_role() -> Role:
    """Create an assistant role fixture."""
    return Role(id=uuid4(), name="assistant")
```

---

## User Fixtures

```python
@pytest.fixture
def sample_user() -> User:
    """Create a sample user fixture."""
    return User(
        id=uuid4(),
        lms_user_id="test-lms-user-123",
        email="test@example.com",
        created_at=datetime.now(timezone.utc),
    )

@pytest.fixture
def mock_user(user_id: UUID | None = None) -> User:
    """Fixture providing a mock User model"""
    return User(
        id=user_id or uuid4(),
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
    """Sample user request data"""
    return {
        "lms_user_id": "8888",
        "school_name": "Test School",
        "civility": "Mr",
        "first_name": "Error",
        "last_name": "Test",
        "email": "error@example.com",
    }
```

---

## Message Fixtures

```python
@pytest.fixture
def sample_user_message(user_role: Role, sample_user: User) -> Message:
    """Create a sample user message fixture."""
    return Message(
        id=uuid4(),
        thread_id=uuid4(),
        user_id=sample_user.id,
        role=user_role,
        content="What is the Pythagorean theorem?",
        llm_content=None,
        llm_processing_status="pending",
        quick_action=None,
        selected_text=None,
        created_at=datetime.now(timezone.utc),
    )

@pytest.fixture
def sample_assistant_message(assistant_role: Role, sample_user: User) -> Message:
    """Create a sample assistant message fixture."""
    return Message(
        id=uuid4(),
        thread_id=uuid4(),
        user_id=sample_user.id,
        role=assistant_role,
        content="The Pythagorean theorem states that...",
        llm_content="Summary: Explained Pythagorean theorem",
        llm_processing_status="completed",
        quick_action=None,
        selected_text=None,
        created_at=datetime.now(timezone.utc),
    )

@pytest.fixture
def mock_message(mock_thread: Thread) -> Message:
    """Fixture providing a mock Message model"""
    mock_role = Role(id=uuid4(), name="user")
    return Message(
        id=uuid4(),
        thread_id=mock_thread.id,
        user_id=mock_thread.user_id,
        role=mock_role,
        content="Test message content",
        selected_text=None,
        quick_action=None,
        created_at=datetime.now(),
    )
```

---

## Thread Fixtures

```python
@pytest.fixture
def sample_thread(
    sample_user: User,
    sample_user_message: Message,
    sample_assistant_message: Message,
) -> Thread:
    """Create a sample thread with messages."""
    thread_id = uuid4()
    sample_user_message.thread_id = thread_id
    sample_assistant_message.thread_id = thread_id
    return Thread(
        id=thread_id,
        user_id=sample_user.id,
        messages=[sample_user_message, sample_assistant_message],
        created_at=datetime.now(timezone.utc),
    )

@pytest.fixture
def empty_thread(sample_user: User) -> Thread:
    """Create an empty thread with no messages."""
    return Thread(
        id=uuid4(),
        user_id=sample_user.id,
        messages=[],
        created_at=datetime.now(timezone.utc),
    )

@pytest.fixture
def mock_thread(mock_user: User) -> Thread:
    """Fixture providing a mock Thread model"""
    return Thread(
        id=uuid4(),
        user_id=mock_user.id,
        created_at=datetime.now(),
        messages=[],
    )
```

---

## Async Task Fixtures

```python
@pytest.fixture
def sample_async_task() -> AsyncTask:
    """Create a sample async task fixture."""
    entity_id = uuid4()
    return AsyncTask(
        id=uuid4(),
        name=f"summarize_answer_{entity_id}",
        task_type="summarize_answer",
        entity_type="message",
        entity_id=entity_id,
        status="pending",
        retry_count=0,
        description=None,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
        deleted_at=None,
    )

@pytest.fixture
def processing_async_task() -> AsyncTask:
    """Create an async task in processing status."""
    # ... (status="processing")

@pytest.fixture
def completed_async_task() -> AsyncTask:
    """Create a completed async task."""
    # ... (status="done")

@pytest.fixture
def error_async_task() -> AsyncTask:
    """Create a failed async task."""
    # ... (status="error", retry_count=3)
```

---

## Context Filter Fixtures

```python
@pytest.fixture
def mock_context_filter_request() -> dict:
    """Default context filter request fixture (text resource)"""
    return {
        "context_type": "studi",
        "ressource": {
            "ressource_id": "res_001",
            "ressource_type": "text",
            "ressource_code": "code_001",
            "ressource_title": "Test Resource",
            "ressource_url": "http://example.com",
            "ressource_path": "/path/to/resource",
        },
        "theme_id": "theme_001",
        "module_id": "module_001",
        "matiere_id": "matiere_001",
        "parcour_id": "parcour_001",
    }

@pytest.fixture
def mock_context_filter_video() -> dict:
    """Context filter request fixture for video resource"""
    # ... (ressource_type="video")

@pytest.fixture
def mock_context_filter_pdf() -> dict:
    """Context filter request fixture for PDF resource"""
    # ... (ressource_type="pdf")
```

---

## Mock Repository Fixtures

### User Repository

```python
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
```

### Thread Repository

```python
@pytest.fixture
def mock_thread_repository() -> Mock:
    """Fixture providing a mocked ThreadRepository"""
    repo = Mock()
    repo.acreate_thread = AsyncMock()
    repo.aadd_message_to_thread = AsyncMock()
    repo.aget_thread_by_id = AsyncMock()
    repo.aget_user_all_threads_async = AsyncMock()
    repo.adoes_thread_exist = AsyncMock()
    repo.aget_threads_ids_by_user_and_context = AsyncMock()
    repo.aget_user_message_count_since_start_of_day = AsyncMock(return_value=0)
    repo.aget_user_message_count_since_start_of_month = AsyncMock(return_value=0)
    repo.aclear_thread_messages = AsyncMock()
    repo.aget_thread_messages_count = AsyncMock()
    return repo
```

### Other Mock Repositories

```python
@pytest.fixture
def mock_school_repository() -> Mock:
    """Fixture providing a mocked SchoolRepository"""
    repo = Mock()
    repo.acreate_or_get_by_name = AsyncMock()
    return repo

@pytest.fixture
def mock_async_task_repo() -> AsyncMock:
    """Create a mock AsyncTaskRepository."""
    mock = AsyncMock()
    mock.acreate = AsyncMock()
    mock.aget_by_id = AsyncMock()
    mock.aget_by_name = AsyncMock()
    mock.aget_pending_by_type = AsyncMock(return_value=[])
    mock.aget_by_entity_id = AsyncMock(return_value=[])
    mock.aupdate_status = AsyncMock()
    mock.amark_as_processing = AsyncMock()
    mock.amark_as_completed = AsyncMock()
    mock.amark_as_error = AsyncMock()
    mock.adelete_soft = AsyncMock()
    return mock

@pytest.fixture
def mock_message_repo() -> AsyncMock:
    """Create a mock MessageRepository."""
    mock = AsyncMock()
    mock.aget_by_id = AsyncMock()
    mock.aget_messages_pending_llm_processing = AsyncMock(return_value=[])
    mock.aget_messages_for_takeaway_extraction = AsyncMock(return_value=[])
    mock.aupdate_llm_processing_status = AsyncMock()
    mock.aupdate_llm_content = AsyncMock()
    mock.aupdate_llm_processing = AsyncMock()
    return mock

@pytest.fixture
def mock_qa_pair_repo() -> AsyncMock:
    """Create a mock QuestionAnswerPairRepository."""
    mock = AsyncMock()
    mock.acreate = AsyncMock()
    mock.aget_by_id = AsyncMock()
    mock.aget_by_question_message_id = AsyncMock()
    mock.aget_by_answer_message_id = AsyncMock()
    mock.aget_by_message_id = AsyncMock()
    mock.aget_recent_pairs = AsyncMock(return_value=[])
    return mock

@pytest.fixture
def mock_takeaway_repo() -> AsyncMock:
    """Create a mock TakeawayRepository."""
    mock = AsyncMock()
    mock.acreate = AsyncMock()
    mock.aget_by_id = AsyncMock()
    mock.aget_by_answer_message_id = AsyncMock(return_value=[])
    mock.aget_by_user_id = AsyncMock(return_value=[])
    mock.aget_by_thread_id = AsyncMock(return_value=[])
    mock.aget_by_type = AsyncMock(return_value=[])
    mock.aget_by_theme_id = AsyncMock(return_value=[])
    mock.acount_by_answer_message_id = AsyncMock(return_value=0)
    return mock
```

---

## Mock Service Fixtures

```python
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

@pytest.fixture
def mock_llm_service_episodic() -> AsyncMock:
    """Create a mock LlmService with episodic memory methods."""
    mock = AsyncMock()
    mock.aquery = AsyncMock()
    mock.acontextualize_question = AsyncMock(return_value="Contextualized question")
    mock.asummarize_message = AsyncMock(return_value="Answer summary")
    mock.acreate_thread_takeaways = AsyncMock(return_value=[])
    return mock
```

---

## Test Database Fixtures

### Session Manager Setup

```python
@pytest.fixture(scope="function")
async def setup_test_session_manager(monkeypatch):
    """Initialize test SessionManager with temporary SQLite database.

    This fixture:
    1. Creates a temporary SQLite database for testing
    2. Initializes the SessionManager singleton with this test database
    3. Creates all required tables
    4. Fills static data (roles, etc.)
    5. Yields control to the test
    6. Cleans up by disposing SessionManager and removing temp database
    """
    # ... implementation details
    yield
    # ... cleanup
```

### Test Repository Fixtures

```python
@pytest.fixture
async def test_user_repository(setup_test_session_manager) -> UserRepository:
    """Fixture providing UserRepository with temporary SQLite database."""
    return UserRepository()

@pytest.fixture
async def test_school_repository(setup_test_session_manager) -> SchoolRepository:
    """Fixture providing SchoolRepository sharing same test database."""
    return SchoolRepository()

@pytest.fixture
async def test_thread_repository(setup_test_session_manager) -> ThreadRepository:
    """Fixture providing ThreadRepository sharing same test database."""
    return ThreadRepository()

@pytest.fixture
async def test_context_repository(setup_test_session_manager) -> ContextRepository:
    """Fixture providing ContextRepository sharing same test database."""
    return ContextRepository()

@pytest.fixture
async def test_migration_history_repository(setup_test_session_manager) -> MigrationHistoryRepository:
    """Fixture providing MigrationHistoryRepository sharing same test database."""
    return MigrationHistoryRepository()

@pytest.fixture
async def test_async_task_repository(setup_test_session_manager) -> AsyncTaskRepository:
    """Fixture providing AsyncTaskRepository with temporary SQLite database."""
    return AsyncTaskRepository()

@pytest.fixture
async def test_message_repository(setup_test_session_manager) -> MessageRepository:
    """Fixture providing MessageRepository with temporary SQLite database."""
    return MessageRepository()

@pytest.fixture
async def test_qa_pair_repository(setup_test_session_manager) -> QuestionAnswerPairRepository:
    """Fixture providing QuestionAnswerPairRepository with temporary SQLite database."""
    return QuestionAnswerPairRepository()

@pytest.fixture
async def test_takeaway_repository(setup_test_session_manager) -> TakeawayRepository:
    """Fixture providing TakeawayRepository with temporary SQLite database."""
    return TakeawayRepository()
```

### Test Service Fixtures

```python
@pytest.fixture
def test_user_service(
    test_user_repository: UserRepository,
    test_school_repository: SchoolRepository,
) -> UserService:
    """Fixture providing UserService with test repository"""
    return UserService(
        user_repository=test_user_repository,
        school_repository=test_school_repository,
    )

@pytest.fixture
def test_thread_service(
    test_user_service: UserService,
    test_context_repository: ContextRepository,
    test_content_service,
    test_course_hierarchy_service,
    test_thread_repository: ThreadRepository,
    test_user_repository: UserRepository,
    test_message_repository: MessageRepository,
    test_qa_pair_repository: QuestionAnswerPairRepository,
    test_async_task_repository: AsyncTaskRepository,
    test_llm_service,
) -> ThreadService:
    """Fixture providing ThreadService with test repositories"""
    return ThreadService(
        user_service=test_user_service,
        content_service=test_content_service,
        course_hierarchy_service=test_course_hierarchy_service,
        thread_repository=test_thread_repository,
        context_repository=test_context_repository,
        message_repository=test_message_repository,
        question_answer_pair_repository=test_qa_pair_repository,
        async_task_repository=test_async_task_repository,
        llm_service=test_llm_service,
    )
```

---

## App and Client Fixtures

```python
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
    """Fixture providing test client with full dependency chain"""
    with deps.override_for_test() as test_container:
        test_container[UserRepository] = test_user_repository
        test_container[SchoolRepository] = test_school_repository
        test_container[ThreadRepository] = test_thread_repository
        test_container[ContextRepository] = test_context_repository
        test_container[UserService] = test_user_service
        test_container[ThreadService] = test_thread_service
        yield TestClient(app)
```

---

## Helper Functions

```python
def create_mock_async_session():
    """Helper function to create a properly mocked async session"""
    mock_session = MagicMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=None)
    mock_session.execute = AsyncMock()
    return mock_session
```

---

## Fixture Dependencies Summary

| Fixture | Depends On |
|---------|------------|
| `test_*_repository` | `setup_test_session_manager` |
| `test_user_service` | `test_user_repository`, `test_school_repository` |
| `test_thread_service` | Multiple repositories + services |
| `client` | `app`, all test repositories + services |
| `mock_*_repository` | None (pure mocks) |
| `mock_*_service` | None (pure mocks) |

---

## Creating Custom Fixtures

### New Repository Fixture

```python
@pytest.fixture
async def test_{entity}_repository(setup_test_session_manager) -> {Entity}Repository:
    """Fixture providing {Entity}Repository with temporary SQLite database.

    Depends on setup_test_session_manager to initialize the test database.
    """
    return {Entity}Repository()
```

### New Mock Repository Fixture

```python
@pytest.fixture
def mock_{entity}_repository() -> Mock:
    """Fixture providing a mocked {Entity}Repository"""
    repo = Mock()
    repo.acreate = AsyncMock()
    repo.aget_by_id = AsyncMock()
    repo.aupdate = AsyncMock()
    repo.adelete = AsyncMock()
    # Add other methods as needed
    return repo
```

### New Mock Service Fixture

```python
@pytest.fixture
def mock_{entity}_service() -> Mock:
    """Fixture providing a mocked {Entity}Service"""
    service = Mock()
    service.acreate_{entity} = AsyncMock()
    service.aget_{entity}_by_id = AsyncMock()
    service.aupdate_{entity} = AsyncMock()
    service.adelete_{entity} = AsyncMock()
    # Add other methods as needed
    return service
```
