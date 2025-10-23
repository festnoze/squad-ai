"""
Build MkDocs documentation and copy to static directory for serving.

Usage:
    python scripts/build_docs.py         # Build docs to static/docs-site
    python scripts/build_docs.py --dev   # Start mkdocs serve for development
"""

import shutil
import subprocess
import sys
from pathlib import Path

# Fix Windows console encoding for emoji support
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")


def build_docs():
    """Build MkDocs documentation and copy to static directory."""
    project_root = Path(__file__).parent.parent
    build_dir = project_root / "site"
    static_dir = project_root / "static" / "docs-site"

    print("Building MkDocs documentation...")

    # Build the documentation
    try:
        subprocess.run(["uv", "run", "mkdocs", "build"], cwd=project_root, check=True)
        print(f"[OK] Documentation built successfully to {build_dir}")
    except subprocess.CalledProcessError as e:
        print(f"[ERROR] Failed to build documentation: {e}")
        sys.exit(1)

    # Create static directory if it doesn't exist
    static_dir.parent.mkdir(parents=True, exist_ok=True)

    # Remove old docs if they exist
    if static_dir.exists():
        shutil.rmtree(static_dir)
        print(f"[INFO] Removed old documentation from {static_dir}")

    # Copy built docs to static directory
    shutil.copytree(build_dir, static_dir)
    print(f"[INFO] Copied documentation to {static_dir}")
    print("[OK] Documentation is ready to be served at /docs-site/")


def serve_docs():
    """Start mkdocs serve for development."""
    project_root = Path(__file__).parent.parent
    print("Starting MkDocs development server...")
    print("Documentation will be available at http://127.0.0.1:8000")
    print("Press Ctrl+C to stop")

    try:
        subprocess.run(["uv", "run", "mkdocs", "serve"], cwd=project_root)
    except KeyboardInterrupt:
        print("\nMkDocs server stopped")
    except subprocess.CalledProcessError as e:
        print(f"[ERROR] Failed to start mkdocs serve: {e}")
        sys.exit(1)


def main():
    """Main entry point."""
    if len(sys.argv) > 1 and sys.argv[1] == "--dev":
        serve_docs()
    else:
        build_docs()


if __name__ == "__main__":
    main()
