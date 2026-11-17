"""Shared configuration of the bench's own tests."""


def pytest_configure(config):
    config.addinivalue_line("markers", "browser: drives a real headless browser (skipped when none starts)")
