"""Read-only lifecycle counterproof, using only the integration fake daemon."""
import pytest

from autospec.orchestrator import docker_deploy
from tests.test_owned_publication import setup, cleanup


def test_stop_after_daemon_cleanup_before_journal_flush_does_not_revive_on_startup(tmp_path, monkeypatch):
    source, spec, fake, registry = setup(tmp_path, monkeypatch)
    first = registry.publish("project", source, spec)
    original_write = registry._write
    def fail_final_stop_flush(row):
        if row["status"] == "stopped":
            raise OSError("trusted injected crash boundary before terminal stop flush")
        original_write(row)
    monkeypatch.setattr(registry, "_write", fail_final_stop_flush)
    try:
        with pytest.raises(OSError, match="crash boundary"):
            registry.stop("project")
        assert first["container_id"] not in fake.containers
        assert fake.volumes, "normal stop must retain DB"
        before = len(fake.calls)
        result = docker_deploy.recover_publication("project", registry.root, intended_active_only=True)
        assert not result.ok, "startup resurrected a service after deliberate stop removed its owned container"
        assert not any(call[1] == "run" for call in fake.calls[before:])
    finally:
        monkeypatch.setattr(registry, "_write", original_write)
        cleanup(registry)
