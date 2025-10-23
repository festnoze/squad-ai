"""Unit tests for UserService"""

import pytest
from uuid import uuid4
from unittest.mock import Mock

from application.user_service import UserService
from models.user import User


class TestUserService:
    """Unit tests for UserService class"""

    @pytest.fixture
    def service(self, mock_user_repository: Mock, mock_school_repository: Mock) -> UserService:
        """Fixture providing UserService with mocked repository"""
        return UserService(user_repository=mock_user_repository, school_repository=mock_school_repository)

    async def test_acreate_or_update_user_async(self, service: UserService, mock_user: User):
        """Test creating or updating a user"""
        # Arrange
        service.user_repository.acreate_or_update.return_value = mock_user

        # Act
        result = await service.acreate_or_update_user(mock_user)

        # Assert
        assert result == mock_user
        service.user_repository.acreate_or_update.assert_called_once_with(mock_user)

    async def test_aget_user_by_lms_id_found_async(self, service: UserService, mock_user_repository: Mock, mock_user: User):
        """Test retrieving user by LMS ID when user exists"""
        # Arrange
        mock_user_repository.aget_user_by_lms_user_id.return_value = mock_user

        # Act
        result = await service.aget_user_by_lms_user_id(mock_user.lms_user_id)

        # Assert
        assert result == mock_user
        mock_user_repository.aget_user_by_lms_user_id.assert_called_once_with(mock_user.lms_user_id)

    async def test_aget_user_by_lms_id_not_found_async(self, service: UserService, mock_user_repository: Mock):
        """Test retrieving user by LMS ID when user doesn't exist"""
        # Arrange
        mock_user_repository.aget_user_by_lms_user_id.return_value = None

        # Act
        result = await service.aget_user_by_lms_user_id("nonexistent_lms_id")

        # Assert
        assert result is None
        mock_user_repository.aget_user_by_lms_user_id.assert_called_once_with("nonexistent_lms_id")

    async def test_aget_user_by_id_found_async(self, service: UserService, mock_user_repository: Mock, mock_user: User):
        """Test retrieving user by UUID when user exists"""
        # Arrange
        user_id = uuid4()
        mock_user_repository.aget_user_by_id.return_value = mock_user

        # Act
        result = await service.aget_user_by_id(user_id)

        # Assert
        assert result == mock_user
        mock_user_repository.aget_user_by_id.assert_called_once_with(user_id)

    async def test_aget_user_by_id_not_found_async(self, service: UserService, mock_user_repository: Mock):
        """Test retrieving user by UUID when user doesn't exist"""
        # Arrange
        user_id = uuid4()
        mock_user_repository.aget_user_by_id.return_value = None

        # Act
        result = await service.aget_user_by_id(user_id)

        # Assert
        assert result is None
        mock_user_repository.aget_user_by_id.assert_called_once_with(user_id)

    async def test_acreate_or_update_user_propagates_exception_async(self, service: UserService, mock_user_repository: Mock, mock_user: User):
        """Test that exceptions from repository are propagated"""
        # Arrange
        mock_user_repository.acreate_or_update.side_effect = Exception("Database error")

        # Act & Assert
        with pytest.raises(Exception, match="Database error"):
            await service.acreate_or_update_user(mock_user)
