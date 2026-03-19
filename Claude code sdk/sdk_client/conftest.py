"""Pytest configuration for cc tests."""

import pytest


# Configure pytest-asyncio to use auto mode
pytest_plugins = ["pytest_asyncio"]


def pytest_configure(config):
    """Configure pytest markers."""
    config.addinivalue_line(
        "markers", "asyncio: mark test as async"
    )


@pytest.fixture(scope="session")
def anyio_backend():
    """Use asyncio as the async backend."""
    return "asyncio"
