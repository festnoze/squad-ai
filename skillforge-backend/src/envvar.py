# /!\ 'load_dotenv()'  Must be done beforehand in the main script!
import os
from pathlib import Path
from typing import Any
from dotenv import load_dotenv


class EnvHelper:
    is_env_loaded = False

    @staticmethod
    def get_openai_api_key() -> str:
        return EnvHelper._get_env_variable_value_by_name("OPENAI_API_KEY") or ""

    @staticmethod
    def get_company_name() -> str:
        return EnvHelper._get_env_variable_value_by_name("COMPANY_NAME", fails_if_missing=False) or "Studi"

    @staticmethod
    def get_admin_api_keys() -> list[str]:
        """Get the list of allowed API keys for admin endpoints"""
        keys_str = EnvHelper._get_env_variable_value_by_name("ADMIN_API_KEYS", fails_if_missing=False)
        return [key.strip() for key in keys_str.split(",")] if keys_str else []

    @staticmethod
    def is_valid_admin_api_key(api_key: str) -> bool:
        """Check if the provided API key is valid for admin operations"""
        allowed_keys = EnvHelper.get_admin_api_keys()
        return api_key in allowed_keys and len(allowed_keys) > 0

    @staticmethod
    def load_all_env_var(force_load_from_env_file: bool = False) -> None:
        if not EnvHelper.is_env_loaded or force_load_from_env_file:
            env_file = Path(".env")
            if not env_file.exists():
                EnvHelper.handle_missing_dotenv_file()
            else:
                load_dotenv()
            EnvHelper._load_custom_env_files()
            EnvHelper.is_env_loaded = True

    @staticmethod
    def handle_missing_dotenv_file(logger: Any = None, e: Exception | None = None) -> None:
        if not logger:
            logger.warning(f"Missing '.env' file: {e}")
        if EnvHelper.get_environment() == "development":
            if e:
                raise e
            else:
                raise FileNotFoundError("❌ '.env' file or custom env file is missing and is needed for 'development' environment. Please create it by copying: '.env.sample'.")

    @staticmethod
    def get_remove_logs_upon_startup() -> bool:
        value = EnvHelper._get_env_variable_value_by_name("REMOVE_LOGS_UPON_STARTUP", fails_if_missing=False)
        return value is not None and value.lower() == "true"

    @staticmethod
    def get_serve_documentation() -> bool:
        """
        Get whether to serve MkDocs documentation alongside the API.

        Returns:
            bool: True if documentation should be served at /docs-site/, False otherwise.
                  Defaults to True for development, False for production.
        """
        value = EnvHelper._get_env_variable_value_by_name("SERVE_DOCUMENTATION", fails_if_missing=False)
        if value is not None:
            return value.lower() == "true"

        # Default behavior: serve docs in development, not in production
        environment = EnvHelper.get_environment()
        return environment.lower() == "development"

    @staticmethod
    def get_aicommontools_local_path() -> str:
        """
        Get the local path to AICommonTools repository for development installation.

        Returns:
            str: Local filesystem path to AICommonTools (e.g., C:/Dev/IA/AzureDevOps/ai-commun-tools)
        """
        return EnvHelper._get_env_variable_value_by_name("AICOMMONTOOLS_LOCAL_PATH", fails_if_missing=False) or "C:/Dev/IA/AzureDevOps/ai-commun-tools"

    @staticmethod
    def get_azure_artifact_feed_url() -> str:
        """
        Get the Azure Artifacts feed URL for production AICommonTools installation.

        Returns:
            str: Azure Artifacts PyPI feed URL
        """
        return EnvHelper._get_env_variable_value_by_name("AZURE_ARTIFACT_FEED_URL", fails_if_missing=False) or ""

    @staticmethod
    def get_azure_artifact_feed_token() -> str:
        """
        Get the Azure Artifacts Personal Access Token (PAT) for authentication.

        Returns:
            str: Azure DevOps PAT token with Packaging Read permissions
        """
        return EnvHelper._get_env_variable_value_by_name("AZURE_ARTIFACT_FEED_TOKEN", fails_if_missing=False) or ""

    @staticmethod
    def get_aicommontools_version() -> str:
        """
        Get the specific version of AICommonTools to install in production.

        Returns:
            str: Version string (e.g., "1.0.0") or empty string for latest version
        """
        return EnvHelper._get_env_variable_value_by_name("AICOMMONTOOLS_VERSION", fails_if_missing=False) or ""

    @staticmethod
    def get_common_tools_install_mode() -> str:
        """
        Get the installation mode/extras for common_tools library.

        Returns:
            str: Comma-separated list of extras (e.g., "database,qdrant") or "full" for all dependencies.
                 Defaults to "database" for skillforge backend.
        """
        return EnvHelper._get_env_variable_value_by_name("COMMON_TOOLS_INSTALL_MODE", fails_if_missing=False) or "database"

    @staticmethod
    def get_environment() -> str:
        """
        Get the current environment mode.

        Returns:
            str: Environment mode ("development" or "production"), defaults to "development"
        """
        value = EnvHelper._get_env_variable_value_by_name("ENVIRONMENT", fails_if_missing=False)
        return value.lower() if value else "development"

    @staticmethod
    def get_postgres_username() -> str:
        """
        Get the PostgreSQL database username.

        Returns:
            str: Database username, defaults to "postgres"
        """
        return EnvHelper._get_env_variable_value_by_name("POSTGRES_USERNAME", fails_if_missing=False) or "postgres"

    @staticmethod
    def get_postgres_password() -> str:
        """
        Get the PostgreSQL database password.

        Returns:
            str: Database password, defaults to "admin"
        """
        return EnvHelper._get_env_variable_value_by_name("POSTGRES_PASSWORD", fails_if_missing=False) or "admin"

    @staticmethod
    def get_postgres_host() -> str:
        """
        Get the PostgreSQL database host with port.

        Returns:
            str: Database host:port (e.g., "localhost:5432"), defaults to "localhost:5432"
        """
        return EnvHelper._get_env_variable_value_by_name("POSTGRES_HOST", fails_if_missing=False) or "localhost:5432"

    @staticmethod
    def get_postgres_database_name() -> str:
        """
        Get the PostgreSQL database name.

        Returns:
            str: Database name, defaults to "skillforge_dev"
        """
        return EnvHelper._get_env_variable_value_by_name("POSTGRES_DATABASE_NAME", fails_if_missing=False) or "skillforge_dev"

    @staticmethod
    def get_jwt_secret_key() -> str:
        """
        Get the JWT secret key for token signing/verification.

        Returns:
            str: JWT secret key, defaults to "dev-secret-key-change-in-production"
        """
        return EnvHelper._get_env_variable_value_by_name("JWT_SECRET_KEY", fails_if_missing=False) or ""

    @staticmethod
    def get_jwt_algorithm() -> str:
        """
        Get the JWT algorithm for token encoding/decoding.

        Returns:
            str: JWT algorithm (e.g., "HS256", "RS256"), defaults to "HS256"
        """
        return EnvHelper._get_env_variable_value_by_name("JWT_ALGORITHM", fails_if_missing=False) or "HS256"

    @staticmethod
    def get_jwt_verify_signature() -> bool:
        """
        Get whether to verify JWT token signatures.

        Returns:
            bool: True if signature verification is enabled, False otherwise.
                  Defaults to True for security.
        """
        value = EnvHelper._get_env_variable_value_by_name("JWT_VERIFY_SIGNATURE", fails_if_missing=False)
        if value is not None:
            return value.lower() == "true"
        return True  # Default to True for security

    @staticmethod
    def get_dev_token() -> str | None:
        """
        Get the development default token for testing.
        Only used when ENVIRONMENT=development and no token is provided.

        Returns:
            str | None: Development token or None if not set
        """
        return EnvHelper._get_env_variable_value_by_name("DEV_TOKEN", fails_if_missing=False)

    @staticmethod
    def get_allow_on_the_fly_lms_retrieval_of_unknown_user() -> bool:
        """
        Get whether to allow on-the-fly retrieval from LMS for unknown users.

        Returns:
            bool: True if on-the-fly LMS retrieval is allowed for unknown users, False otherwise.
                  Defaults to True.
        """
        value = EnvHelper._get_env_variable_value_by_name("ALLOW_ON_THE_FLY_LMS_RETRIEVAL_OF_UNKNOWN_USER", fails_if_missing=False)
        if value is not None:
            return value.lower() == "true"
        return True  # Default to enabled

    @staticmethod
    def get_allow_on_the_fly_lms_retrieval_of_unknown_course_hierarchy() -> bool:
        """
        Get whether to allow on-the-fly retrieval from LMS for unknown course hierarchies.

        Returns:
            bool: True if on-the-fly LMS retrieval is allowed for unknown course hierarchies, False otherwise.
                  Defaults to True.
        """
        value = EnvHelper._get_env_variable_value_by_name("ALLOW_ON_THE_FLY_LMS_RETRIEVAL_OF_UNKNOWN_COURSE_HIERARCHY", fails_if_missing=False)
        if value is not None:
            return value.lower() == "true"
        return True  # Default to enabled

    @staticmethod
    def get_allow_on_the_fly_lms_retrieval_of_unknown_lesson_content() -> bool:
        """
        Get whether to allow on-the-fly retrieval from LMS for unknown lesson content.

        Returns:
            bool: True if on-the-fly LMS retrieval is allowed for unknown lesson content, False otherwise.
                  Defaults to False.
        """
        value = EnvHelper._get_env_variable_value_by_name("ALLOW_ON_THE_FLY_LMS_RETRIEVAL_OF_UNKNOWN_LESSON_CONTENT", fails_if_missing=False)
        if value is not None:
            return value.lower() == "true"
        return False  # Default to disabled

    @staticmethod
    def get_fails_on_not_found_user() -> bool:
        """
        Get whether to fail when a user is not found.

        Returns:
            bool: True if should fail on not found user, False otherwise.
                  Defaults to False.
        """
        value = EnvHelper._get_env_variable_value_by_name("FAILS_ON_NOT_FOUND_USER", fails_if_missing=False)
        if value is not None:
            return value.lower() == "true"
        return False  # Default to False

    @staticmethod
    def get_fails_on_not_found_course_hierarchy() -> bool:
        """
        Get whether to fail when course hierarchy is not found.

        Returns:
            bool: True if should fail on not found course hierarchy, False otherwise.
                  Defaults to False.
        """
        value = EnvHelper._get_env_variable_value_by_name("FAILS_ON_NOT_FOUND_COURSE_HIERARCHY", fails_if_missing=False)
        if value is not None:
            return value.lower() == "true"
        return False  # Default to False

    @staticmethod
    def get_fails_on_not_found_lesson_content() -> bool:
        """
        Get whether to fail when lesson content is not found.

        Returns:
            bool: True if should fail on not found lesson content, False otherwise.
                  Defaults to False.
        """
        value = EnvHelper._get_env_variable_value_by_name("FAILS_ON_NOT_FOUND_LESSON_CONTENT", fails_if_missing=False)
        if value is not None:
            return value.lower() == "true"
        return False  # Default to False

    @staticmethod
    def get_other_api_base_url() -> str:
        """
        Get the base URL for the Studi Parcours API.

        Returns:
            str: Base URL for Parcours API (e.g., "https://api.studi.fr")
        """
        return EnvHelper._get_env_variable_value_by_name("OTHERS_API_BASE_URL", fails_if_missing=False) or "https://api.studi.fr"

    @staticmethod
    def get_lms_api_base_url() -> str:
        """
        Get the base URL for the Studi LMS API.

        Returns:
            str: Base URL for LMS API (e.g., "https://app.studi.fr/ws/api"), defaults to "https://app.studi.fr/ws/api"
        """
        return EnvHelper._get_env_variable_value_by_name("LMS_API_BASE_URL", fails_if_missing=False) or "https://app.studi.fr/ws/api"

    @staticmethod
    def get_redis_host() -> str:
        """
        Get the Redis server host.

        Returns:
            str: Redis host address, defaults to "localhost"
        """
        return EnvHelper._get_env_variable_value_by_name("REDIS_HOST", fails_if_missing=False) or "localhost"

    @staticmethod
    def get_redis_port() -> int:
        """
        Get the Redis server port.

        Returns:
            int: Redis port number, defaults to 6379
        """
        port_str = EnvHelper._get_env_variable_value_by_name("REDIS_PORT", fails_if_missing=False)
        return int(port_str) if port_str else 6379

    @staticmethod
    def get_redis_db() -> int:
        """
        Get the Redis database number.

        Returns:
            int: Redis database index (0-15), defaults to 0
        """
        db_str = EnvHelper._get_env_variable_value_by_name("REDIS_DB", fails_if_missing=False)
        return int(db_str) if db_str else 0

    @staticmethod
    def get_redis_password() -> str | None:
        """
        Get the Redis server password.

        Returns:
            str | None: Redis password or None if not set
        """
        password = EnvHelper._get_env_variable_value_by_name("REDIS_PASSWORD", fails_if_missing=False)
        return password if password and password.strip() else None

    @staticmethod
    def get_redis_ttl() -> int:
        """
        Get the default Redis cache TTL (time-to-live) in seconds.

        Returns:
            int: Cache TTL in seconds, defaults to 3600 (1 hour)
        """
        ttl_str = EnvHelper._get_env_variable_value_by_name("REDIS_TTL", fails_if_missing=False)
        return int(ttl_str) if ttl_str else 3600

    @staticmethod
    def get_redis_enabled() -> bool:
        """
        Get whether Redis caching is enabled.

        Returns:
            bool: True if Redis caching is enabled, False otherwise.
                  Defaults to True.
        """
        value = EnvHelper._get_env_variable_value_by_name("REDIS_ENABLED", fails_if_missing=False)
        if value is not None:
            return value.lower() == "true"
        return True  # Default to enabled

    @staticmethod
    def get_lms_type() -> str:
        """
        Get the Learning Management System (LMS) type ("studi", "blackboard", etc.), defaults to "studi"
        """
        value = EnvHelper._get_env_variable_value_by_name("LMS_TYPE", fails_if_missing=False)
        if value is not None:
            return value.lower()
        return "studi"  # Default LMS type to studi

    ########################
    ### Internal methods ###
    ########################

    @staticmethod
    def _get_custom_env_files() -> str:
        return EnvHelper._get_env_variable_value_by_name("CUSTOM_ENV_FILES", load_env=False, fails_if_missing=False) or ""

    @staticmethod
    def _get_llms_json() -> str:
        return EnvHelper._get_env_variable_value_by_name("LLMS_JSON") or ""

    @staticmethod
    def _load_custom_env_files() -> None:
        custom_env_files = EnvHelper._get_custom_env_files()

        # In case no custom additionnal env. files are defined into a 'CUSTOM_ENV_FILES' key of the '.env' file
        if not custom_env_files:
            return

        custom_env_filenames = [filename.strip() for filename in custom_env_files.split(",")]
        for custom_env_filename in custom_env_filenames:
            if not os.path.exists(custom_env_filename):
                EnvHelper.handle_missing_dotenv_file()
            else:
                load_dotenv(custom_env_filename)

    @staticmethod
    def _get_env_variable_value_by_name(variable_name: str, load_env: bool = True, fails_if_missing: bool = True, remove_comments: bool = True, force_load_from_env_file: bool = False) -> str | None:
        if variable_name not in os.environ:
            if load_env:
                EnvHelper.load_all_env_var()
            variable_value: str | None = os.getenv(variable_name, None)
            if not variable_value:
                if fails_if_missing:
                    raise ValueError(f'Variable named: "{variable_name}" is not set in the environment')
                else:
                    return None
            os.environ[variable_name] = variable_value

        value = os.environ[variable_name]
        if remove_comments and "#" in value:
            value = value.split("#")[0].strip()

        return value
