#!/usr/bin/env python3
"""
Build MkDocs documentation for serving as static files.
"""
import os
import subprocess
import shutil
from pathlib import Path


def build_docs():
    """Build MkDocs documentation"""
    print("Building MkDocs documentation...")

    # Get project root
    project_root = Path(__file__).parent.parent
    docs_output_dir = project_root / "static" / "docs-site"

    try:
        # Clean existing docs
        if docs_output_dir.exists():
            shutil.rmtree(docs_output_dir)

        # Build docs
        result = subprocess.run(
            ["mkdocs", "build", "--site-dir", str(docs_output_dir)],
            cwd=project_root,
            capture_output=True,
            text=True,
            check=True
        )

        print("Documentation built successfully!")
        print(f"Output directory: {docs_output_dir}")
        return True

    except subprocess.CalledProcessError as e:
        print("X Error building documentation:")
        print(f"  {e.stdout}")
        print(f"  {e.stderr}")
        return False
    except FileNotFoundError:
        print("X mkdocs command not found. Please install mkdocs:")
        print("  pip install mkdocs mkdocs-material")
        return False


def serve_docs_dev():
    """Start mkdocs serve for development alongside the API"""
    print("Starting MkDocs development server...")
    try:
        # Start mkdocs serve on a different port
        subprocess.Popen(
            ["mkdocs", "serve", "--dev-addr", "127.0.0.1:8001"],
            cwd=Path(__file__).parent.parent
        )
        print("MkDocs development server started on http://127.0.0.1:8001")
        print("Documentation available at: http://127.0.0.1:8001")
        return True
    except FileNotFoundError:
        print("X mkdocs command not found.")
        return False


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "--dev":
        serve_docs_dev()
    else:
        build_docs()