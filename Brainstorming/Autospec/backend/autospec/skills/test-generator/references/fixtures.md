# Async fixtures & mocking

## Async mocks
Use `AsyncMock` for any awaited collaborator; its return value is awaited for you.
```python
from unittest.mock import AsyncMock
repo = AsyncMock()
repo.aget_user_by_id.return_value = sample_user        # awaited result
repo.aget_user_by_id.side_effect = NotFoundError(...)  # raise on await
repo.acreate_user.assert_awaited_once_with(sample_user)
```

## Sample-data fixture
```python
import pytest
from uuid import uuid4
from datetime import datetime, timezone

@pytest.fixture
def sample_user():
    return User(id=uuid4(), email="test@example.com",
                created_at=datetime.now(timezone.utc))
```

## Service-under-test fixture
```python
@pytest.fixture
def mock_user_repository():
    return AsyncMock()

@pytest.fixture
def service(mock_user_repository):
    return UserService(user_repository=mock_user_repository)
```

## pytest config
- `@pytest.mark.asyncio` on every async test (or `asyncio_mode = "auto"` in config).
- In-memory DB per test for integration; roll back / recreate schema between tests.
- Keep unit tests free of IO: no real DB, no network, no filesystem.
