from common_tools.helpers.env_helper import EnvHelper
from common_tools.rag.rag_service import RagService

class RagServiceFactory:
    @staticmethod
    def build_from_env_config(vector_db_base_path:str = None, documents_json_filename:str = None) -> RagService:
        embedding_model = EnvHelper.get_embedding_model()
        llms_or_info    = EnvHelper.get_built_llms_infos()
        vector_db_type  = EnvHelper.get_vector_db_type()
        vector_db_name  = EnvHelper.get_vector_db_name()

        return RagService(
                llms_or_info= llms_or_info,
                embedding_model= embedding_model,
                vector_db_base_path= vector_db_base_path,
                vector_db_type= vector_db_type,
                vector_db_name= vector_db_name,
                documents_json_filename= documents_json_filename
        )