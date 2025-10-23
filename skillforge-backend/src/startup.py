import os
import sys
import shutil
from pathlib import Path

# Add src directory to Python path to allow importing from src/
# This ensures the app can run from make, Docker, or any other context
src_path = Path(__file__).parent
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

from common_tools.helpers.txt_helper import txt  # type: ignore[import-untyped]
from envvar import EnvHelper

# # Analyse upon startup the whole project to find all types and generate strong typing
# from strong_types.dynamic_type_analyzer import DynamicTypeAnalyzer
# DynamicTypeAnalyzer.initialize_strong_typing(project_namespace="app.")

# Clear logs and temporary audio files
if EnvHelper.get_remove_logs_upon_startup():
    for folder in ["outputs/logs"]:
        if os.path.exists(folder):
            shutil.rmtree(folder)
        os.makedirs(folder, exist_ok=True)

# Start the app
from api_config import ApiConfig
import dependency_injection_config  # Initialize DI container  # noqa: F401

txt.activate_print = True

app = ApiConfig.create_app()
