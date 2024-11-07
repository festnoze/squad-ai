import os
import json
from dotenv import load_dotenv

from common_tools.models.embedding import EmbeddingModel
from common_tools.models.langchain_adapter_type import LangChainAdapterType
from common_tools.models.llm_info import LlmInfo

#load_dotenv() # Must be done beforehand in the main script
class ConfigHelper:
    @staticmethod
    def get_embedding_model_from_env():
        model_name = os.getenv('EMBEDDING_MODEL')
        if not model_name:
            raise ValueError("EMBEDDING_MODEL is not set in the environment")
        try:
            return EmbeddingModel[model_name]
        except KeyError:
            raise ValueError(f"Invalid EMBEDDING_MODEL: '{model_name}'")
    
    @staticmethod
    def get_vector_db_type_from_env():
        vector_db_type = os.getenv('VECTOR_DB_TYPE')
        if not vector_db_type:
            raise ValueError("VECTOR_DB_TYPE is not set in the environment")
        return vector_db_type
    
    @staticmethod
    def get_llms_from_env():
        llms_list_json = os.getenv('LLMS_JSON')
        if not llms_list_json:
            raise ValueError("LLMS_JSON is not set in the environment")
        try:
            # Remove surrounding single quotes if present
            llms_list_json = llms_list_json.strip('\'"')
            llms_list = json.loads(llms_list_json)
            llms = []
            for llm_dict in llms_list:
                llm_type_str = llm_dict['type']
                model = llm_dict['model']
                timeout = llm_dict['timeout']
                temperature = llm_dict['temperature']
                # Map the type string to LangChainAdapterType enum
                llm_type_enum = LangChainAdapterType[llm_type_str]
                llm_info = LlmInfo(type=llm_type_enum, model=model, timeout=timeout, temperature=temperature)
                llms.append(llm_info)
            return llms
        except json.JSONDecodeError as e:
            raise ValueError(f"Error parsing LLMS_JSON: {e}")
        except KeyError as e:
            raise ValueError(f"Missing key in LLMS_JSON: {e}")


