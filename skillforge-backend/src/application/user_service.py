import logging
from infrastructure.user_repository import UserRepository
from infrastructure.school_repository import SchoolRepository
from models.user import User
from models.school import School
from pydantic import ValidationError
from api_client import StudiLmsApiClient, StudiLmsApiClientException
from api_client.models.studi_lms_user_models import StudiLmsUserInfoResponse
from envvar import EnvHelper
from security.jwt_skillforge_payload import JWTSkillForgePayload


class UserService:
    def __init__(self, user_repository: UserRepository, school_repository: SchoolRepository) -> None:
        self.logger = logging.getLogger(__name__)
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

    async def aretrieve_or_create_user(self, lms_user_id: str, token_payload: JWTSkillForgePayload) -> User | None:
        """Retrieve a user by their internal LMS ID.

        If the user is not found in the database and on-the-fly LMS retrieval is enabled,
        this method will attempt to fetch user information from the LMS API.

        Args:
            lms_user_id: Unique user identifier from LMS
            token_payload: JWT payload containing user information

        Returns:
            User model if found, None otherwise
        """
        user: User | None = None

        # If user not found and on-the-fly retrieval is enabled, try to fetch from LMS API
        if EnvHelper.get_allow_on_the_fly_lms_retrieval_of_unknown_user():
            self.logger.info(f"User {lms_user_id} not found in DB, attempting to retrieve from LMS API")
            try:
                original_token = token_payload.get_original_token()
                school_name = token_payload.get_school_name()
                if original_token and school_name:
                    user_profile = await self.aretrieve_user_infos_from_lms_api(original_token)
                    if user_profile:
                        self.logger.debug(f"Successfully retrieved user profile for {lms_user_id} from LMS API")
                        user = user_profile.convert_to_user_model(school_name)
                        user = await self.acreate_or_update_user(user)
                        self.logger.debug(f"Successfully persisted user {lms_user_id} in database")
            except Exception as e:
                self.logger.warning(f"Failed to retrieve user {lms_user_id} from LMS API: {str(e)}")

        if not user:
            if EnvHelper.get_fails_on_not_found_user():
                raise ValueError(f"No user found corresponding to the internal LMS user id: {lms_user_id}")
            school_name = token_payload.get_school_name() or "Unknown"
            user = User(
                lms_user_id=lms_user_id,
                school=School(name=school_name),
                civility="",
                first_name="",
                last_name="",
                email="tmp@fake.com",
            )
            user = await self.acreate_or_update_user(user)
            self.logger.debug(f"Successfully persisted user {lms_user_id} in database")

        return user

    async def aget_user_by_lms_user_id(self, lms_user_id: str) -> User | None:
        """Retrieve a user by their internal LMS ID.

        If the user is not found in the database and on-the-fly LMS retrieval is enabled,
        this method will NOT attempt to fetch user information from the LMS API.

        Args:
            lms_user_id: Unique user identifier from LMS

        Returns:
            User model if found, None otherwise
        """
        user = await self.user_repository.aget_user_by_lms_user_id(lms_user_id)
        return user

    async def aretrieve_user_infos_from_lms_api(self, jwt_token: str) -> StudiLmsUserInfoResponse | None:
        """Retrieve user profile information from the LMS API.

        This method calls the Studi LMS API /v2/profile/me endpoint to fetch
        detailed user information including personal details, addresses, phone numbers,
        and active promotions.

        Args:
            jwt_token: JWT token for authentication with the LMS API

        Returns:
            StudiLmsUserInfoResponse model if successful, None if retrieval fails

        Raises:
            StudiLmsApiClientException: If the API request fails
        """
        try:
            client = StudiLmsApiClient(jwt_token=jwt_token)
            user_profile = await client.aget_user_infos(jwt_token=jwt_token)
            return user_profile
        except StudiLmsApiClientException as e:
            self.logger.error(f"LMS API error while retrieving user infos: {str(e)}")
            raise
        except Exception as e:
            self.logger.error(f"Unexpected error while retrieving user infos from LMS: {str(e)}")
            raise
