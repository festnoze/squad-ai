#!/usr/bin/env python3
"""
Test documentation integration with API
"""
import os
import sys
from pathlib import Path

# Add project root to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))
os.chdir(project_root)

# Set PYTHONPATH environment variable for subprocesses
os.environ['PYTHONPATH'] = str(project_root)

def test_docs_built():
    """Test that documentation is built correctly"""
    docs_path = project_root / "static" / "docs-site"

    if not docs_path.exists():
        print("X Documentation not built")
        return False

    if not (docs_path / "index.html").exists():
        print("X Main documentation index not found")
        return False

    print("Documentation built successfully")
    return True

def test_api_integration():
    """Test API integration with documentation"""
    try:
        # Set environment variables for testing
        os.environ.setdefault('SERVE_DOCUMENTATION', 'true')
        os.environ.setdefault('ENVIRONMENT', 'development')

        # Import and test the API
        from app.api.startup import app
        from fastapi.testclient import TestClient

        client = TestClient(app)

        # Test root endpoint
        response = client.get('/')
        if response.status_code != 200:
            print(f"X Root endpoint failed: {response.status_code}")
            return False

        data = response.json()
        if 'documentation' not in data:
            print("X Documentation links not found in root response")
            return False

        print("API integration successful")
        return True

    except Exception as e:
        print(f"X API integration failed: {e}")
        return False

def main():
    """Run all tests"""
    print("Testing documentation integration...")
    print("=" * 40)

    # Test documentation build
    docs_ok = test_docs_built()

    # Test API integration
    api_ok = test_api_integration()

    print("=" * 40)

    if docs_ok and api_ok:
        print("All tests passed!")
        print("")
        print("Ready to serve documentation:")
        print("  • Built documentation: /docs-site/")
        print("  • MkDocs serve: python scripts/build_docs.py --dev")
        print("  • Both servers: python scripts/dev_with_docs.py")
        return True
    else:
        print("Some tests failed")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)