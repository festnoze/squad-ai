# Test patterns by layer

## Router unit test (mock the service)
```python
import pytest
from unittest.mock import AsyncMock
from fastapi.testclient import TestClient

@pytest.fixture
def mock_user_service():
    return AsyncMock()

@pytest.fixture
def client(app, mock_user_service):
    app.dependency_overrides[get_user_service] = lambda: mock_user_service
    return TestClient(app)

def test_aget_user_success(client, mock_user_service, sample_user):
    mock_user_service.aget_user_by_id.return_value = sample_user
    resp = client.get(f"/users/{sample_user.id}")
    assert resp.status_code == 200
    assert resp.json()["id"] == str(sample_user.id)

def test_aget_user_not_found(client, mock_user_service):
    mock_user_service.aget_user_by_id.side_effect = NotFoundError("USER_NOT_FOUND")
    assert client.get("/users/unknown").status_code == 404
```

## Service unit test (mock the repository)
```python
@pytest.mark.asyncio
async def test_acreate_user_already_exists(service, mock_user_repository, sample_user):
    mock_user_repository.adoes_user_exist_by_email.return_value = True
    with pytest.raises(ConflictError):
        await service.acreate_user(sample_user)
    mock_user_repository.acreate_user.assert_not_awaited()
```

## Repository integration test (real in-memory DB)
```python
@pytest.mark.asyncio
async def test_acreate_and_get_user(repository):
    created = await repository.acreate_user(User(id=uuid4(), email="a@b.c"))
    fetched = await repository.aget_user_by_id(created.id)
    assert fetched.email == "a@b.c"
```

## E2E workflow test (full stack, mock only auth)
Drive the real router → service → repository → DB through the HTTP client; assert
on the visible outcome (status + body), not internals.
