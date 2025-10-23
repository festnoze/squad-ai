"""Integration tests for User feature (endpoint -> service -> repository)"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api_config import ApiConfig
from application.user_service import UserService
from infrastructure.user_repository import UserRepository
from infrastructure.school_repository import SchoolRepository
from dependency_injection_config import deps
from security.auth_dependency import authentication_required
from security.jwt_skillforge_payload import JWTSkillForgePayload


class TestUserIntegration:
    """Integration tests for complete user flow"""

    @pytest.fixture
    def app(self) -> FastAPI:
        """Fixture providing FastAPI app with full middleware configuration"""
        app = ApiConfig.create_app()
        return app

    def _create_mock_auth_dependency(self, lms_user_id: int):
        """Create a mock authentication dependency that returns a JWT payload with the given LMS user ID"""

        async def mock_auth():
            return JWTSkillForgePayload(client=lms_user_id, exp=9999999999)

        return mock_auth

    @pytest.fixture
    async def test_repository(self) -> UserRepository:
        """Fixture providing UserRepository with temporary SQLite database"""
        import tempfile

        # Create a temporary database file
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
            db_path = tmp.name

        repo = UserRepository(db_path_or_url=db_path)
        # Create tables asynchronously for async SQLite
        await repo.data_context.create_database_async()
        return repo

    @pytest.fixture
    async def test_school_repository(self) -> SchoolRepository:
        """Fixture providing SchoolRepository with temporary SQLite database"""
        import tempfile

        # Create a temporary database file
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
            db_path = tmp.name

        repo = SchoolRepository(db_path_or_url=db_path)
        # Create tables asynchronously for async SQLite
        await repo.data_context.create_database_async()
        return repo

    @pytest.fixture
    def test_service(self, test_repository: UserRepository, test_school_repository: SchoolRepository) -> UserService:
        """Fixture providing UserService with test repository"""
        return UserService(user_repository=test_repository, school_repository=test_school_repository)

    @pytest.fixture
    def client(self, app: FastAPI, test_service: UserService, test_repository: UserRepository) -> TestClient:
        """Fixture providing test client with full dependency chain"""
        with deps.override_for_test() as test_container:
            test_container[UserRepository] = test_repository
            test_container[UserService] = test_service
            yield TestClient(app)

    def test_create_user_full_flow(self, app: FastAPI, client: TestClient, mock_user_request: dict):
        """Test creating a user through all layers (endpoint -> service -> repository)"""
        # Arrange
        lms_user_id = mock_user_request["lms_user_id"]
        # Override authentication (to match the LMS user id)
        app.dependency_overrides[authentication_required] = self._create_mock_auth_dependency(lms_user_id)

        try:
            # Act
            response = client.patch("/user/set-infos", json=mock_user_request)

            # Assert
            assert response.status_code == 200
            data = response.json()
            assert "id" in data
            assert data["first_name"] == mock_user_request["first_name"]
            assert data["last_name"] == mock_user_request["last_name"]
            assert data["email"] == mock_user_request["email"]
            assert data["lms_user_id"] == str(lms_user_id)
        finally:
            app.dependency_overrides.clear()

    def test_update_user_full_flow(self, app: FastAPI, client: TestClient, mock_user_request: dict):
        """Test updating an existing user through all layers"""
        # Arrange
        lms_user_id = mock_user_request["lms_user_id"]
        # Override authentication (to match the LMS user id)
        app.dependency_overrides[authentication_required] = self._create_mock_auth_dependency(lms_user_id)

        try:
            create_response = client.patch("/user/set-infos", json=mock_user_request)
            assert create_response.status_code == 200

            # Act - Update the same user
            mock_user_request["civility"] = "Dr"
            mock_user_request["first_name"] = "Robert"
            mock_user_request["email"] = "robert.johnson@example.com"
            update_response = client.patch("/user/set-infos", json=mock_user_request)

            # Assert
            assert update_response.status_code == 200
            data = update_response.json()
            assert data["first_name"] == "Robert"
            assert data["email"] == "robert.johnson@example.com"
            assert data["civility"] == "Dr"
        finally:
            app.dependency_overrides.clear()

    def test_invalid_email_validation_full_flow(self, app: FastAPI, client: TestClient, mock_user_request: dict):
        """Test that email validation works through the full stack"""
        # Arrange
        mock_user_request["email"] = "invalid-email"
        lms_user_id = mock_user_request["lms_user_id"]
        # Override authentication (to match the LMS user id)
        app.dependency_overrides[authentication_required] = self._create_mock_auth_dependency(lms_user_id)

        try:
            # Act
            response = client.patch("/user/set-infos", json=mock_user_request)

            # Assert
            assert response.status_code == 422  # Validation error from Pydantic
        finally:
            app.dependency_overrides.clear()

    def test_service_layer_error_handling(self, app: FastAPI, test_service: UserService, test_school_repository: SchoolRepository, mock_user_request: dict):
        """Test error handling when service layer encounters issues"""
        # This test demonstrates testing with partial mocking in integration tests
        # We use real repository but can still test error scenarios

        lms_user_id = 8888

        with deps.override_for_test() as test_container:
            # Inject a service that will raise an error
            class FailingUserService(UserService):
                async def acreate_or_update_user(self, *args, **kwargs):
                    raise Exception("Simulated service error")

            test_container[UserService] = FailingUserService(user_repository=test_service.user_repository, school_repository=test_school_repository)

            # Override authentication
            app.dependency_overrides[authentication_required] = self._create_mock_auth_dependency(lms_user_id)

            try:
                # Act
                response = TestClient(app).patch("/user/set-infos", json=mock_user_request)

                # Assert
                assert response.status_code == 500
                data = response.json()
                assert data["status"] == "error"
                assert "detail" in data
            finally:
                app.dependency_overrides.clear()
