import os
from api.api_config import ApiConfig
import shutil

# # Analyse upon startup the whole project to find all types and generate strong typing
# from strong_types.dynamic_type_analyzer import DynamicTypeAnalyzer
# DynamicTypeAnalyzer.initialize_strong_typing(project_namespace="app.")

# Clear logs and temporary audio files
for folder in ["outputs/logs", "static/outgoing_audio", "static/incoming_audio"]:
    if os.path.exists(folder):
        shutil.rmtree(folder)
    os.makedirs(folder, exist_ok=True)

#from agents.agents_graph import AgentsGraph
#tmp = AgentsGraph(None, None, None, None)

# Start the app
app = ApiConfig.create_app()

# import asyncio
# from speech.speech_to_text import get_speech_to_text_provider
# filename = "C:/Users/e.millerioux/Music/" + "2025_07_30_18_57_23.wav"
# stt = get_speech_to_text_provider()

# async def tmp():
#     stt.transcribe_audio_async(filename)
# transcript = asyncio.to_thread(