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
    # The maker->critic->judge harness (REFINE / REFINE_PO / REFINE_DEV) adds
    # judge+critic agent calls to the plan and build phases: a developer's .env
    # turning it on consumed the canned QA/Dev replies of FakeRunner-driven tests
    # (US-1 ended FAILED with "FakeRunner has no queued reply"). Pin OFF; the
    # refine tests re-enable it explicitly.
    monkeypatch.setattr(settings, "refine_enabled", False)
    # Post-build best-effort phases (tech-writer README, product evaluator,
    # security audit) each spend one agent reply; pin them to their code
    # defaults (OFF) for the same hermeticity reason.
    monkeypatch.setattr(settings, "tech_writer_enabled", False)
    monkeypatch.setattr(settings, "evaluator_enabled", False)
    monkeypatch.setattr(settings, "security_review_enabled", False)
    monkeypatch.setattr(settings, "partial_delivery_enabled", False)
    monkeypatch.setattr(settings, "po_pipeline", "off")
    monkeypatch.setattr(settings, "split_on_failure_enabled", False)
    monkeypatch.setattr(settings, "setup_install", False)
    monkeypatch.setattr(settings, "ui_tests_enabled", False)
    monkeypatch.setattr(settings, "smoke_run", False)
    # FACTORY_IMPROVEMENTS #4: the CLI smoke adds a SECOND subprocess
    # (`main.py --help`) to the non-web smoke path. Pinned to its CODE default
    # (ON, what production does) - `smoke_run` above is already OFF, so no
    # existing test reaches it; the tests covering it drive
    # `_smoke_run_python` directly and opt in or out explicitly.
    monkeypatch.setattr(settings, "smoke_cli_help", True)
    # FACTORY_IMPROVEMENTS (orphan sweep): pinned OFF, and this pin is a SAFETY
    # rule, not a hermeticity one - the sweep shells out to PowerShell/ps and
    # kills real process trees, which a test suite must never do. The tests
    # covering it monkeypatch `subprocess.run` and call the helper directly.
    monkeypatch.setattr(settings, "orphan_sweep_on_boot", False)
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
    # P0-A: the empty-canary replay adds a SECOND suite run (and a venv purge)
    # whenever a canary is red with zero test executed - pin it OFF (its default
    # is ON) so the existing canary tests keep their single-run flow; the tests
    # that cover the replay opt in explicitly.
    monkeypatch.setattr(settings, "canary_replay_on_empty", False)
    # P1-A: the canary by burst only changes anything under merge-lock
    # contention (a burst of size 1 replays the historic single canary), so it
    # is pinned to its CODE default (ON, what production does); the tests that
    # exercise a real burst opt in or out explicitly.
    monkeypatch.setattr(settings, "canary_batch_enabled", True)
    # WF-P1: an empty red (a RED suite that executed ZERO test) is treated as an
    # infra failure - it adds a venv purge + a SECOND suite run and refunds the
    # dev attempt, which flips every test whose fake runner answers red with no
    # parsed outcome. Pin it OFF (its default is ON); the tests covering it opt
    # in explicitly.
    monkeypatch.setattr(settings, "empty_red_is_infra", False)
    # P0-B: the fusion requeue budget (merge conflict / canary revert) is pinned
    # to its code default so a developer's REQUEUE_MAX cannot change how many
    # times a conflicting item is re-queued in the tests.
    monkeypatch.setattr(settings, "requeue_max", 3)
    # P2-A: the solo last resort inserts ONE extra rebuild between the exhausted
    # requeue budget and the historic ending, which changes how many merges the
    # existing conflict tests observe before FAILED (e.g.
    # test_wave1_requeue_budget's exhausted/REQUEUE_MAX=0 cases). Pin it OFF (its
    # default is ON) so those tests keep their historic counts; the tests
    # covering the solo path opt in explicitly.
    monkeypatch.setattr(settings, "solo_on_conflict", False)
    # D11 (P3 wave): consolidating a task-decomposed story writes the container's
    # STORED status and emits ONE extra "story <id> done" commit when its last
    # task merges. Pinned to its CODE default (ON, what production does) - the
    # existing stream tests read `effective_status()` (unchanged) and a story
    # with an incomplete rollup is untouched; the tests covering the rollup opt
    # in or out explicitly.
    monkeypatch.setattr(settings, "consolidate_story_status", True)
    # FACTORY_IMPROVEMENTS (TS criteria): an extracted Technical Story is now
    # born with acceptance criteria and a technical Gherkin instead of neither.
    # Pinned to its CODE default (ON, what production does) - the existing split
    # tests assert on the TS's id/contract/tasks, never on empty criteria.
    monkeypatch.setattr(settings, "ts_acceptance_criteria", True)
    # R6: the story trash only ADDS an entry to `state.trash` on a delete - the
    # story still leaves `state.stories` and its .feature file is still removed,
    # so the existing delete tests are unaffected. Pinned to its CODE default
    # (ON, what production does); the tests covering the hard-delete path opt
    # out explicitly.
    monkeypatch.setattr(settings, "soft_delete_stories", True)
    # P2-B: the shared npm cache only changes the `npm ci` argv (and creates one
    # cache dir under the workspace root). Pinned to its CODE default (ON), so a
    # developer's NPM_SHARED_CACHE cannot change what the frontend tests observe.
    monkeypatch.setattr(settings, "npm_shared_cache", True)
    # P1-C: the critical-path pick order and the fan-out attempt bonus are pinned
    # to their CODE defaults (they are on in production and the existing stream
    # tests stay green with them), so a developer's FANOUT_FIRST /
    # FANOUT_BONUS_THRESHOLD can never change the order items are built in.
    monkeypatch.setattr(settings, "fanout_first_enabled", True)
    monkeypatch.setattr(settings, "fanout_bonus_threshold", 5)
    # P1-B: releasing the dev slot while an item merges lets a second worker
    # start (up to cap + 1 in flight), which changes how many builds a stream
    # test observes at once. Pin it to its CODE default (ON, what production
    # does); the tests covering the release opt in or out explicitly.
    monkeypatch.setattr(settings, "slot_release_on_merge", True)
    # WF-P7: re-probing the usage window would shell out to ccusage (subprocess)
    # from the resume timer. Pin it OFF (its default is 30 minutes) so every test
    # keeps the historical single-sleep path.
    monkeypatch.setattr(settings, "resume_reprobe_min", 0)
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
