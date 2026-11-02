# Autospec v2: module contracts (phase 0-1)

Source of truth for the parallel build of the v2 core. Plan and rationale: `docs/REFONTE_V2.md`.
Shared code already written (do not modify, ask the lead): `backend/autospec/core/models.py`,
`ports.py`, `jsonx.py`, `procs.py`, `settings.py`.

## 1. File ownership

| Owner | Files (create / modify only these) |
|---|---|
| lead | `core/models.py`, `ports.py`, `jsonx.py`, `procs.py`, `settings.py`, `machine.py`, `store.py`, `pipeline.py`, `fake.py`, `__main__.py`, `tests_v2/test_machine.py`, `test_store.py`, `test_pipeline.py`, `test_jsonx.py`, `test_procs.py`, `test_architecture.py` |
| runner | `core/agent.py`, `tests_v2/test_agent.py`, `tests_v2/fixtures/fake_claude.py` |
| verify | `core/profiles.py`, `core/verify.py`, `tests_v2/test_profiles.py`, `tests_v2/test_verify.py` |
| prompts | `core/prompts.py`, `core/plan.py`, `tests_v2/test_prompts.py`, `tests_v2/test_plan.py` |
| bench | everything under `backend/bench/` (incl. its own `backend/bench/tests/`) |

Paths are relative to `backend/` (`core/` = `backend/autospec/core/`).

Rules for every owner:
- `autospec.core` never imports v1 modules (`autospec.orchestrator`, `autospec.agents`,
  `autospec.config`, `autospec.api`, `autospec.models`, ...). Stdlib + pydantic only.
- Async functions are prefixed with `a` (`arun_suite`, never `run_suite_async`).
- Code comments and docstrings in English. Never use the em dash character.
- Run only your own tests, from `backend/` with the venv activated:
  `source .venv/Scripts/activate && python -m pytest tests_v2/test_x.py -q -p no:cacheprovider`.
  Never run the v1 suite (`tests/`, 20 min). Never run `ruff check` without `--no-fix`.
- Do not commit; the lead commits. Do not touch files outside your row.

## 2. Product workspace layout (what the factory generates)

```
<workspace_root>/<project_id>/
  pyproject.toml        [project] name, deps; [dependency-groups] dev = pytest, pytest-json-report (+ httpx for api)
                        [tool.pytest.ini_options] pythonpath = ["."], testpaths = ["tests"]
  uv.lock               always in sync with pyproject (`uv sync --locked` must pass)
  <package>/            the product (importable from the repo root)
    __init__.py
    __main__.py         cli and api profiles: entry point (`python -m <package>`)
    app.py              api profile: `create_app()` FastAPI factory with GET /health -> {"status": "ok"}
  tests/
    acceptance/         written by the QA agent ONLY, one file per story: test_us_<n>.py
    unit/               written by the dev agent
  .gitignore            .venv/, __pycache__/, .pytest_cache/, *.db, *.sqlite*, .autospec/
  .autospec/            factory-owned, git-ignored: state.json, events.jsonl, logs/, verify-venv/
```

Profiles: `lib` (import only), `cli` (`python -m <package> --help`), `api` (`python -m <package>`
serves HTTP on `$PORT`, default 8000, `GET /health` 200). `fullstack` is phase 3 (not now).

Nodeids are POSIX paths relative to the workspace root: `tests/acceptance/test_us_1.py::test_ac1_...`.

## 3. `core/agent.py` (runner)

```python
class ClaudeCodeRunner:                      # implements ports.AgentRunner
    def __init__(self, settings: Settings): ...
    async def arun(self, call: AgentCall) -> AgentResult  # raises AgentError

def resolve_claude_command(cmd: str) -> list[str]   # claude.cmd shim -> the native claude.exe
def build_argv(settings: Settings, call: AgentCall, system_prompt_file: Path) -> list[str]
def parse_cli_output(stdout: str) -> AgentResult    # raises AgentError(kind="cli")
```

- Prompt goes through **stdin** (`procs.run_capped(..., input_text=prompt)`), system prompt through
  `--append-system-prompt-file` (no newline or quote ever on the command line).
- Always: `-p --output-format json --model <call.model or settings.model> --safe-mode
  --strict-mcp-config --permission-mode dontAsk --permission-prompts none`,
  `--max-budget-usd` when `call.max_budget_usd`, `--resume <id>` when `call.resume_session_id`.
- Capability -> tools (validated by a real spike on 2026-11-02):
  - `TEXT`: `--tools ""` (no tool at all).
  - `QA`: `--restricted --tools Read,Edit,Write,Glob,Grep,Bash --allowedTools Read Edit Write Glob Grep
    "Bash(uv run pytest:*)"`.
  - `DEV`: same plus `"Bash(uv add:*)" "Bash(uv remove:*)" "Bash(uv sync:*)" "Bash(uv lock:*)"`.
- `cwd` = `call.cwd`. Timeout -> `procs.kill_tree` -> `AgentError(kind="timeout")`.
- Usage: `total_cost_usd`, `usage.input_tokens + cache_creation_input_tokens + cache_read_input_tokens`,
  `usage.output_tokens`, `duration_ms`, `num_turns`, `session_id`, `permission_denials`.
- `is_error: true` or `subtype` not `success` -> `AgentError(kind="cli")` (or `"budget"` for
  `error_max_budget_usd`), with the partial `AgentResult` attached.
- Each call writes its raw stdout to `<cwd>/.autospec/logs/<role>-<timestamp>.json` when `cwd` is set.

## 4. `core/profiles.py` and `core/verify.py` (verify)

```python
# profiles.py
def scaffold(ws: Path, *, project_name: str, package: str, profile: Profile) -> None
    # writes the layout of section 2, runs `uv lock`, `git init`, commits "scaffold"
def package_name(project_name: str) -> str        # "Todo CLI" -> "todo_cli" (valid identifier)

# verify.py
@dataclass
class SuiteResult:
    ok: bool                       # env built, suite exit code 0, no collection error
    returncode: int | None
    outcomes: dict[str, str]       # nodeid -> "passed" | "failed" | "error" | "skipped"
    collection_errors: list[str]   # files that failed to collect
    output_tail: str               # last ~4000 chars, the useful part for a retry prompt
    env_error: str = ""            # `uv sync --locked` failed: lock out of date, unresolvable dep
    duration_s: float = 0.0

@dataclass
class SmokeResult:
    ok: bool
    detail: str

async def arun_suite(ws: Path, *, select: list[str] | None = None, clean: bool = True,
                     timeout_s: float = 600) -> SuiteResult
    # clean=True: delete then rebuild <ws>/.autospec/verify-venv with
    # UV_PROJECT_ENVIRONMENT + `uv sync --locked`, then `uv run --locked pytest --json-report`.
    # A dependency missing from pyproject therefore fails here (REM-04 lesson).
async def asmoke(ws: Path, *, package: str, profile: Profile, timeout_s: float = 60) -> SmokeResult
def red_check(result: SuiteResult, nodeids: list[str]) -> list[str]   # nodeids that PASSED (must be [])
def missing_criteria(story: Story, result: SuiteResult) -> list[str]  # AC ids with no passed nodeid
def fingerprint(ws: Path, paths: list[str]) -> dict[str, str]          # path -> sha256
def changed_paths(ws: Path) -> list[str]   # vs HEAD, untracked included, .autospec/ excluded
def git_commit(ws: Path, message: str) -> str   # returns the sha ("" when nothing to commit)
def repo_tree(ws: Path, limit: int = 200) -> str  # tracked + untracked files, for prompts
```

## 5. `core/prompts.py` and `core/plan.py` (prompts)

```python
# prompts.py: every builder returns the user prompt; SYSTEM[role] is the appended system prompt.
SYSTEM: dict[str, str]   # keys "pm", "po", "qa", "dev"
def pm_brief(goal: str) -> str
def po_plan(brief: str, *, package: str, profile: Profile | None) -> str
def qa_tests(story: Story, *, package: str, profile: Profile, repo_tree: str) -> str
def dev_story(story: Story, *, package: str, profile: Profile, repo_tree: str) -> str
def dev_retry(failure: str) -> str     # sent on --resume of the same dev session

# plan.py
class PlanError(ValueError): ...
def parse_brief(text: str) -> str
def parse_plan(text: str, *, profile: Profile | None) -> tuple[Profile, list[Epic], list[Story]]
def parse_qa(text: str, story: Story) -> list[AcceptanceTest]
def parse_dev(text: str) -> dict
def next_ready(stories: list[Story]) -> Story | None   # first TODO whose deps are DONE
```

Expected agent outputs (final JSON object of the answer, parsed with `jsonx.extract_json`):
- PM: `{"brief": "<markdown>"}`
- PO: `{"profile": "lib|cli|api", "epics": [{"id": "EPIC-1", "title", "description"}],
  "stories": [{"id": "US-1", "epic_id", "title", "description", "criteria": ["..."],
  "gherkin", "depends_on": [], "priority": 1}]}`. `parse_plan` qualifies criteria ids as
  `US-1.AC-1`, `US-1.AC-2`... in order; rejects unknown epic, unknown or cyclic `depends_on`,
  duplicate ids, empty criteria.
- QA: `{"tests": [{"ac_id": "US-1.AC-1", "nodeids": ["tests/acceptance/test_us_1.py::test_ac1_x"]}]}`;
  every criterion of the story covered, every nodeid under `tests/acceptance/`.
- Dev: `{"summary": "...", "dependencies_added": ["argon2-cffi"]}` (lenient).

## 6. Pipeline (lead), for reference

Per story: QA session writes `tests/acceptance/test_us_<n>.py` -> factory runs them, every mapped
nodeid must NOT pass (red check) and only `tests/acceptance/` may have changed -> fingerprint +
commit -> dev session (native TDD) -> factory: clean suite green, fingerprint unchanged,
`missing_criteria` empty -> commit "US-n done". Dev failure -> resume the same session with
`dev_retry(output_tail)`, up to `dev_max_attempts`. Story failed -> phase `needs_attention`.
End: clean suite + smoke -> `done`.

## 7. CLI (lead), consumed by the bench

```
python -m autospec.core run --name NAME [--package PKG] --profile lib|cli|api
    (--brief-file PATH | --goal TEXT) [--workspace-root DIR] [--model M] [--fake]
python -m autospec.core resume WORKSPACE_DIR
```
Exit 0 when the final phase is `done`, 1 otherwise. The LAST stdout line is a JSON summary:
`{"id", "workspace", "phase", "stories": [{"id", "status", "attempts"}], "usage": {...},
"error", "duration_s"}`.
