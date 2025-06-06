import os
from app.api_config import ApiConfig
import shutil

#import sys
# project_namespace = "app"
# for module_name in list(sys.modules.keys()):
#     if project_namespace and module_name.startswith(project_namespace):
#         print(module_name)

from strong_types.dynamic_type_analyzer import DynamicTypeAnalyzer
DynamicTypeAnalyzer.initialize_strong_typing(project_namespace="app")

# Clear logs and temporary audio files
for folder in ["outputs/logs", "static/audio"]:
    if os.path.exists(folder):
        shutil.rmtree(folder)
    os.makedirs(folder, exist_ok=True)

# Start the app
app = ApiConfig.create_app()