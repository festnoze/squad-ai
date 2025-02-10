from common_tools.helpers.import_helper import ImportHelper
from common_tools.helpers.txt_helper import txt
import time

prev_value = txt.activate_print
txt.activate_print = True
txt.print("\r\n")

files_paths_to_test_for_import = []

ImportHelper.test_api_imports_duration(files_paths_to_test_for_import)

begin_at = time.time()
from api.api_config import ApiConfig
txt.print(f"\n> ApiConfig import duration: {time.time() - begin_at:.2f}s.")
txt.activate_print = prev_value

app = ApiConfig.create_app()