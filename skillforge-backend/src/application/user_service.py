from uuid import UUID
from infrastructure.user_repository import UserRepository
from infrastructure.school_repository import SchoolRepository
from models.user import User
from pydantic import ValidationError


class UserService:
    def __init__(self, user_repository: UserRepository, school_repository: SchoolRepository) -> None:
        self.user_repository: UserRepository = user_repository
        self.school_repository: SchoolRepository = school_repository

    async def acreate_or_update_user(self, user: User) -> User:
        """Create or update a user with school and preferences.

        This method handles:
        1. Creating or getting the school by name
        2. Creating or updating the user with the school reference
        3. Creating or updating user preferences

        Args:
            user: User model containing user data, school, and preferences

        Returns:
            Created/updated User model with all relationships populated

        Raises:
            ValueError: If user data validation fails
        """
        try:
            # Step 1: Handle school - create or get existing school by name
            if user.school and user.school.name:
                user.school = await self.school_repository.acreate_or_get_by_name(user.school.name)
            user_perferences = user.preference

            # Step 2: Create or update user
            user = await self.user_repository.acreate_or_update(user)

            # Step 3: Handle user preferences if provided
            if user_perferences and user.id:
                user_perferences.user_id = user.id
                user.preference = await self.user_repository.acreate_or_update_user_preference(user.id, user_perferences)

            return user

        except ValidationError as e:
            raise ValueError(f"Invalid user data: {e}") from e
        except Exception as e:
            raise ValueError(f"Failed to create or update user: {e}") from e

    async def aservice_activation(self, lms_user_id: str) -> bool:
        """Activate the service for a user."""
        user_id = await self.user_repository.aget_user_id_by_lms_user_id(lms_user_id)
        if not user_id:
            raise ValueError(f"User not found from its internal LMS id: {lms_user_id}")

        return await self.user_repository.aservice_activation(user_id)

    async def aget_user_by_lms_user_id(self, lms_user_id: str) -> User | None:
        """Retrieve a user by their internal LMS ID.

        Args:
            lms_user_id: Unique user identifier from LMS

        Returns:
            User model if found, None otherwise
        """
        return await self.user_repository.aget_user_by_lms_user_id(lms_user_id)

    async def aget_user_by_id(self, user_id: UUID) -> User | None:
        """Retrieve a user by their UUID.

        Args:
            user_id: User's UUID

        Returns:
            User model if found, None otherwise
        """
        return await self.user_repository.aget_user_by_id(user_id)
