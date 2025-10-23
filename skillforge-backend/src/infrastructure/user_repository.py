from uuid import UUID
from sqlalchemy import select
from common_tools.database.generic_datacontext import GenericDataContext  # type: ignore[import-untyped]
from infrastructure.entities import Base
from infrastructure.entities.user_entity import UserEntity
from infrastructure.entities.user_preference_entity import UserPreferenceEntity
from infrastructure.converters.user_converters import UserConverters
from infrastructure.converters.user_preference_converters import UserPreferenceConverters
from models.user import User
from models.user_preference import UserPreference
from envvar import EnvHelper
from datetime import datetime


class UserRepository:
    def __init__(self, db_path_or_url: str | None = None) -> None:
        if db_path_or_url:
            self.db_path_or_url = db_path_or_url
        else:
            username = EnvHelper.get_postgres_username()
            password = EnvHelper.get_postgres_password()
            host = EnvHelper.get_postgres_host()
            dbname = EnvHelper.get_postgres_database_name()
            self.db_path_or_url = f"postgresql://{username}:{password}@{host}/{dbname}"
        #
        self.data_context = GenericDataContext(Base, self.db_path_or_url)

    async def acreate_user(self, user: User) -> User:
        """Create a new user into the database from a User model.

        Args:
            user: User model containing user data (including optional school)

        Returns:
            Created User model with all relationships loaded

        Raises:
            ValueError: If user already exists with the given lms_user_id
        """
        try:
            # Check if user already exists
            existing_user = await self.aget_user_by_lms_user_id(user.lms_user_id)
            if existing_user:
                raise ValueError(f"User with lms_user_id '{user.lms_user_id}' already exists")

            # Convert User model to UserEntity using converter
            user_entity = UserConverters.convert_user_model_to_entity(user)
            user_entity = await self.data_context.add_entity_async(user_entity)

            # Re-fetch the user to ensure relationships are properly loaded within a new session
            created_user = await self.aget_user_by_lms_user_id(user.lms_user_id)
            if not created_user:
                raise ValueError(f"Failed to retrieve created user with lms_user_id '{user.lms_user_id}'")

            return created_user

        except Exception as e:
            print(f"Failed to create user: {e}")
            raise

    async def aupdate_user(self, user: User) -> User:
        """Update an existing user in the database from a User model.

        Args:
            user: User model containing updated user data (including optional school)

        Returns:
            Updated User model with all relationships loaded

        Raises:
            ValueError: If user does not exist with the given lms_user_id
        """
        try:
            # Check if user exists
            existing_user = await self.aget_user_by_lms_user_id(user.lms_user_id)
            if not existing_user:
                raise ValueError(f"User with lms_user_id '{user.lms_user_id}' does not exist")

            # Update existing user
            user_id = existing_user.id
            await self.data_context.update_entity_async(
                UserEntity, user_id, school_id=user.school.id if user.school else None, civility=user.civility, first_name=user.first_name, last_name=user.last_name, email=user.email
            )

            # Re-fetch the updated user to ensure relationships are properly loaded
            updated_user = await self.aget_user_by_lms_user_id(user.lms_user_id)
            if not updated_user:
                raise ValueError(f"Failed to retrieve updated user with lms_user_id '{user.lms_user_id}'")

            return updated_user

        except Exception as e:
            print(f"Failed to update user: {e}")
            raise

    async def acreate_or_update(self, user: User) -> User:
        """Create or update user in the database from a User model.

        Args:
            user: User model containing user data (including optional school)

        Returns:
            User model (created or updated) with all relationships loaded
        """
        try:
            existing_user = await self.aget_user_by_lms_user_id(user.lms_user_id)
            if existing_user:
                return await self.aupdate_user(user)
            else:
                return await self.acreate_user(user)

        except Exception as e:
            print(f"Failed to create or update user: {e}")
            raise

    async def aservice_activation(self, user_id: UUID) -> bool:
        """Activate the service for a user."""
        try:
            user: User | None = await self.aget_user_by_id(user_id)
            if not user:
                raise ValueError(f"User with id '{user_id}' does not exist")

            # TODO: to activate when database structure is ready to handle "service activation"
            now = datetime.utcnow()
            await self.data_context.update_entity_async(UserEntity, user_id, service_activation_date=now)
            return True
        except Exception as e:
            print(f"Failed to activate service for user: {e}")
            return False

    async def aget_user_by_id(self, user_id: UUID) -> User | None:
        """Retrieve user by their UUID.

        Args:
            user_id: User's UUID

        Returns:
            User model if found, None otherwise
        """
        try:
            user_entity: UserEntity = await self.data_context.get_entity_by_id_async(UserEntity, user_id)
            return UserConverters.convert_user_entity_to_model(user_entity) if user_entity else None
        except Exception as e:
            print(f"Failed to get user by id: {e}")
            return None

    async def aget_user_by_lms_user_id(self, lms_user_id: str) -> User | None:
        """Retrieve user by their internal LMS ID.

        Args:
            lms_user_id: Unique user identifier from LMS

        Returns:
            User model if found, None otherwise
        """
        try:
            user_entity = await self.data_context.get_first_entity_async(UserEntity, filters=[UserEntity.lms_user_id == lms_user_id], fails_if_not_found=False)
            result: User | None = UserConverters.convert_user_entity_to_model(user_entity) if user_entity else None
            return result
        except Exception as e:
            print(f"Failed to get user by LMS ID: {e}")
            return None

    async def adoes_user_exists_by_id(self, user_id: UUID) -> bool:
        """Check if a user exists by their UUID.

        Args:
            user_id: User's UUID

        Returns:
            True if user exists, False otherwise
        """
        try:
            retrieved_user_id: UUID | None = await self.data_context.get_entity_by_id_async(UserEntity, user_id, [UserEntity.id], fails_if_not_found=False)
            return True if retrieved_user_id else False
        except Exception as e:
            print(f"Failed to check if user exists: {e}")
            return False

    async def aget_user_id_by_lms_user_id(self, lms_user_id: str) -> UUID | None:
        """Check if a user exists by their internal LMS ID.

        Args:
            user_id: User's internal LMS ID

        Returns:
            User's UUID if found, None otherwise
        """
        try:
            retrieved_user_id = await self.data_context.get_first_entity_async(UserEntity, filters=[UserEntity.lms_user_id == lms_user_id], selected_columns=[UserEntity.id], fails_if_not_found=False)
            return retrieved_user_id if isinstance(retrieved_user_id, UUID) else None
        except Exception as e:
            print(f"Failed to check if user exists: {e}")
            return None

    # User Preference Methods

    async def acreate_or_update_user_preference(self, user_id: UUID, preference: UserPreference) -> UserPreference:
        """Create or update user preferences for a user.

        Args:
            user_id: UUID of the user
            preference: UserPreference model containing preference data

        Returns:
            UserPreference model (created or updated)
        """
        try:
            # Check if preference already exists for this user
            existing_preference = await self.aget_user_preference(user_id)

            if existing_preference:
                # Update existing preference
                await self.data_context.update_entity_async(
                    UserPreferenceEntity,
                    existing_preference.id,
                    language=preference.language,
                    theme=preference.theme,
                    timezone=preference.timezone,
                    notifications_enabled=preference.notifications_enabled,
                    email_notifications=preference.email_notifications,
                )
                updated_preference = await self.aget_user_preference(user_id)
                if not updated_preference:
                    raise ValueError(f"Failed to retrieve updated user preference for user {user_id}")
                return updated_preference
            else:
                # Create new preference - use converter
                preference_entity = UserPreferenceConverters.convert_user_preference_model_to_entity(preference)
                preference_entity = await self.data_context.add_entity_async(preference_entity)

                # Re-fetch to ensure relationships are properly loaded
                created_preference = await self.aget_user_preference(user_id)
                if not created_preference:
                    raise ValueError(f"Failed to retrieve created user preference for user {user_id}")
                return created_preference

        except Exception as e:
            print(f"Failed to create or update user preference: {e}")
            raise

    async def aget_user_preference(self, user_id: UUID) -> UserPreference | None:
        """Retrieve user preferences by user UUID.

        Args:
            user_id: User's UUID

        Returns:
            UserPreference model if found, None otherwise
        """
        try:
            async with self.data_context.get_session_async() as session:
                stmt = select(UserPreferenceEntity).where(UserPreferenceEntity.user_id == user_id)
                result = await session.execute(stmt)
                preference_entity = result.unique().scalar_one_or_none()
                return UserPreferenceConverters.convert_user_preference_entity_to_model(preference_entity) if preference_entity else None
        except Exception as e:
            print(f"Failed to get user preference: {e}")
            return None

    async def adelete_user_preference(self, user_id: UUID) -> bool:
        """Delete user preferences for a user.

        Args:
            user_id: User's UUID

        Returns:
            True if deleted successfully, False otherwise
        """
        try:
            preference = await self.aget_user_preference(user_id)
            if preference and preference.id:
                await self.data_context.delete_entity_async(UserPreferenceEntity, preference.id)
                return True
            return False
        except Exception as e:
            print(f"Failed to delete user preference: {e}")
            return False
