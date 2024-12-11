# conftest.py

import pytest

# Set asyncio default fixture loop scope to avoid deprecation warnings
def pytest_configure(config):
    config.option.asyncio_default_fixture_loop_scope = 'function'

# Additional common fixtures or configurations can be added here if needed
