"""Unit tests for UserRepository using in-memory SQLite database"""

import pytest
from uuid import uuid4

from infrastructure.user_repository import UserRepository
from models.user import User


@pytest.fixture
async def repository():
    """Fixture providing UserRepository with temporary SQLite database"""
    # Use a temporary file-based SQLite database for testing
    import tempfile
    import os

    # Create a temporary database file
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        db_path = tmp.name

    try:
        # Pass just the file path - GenericDataContext will handle the SQLite URL construction
        repo = UserRepository(db_path_or_url=db_path)
        # Create tables asynchronously for async SQLite
        await repo.data_context.create_database_async()
        yield repo
    finally:
        # Cleanup
        try:
            os.unlink(db_path)
        except Exception:
            pass


class TestUserRepository:
    """Unit tests for UserRepository class using in-memory database"""

    def _create_fake_user(
        self,
        lms_user_id: str = "test_lms_123",
        civility: str = "Mr",
        first_name: str = "John",
        last_name: str = "Doe",
        email: str = "john.doe@example.com",
    ) -> User:
        """Helper method to create a fake User instance with default test values

        Args:
            lms_user_id: LMS user ID (default: "test_lms_123")
            civility: User civility (default: "Mr")
            first_name: User first name (default: "John")
            last_name: User last name (default: "Doe")
            email: User email (default: "john.doe@example.com")

        Returns:
            User instance with provided or default values
        """
        return User(
            lms_user_id=lms_user_id,
            civility=civility,
            first_name=first_name,
            last_name=last_name,
            email=email,
        )

    async def test_acreate_success_async(self, repository: UserRepository):
        """Test successful user creation"""
        # Arrange
        user = self._create_fake_user()

        # Act
        result = await repository.acreate_user(user)

        # Assert
        assert isinstance(result, User)
        assert result.first_name == "John"
        assert result.last_name == "Doe"
        assert result.email == "john.doe@example.com"
        assert result.lms_user_id == "test_lms_123"

    async def test_acreate_user_already_exists_async(self, repository: UserRepository):
        """Test user creation when user already exists"""
        # Arrange - Create initial user
        user = self._create_fake_user()
        await repository.acreate_user(user)

        # Act & Assert - Try to create same user again
        duplicate_user = self._create_fake_user()  # Same lms_user_id
        with pytest.raises(ValueError, match="already exists"):
            await repository.acreate_user(duplicate_user)

    async def test_aupdate_success_async(self, repository: UserRepository):
        """Test successful user update"""
        # Arrange - Create user first
        user = self._create_fake_user()
        created_user = await repository.acreate_user(user)

        # Act - Update the user
        updated_user = self._create_fake_user(
            lms_user_id="test_lms_123",
            civility="Mrs",
            first_name="Jane",
            last_name="Doe",
            email="jane.doe@example.com",
        )
        result = await repository.aupdate_user(updated_user)

        # Assert
        assert isinstance(result, User)
        assert result.first_name == "Jane"
        assert result.email == "jane.doe@example.com"
        assert result.id == created_user.id  # Same user

    async def test_aupdate_user_not_exists_async(self, repository: UserRepository):
        """Test user update when user doesn't exist"""
        # Arrange
        nonexistent_user = self._create_fake_user(lms_user_id="nonexistent")

        # Act & Assert
        with pytest.raises(ValueError, match="does not exist"):
            await repository.aupdate_user(nonexistent_user)

    async def test_aget_user_by_id_success_async(self, repository: UserRepository):
        """Test successful retrieval of user by ID"""
        # Arrange
        user = self._create_fake_user()
        created_user = await repository.acreate_user(user)

        # Act
        result = await repository.aget_user_by_id(created_user.id)

        # Assert
        assert isinstance(result, User)
        assert result.id == created_user.id
        assert result.first_name == "John"

    async def test_aget_user_by_id_not_found_async(self, repository: UserRepository):
        """Test user retrieval by ID when user doesn't exist"""
        # Act
        result = await repository.aget_user_by_id(uuid4())

        # Assert
        assert result is None

    async def test_aget_user_by_lms_id_success_async(self, repository: UserRepository):
        """Test successful retrieval of user by LMS ID"""
        # Arrange
        user = self._create_fake_user()
        await repository.acreate_user(user)

        # Act
        result = await repository.aget_user_by_lms_user_id("test_lms_123")

        # Assert
        assert isinstance(result, User)
        assert result.lms_user_id == "test_lms_123"
        assert result.first_name == "John"

    async def test_aget_user_by_lms_id_not_found_async(self, repository: UserRepository):
        """Test user retrieval by LMS ID when user doesn't exist"""
        # Act
        result = await repository.aget_user_by_lms_user_id("nonexistent_lms_id")

        # Assert
        assert result is None

    async def test_adoes_user_exists_true_async(self, repository: UserRepository):
        """Test user existence check when user exists"""
        # Arrange
        user = self._create_fake_user()
        created_user = await repository.acreate_user(user)

        # Act
        result = await repository.adoes_user_exists_by_id(created_user.id)

        # Assert
        assert result is True

    async def test_adoes_user_exists_false_async(self, repository: UserRepository):
        """Test user existence check when user doesn't exist"""
        # Act
        result = await repository.adoes_user_exists_by_id(uuid4())

        # Assert
        assert result is False

    async def test_acreate_or_update_creates_new_user_async(self, repository: UserRepository):
        """Test create_or_update when user doesn't exist (should create)"""
        # Arrange
        user = self._create_fake_user(lms_user_id="test_lms_new")

        # Act
        result = await repository.acreate_or_update(user)

        # Assert
        assert isinstance(result, User)
        assert result.first_name == "John"
        assert result.lms_user_id == "test_lms_new"

    async def test_acreate_or_update_updates_existing_user_async(self, repository: UserRepository):
        """Test create_or_update when user exists (should update)"""
        # Arrange - Create user first
        user = self._create_fake_user()
        created_user = await repository.acreate_user(user)

        # Act - Update via create_or_update
        updated_user = self._create_fake_user(
            lms_user_id="test_lms_123",
            civility="Dr",
            first_name="Jane",
            last_name="Smith",
            email="jane.smith@example.com",
        )
        result = await repository.acreate_or_update(updated_user)

        # Assert
        assert isinstance(result, User)
        assert result.id == created_user.id  # Same user
        assert result.first_name == "Jane"
        assert result.last_name == "Smith"
        assert result.email == "jane.smith@example.com"
