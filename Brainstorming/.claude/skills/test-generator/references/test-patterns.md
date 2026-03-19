# Test Patterns Reference

Complete test templates for each layer in SkillForge API.

---

## Unit Router

Location: `tests/unit/facade/test_{entity}_router.py`

### Complete Template

```python
"""Unit tests for {Entity} Router"""

import pytest
from unittest.mock import Mock
from fastapi import FastAPI
from fastapi.testclient import TestClient

from API.api_config import ApiConfig
from API.dependency_injection_config import deps
from application.{entity}_service import {Entity}Service
from models.{entity} import {Entity}
from security.jwt_skillforge_payload import JWTSkillForgePayload
from security.auth_dependency import authentication_required


class Test{Entity}Router:
    """Unit tests for {entity} router endpoints"""

    @pytest.fixture
    def mock_jwt_payload(self) -> JWTSkillForgePayload:
        """Fixture providing a mock JWT payload"""
        return JWTSkillForgePayload(
            sid="test_session_123",
            client=8888,
            schoolId=1009,
            iss="uat-lms-studi.studi.fr",
            roles=["user"],
        )

    @pytest.fixture
    def app(self) -> FastAPI:
        """Fixture providing FastAPI app with full middleware configuration"""
        app = ApiConfig.create_app()
        return app

    @pytest.fixture
    def client(
        self,
        app: FastAPI,
        mock_{entity}_service: Mock,
        mock_{entity}: {Entity},
        mock_jwt_payload: JWTSkillForgePayload,
    ) -> TestClient:
        """Fixture providing test client with mocked service"""
        # Mock the service to return test data
        mock_{entity}_service.aget_{entity}_by_id.return_value = mock_{entity}

        # Override the dependency
        with deps.override_for_test() as test_container:
            test_container[{Entity}Service] = mock_{entity}_service
            # Override authentication to return mock JWT payload
            app.dependency_overrides[authentication_required] = lambda: mock_jwt_payload
            yield TestClient(app)
            # Clean up overrides
            app.dependency_overrides.clear()

    # ----- Success Scenarios -----

    def test_aget_{entity}_by_id_success(
        self,
        client: TestClient,
        mock_{entity}: {Entity},
    ) -> None:
        """Test successful {entity} retrieval via endpoint"""
        # Act
        response = client.get(f"/{entity}/{mock_{entity}.id}")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == str(mock_{entity}.id)

    def test_acreate_{entity}_success(
        self,
        app: FastAPI,
        mock_{entity}_service: Mock,
        mock_{entity}: {Entity},
        mock_jwt_payload: JWTSkillForgePayload,
    ) -> None:
        """Test successful {entity} creation via endpoint"""
        # Arrange
        mock_{entity}_service.acreate_{entity}.return_value = mock_{entity}
        request_data = {
            # Add required request fields
        }

        with deps.override_for_test() as test_container:
            test_container[{Entity}Service] = mock_{entity}_service
            app.dependency_overrides[authentication_required] = lambda: mock_jwt_payload
            client = TestClient(app)

            # Act
            response = client.post("/{entity}", json=request_data)

            # Assert
            assert response.status_code == 200  # or 201 for POST create
            mock_{entity}_service.acreate_{entity}.assert_called_once()

            app.dependency_overrides.clear()

    # ----- Error Scenarios -----

    def test_aget_{entity}_not_found(
        self,
        app: FastAPI,
        mock_{entity}_service: Mock,
        mock_jwt_payload: JWTSkillForgePayload,
    ) -> None:
        """Test {entity} retrieval when not found"""
        # Arrange
        mock_{entity}_service.aget_{entity}_by_id.return_value = None

        with deps.override_for_test() as test_container:
            test_container[{Entity}Service] = mock_{entity}_service
            app.dependency_overrides[authentication_required] = lambda: mock_jwt_payload
            client = TestClient(app)

            # Act
            response = client.get("/{entity}/nonexistent-id")

            # Assert
            assert response.status_code == 404

            app.dependency_overrides.clear()

    def test_aget_{entity}_service_error(
        self,
        app: FastAPI,
        mock_{entity}_service: Mock,
        mock_jwt_payload: JWTSkillForgePayload,
    ) -> None:
        """Test handling of service errors"""
        # Arrange
        mock_{entity}_service.aget_{entity}_by_id.side_effect = Exception("Service error")

        with deps.override_for_test() as test_container:
            test_container[{Entity}Service] = mock_{entity}_service
            app.dependency_overrides[authentication_required] = lambda: mock_jwt_payload
            client = TestClient(app)

            # Act
            response = client.get("/{entity}/some-id")

            # Assert
            assert response.status_code == 500
            data = response.json()
            assert data["status"] == "error"

            app.dependency_overrides.clear()

    def test_acreate_{entity}_validation_error(
        self,
        app: FastAPI,
        mock_{entity}_service: Mock,
        mock_jwt_payload: JWTSkillForgePayload,
    ) -> None:
        """Test {entity} creation with invalid data"""
        # Arrange - Invalid request data
        invalid_request = {}  # Missing required fields

        with deps.override_for_test() as test_container:
            test_container[{Entity}Service] = mock_{entity}_service
            app.dependency_overrides[authentication_required] = lambda: mock_jwt_payload
            client = TestClient(app)

            # Act
            response = client.post("/{entity}", json=invalid_request)

            # Assert
            assert response.status_code == 422  # Pydantic validation error

            app.dependency_overrides.clear()
```

---

## Unit Service

Location: `tests/unit/application/test_{entity}_service.py`

### Complete Template

```python
"""Unit tests for {Entity}Service"""

import pytest
from unittest.mock import Mock, AsyncMock
from uuid import uuid4

from application.{entity}_service import {Entity}Service
from models.{entity} import {Entity}
from errors import InternalServerException, NotFoundError


class Test{Entity}Service:
    """Unit tests for {Entity}Service class"""

    @pytest.fixture
    def mock_{entity}_repository(self) -> Mock:
        """Fixture providing a mocked {Entity}Repository"""
        repo = Mock()
        repo.acreate = AsyncMock()
        repo.aupdate = AsyncMock()
        repo.aget_by_id = AsyncMock()
        repo.adelete = AsyncMock()
        return repo

    @pytest.fixture
    def service(self, mock_{entity}_repository: Mock) -> {Entity}Service:
        """Fixture providing {Entity}Service with mocked repository"""
        return {Entity}Service({entity}_repository=mock_{entity}_repository)

    # ----- Success Scenarios -----

    async def test_acreate_{entity}_success(
        self,
        service: {Entity}Service,
        mock_{entity}_repository: Mock,
    ) -> None:
        """Test successful {entity} creation"""
        # Arrange
        {entity}_id = uuid4()
        {entity} = {Entity}(id={entity}_id, ...)  # Add required fields
        mock_{entity}_repository.acreate.return_value = {entity}

        # Act
        result = await service.acreate_{entity}({entity})

        # Assert
        assert result == {entity}
        mock_{entity}_repository.acreate.assert_called_once_with({entity})

    async def test_aget_{entity}_by_id_success(
        self,
        service: {Entity}Service,
        mock_{entity}_repository: Mock,
    ) -> None:
        """Test successful {entity} retrieval by ID"""
        # Arrange
        {entity}_id = uuid4()
        {entity} = {Entity}(id={entity}_id, ...)  # Add required fields
        mock_{entity}_repository.aget_by_id.return_value = {entity}

        # Act
        result = await service.aget_{entity}_by_id({entity}_id)

        # Assert
        assert result == {entity}
        mock_{entity}_repository.aget_by_id.assert_called_once_with({entity}_id)

    async def test_aupdate_{entity}_success(
        self,
        service: {Entity}Service,
        mock_{entity}_repository: Mock,
    ) -> None:
        """Test successful {entity} update"""
        # Arrange
        {entity}_id = uuid4()
        {entity} = {Entity}(id={entity}_id, ...)  # Add required fields
        mock_{entity}_repository.aupdate.return_value = {entity}

        # Act
        result = await service.aupdate_{entity}({entity})

        # Assert
        assert result == {entity}
        mock_{entity}_repository.aupdate.assert_called_once_with({entity})

    # ----- Not Found Scenarios -----

    async def test_aget_{entity}_by_id_not_found(
        self,
        service: {Entity}Service,
        mock_{entity}_repository: Mock,
    ) -> None:
        """Test {entity} retrieval when not found"""
        # Arrange
        mock_{entity}_repository.aget_by_id.return_value = None

        # Act
        result = await service.aget_{entity}_by_id(uuid4())

        # Assert
        assert result is None

    # ----- Error Scenarios -----

    async def test_acreate_{entity}_repository_error(
        self,
        service: {Entity}Service,
        mock_{entity}_repository: Mock,
    ) -> None:
        """Test that repository errors are wrapped in InternalServerException"""
        # Arrange
        {entity} = {Entity}(...)  # Add required fields
        mock_{entity}_repository.acreate.side_effect = Exception("Database error")

        # Act & Assert
        with pytest.raises(InternalServerException):
            await service.acreate_{entity}({entity})

    async def test_aupdate_{entity}_not_exists(
        self,
        service: {Entity}Service,
        mock_{entity}_repository: Mock,
    ) -> None:
        """Test update when {entity} doesn't exist"""
        # Arrange
        {entity} = {Entity}(...)  # Add required fields
        mock_{entity}_repository.aupdate.side_effect = NotFoundError("NOT_FOUND")

        # Act & Assert
        with pytest.raises(NotFoundError):
            await service.aupdate_{entity}({entity})
```

---

## Integration Repository

Location: `tests/integration/test_{entity}_repository.py` or `tests/unit/infrastructure/test_{entity}_repository.py`

### Complete Template

```python
"""Integration tests for {Entity}Repository using test database"""

import pytest
from uuid import uuid4
from datetime import datetime, timezone

from infrastructure.{entity}_repository import {Entity}Repository
from models.{entity} import {Entity}
from errors import ConflictError, NotFoundError


class Test{Entity}Repository:
    """Integration tests for {Entity}Repository using test database"""

    def _create_fake_{entity}(
        self,
        # Add parameters with defaults
        name: str = "Test Name",
    ) -> {Entity}:
        """Helper method to create a fake {Entity} instance with default test values"""
        return {Entity}(
            name=name,
            # Add other required fields with defaults
        )

    # ----- Create Tests -----

    async def test_acreate_success(
        self,
        test_{entity}_repository: {Entity}Repository,
    ) -> None:
        """Test successful {entity} creation"""
        # Arrange
        {entity} = self._create_fake_{entity}()

        # Act
        result = await test_{entity}_repository.acreate({entity})

        # Assert
        assert isinstance(result, {Entity})
        assert result.id is not None
        assert result.name == "Test Name"

    async def test_acreate_conflict(
        self,
        test_{entity}_repository: {Entity}Repository,
    ) -> None:
        """Test {entity} creation when already exists"""
        # Arrange - Create initial entity
        {entity} = self._create_fake_{entity}()
        await test_{entity}_repository.acreate({entity})

        # Act & Assert - Try to create duplicate
        duplicate = self._create_fake_{entity}()  # Same unique constraint
        with pytest.raises(ConflictError):
            await test_{entity}_repository.acreate(duplicate)

    # ----- Read Tests -----

    async def test_aget_by_id_success(
        self,
        test_{entity}_repository: {Entity}Repository,
    ) -> None:
        """Test successful retrieval by ID"""
        # Arrange
        {entity} = self._create_fake_{entity}()
        created = await test_{entity}_repository.acreate({entity})

        # Act
        result = await test_{entity}_repository.aget_by_id(created.id)

        # Assert
        assert isinstance(result, {Entity})
        assert result.id == created.id
        assert result.name == "Test Name"

    async def test_aget_by_id_not_found(
        self,
        test_{entity}_repository: {Entity}Repository,
    ) -> None:
        """Test retrieval when ID doesn't exist"""
        # Act
        result = await test_{entity}_repository.aget_by_id(uuid4())

        # Assert
        assert result is None

    # ----- Update Tests -----

    async def test_aupdate_success(
        self,
        test_{entity}_repository: {Entity}Repository,
    ) -> None:
        """Test successful {entity} update"""
        # Arrange - Create entity first
        {entity} = self._create_fake_{entity}()
        created = await test_{entity}_repository.acreate({entity})

        # Act - Update the entity
        updated_{entity} = self._create_fake_{entity}(name="Updated Name")
        updated_{entity}.id = created.id
        result = await test_{entity}_repository.aupdate(updated_{entity})

        # Assert
        assert isinstance(result, {Entity})
        assert result.id == created.id
        assert result.name == "Updated Name"

    async def test_aupdate_not_found(
        self,
        test_{entity}_repository: {Entity}Repository,
    ) -> None:
        """Test update when {entity} doesn't exist"""
        # Arrange
        nonexistent = self._create_fake_{entity}()
        nonexistent.id = uuid4()

        # Act & Assert
        with pytest.raises(NotFoundError):
            await test_{entity}_repository.aupdate(nonexistent)

    # ----- Delete Tests -----

    async def test_adelete_success(
        self,
        test_{entity}_repository: {Entity}Repository,
    ) -> None:
        """Test successful {entity} deletion"""
        # Arrange
        {entity} = self._create_fake_{entity}()
        created = await test_{entity}_repository.acreate({entity})

        # Act
        await test_{entity}_repository.adelete(created.id)

        # Assert - Verify deletion
        result = await test_{entity}_repository.aget_by_id(created.id)
        assert result is None

    # ----- Exists Tests -----

    async def test_aexists_true(
        self,
        test_{entity}_repository: {Entity}Repository,
    ) -> None:
        """Test existence check when {entity} exists"""
        # Arrange
        {entity} = self._create_fake_{entity}()
        created = await test_{entity}_repository.acreate({entity})

        # Act
        result = await test_{entity}_repository.aexists(created.id)

        # Assert
        assert result is True

    async def test_aexists_false(
        self,
        test_{entity}_repository: {Entity}Repository,
    ) -> None:
        """Test existence check when {entity} doesn't exist"""
        # Act
        result = await test_{entity}_repository.aexists(uuid4())

        # Assert
        assert result is False
```

### Required Fixture in conftest.py

```python
@pytest.fixture
async def test_{entity}_repository(setup_test_session_manager) -> {Entity}Repository:
    """Fixture providing {Entity}Repository with temporary SQLite database.

    Depends on setup_test_session_manager to initialize the test database.
    """
    return {Entity}Repository()
```

---

## E2E Tests

Location: `tests/e2e/test_{workflow}.py`

### Complete Template

```python
"""End-to-end tests for {workflow} flow through the API

This test module verifies the complete user journey for {workflow}:
1. Step description
2. Step description
3. ...
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from uuid import UUID

from security.auth_dependency import authentication_required
from security.jwt_skillforge_payload import JWTSkillForgePayload


class Test{Workflow}Flow:
    """End-to-end tests for {workflow} flow through the API"""

    def _create_mock_auth_dependency(self, lms_user_id: int):
        """Create a mock authentication dependency with given LMS user ID"""
        async def mock_auth():
            return JWTSkillForgePayload(client=lms_user_id, exp=9999999999)
        return mock_auth

    def test_complete_{workflow}_flow_e2e(
        self,
        app: FastAPI,
        client: TestClient,
        mock_context_filter_request: dict,
    ) -> None:
        """Test complete {workflow} flow from start to finish"""
        # Arrange
        lms_user_id = 9001
        app.dependency_overrides[authentication_required] = self._create_mock_auth_dependency(lms_user_id)

        try:
            # Step 1: Create/update user
            user_data = {
                "lms_user_id": str(lms_user_id),
                "school_name": "E2E Test School",
                "civility": "Ms",
                "first_name": "Alice",
                "last_name": "Johnson",
                "email": "alice.johnson@example.com",
            }
            user_response = client.patch("/user/set-infos", json=user_data)

            # Assert Step 1
            assert user_response.status_code == 200
            user_data_response = user_response.json()
            assert user_data_response["first_name"] == "Alice"

            # Step 2: Perform action
            # ...

            # Step 3: Verify results
            # ...

        finally:
            app.dependency_overrides.clear()

    def test_{workflow}_error_scenario(
        self,
        app: FastAPI,
        client: TestClient,
    ) -> None:
        """Test {workflow} when error occurs"""
        # Arrange
        lms_user_id = 9002
        app.dependency_overrides[authentication_required] = self._create_mock_auth_dependency(lms_user_id)

        try:
            # Test error scenario
            # ...
            pass

        finally:
            app.dependency_overrides.clear()
```

### Key E2E Patterns

#### Streaming Response Handling

```python
# Use stream for streaming endpoints
with client.stream("POST", f"/thread/{thread_id}/query", json=query_data) as response:
    assert response.status_code == 200
    # Consume the stream to persist data
    content = b"".join(response.iter_bytes())
    assert len(content) > 0
```

#### Pagination Testing

```python
# Test pagination
page1_response = client.get(f"/{entity}?page_number=1&page_size=3")
assert page1_response.status_code == 200
page1_data = page1_response.json()
assert page1_data["total_count"] == expected_total
assert len(page1_data["items"]) == 3
```

#### Multi-Step Flow

```python
# Step 1: Setup
response1 = client.post("/step1", json=data1)
assert response1.status_code == 200
id_from_step1 = response1.json()["id"]

# Step 2: Use result from step 1
response2 = client.post(f"/step2/{id_from_step1}", json=data2)
assert response2.status_code == 200

# Step 3: Verify
response3 = client.get(f"/verify/{id_from_step1}")
assert response3.status_code == 200
assert response3.json()["status"] == "completed"
```

---

## Naming Convention Summary

| Test Type | Pattern | Example |
|-----------|---------|---------|
| Success | `test_a{action}_{entity}_success` | `test_acreate_user_success` |
| Not Found | `test_a{action}_{entity}_not_found` | `test_aget_user_not_found` |
| Conflict | `test_a{action}_{entity}_conflict` | `test_acreate_user_conflict` |
| Validation | `test_a{action}_{entity}_validation_error` | `test_acreate_user_validation_error` |
| Service Error | `test_a{action}_{entity}_service_error` | `test_aget_user_service_error` |
| E2E Flow | `test_complete_{workflow}_flow_e2e` | `test_complete_user_flow_e2e` |
