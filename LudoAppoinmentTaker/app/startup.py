import os
from app.api_config import ApiConfig

# Empty logs and temporary audio files
os.system("rm -rf outputs/logs/*")
os.system("rm -rf static/audio/*")

app = ApiConfig.create_app()