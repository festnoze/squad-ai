"""Unit tests for User Router"""

import pytest
from unittest.mock import Mock
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from api_config import ApiConfig
from application.user_service import UserService
from models.user import User
from dependency_injection_config import deps


class TestUserRouter:
    """Unit tests for user router endpoints"""

    @pytest.fixture
    def app(self) -> FastAPI:
        """Fixture providing FastAPI app with full middleware configuration"""
        app = ApiConfig.create_app()
        return app

    @pytest.fixture
    def client(self, app: FastAPI, mock_user_service: Mock, mock_user: User) -> TestClient:
        """Fixture providing test client with mocked user service"""
        # Mock the service to return our test user
        mock_user_service.acreate_or_update_user.return_value = mock_user

        # Override the dependency
        with deps.override_for_test() as test_container:
            test_container[UserService] = mock_user_service
            yield TestClient(app)

    def test_acreate_or_update_user_success(self, client: TestClient, mock_user_request: dict):
        """Test successful user creation/update via endpoint"""
        # Act
        response = client.patch("/user/set-infos", json=mock_user_request)

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["first_name"] == "John"
        assert data["last_name"] == "Doe"
        assert data["email"] == "john.doe@example.com"

    def test_acreate_or_update_user_invalid_email(self, app: FastAPI, mock_user_service: Mock, mock_user_request: dict):
        """Test user creation with invalid email"""
        # Arrange - Mock service to raise ValidationError for invalid email
        # Create a real ValidationError by attempting to create a User with invalid email
        from datetime import datetime, timezone
        from uuid import uuid4

        try:
            User(
                id=uuid4(),
                lms_user_id="test",
                civility="Mr",
                first_name="John",
                last_name="Doe",
                email="invalid-email",  # This will raise ValidationError
                created_at=datetime.now(timezone.utc),
            )
        except ValidationError as validation_error:
            mock_user_service.acreate_or_update_user.side_effect = validation_error

        with deps.override_for_test() as test_container:
            test_container[UserService] = mock_user_service
            client = TestClient(app)

            # Act
            response = client.patch("/user/set-infos", json=mock_user_request)

            # Assert
            assert response.status_code == 400  # Middleware catches ValidationError as ValueError

    def test_acreate_or_update_user_missing_fields(self, app: FastAPI, mock_user_service: Mock, mock_user_request: dict):
        """Test user creation with missing required fields"""
        # Arrange
        with deps.override_for_test() as test_container:
            test_container[UserService] = mock_user_service
            client = TestClient(app)

            # Act
            response = client.patch("/user/set-infos", json=mock_user_request)

            # Assert
            assert response.status_code == 400  # Middleware catches ValidationError as ValueError

    def test_acreate_or_update_user_service_error(self, app: FastAPI, mock_user_service: Mock, mock_user_request: dict):
        """Test handling of service errors"""
        # Arrange
        mock_user_service.acreate_or_update_user.side_effect = Exception("Service error")

        with deps.override_for_test() as test_container:
            test_container[UserService] = mock_user_service
            client = TestClient(app)

            # Act
            response = client.patch("/user/set-infos", json=mock_user_request)

            # Assert
            assert response.status_code == 500
            data = response.json()
            assert data["status"] == "error"
            assert "detail" in data
