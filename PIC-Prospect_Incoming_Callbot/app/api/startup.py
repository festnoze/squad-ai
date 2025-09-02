import os
import shutil
from api.api_config import ApiConfig
from utils.envvar import EnvHelper
from utils.latency_config import latency_config

# # Analyse upon startup the whole project to find all types and generate strong typing
# from strong_types.dynamic_type_analyzer import DynamicTypeAnalyzer
# DynamicTypeAnalyzer.initialize_strong_typing(project_namespace="app.")

# Clear logs and temporary audio files
if EnvHelper.get_remove_logs_upon_startup():
    for folder in ["outputs/logs", "static/outgoing_audio", "static/incoming_audio"]:
        if os.path.exists(folder):
            shutil.rmtree(folder)
        os.makedirs(folder, exist_ok=True)

# Initialize latency monitoring system
print("Initializing latency monitoring system...")
latency_config.initialize_latency_system()

# Start the app
app = ApiConfig.create_app()
