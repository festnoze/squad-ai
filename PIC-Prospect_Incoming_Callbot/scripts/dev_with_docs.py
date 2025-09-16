#!/usr/bin/env python3
"""
Development script to run both API and documentation server simultaneously.
"""
import asyncio
import subprocess
import sys
import signal
import time
from pathlib import Path


def start_mkdocs_serve():
    """Start MkDocs serve process"""
    project_root = Path(__file__).parent.parent
    print("🚀 Starting MkDocs serve on http://127.0.0.1:8001...")

    return subprocess.Popen(
        ["mkdocs", "serve", "--dev-addr", "127.0.0.1:8001"],
        cwd=project_root,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )


def start_api_server():
    """Start FastAPI server"""
    print("🚀 Starting API server on http://127.0.0.1:8344...")
    return subprocess.Popen([
        "uvicorn", "app.api.startup:app",
        "--reload",
        "--host", "127.0.0.1",
        "--port", "8344"
    ])


def main():
    """Run both servers simultaneously"""
    print("🎯 Starting development environment with API and documentation...")
    print("=" * 60)

    mkdocs_process = None
    api_process = None

    try:
        # Start MkDocs serve
        mkdocs_process = start_mkdocs_serve()
        time.sleep(2)  # Give MkDocs time to start

        # Start API server
        api_process = start_api_server()

        print("")
        print("✅ Development environment started successfully!")
        print("")
        print("📖 Services available:")
        print("   • API Server:      http://127.0.0.1:8344")
        print("   • API Docs:        http://127.0.0.1:8344/docs")
        print("   • Site Docs:       http://127.0.0.1:8001")
        print("   • Built Docs:      http://127.0.0.1:8344/docs-site/")
        print("")
        print("🛑 Press Ctrl+C to stop both servers")
        print("=" * 60)

        # Wait for API process to complete
        api_process.wait()

    except KeyboardInterrupt:
        print("\n🛑 Shutting down development environment...")

    finally:
        # Clean up processes
        if mkdocs_process:
            mkdocs_process.terminate()
            try:
                mkdocs_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                mkdocs_process.kill()

        if api_process:
            api_process.terminate()
            try:
                api_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                api_process.kill()

        print("✅ Development environment stopped.")


if __name__ == "__main__":
    main()