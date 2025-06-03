import os
from app.api_config import ApiConfig
import shutil

# Clear logs and temporary audio files
for folder in ["outputs/logs", "static/audio"]:
    if os.path.exists(folder):
        shutil.rmtree(folder)
    os.makedirs(folder, exist_ok=True)

# Start the app
app = ApiConfig.create_app()