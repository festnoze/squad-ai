import os

# Base directory for the application
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Directory to watch for new transcripts
# Going up one level from app/ to reach the root, then into transcripts
WATCH_DIR = os.path.join(os.path.dirname(BASE_DIR), 'transcripts')

# Directory to move processed transcripts to
ARCHIVE_DIR = os.path.join(os.path.dirname(BASE_DIR), 'transcripts', 'archive')

# Ensure directories exist
os.makedirs(WATCH_DIR, exist_ok=True)
os.makedirs(ARCHIVE_DIR, exist_ok=True)
