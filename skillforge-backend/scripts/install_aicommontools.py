"""
Script to install common-tools (AICommonTools) based on ENVIRONMENT variable.

- Development: Installs from local path as editable
- Production: Installs from Azure Artifacts feed
"""

import subprocess
import sys
from pathlib import Path

# Add src directory to Python path to allow importing from src/
src_path = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(src_path))

from envvar import EnvHelper

# Fix Windows console encoding for emoji support
if sys.platform == "win32":
    import io

    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")


def install_development() -> None:
    """Install common-tools from local path as editable package with specified extras."""
    local_path = EnvHelper.get_aicommontools_local_path()
    install_mode = EnvHelper.get_common_tools_install_mode()

    print(f"🔧 Installing common-tools from local path: {local_path}")
    print(f"📦 Install mode: {install_mode}")

    if not Path(local_path).exists():
        print(f"❌ Error: Local path does not exist: {local_path}")
        print("   Set AICOMMONTOOLS_LOCAL_PATH in your .env file to the correct path.")
        sys.exit(1)

    # Build the installation command with extras
    package_spec = f"common-tools @ {local_path}"
    if install_mode and install_mode.lower() != "none":
        # Format: common-tools[database,qdrant] @ path
        package_spec = f"common-tools[{install_mode}] @ {local_path}"

    try:
        subprocess.run(
            ["uv", "pip", "install", "-e", package_spec],
            check=True,
        )
        print("✅ common-tools installed successfully from local path")
    except subprocess.CalledProcessError as e:
        print(f"❌ Failed to install common-tools: {e}")
        sys.exit(1)


def install_from_built_lib(lib_version: str = "0.5.35") -> None:
    """Install AI common-tools lib. from a wheel file in 'wheels' folder with specified extras."""
    install_mode = EnvHelper.get_common_tools_install_mode()
    dist_path = Path(__file__).parent.parent / "wheels"
    wheel_file = dist_path / f"common_tools-{lib_version}-py3-none-any.whl"

    print(f"📦 Installing common-tools from wheel file: {wheel_file}")
    print(f"📦 Install mode: {install_mode}")

    if not wheel_file.exists():
        print(f"❌ Error: Wheel file does not exist: {wheel_file}")
        print(f"   Expected location: {wheel_file}")
        sys.exit(1)

    # Build the installation command with extras
    package_spec = str(wheel_file)
    if install_mode and install_mode.lower() != "none":
        # Format: path/to/wheel.whl[database,qdrant]
        package_spec = f"{wheel_file}[{install_mode}]"

    try:
        subprocess.run(
            ["uv", "pip", "install", package_spec],
            check=True,
        )
        print("✅ common-tools installed successfully from wheel file")
    except subprocess.CalledProcessError as e:
        print(f"❌ Failed to install common-tools: {e}")
        sys.exit(1)


def install_production() -> None:
    """Install common-tools from Azure Artifacts feed with specified extras."""
    # Get Azure Artifacts configuration from environment
    artifact_feed_url = EnvHelper.get_azure_artifact_feed_url()
    artifact_feed_token = EnvHelper.get_azure_artifact_feed_token()
    aicommontools_version = EnvHelper.get_aicommontools_version()
    install_mode = EnvHelper.get_common_tools_install_mode()

    if not artifact_feed_url:
        print("❌ Error: AZURE_ARTIFACT_FEED_URL not set in environment")
        print("   Required environment variables for production:")
        print("   - AZURE_ARTIFACT_FEED_URL: Azure Artifacts feed URL")
        print("   - AZURE_ARTIFACT_FEED_TOKEN: Personal Access Token (PAT) for authentication")
        print("   - AICOMMONTOOLS_VERSION: (Optional) Specific version to install")
        print("   - COMMON_TOOLS_INSTALL_MODE: (Optional) Extras to install (e.g., 'database')")
        sys.exit(1)

    print("📦 Installing common-tools from Azure Artifacts")
    print(f"📦 Install mode: {install_mode}")

    # Construct the package specification with extras
    package_spec = "common-tools"
    if install_mode and install_mode.lower() != "none":
        package_spec = f"common-tools[{install_mode}]"

    if aicommontools_version:
        if "[" in package_spec:
            # Insert version before the brackets: common-tools[extras] -> common-tools==version[extras]
            package_spec = package_spec.replace("[", f"=={aicommontools_version}[")
        else:
            package_spec = f"common-tools=={aicommontools_version}"
        print(f"   Version: {aicommontools_version}")

    # Construct index URL with authentication if token is provided
    index_url = artifact_feed_url
    if artifact_feed_token:
        # Format: https://{token}@pkgs.dev.azure.com/...
        if "://" in artifact_feed_url:
            protocol, rest = artifact_feed_url.split("://", 1)
            index_url = f"{protocol}://{artifact_feed_token}@{rest}"

    try:
        subprocess.run(
            ["uv", "pip", "install", package_spec, "--index-url", index_url],
            check=True,
        )
        print("✅ common-tools installed successfully from Azure Artifacts")
    except subprocess.CalledProcessError as e:
        print(f"❌ Failed to install common-tools: {e}")
        print("   Make sure AZURE_ARTIFACT_FEED_TOKEN is valid and has read permissions")
        sys.exit(1)


def main():
    """Main entry point for the installation script."""
    environment = EnvHelper.get_environment()
    print(f"🌍 Environment: {environment}")

    if environment == "development":
        install_development()
    elif environment == "built-lib":
        install_from_built_lib()
    elif environment == "production":
        install_production()
    else:
        print(f"⚠️  Unknown environment: {environment}")
        print("   Defaulting to development installation")
        install_development()


if __name__ == "__main__":
    main()
