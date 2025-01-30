from common_tools.helpers.duration_helper import DurationHelper
from common_tools.helpers.txt_helper import txt

prev_value = txt.activate_print
txt.activate_print = True
DurationHelper.print_all_imports_duration_for_file("src/application/available_service.py")
txt.activate_print = prev_value

from api.api_config import ApiConfig

app = ApiConfig.create_app()