import os
from api.api_config import ApiConfig
import shutil

# # Analyse upon startup the whole project to find all types and generate strong typing
# from strong_types.dynamic_type_analyzer import DynamicTypeAnalyzer
# DynamicTypeAnalyzer.initialize_strong_typing(project_namespace="app.")

# Clear logs and temporary audio files
for folder in ["outputs/logs", "static/audio"]:
    if os.path.exists(folder):
        shutil.rmtree(folder)
    os.makedirs(folder, exist_ok=True)

#from agents.agents_graph import AgentsGraph
#tmp = AgentsGraph(None, None, None, None)

# Start the app
app = ApiConfig.create_app()