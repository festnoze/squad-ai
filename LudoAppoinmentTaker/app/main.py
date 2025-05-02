import os
from dotenv import load_dotenv
from fastapi import FastAPI
from endpoints import router as api_router

# Load environment variables early
load_dotenv()

# Explicitly set Google Credentials path if needed (adapt path as necessary)
# Assumes credentials file is in the project root, relative to this file in app/
project_root = os.path.dirname(os.path.dirname(__file__))
cred_filename = "secrets/studi-ai-454216-185215ccea8c.json" # Consider getting this filename from env var
credentials_path = os.path.join(project_root, os.getenv("GOOGLE_APPLICATION_CREDENTIALS_FILENAME", cred_filename))

if os.path.exists(credentials_path):
    os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = credentials_path
    print(f"Set GOOGLE_APPLICATION_CREDENTIALS to: {credentials_path}") # Added print for confirmation
else:
    # Consider logging a warning if the file is expected but not found
    print(f"Warning: Google credentials file not found at {credentials_path}")

app = FastAPI()
app.include_router(api_router)