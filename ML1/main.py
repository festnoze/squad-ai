import subprocess
import sys

def main():
    """Launch the Streamlit ML Pipeline Dashboard"""
    print("🍷 Starting Wine Quality ML Pipeline Dashboard...")
    print("📱 Opening in your default web browser at http://localhost:8501")
    print("💡 Press Ctrl+C to stop the application")

    try:
        # Launch Streamlit app
        subprocess.run([sys.executable, '-m', 'streamlit', 'run', 'visualize.py'])
    except KeyboardInterrupt:
        print("\n👋 Application stopped. Goodbye!")
    except ImportError:
        print("❌ ERROR: Streamlit not installed!")
        print("Please install with: pip install streamlit")
    except Exception as e:
        print(f"❌ ERROR: {e}")

if __name__ == "__main__":
    main()
