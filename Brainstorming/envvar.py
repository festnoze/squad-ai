# /!\ 'load_dotenv()'  Must be done beforehand in the main script!
import os
from pathlib import Path
from typing import Any
from dotenv import load_dotenv
import json


class EnvVar:
    is_env_loaded = False


    @staticmethod
    def get_openai_api_key() -> str | None:
        return EnvVar._get_env_variable_value_by_name('OPENAI_API_KEY')
    
    @staticmethod
    def get_google_api_key() -> str | None:
        return EnvVar._get_env_variable_value_by_name("GOOGLE_API_KEY", fails_if_missing=False)

    @staticmethod
    def get_google_credentials_filepath_and_add_to_env(project_root_path: str) -> str:
        google_credentials_filepath = EnvVar._get_env_variable_value_by_name("GOOGLE_CREDENTIALS_FILEPATH") or ""
        
        # Clean secrets path and google credentials filepath
        project_root_path = project_root_path.replace("\\", "/")
        if project_root_path.endswith("/"):
            project_root_path = project_root_path[:-1]

        google_credentials_absolute_path = os.path.join(project_root_path, google_credentials_filepath)
        google_credentials_absolute_path = google_credentials_absolute_path.replace("\\", "/")
        if "/secrets/secrets" in google_credentials_absolute_path:
            google_credentials_absolute_path = google_credentials_absolute_path.replace("/secrets/secrets", "/secrets")

        if os.path.exists(google_credentials_absolute_path):
            os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = google_credentials_absolute_path
        else:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"EnvHelper: Google credentials file not found at: '{google_credentials_absolute_path}'.")
            raise ValueError(f"Google credentials file not found at: '{google_credentials_absolute_path}'.")
        return google_credentials_absolute_path


    @staticmethod
    def load_all_env_var(force_load_from_env_file: bool = False) -> None:
        if not EnvVar.is_env_loaded or force_load_from_env_file:
            env_file = Path(".env")
            if env_file.exists():
                load_dotenv()
            #EnvVar._load_custom_env_files()
            EnvVar.is_env_loaded = True

    @staticmethod
    def _get_env_variable_value_by_name(variable_name: str, load_env: bool = True, fails_if_missing: bool = True, remove_comments: bool = True, force_load_from_env_file: bool = False) -> str | None:
        if variable_name not in os.environ:
            if load_env:
                EnvVar.load_all_env_var()
            variable_value: str | None = os.getenv(variable_name, None)
            if not variable_value:
                if fails_if_missing:
                    raise Exception(f"Failing to load env. var. {variable_name}")
                else:
                    return None
            os.environ[variable_name] = variable_value

        value = os.environ[variable_name]
        if remove_comments and "#" in value:
            value = value.split("#")[0].strip()

        return value
