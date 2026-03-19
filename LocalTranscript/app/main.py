import sys
import os

# Add the parent directory to sys.path to allow imports if running directly
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import watcher

if __name__ == "__main__":
    print("Starting Vibe Injector...")
    watcher.start_watching()
