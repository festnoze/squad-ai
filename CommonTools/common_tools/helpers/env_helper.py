# /!\ 'load_dotenv()'  Must be done beforehand in the main script!
import json
import os
from dotenv import load_dotenv

from common_tools.models.langchain_adapter_type import LangChainAdapterType
from common_tools.models.llm_info import LlmInfo
from common_tools.models.vector_db_type import VectorDbType
from common_tools.models.embedding_model import EmbeddingModel

class EnvHelper:
    is_env_loaded = False

    @staticmethod
    def get_custom_env_files():
        return EnvHelper.generic_get_env_variable_value_by_name('CUSTOM_ENV_FILES')
    
    @staticmethod
    def get_openai_api_key():
        return EnvHelper.generic_get_env_variable_value_by_name('OPENAI_API_KEY')
    
    @staticmethod
    def get_anthropic_api_key():
        return EnvHelper.generic_get_env_variable_value_by_name('ANTHROPIC_API_KEY')
    
    @staticmethod
    def get_groq_api_key():
        return EnvHelper.generic_get_env_variable_value_by_name('GROQ_API_KEY')

    @staticmethod
    def get_pinecone_api_key():
        return EnvHelper.generic_get_env_variable_value_by_name('PINECONE_API_KEY')

    @staticmethod
    def get_pinecone_environment():
        return EnvHelper.generic_get_env_variable_value_by_name('PINECONE_ENVIRONMENT')
    
    @staticmethod
    def get_embedding_model() -> EmbeddingModel:
        embedding_model_value = EnvHelper.generic_get_env_variable_value_by_name('EMBEDDING_MODEL')
        try:
            embedding_model = EmbeddingModel[embedding_model_value]
        except KeyError:
            raise ValueError(f"Invalid value for 'EMBEDDING_MODEL': '{embedding_model_value}' (cannot be found within 'EmbeddingModel' allowed values)")
        return embedding_model
    
    @staticmethod
    def get_vector_db_type() -> VectorDbType:
        vector_db_type_str = EnvHelper.generic_get_env_variable_value_by_name('VECTOR_DB_TYPE')
        try:
            vector_db_type = VectorDbType(vector_db_type_str)
        except KeyError:
            raise ValueError(f"Invalid value for 'VECTOR_DB_TYPE': '{vector_db_type_str}' (cannot be found within 'VectorDbType' allowed values)")
        return vector_db_type

    @staticmethod
    def get_vector_db_name():
        return EnvHelper.generic_get_env_variable_value_by_name('VECTOR_DB_NAME')
    
    @staticmethod
    def get_pinecone_native_hybrid_search() -> bool:
        pinecone_native_hybrid_search_str = EnvHelper.generic_get_env_variable_value_by_name('PINECONE_NATIVE_HYBRID_SEARCH')
        if pinecone_native_hybrid_search_str.lower() == 'false':
            return False
        elif pinecone_native_hybrid_search_str.lower() == 'true':
            return True
        else:
            raise ValueError(f"Invalid value for 'PINECONE_NATIVE_HYBRID_SEARCH': '{pinecone_native_hybrid_search_str}' (cannot be converted to a boolean)")

    @staticmethod
    def get_built_llms_infos() -> list[LlmInfo]:
        llms_list_json = EnvHelper._get_llms_json()
        temperature = EnvHelper._get_llms_temperature()

        try:
            llms_list_json = llms_list_json.strip('\'"') # Remove surrounding single quotes
            llms_list = json.loads(llms_list_json)
            llms = []
            for llm_dict in llms_list:
                llm_type_str = llm_dict['type']
                model = llm_dict['model']
                timeout = llm_dict['timeout']
                llm_type_enum = LangChainAdapterType[llm_type_str]
                llm_info = LlmInfo(type=llm_type_enum, model=model, timeout=timeout, temperature=temperature)
                llms.append(llm_info)
            return llms
        
        except json.JSONDecodeError as e:
            raise ValueError(f"Error parsing LLMS_JSON value: {e}")
        except KeyError as e:
            raise ValueError(f"Missing key in LLMS_JSON: {e}")
    
    @staticmethod
    def _get_llms_temperature() -> float:
        temperature_str = EnvHelper.generic_get_env_variable_value_by_name('LLMS_TEMPERATURE')
        try:
            temperature = float(temperature_str)
        except ValueError:
            raise ValueError("'LLMS_TEMPERATURE' was found in the environment, but its value is not a valid float")
        return temperature

    @staticmethod
    def _get_llms_json() -> str:
        return EnvHelper.generic_get_env_variable_value_by_name('LLMS_JSON')  
    
    @staticmethod
    def _init_load_env():
        if not EnvHelper.is_env_loaded:
            load_dotenv()
            EnvHelper._load_custom_env_files()
            EnvHelper.is_env_loaded = True


    def _load_custom_env_files():
        custom_env_files = EnvHelper.get_custom_env_files()
        
        # In case no custom additionnal env. files are defined into a 'CUSTOM_ENV_FILES' key of the '.env' file 
        if not custom_env_files:
            return 
        
        custom_env_filenames = [file.strip() for file in custom_env_files.split(",")]
        for custom_env_filename in custom_env_filenames:
            if not os.path.exists(custom_env_filename):
                raise FileNotFoundError(f"/!\\ Environment file: '{custom_env_filename}' was not found at the project root.")
            load_dotenv(custom_env_filename)
    
    @staticmethod
    def generic_get_env_variable_value_by_name(variable_name: str) -> str:
        if not variable_name in os.environ:
            EnvHelper._init_load_env()
            variable_value: str = os.getenv(variable_name)
            if not variable_value:
                raise ValueError(f'Variable named: "{variable_name}" is not set in the environment')
            os.environ[variable_name] = variable_value            
        return os.environ[variable_name]
    