from common_tools.helpers.import_helper import ImportHelper
import time
import logging

logger = logging.getLogger(__name__)

files_paths_to_test_for_import = [
    # "C:/Dev/IA/CommonTools/common_tools/rag/rag_service.py",
    # "C:/Dev/IA/CommonTools/common_tools/rag/rag_ingestion_pipeline/rag_ingestion_pipeline.py",
    # "C:/Dev/IA/CommonTools/common_tools/rag/rag_inference_pipeline/rag_inference_pipeline.py",
    # "src/application/available_service.py",
    # "src/api/api_config.py",
]
ImportHelper.test_api_imports_duration(files_paths_to_test_for_import)

begin_at = time.time()
from api.api_config import ApiConfig
logger.info(f"> ApiConfig import duration: {time.time() - begin_at:.2f}s.")

app = ApiConfig.create_app()