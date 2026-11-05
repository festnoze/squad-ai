"""The browser half of the B5 oracle (bench/oracles/b5_ui.py) against a stub product.

The stub (fixtures/relais_ui) is a FastAPI app holding just enough of the annex's API in
memory and serving a vanilla JS page that implements the UX behaviours of the specification.
A correct stub passes UX-01 to UX-07; defects switched on in groups that do not overlap prove
that each check fails for its own reason and leaves the others green. No factory, no npm.
"""

import json
import shutil
import sys
from contextlib import contextmanager
from pathlib import Path

import pytest

from bench import browser
from bench.oracle import Product
from bench.oracles import b5_ui

STUB = Path(__file__).parent / "fixtures" / "relais_ui"
VARIANTS = {
    "correct": set(),
    "focus-overflow-cache-stale": {"no-focus-style", "overflow", "keep-cache", "no-stale-guard"},
    "feedback-uuid-timeout-reapply": {"no-feedback", "new-uuid", "no-timeout", "auto-reapply"},
}


class StubProduct(Product):
    """A product whose interpreter is the bench's own (FastAPI and uvicorn are installed there)."""

    @property
    def python(self) -> str:
        return sys.executable


def _stub(root: Path, defects: set[str], page: str | None = None) -> StubProduct:
    package = root / "relais_support"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("", encoding="utf-8")
    shutil.copyfile(STUB / "__main__.py", package / "__main__.py")
    html = page or (STUB / "index.html").read_text(encoding="utf-8").replace("/*DEFECTS*/[]", json.dumps(sorted(defects)))
    (package / "index.html").write_text(html, encoding="utf-8")
    return StubProduct(dir=root, env_dir=root / "no-env", package="relais_support", lock_present=False, sync_ok=True)


@pytest.fixture(scope="module")
def judged(tmp_path_factory):
    """Run the seven UX checks once per stub variant (each run takes about a minute)."""
    reason = browser.available()
    if reason:
        pytest.skip(reason)
    cache: dict[str, dict] = {}

    def get(name: str) -> dict:
        if name not in cache:
            root = tmp_path_factory.mktemp(name)
            work = root / "work"
            work.mkdir()
            cache[name] = b5_ui.run(_stub(root / "product", VARIANTS[name]), work)
        return cache[name]

    return get


def _failed(results: dict) -> dict[str, str]:
    return {cid: check.detail for cid, check in results.items() if not check.passed}


@pytest.mark.browser
def test_a_stub_implementing_the_specified_behaviours_passes_every_ux_check(judged):
    results = judged("correct")

    assert list(results) == b5_ui.UX_IDS
    assert not _failed(results)
    assert results["UX-01"].detail.split()[0] in browser.CHANNELS  # the browser used is recorded


@pytest.mark.browser
def test_focus_overflow_cache_and_stale_answer_defects_fail_their_own_checks(judged):
    failed = _failed(judged("focus-overflow-cache-stale"))

    assert set(failed) == {"UX-03", "UX-04", "UX-05", "UX-06"}, failed
    assert "no visible focus indicator" in failed["UX-03"]
    assert "390 px list" in failed["UX-04"] and "390 px detail" in failed["UX-04"]
    assert "draft is offered to the next account" in failed["UX-05"]
    assert "late answer" in failed["UX-06"]


@pytest.mark.browser
def test_feedback_uuid_timeout_and_reapply_defects_fail_their_own_checks(judged):
    failed = _failed(judged("feedback-uuid-timeout-reapply"))

    assert set(failed) == {"UX-01", "UX-02", "UX-07"}, failed
    assert "no feedback" in failed["UX-01"]
    assert "new client_request_id" in failed["UX-02"] and "15 s at most" in failed["UX-02"]
    assert "sends the change again" in failed["UX-07"] and "overwritten" in failed["UX-07"]


@pytest.mark.browser
def test_a_ui_without_login_form_blocks_every_ux_check_with_the_reason(tmp_path, monkeypatch):
    reason = browser.available()
    if reason:
        pytest.skip(reason)
    monkeypatch.setattr(b5_ui, "PROBE_S", 2.0)
    page = '<!doctype html><html><body><div id="root">Bientôt disponible</div></body></html>'
    (tmp_path / "work").mkdir()

    results = b5_ui.run(_stub(tmp_path / "product", set(), page=page), tmp_path / "work")

    assert all(not c.passed and c.detail.startswith("blocked: GET / shows no login form") for c in results.values())


def test_without_a_browser_every_ux_check_is_reported_not_run(tmp_path, monkeypatch):
    @contextmanager
    def unavailable():
        raise browser.BrowserUnavailable("no headless browser: msedge: missing")
        yield  # pragma: no cover

    monkeypatch.setattr(browser, "launch", unavailable)
    (tmp_path / "work").mkdir()

    results = b5_ui.run(_stub(tmp_path / "product", set()), tmp_path / "work")

    assert list(results) == b5_ui.UX_IDS
    assert {c.detail for c in results.values()} == {"not run: no headless browser: msedge: missing"}


def test_a_product_whose_server_does_not_start_reports_every_ux_check_not_run(tmp_path):
    product = _stub(tmp_path / "product", set())
    main = product.dir / "relais_support" / "__main__.py"
    main.write_text(main.read_text(encoding="utf-8").replace("    import uvicorn\n", "    sys.exit(3)\n"),
                    encoding="utf-8")
    (tmp_path / "work").mkdir()

    results = b5_ui.run(product, tmp_path / "work")

    assert all(c.detail == "not run: UI server: server exited with 3" for c in results.values())


def test_the_browser_channel_can_be_forced(monkeypatch):
    monkeypatch.setenv("BENCH_BROWSER_CHANNEL", "chrome")

    assert browser._channels() == ("chrome",)
