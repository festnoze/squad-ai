# /!\ 'load_dotenv()'  Must be done beforehand in the main script!
import os
from dotenv import load_dotenv

class EnvHelper:
    is_env_loaded = False

    @staticmethod
    def _get_custom_env_files():
        return EnvHelper.get_env_variable_value_by_name('CUSTOM_ENV_FILES', load_env=False, fails_if_missing=False)
    
    @staticmethod
    def get_openai_api_key():
        return EnvHelper.get_env_variable_value_by_name('OPENAI_API_KEY')
    
    @staticmethod
    def _get_llms_json() -> str:
        return EnvHelper.get_env_variable_value_by_name('LLMS_JSON')  
    
    @staticmethod
    def _init_load_env():
        if not EnvHelper.is_env_loaded:
            load_dotenv()
            EnvHelper._load_custom_env_files()
            EnvHelper.is_env_loaded = True

    @staticmethod
    def _load_custom_env_files():
        custom_env_files = EnvHelper._get_custom_env_files()
        
        # In case no custom additionnal env. files are defined into a 'CUSTOM_ENV_FILES' key of the '.env' file 
        if not custom_env_files:
            return 
        
        custom_env_filenames = [filename.strip() for filename in custom_env_files.split(",")]
        for custom_env_filename in custom_env_filenames:
            if not os.path.exists(custom_env_filename):
                raise FileNotFoundError(f"/!\\ Environment file: '{custom_env_filename}' was not found at the project root.")
            load_dotenv(custom_env_filename)
    
    @staticmethod
    def get_env_variable_value_by_name(variable_name: str, load_env=True, fails_if_missing=True) -> str:
        if variable_name not in os.environ:
            if load_env:
                EnvHelper._init_load_env()
            variable_value: str = os.getenv(variable_name)
            if not variable_value:
                if fails_if_missing:
                    raise ValueError(f'Variable named: "{variable_name}" is not set in the environment')
                else:
                    return None
            os.environ[variable_name] = variable_value            
        return os.environ[variable_name]
    
    def _get_llm_env_variables(skip_commented_lines:bool = True):
        return file.get_as_yaml('.llm.env.yaml', skip_commented_lines)
    