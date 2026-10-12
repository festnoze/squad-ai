import sys

from autospec.config import settings
from autospec.orchestrator import setup_exec


def test_install_hooks_do_not_inherit_provider_credentials(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-secret-must-not-leak")
    monkeypatch.setenv("DATABASE_URL", "postgresql://private:secret@server/db")
    monkeypatch.setenv("NODE_OPTIONS", "--require=/injected.js")
    ok, output = setup_exec._run_install([
        sys.executable, "-c",
        "import os; assert 'ANTHROPIC_API_KEY' not in os.environ; assert 'DATABASE_URL' not in os.environ; assert 'NODE_OPTIONS' not in os.environ; print('clean environment')",
    ], tmp_path)
    assert ok, output
    assert "clean environment" in output


def test_install_timeout_returns_without_hanging_on_output(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "agent_timeout_s", 0.2)
    ok, output = setup_exec._run_install([sys.executable, "-c", "import time; time.sleep(30)"], tmp_path)
    assert not ok
    assert "délai" in output
