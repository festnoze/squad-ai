"""Prompts of the four v2 agents (docs/REFONTE_V2.md 4.2, docs/v2/CONTRACTS.md 5 and 8).

Short on purpose: the static text of every builder stays under ~1,500 characters
(~1,900 for the fullstack QA and dev prompts, which carry a second toolchain).
Dynamic content (goal, brief, repo tree, failure) is wrapped in tags so a quote or a
code fence inside it cannot break the prompt. Every prompt ends with the exact final
JSON object the factory parses (core/plan.py).
"""

from __future__ import annotations

from .models import Profile, Story
from .plan import acceptance_files

# Bash commands the runner's allowlist accepts per role (CONTRACTS.md 3 and 8.1). A real dev
# session that tried `pwd; ls` got denied and stopped without running pytest: say it explicitly.
_QA_BASH = "`uv run pytest ...`"
_DEV_BASH = "`uv run pytest ...`, `uv add <pkg>`, `uv remove <pkg>`, `uv sync`, `uv lock`"
_NPM = "`npm --prefix frontend ...`"


def _tool_rules(bash: str) -> str:
    return ("The working directory is already the project root. Explore files with the Read, Glob and "
            "Grep tools, never ls, cat, find or pwd. Bash accepts only these command prefixes: "
            f"{bash}, and {_NPM} (never cd) if there is a frontend/; one command per call, no chaining "
            "with `;`, `&&`, `|` and no redirections.\n"
            "A denied command is not a reason to stop: carry on with the allowed tools.")


def _tool_hint(bash: str) -> str:
    return (f"- Tools: Read, Glob, Grep to explore; Bash only for {bash}, one command per call, "
            "no chaining. A denied command is no reason to stop.")


SYSTEM: dict[str, str] = {
    "pm": "You are the product manager of Autospec, an automated spec-to-code factory.\n"
          "You write short, decisive product briefs. You never ask questions: you make "
          "reasonable minimal choices and state them as assumptions.",
    "po": "You are the product owner of Autospec, an automated spec-to-code factory.\n"
          "You size a brief into as few user stories as it needs, each vertical, with acceptance "
          "criteria that are observable and testable. The brief's public interface is a contract "
          "you never rename.",
    "qa": "You are the QA engineer of Autospec, an automated spec-to-code factory. You write "
          "black-box acceptance tests (pytest, plus vitest for a frontend) before the code exists and "
          "check they fail; you only write the acceptance files you are given, never product code.\n"
          + _tool_rules(_QA_BASH),
    "dev": "You are a senior Python developer (React + TypeScript for a frontend) in Autospec, an "
           "automated spec-to-code factory. You work in strict TDD, run the tests yourself until the "
           "full suite is green, never touch tests/acceptance/ nor frontend/src/acceptance/ and declare "
           "every dependency (`uv add`, npm install).\n" + _tool_rules(_DEV_BASH),
}

_KIND = {
    Profile.LIB: "a library: callers `import {pkg}`",
    Profile.CLI: "a command line tool run as `python -m {pkg} ...`",
    Profile.API: "an HTTP API, FastAPI `create_app()` in `{pkg}/app.py` served by `python -m {pkg}`",
    Profile.FULLSTACK: "a web app, FastAPI `create_app()` in `{pkg}/app.py` (JSON under /api/) "
                       "serving the React page of frontend/",
}

_API_HOW = ("inside each test, `from {pkg}.app import create_app` and "
            "`fastapi.testclient.TestClient(create_app())`; assert status codes and JSON. "
            "Put stored data in tmp_path via `monkeypatch.setenv(\"DATABASE_PATH\", ...)` "
            "unless the criteria name another setting.")

_QA_HOW = {
    Profile.LIB: "import the public API inside each test (`from {pkg} import name`) and call it.",
    Profile.CLI: "`subprocess.run([sys.executable, \"-m\", \"{pkg}\", ...], capture_output=True, "
                 "text=True, timeout=60, cwd=tmp_path, env={**os.environ, \"PYTHONPATH\": str(ROOT)})` "
                 "with `ROOT = Path(__file__).resolve().parents[2]`; assert exit code and output.",
    Profile.API: _API_HOW,
    Profile.FULLSTACK: "pytest for API criteria, inside each test `from {pkg}.app import create_app` and "
                       "`TestClient(create_app())`; assert status codes and JSON; "
                       "stored data in tmp_path via `monkeypatch.setenv` (DATABASE_PATH unless the "
                       "criteria name another setting).\n- vitest for UI criteria: "
                       "@testing-library/react, `render(<App />)` from `../App` only, `globalThis.fetch = "
                       "vi.fn(...)` resolving `new Response(JSON.stringify(body))`, `afterEach(cleanup)`, "
                       "no jest-dom; assert visible text and fetch calls.",
}

_DEV_ENTRY = {
    Profile.LIB: "`import {pkg}` keeps working.",
    Profile.CLI: "`python -m {pkg} --help` exits 0 (`{pkg}/__main__.py`).",
    Profile.API: "`{pkg}/app.py` keeps `create_app()` and GET /health; `python -m {pkg}` "
                 "serves it on $PORT (default 8000).",
    Profile.FULLSTACK: "`{pkg}/app.py` keeps `create_app()`, GET /health and serves the built "
                       "frontend/dist (GET / and its assets); `python -m {pkg}` serves it on $PORT "
                       "(default 8000).",
}


def _is_fullstack(profile: Profile | str | None) -> bool:
    return profile is not None and Profile(profile) is Profile.FULLSTACK


def _story_block(story: Story, *, with_tests: bool = False) -> str:
    lines = [f"Story {story.id}: {story.title}"]
    if story.description:
        lines.append(story.description)
    lines.append("Acceptance criteria:")
    tests = {t.ac_id: t.nodeids for t in story.acceptance_tests} if with_tests else {}
    for criterion in story.criteria:
        lines.append(f"- {criterion.id}: {criterion.text}")
        if tests.get(criterion.id):
            lines.append(f"  tests: {', '.join(tests[criterion.id])}")
    if story.gherkin:
        lines.append(f"<gherkin>\n{story.gherkin}\n</gherkin>")
    return "\n".join(lines)


def _vitest_run(front: str) -> str:
    """The command that runs one frontend acceptance file (npm runs the script in frontend/)."""
    return f"`npm --prefix frontend test -- {front.removeprefix('frontend/')}`"


def pm_brief(goal: str) -> str:
    return f"""Write the product brief for this goal:
<goal>
{goal.strip()}
</goal>

An automated factory then builds it as a small Python product (library, command line tool, \
HTTP API, or web app with a React page). Do not ask questions.

Markdown, concise (under 60 lines), in the language of the goal, with these sections:
- Problem and users.
- Product kind: lib, cli, api or fullstack (pick the smallest that fits).
- Features of the first version, each with its observable behaviour.
- Public interface: the exact names users rely on (package, functions, CLI commands and \
options, HTTP routes, JSON fields, messages, exit codes). It is a contract.
- Data and storage, if any (local files or SQLite only, no external service, no network).
- Out of scope.
- Assumptions you made.

End your answer with exactly this JSON object (the whole brief in one JSON string):
{{"brief": "<markdown>"}}"""


def po_plan(brief: str, *, package: str, profile: Profile | str | None) -> str:
    if profile is None:
        kind = ("Choose the profile: lib, cli, api or fullstack (API + React page); follow the brief "
                "when it states one.")
        value = "lib|cli|api|fullstack"
    else:
        value = Profile(profile).value
        kind = f"Profile `{value}` (fixed): {_KIND[Profile(profile)].replace('{pkg}', package)}."
    return f"""Split this product brief into epics and user stories.
<brief>
{brief.strip()}
</brief>

The importable package is `{package}`. {kind}
Each story is then built alone by a QA agent (tests from its criteria) and a dev agent; \
neither sees the brief.

Rules:
- The brief's public interface (names, commands, options, routes, JSON fields, messages, exit \
codes) is a contract: copy it verbatim into the criteria, never rename.
- Size: exactly ONE story (up to 15 criteria) when the whole product fits one focused agent \
session, roughly up to 8 source files and 8 public operations. Only a bigger product is split \
into small vertical slices of 2 to 5 criteria, US-1 creating the entry point.
- Criteria are observable behaviours testable through the public interface: concrete input, \
exact expected output, status, message or exit code.
- `depends_on`: every story whose code this one needs. `priority`: 1 (first) to 5.
- `gherkin`: one Feature, one Scenario per criterion.
- User-facing text stays in the brief's language.

End your answer with exactly this JSON object (criteria are plain strings, numbered by the factory):
{{"profile": "{value}", "epics": [{{"id": "EPIC-1", "title": "...", "description": "..."}}], \
"stories": [{{"id": "US-1", "epic_id": "EPIC-1", "title": "...", "description": "...", \
"criteria": ["..."], "gherkin": "Feature: ...", "depends_on": [], "priority": 1}}]}}"""


def qa_tests(story: Story, *, package: str, profile: Profile | str, repo_tree: str) -> str:
    value = Profile(profile)
    files = acceptance_files(story.id, value)
    path = files[0]
    how = _QA_HOW[value].replace("{pkg}", package)
    first = story.criteria[0].id if story.criteria else f"{story.id}.AC-1"
    ids = ", ".join(c.id for c in story.criteria)
    example = f'"{path}::test_ac1_<slug>"'
    if value is Profile.FULLSTACK:
        front = files[1]
        target, libs = f"in `{path}` and `{front}`", ", install nothing."
        run = f"`uv run pytest {path}` and {_vitest_run(front)}"
        scope = "these two files, no product code."
        bash = f"{_QA_BASH}, {_NPM}"
        # vitest nodeid: file, then the describe and test titles joined by " > " (CONTRACTS.md 8.2).
        example += f', "{front}::<describe> > ac1 <test title>"'
    else:
        target, libs, bash = f"in `{path}`", "; only pytest and httpx exist.", _QA_BASH
        run = f"`uv run pytest {path}`"
        scope = f"`{path}`: no product code, nothing outside tests/acceptance/."
    return f"""Write the acceptance tests of story {story.id} {target}. \
The feature is not implemented yet.

{_story_block(story)}

Package `{package}`, profile {value.value}. Repository:
<repo>
{repo_tree.strip()}
</repo>

Rules:
- At least one test per criterion, named `test_ac<m>_<short_slug>` (US-1.AC-2 -> test_ac2_...).
- Black-box through the public interface only: {how}
- Self-contained: tmp_path for files and databases, no network, no other test file{libs}
- Assert the exact names, outputs, messages and exit codes of the criteria.
- Run {run}: tests must FAIL now for the right reason (ImportError, \
AttributeError, failed assertion), never from a SyntaxError or NameError in the test. Only \
behaviour from earlier stories may pass; never bend a test.
- Write only {scope}
{_tool_hint(bash)}

End your answer with exactly this JSON object, one entry per criterion ({ids}):
{{"tests": [{{"ac_id": "{first}", "nodeids": [{example}]}}]}}"""


def dev_story(story: Story, *, package: str, profile: Profile | str, repo_tree: str) -> str:
    value = Profile(profile)
    files = acceptance_files(story.id, value)
    path = files[0]
    entry = _DEV_ENTRY[value].replace("{pkg}", package)
    if value is Profile.FULLSTACK:
        front = files[1]
        where = f"`{path}` and `{front}`"
        red = f"`uv run pytest {path}` and {_vitest_run(front)}"
        code = f"`{package}/` and frontend/src/"
        full = ("`uv run pytest`, `npm --prefix frontend test` and `npm --prefix frontend run build` "
                "(must pass)")
        guarded = "tests/acceptance/ or frontend/src/acceptance/, nor the vitest test file selection,"
        deps = (" and every frontend package with `npm --prefix frontend install <pkg>`: the factory "
                "re-runs everything in a clean environment (uv.lock, npm ci).")
        bash = f"{_DEV_BASH}, {_NPM}"
    else:
        where, red, code, full = f"`{path}`", f"`uv run pytest {path}`", f"`{package}/`", "`uv run pytest`"
        guarded = "tests/acceptance/,"
        deps = (": the factory re-runs the suite in a clean environment built only from "
                "pyproject.toml and uv.lock.")
        bash = _DEV_BASH
    return f"""Implement story {story.id} in this repository (package `{package}`, profile \
{value.value}), in TDD. Its acceptance tests are in {where}.

{_story_block(story, with_tests=True)}

<repo>
{repo_tree.strip()}
</repo>

Method:
1. Run {red} and watch the tests fail.
2. Write focused unit tests in tests/unit/, then the simplest code in {code} that passes.
3. Run the FULL suite {full} until all is green (earlier stories too), then refactor \
while green.

Hard rules:
- Never modify, rename or delete anything under {guarded} never create or edit a \
conftest.py nor the [tool.pytest] section of pyproject.toml: the factory rejects the story.
- Declare every third-party import with `uv add <name>` (never pip){deps}
- Keep the public interface exactly as the criteria state it. {entry}
- User-facing strings stay in the language of the criteria.
- No network; leave no server or background process running.
{_tool_hint(bash)}

End your answer with exactly this JSON object:
{{"summary": "<what you built, 1 to 3 sentences>", "dependencies_added": ["<names given to uv add>"]}}"""


def dev_retry(failure: str, *, profile: Profile | str | None = None) -> str:
    """Sent on --resume of the dev session. ``profile=None`` keeps the Python-only wording."""
    tail = failure.strip()[-8000:]
    if _is_fullstack(profile):
        env = "pyproject.toml, uv.lock and npm ci"
        full = "`uv run pytest`, `npm --prefix frontend test` and `npm --prefix frontend run build`"
        guarded, bash = "tests/acceptance/ or frontend/src/acceptance/", f"{_DEV_BASH}, {_NPM}"
    else:
        env, full = "pyproject.toml and uv.lock", "`uv run pytest`"
        guarded, bash = "tests/acceptance/", _DEV_BASH
    return f"""The factory's independent verification of your work FAILED (clean environment \
built from {env}, full suite, acceptance tests fingerprint, every \
criterion covered by a passing test):
<failure>
{tail}
</failure>

Fix the cause, then run the FULL suite {full} until green. Hard rules:
- Never modify, rename or delete anything under {guarded}, nor any conftest.py or the \
[tool.pytest] configuration.
- Declare every third-party import with `uv add <name>` (never pip).
- Keep the public interface exactly as the criteria state it.
- No network; leave no server or background process running.
{_tool_hint(bash)}

End your answer with exactly this JSON object:
{{"summary": "<what you fixed, 1 to 3 sentences>", "dependencies_added": ["<names given to uv add>"]}}"""
