# /!\ 'load_dotenv()'  Must be done beforehand in the main script!
import json
import os
from dotenv import load_dotenv
#
from common_tools.helpers.file_helper import file
from common_tools.models.llm_info import LlmInfo
from common_tools.models.vector_db_type import VectorDbType
from common_tools.models.embedding_model import EmbeddingModel
from common_tools.models.langchain_adapter_type import LangChainAdapterType

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
    def get_openrouter_api_key():
        return EnvHelper.generic_get_env_variable_value_by_name('OPENROUTER_API_KEY')

    @staticmethod
    def get_openrouter_base_url():
        return EnvHelper.generic_get_env_variable_value_by_name('OPENROUTER_BASE_URL')
    
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
    def get_BM25_storage_as_db_sparse_vectors() -> bool:
        BM25_storage_as_db_sparse_vectors_str = EnvHelper.generic_get_env_variable_value_by_name('BM25_STORAGE_AS_DB_SPARSE_VECTORS')
        if BM25_storage_as_db_sparse_vectors_str.lower() == 'false':
            return False
        elif BM25_storage_as_db_sparse_vectors_str.lower() == 'true':
            return True
        else:
            raise ValueError(f"Invalid value for 'BM25_STORAGE_AS_DB_SPARSE_VECTORS': '{BM25_storage_as_db_sparse_vectors_str}' (cannot be converted to a boolean)")

    @staticmethod
    def get_is_common_db_for_sparse_and_dense_vectors() -> bool:
        is_common_db_for_sparse_and_dense_vectors_str = EnvHelper.generic_get_env_variable_value_by_name('IS_COMMON_DB_FOR_SPARSE_AND_DENSE_VECTORS')
        if is_common_db_for_sparse_and_dense_vectors_str.lower() == 'false':
            return False
        elif is_common_db_for_sparse_and_dense_vectors_str.lower() == 'true':
            return True
        else:
            raise ValueError(f"Invalid value for 'IS_COMMON_DB_FOR_SPARSE_AND_DENSE_VECTORS': '{is_common_db_for_sparse_and_dense_vectors_str}' (cannot be converted to a boolean)")

    @staticmethod
    def get_llms_infos_from_env_config(skip_commented_lines:bool = True) -> list[LlmInfo]:
        yaml_env_variables = EnvHelper._get_llm_env_variables(skip_commented_lines)
        if not 'Llms_Temperature' in yaml_env_variables:
            raise ValueError("Missing 'Llms_Temperature' key in the yaml environment file")
        llms_temp = yaml_env_variables['Llms_Temperature']
        if not 'Llm_infos' in yaml_env_variables:
            raise ValueError("Missing 'Llm_infos' key in the yaml environment file")
        llms_list = yaml_env_variables['Llm_infos']
        if not 'Llms_order' in yaml_env_variables:
            raise ValueError("Missing 'Llms_order' key in the yaml environment file")
        llms_order = yaml_env_variables['Llms_order']

        # Re-order llms based on specified order
        try:
            ordered_llms_list = [llms_list[i - 1] for i in llms_order]
            if len(llms_list) > len(ordered_llms_list):
                ordered_llms_list.extend([llm for llm in llms_list if llm not in ordered_llms_list])
        except IndexError:
            raise ValueError("The 'Llms_order' env variable list contains invalid indices.")

        try:
            llms_infos = []
            for llm_dict in ordered_llms_list:
                llm_info = LlmInfo.factory_from_dict(llm_dict, llms_temp)
                llms_infos.append(llm_info)
            return llms_infos
        
        except json.JSONDecodeError as e:
            raise ValueError(f"Error parsing Llm_infos value: {e}")
        except KeyError as e:
            raise ValueError(f"Missing key in Llm_infos: {e}")
        except Exception as e:
            raise ValueError(f"Error parsing Llm_infos value: {e}")

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
        
        custom_env_filenames = [filename.strip() for filename in custom_env_files.split(",")]
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
    
    def _get_llm_env_variables(skip_commented_lines:bool = True):
        return file.get_as_yaml('.llm.env.yaml', skip_commented_lines)
    