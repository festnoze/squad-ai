import pytest

from autospec.config import settings
from autospec.orchestrator.pipeline import Pipeline, _PERSIST_EXECUTOR


@pytest.fixture(scope="session", autouse=True)
def _isolate_real_workspace(tmp_path_factory):
    """Guarantee the real ``Autospec/workspace`` is NEVER written by the suite.

    The per-test ``tmp_workspace`` fixture redirects ``workspace_root`` to a
    per-test dir, but state persistence runs on a background thread
    (``_PERSIST_EXECUTOR``) — a pipeline bg task can flush a state write AFTER
    its test finished, once the per-test ``monkeypatch`` has already reverted
    ``workspace_root`` to the real value. Pinning the session-wide default to a
    temp dir means any such late write lands here, not in the developer's real
    workspace (that's why deterministic-id test projects used to pile up there).
    """
    session_root = tmp_path_factory.mktemp("autospec-test-workspace")
    original = settings.workspace_root
    settings.workspace_root = session_root
    yield
    # Drain any state writes still queued on the shared executor before we
    # restore the real path, so none escapes to the real workspace at shutdown.
    _PERSIST_EXECUTOR.shutdown(wait=True)
    settings.workspace_root = original


@pytest.fixture(autouse=True)
def tmp_workspace(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "workspace_root", tmp_path / "workspace")
    monkeypatch.setattr(settings, "max_parallel_devs", 2)
    monkeypatch.setattr(settings, "dev_max_attempts", 2)
    # Hermetic tests: a developer's backend/.env (loaded by config at import) must
    # not change pipeline flow. Pin the flags that add agent calls / phases to
    # their safe defaults; a test exercising one re-enables it via monkeypatch.
    monkeypatch.setattr(settings, "brainstorm_assist_enabled", False)
    monkeypatch.setattr(settings, "architecture_enabled", False)
    monkeypatch.setattr(settings, "components_enabled", False)
    monkeypatch.setattr(settings, "language_selector_enabled", False)
    monkeypatch.setattr(settings, "approval_gates_enabled", False)
    monkeypatch.setattr(settings, "streams_enabled", False)
    monkeypatch.setattr(settings, "skills_enabled", False)
    monkeypatch.setattr(settings, "decompose_enabled", False)
    monkeypatch.setattr(settings, "review_plan_enabled", False)
    monkeypatch.setattr(settings, "po_pipeline", "off")
    monkeypatch.setattr(settings, "split_on_failure_enabled", False)
    monkeypatch.setattr(settings, "setup_install", False)
    monkeypatch.setattr(settings, "ui_tests_enabled", False)
    monkeypatch.setattr(settings, "smoke_run", False)
    monkeypatch.setattr(settings, "definition_of_done_enabled", False)
    monkeypatch.setattr(settings, "definition_of_done_strict_criteria", False)
    monkeypatch.setattr(settings, "runtime_acceptance_enabled", False)
    monkeypatch.setattr(settings, "integration_fix_attempts", 0)
    monkeypatch.setattr(settings, "product_profile", "auto")
    # Verified-swarm & docker-delivery flags (same hermeticity contract: a
    # developer's .env enabling them must not add agent calls, gates or docker
    # subprocesses to tests that don't opt in).
    monkeypatch.setattr(settings, "escalate_on_retry_enabled", False)
    monkeypatch.setattr(settings, "role_routing_enabled", False)
    monkeypatch.setattr(settings, "classify_on_exhaustion_enabled", False)
    monkeypatch.setattr(settings, "dispute_escalation_enabled", False)
    monkeypatch.setattr(settings, "ac_traceability_enabled", False)
    monkeypatch.setattr(settings, "constitution_enabled", False)
    monkeypatch.setattr(settings, "design_amendment_enabled", False)
    monkeypatch.setattr(settings, "test_tamper_guard", "off")
    monkeypatch.setattr(settings, "scope_guard", "off")
    monkeypatch.setattr(settings, "skeleton_guard", "off")
    monkeypatch.setattr(settings, "import_guard", "off")
    monkeypatch.setattr(settings, "flaky_rerun_enabled", False)
    monkeypatch.setattr(settings, "docker_delivery", False)
    # V3-F1: observations add an extractor LLM call per terminal work item — a
    # developer's .env enabling them must not change tests that don't opt in.
    monkeypatch.setattr(settings, "observations_enabled", False)
    # V3-F2: the critic/router chain adds a batched checker call after each
    # extraction — pin it OFF (its default is ON) so F1-only tests keep their
    # NEW-status observations, and pin the optional LLM router for hermeticity.
    monkeypatch.setattr(settings, "observation_critic_enabled", False)
    monkeypatch.setattr(settings, "observation_router_llm", False)
    # V3-F5: the pattern detector adds a boss-tier call just before GOVERN —
    # pin it OFF so a developer's .env can never change tests that don't opt in.
    monkeypatch.setattr(settings, "pattern_detector_enabled", False)
    # V3-F3/F4: governance adds a GOVERN phase (a boss-tier PO call) and the
    # knowledge flag injects memory blocks into prompts — pin both OFF so a
    # developer's .env can never change tests that don't opt in.
    monkeypatch.setattr(settings, "governance_enabled", False)
    monkeypatch.setattr(settings, "governance_auto", False)
    monkeypatch.setattr(settings, "knowledge_enabled", False)
    # V3-F8: the cartographer adds a build-start refresh (workspace scan + an
    # optional worker call) and prompt blocks — pin it OFF so a developer's
    # .env can never change tests that don't opt in.
    monkeypatch.setattr(settings, "cartographer_enabled", False)
    # V3-F6: pin the autonomy policy to its defaults (level 2 = today's exact
    # behaviour, no per-domain override) — a developer's .env raising or
    # lowering the autonomy must not change any gate in tests that don't opt in.
    monkeypatch.setattr(settings, "autonomy_level", 2)
    monkeypatch.setattr(settings, "autonomy_backlog_changes", None)
    monkeypatch.setattr(settings, "autonomy_spec_amendments", None)
    monkeypatch.setattr(settings, "autonomy_memory_writes", None)
    monkeypatch.setattr(settings, "autonomy_delivery", None)
    monkeypatch.setattr(settings, "autonomy_next_feature", None)
    yield tmp_path
    # Drain the shared persist executor BEFORE this test's `workspace_root`
    # monkeypatch is reverted: `_persist` resolves the target path lazily on the
    # executor thread, so a state write still queued from THIS test would
    # otherwise flush into the NEXT test's workspace (a stray project that broke,
    # e.g., test_delete_project's "list is empty" assertion). The executor has a
    # single FIFO worker, so awaiting a trailing no-op guarantees every prior
    # save has completed — landing in this test's (still-current) temp dir.
    try:
        _PERSIST_EXECUTOR.submit(lambda: None).result(timeout=10)
    except Exception:  # noqa: BLE001 — teardown must never fail the test
        pass


@pytest.fixture
def green_pytest(monkeypatch):
    async def _arun_pytest(self):
        return True, "all green", {}

    monkeypatch.setattr(Pipeline, "_arun_pytest", _arun_pytest)


async def wait_until(predicate, timeout=20.0, interval=0.01):
    import asyncio

    deadline = asyncio.get_event_loop().time() + timeout
    while not predicate():
        if asyncio.get_event_loop().time() > deadline:
            raise TimeoutError("condition not met in time")
        await asyncio.sleep(interval)
