"""A headless browser for the oracles (Playwright for Python), never downloaded at run time.

The channels already installed on the machine are tried in order: Microsoft Edge, Google
Chrome, then the Chromium build bundled with Playwright when `playwright install` already
fetched it. `BENCH_BROWSER_CHANNEL` (msedge, chrome or chromium) forces one of them.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass

CHANNELS: tuple[str, ...] = ("msedge", "chrome", "chromium")


class BrowserUnavailable(RuntimeError):
    """No headless browser could be started; the message lists why for each channel."""


@dataclass
class Engine:
    browser: object  # playwright.sync_api.Browser
    channel: str

    @property
    def name(self) -> str:
        return f"{self.channel} {self.browser.version}"


def _channels() -> tuple[str, ...]:
    forced = os.environ.get("BENCH_BROWSER_CHANNEL", "").strip()
    return (forced,) if forced else CHANNELS


@contextmanager
def launch() -> Iterator[Engine]:
    """Yield a started headless browser, closed (with the Playwright driver) on exit."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise BrowserUnavailable(f"playwright is not installed: {exc}") from exc
    errors: list[str] = []
    with sync_playwright() as playwright:
        engine = None
        for channel in _channels():
            try:
                options = {} if channel == "chromium" else {"channel": channel}
                engine = Engine(playwright.chromium.launch(headless=True, **options), channel)
                break
            except Exception as exc:  # each channel may be missing; report them all
                errors.append(f"{channel}: {str(exc).splitlines()[0][:160]}")
        if engine is None:
            raise BrowserUnavailable("no headless browser: " + "; ".join(errors))
        try:
            yield engine
        finally:
            engine.browser.close()


def available() -> str:
    """"" when a browser starts, else the reason (used to skip browser tests)."""
    try:
        with launch():
            return ""
    except BrowserUnavailable as exc:
        return str(exc)
