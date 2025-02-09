from common_tools.helpers.import_helper import ImportHelper
from common_tools.helpers.txt_helper import txt
import time

prev_value = txt.activate_print
txt.activate_print = True
txt.print("\r\n")

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
txt.print(f"\n> ApiConfig import duration: {time.time() - begin_at:.2f}s.")
txt.activate_print = prev_value

app = ApiConfig.create_app()