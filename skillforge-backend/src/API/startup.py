import os
import sys
import platform
import shutil
import asyncio
import logging
from pathlib import Path


# Custom exception handler to suppress known asyncio shutdown errors on Windows
def handle_asyncio_exception(loop: asyncio.AbstractEventLoop, context: dict) -> None:  # noqa: ARG001
    """
    Custom exception handler for asyncio to suppress known shutdown errors on Windows.
    This prevents the API from crashing due to harmless asyncio cleanup errors.

    Args:
        loop: The event loop (required by asyncio API but not used here)
        context: Exception context dictionary containing exception and message
    """
    exception = context.get("exception")
    message = context.get("message", "")

    # Suppress known Windows asyncio shutdown errors
    if isinstance(exception, (asyncio.InvalidStateError, ConnectionResetError, OSError)):
        # These errors commonly occur during shutdown on Windows with Python 3.13
        # WinError 995: I/O operation aborted due to thread exit or application request
        if isinstance(exception, OSError) and getattr(exception, "winerror", None) == 995:
            return  # Silently ignore
        if isinstance(exception, asyncio.InvalidStateError) and "invalid state" in str(exception):
            return  # Silently ignore
        if isinstance(exception, ConnectionResetError):
            return  # Silently ignore

    # For other exceptions, log them
    logger = logging.getLogger("asyncio")
    logger.error(f"Asyncio exception: {message}", exc_info=exception)


# Fix for Python asyncio issues on Windows
# Python 3.13 requires WindowsProactorEventLoopPolicy for proper async I/O handling
# Python 3.8-3.12 work better with WindowsSelectorEventLoopPolicy on Windows
# See: https://github.com/encode/uvicorn/issues/1854
if platform.system() == "Windows" and sys.version_info >= (3, 8):
    # Create custom event loop policies that automatically set the exception handler
    if sys.version_info >= (3, 13):

        class WindowsEventLoopPolicyWithExceptionHandler(asyncio.WindowsProactorEventLoopPolicy):  # type: ignore[unused-ignore]
            """Custom event loop policy that automatically sets exception handler on new loops."""

            def new_event_loop(self) -> asyncio.AbstractEventLoop:
                """Create a new event loop with our custom exception handler."""
                loop = super().new_event_loop()
                loop.set_exception_handler(handle_asyncio_exception)
                return loop

    else:  # Python 3.8-3.12

        class WindowsEventLoopPolicyWithExceptionHandler(asyncio.WindowsSelectorEventLoopPolicy):  # type: ignore[misc,no-redef]
            """Custom event loop policy that automatically sets exception handler on new loops."""

            def new_event_loop(self) -> asyncio.AbstractEventLoop:
                """Create a new event loop with our custom exception handler."""
                loop = super().new_event_loop()
                loop.set_exception_handler(handle_asyncio_exception)
                return loop

    # Install the custom policy
    asyncio.set_event_loop_policy(WindowsEventLoopPolicyWithExceptionHandler())

    # Set it on the current event loop if it exists
    try:
        loop = asyncio.get_event_loop()
        loop.set_exception_handler(handle_asyncio_exception)
    except RuntimeError:
        pass  # No event loop yet

# Add "/src" dir to Python path to auto-import from 'src/'
src_path = Path(__file__).parent.parent
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

from common_tools.helpers.txt_helper import txt  # type: ignore[import-untyped]
from envvar import EnvHelper

# # Analyse upon startup the whole project to find all types and generate strong typing
# from strong_types.dynamic_type_analyzer import DynamicTypeAnalyzer
# DynamicTypeAnalyzer.initialize_strong_typing(project_namespace="app.")

# Clear logs and temporary audio files
if EnvHelper.get_remove_logs_upon_startup():
    for folder in ["outputs/logs"]:
        if os.path.exists(folder):
            shutil.rmtree(folder)
        os.makedirs(folder, exist_ok=True)

# Start the app
from API.api_config import ApiConfig
import API.dependency_injection_config  # Initialize DI container  # noqa: F401

txt.activate_print = True

app = ApiConfig.create_app()
