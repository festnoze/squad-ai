"""Prompts of the four v2 agents (docs/REFONTE_V2.md 4.2, docs/v2/CONTRACTS.md 5).

Short on purpose: the static text of every builder stays under ~1,500 characters.
Dynamic content (goal, brief, repo tree, failure) is wrapped in tags so a quote or a
code fence inside it cannot break the prompt. Every prompt ends with the exact final
JSON object the factory parses (core/plan.py).
"""

from __future__ import annotations

from .models import Profile, Story
from .plan import acceptance_file

# Bash commands the runner's allowlist accepts per role (CONTRACTS.md 3). A real dev session
# that tried `pwd; ls` got denied and stopped without running pytest: say it explicitly.
_QA_BASH = "`uv run pytest ...`"
_DEV_BASH = "`uv run pytest ...`, `uv add <pkg>`, `uv remove <pkg>`, `uv sync`, `uv lock`"


def _tool_rules(bash: str) -> str:
    return ("The working directory is already the project root. Explore files with the Read, Glob and "
            "Grep tools, never ls, cat, find or pwd. Bash accepts only these command prefixes: "
            f"{bash}; one command per call, no chaining with `;`, `&&`, `|` and no redirections.\n"
            "A denied command is not a reason to stop: carry on with the allowed tools.")


def _tool_hint(bash: str) -> str:
    return (f"- Tools: Read, Glob, Grep to explore; Bash only for {bash}, one command per call, "
            "no chaining. A denied command is no reason to stop.")


SYSTEM: dict[str, str] = {
    "pm": "You are the product manager of Autospec, an automated spec-to-code factory.\n"
          "You write short, decisive product briefs. You never ask questions: you make "
          "reasonable minimal choices and state them as assumptions.",
    "po": "You are the product owner of Autospec, an automated spec-to-code factory.\n"
          "You split a brief into small vertical user stories whose acceptance criteria are "
          "observable and testable. The brief's public interface is a contract you never rename.",
    "qa": "You are the QA engineer of Autospec, an automated spec-to-code factory. You write "
          "black-box pytest acceptance tests before the code exists and check they fail; you only "
          "write under tests/acceptance/ and never write product code.\n" + _tool_rules(_QA_BASH),
    "dev": "You are a senior Python developer in Autospec, an automated spec-to-code factory. You "
           "work in strict TDD, run the tests yourself until the full suite is green, never touch "
           "tests/acceptance/ and declare every dependency with `uv add`.\n" + _tool_rules(_DEV_BASH),
}

_KIND = {
    Profile.LIB: "a library: callers `import {pkg}`",
    Profile.CLI: "a command line tool run as `python -m {pkg} ...`",
    Profile.API: "an HTTP API, FastAPI `create_app()` in `{pkg}/app.py` served by `python -m {pkg}`",
    Profile.FULLSTACK: "a web app: FastAPI backend in `{pkg}/app.py` plus a browser frontend",
}

_QA_HOW = {
    Profile.LIB: "import the public API inside each test (`from {pkg} import name`) and call it.",
    Profile.CLI: "`subprocess.run([sys.executable, \"-m\", \"{pkg}\", ...], capture_output=True, "
                 "text=True, timeout=60, cwd=tmp_path, env={**os.environ, \"PYTHONPATH\": str(ROOT)})` "
                 "with `ROOT = Path(__file__).resolve().parents[2]`; assert exit code and output.",
    Profile.API: "inside each test, `from {pkg}.app import create_app` and "
                 "`fastapi.testclient.TestClient(create_app())`; assert status codes and JSON. "
                 "Put stored data in tmp_path via `monkeypatch.setenv(\"DATABASE_PATH\", ...)` "
                 "unless the criteria name another setting.",
}

_DEV_ENTRY = {
    Profile.LIB: "`import {pkg}` keeps working.",
    Profile.CLI: "`python -m {pkg} --help` exits 0 (`{pkg}/__main__.py`).",
    Profile.API: "`{pkg}/app.py` keeps `create_app()` and GET /health; `python -m {pkg}` "
                 "serves it on $PORT (default 8000).",
}


def _profile(profile: Profile | str) -> Profile:
    value = Profile(profile)
    return Profile.API if value is Profile.FULLSTACK else value


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


def pm_brief(goal: str) -> str:
    return f"""Write the product brief for this goal:
<goal>
{goal.strip()}
</goal>

An automated factory then builds it as a small Python product (library, command line tool \
or HTTP API), story by story. Do not ask questions.

Markdown, concise (under 60 lines), in the language of the goal, with these sections:
- Problem and users.
- Product kind: lib, cli or api (pick one).
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
        kind = (f"Choose the profile: lib (library), cli (`python -m {package} ...`) or api "
                "(FastAPI); follow the brief when it states one.")
        value = "lib|cli|api"
    else:
        value = Profile(profile).value
        kind = f"Profile `{value}` (fixed): {_KIND[Profile(profile)].replace('{pkg}', package)}."
    return f"""Split this product brief into epics and user stories.
<brief>
{brief.strip()}
</brief>

The importable package is `{package}`. {kind}
Each story is then built alone by a QA agent (black-box tests from its criteria) and a dev \
agent (TDD); neither sees the brief.

Rules:
- The brief's public interface (function names, CLI commands and options, HTTP routes, JSON \
fields, messages, exit codes) is a contract: copy it verbatim into the criteria, never rename.
- Vertical slices, 1 to 7 stories (a tiny product is one story). Each fits one focused agent \
session: a handful of files, 2 to 5 criteria.
- US-1 creates the entry point and the minimal skeleton of the public interface.
- Criteria are observable behaviours testable through the public interface: concrete input, \
exact expected output, status, message or exit code. Never "the code is clean".
- `depends_on` lists every story whose code this one needs. `priority`: 1 (first) to 5.
- `gherkin`: one Feature, one Scenario per criterion.
- User-facing text stays in the brief's language.

End your answer with exactly this JSON object (criteria are plain strings, numbered by the factory):
{{"profile": "{value}", "epics": [{{"id": "EPIC-1", "title": "...", "description": "..."}}], \
"stories": [{{"id": "US-1", "epic_id": "EPIC-1", "title": "...", "description": "...", \
"criteria": ["..."], "gherkin": "Feature: ...", "depends_on": [], "priority": 1}}]}}"""


def qa_tests(story: Story, *, package: str, profile: Profile | str, repo_tree: str) -> str:
    path = acceptance_file(story.id)
    how = _QA_HOW[_profile(profile)].replace("{pkg}", package)
    first = story.criteria[0].id if story.criteria else f"{story.id}.AC-1"
    ids = ", ".join(c.id for c in story.criteria)
    return f"""Write the acceptance tests of story {story.id} in `{path}`. \
The feature is not implemented yet.

{_story_block(story)}

Package `{package}`, profile {Profile(profile).value}. Repository:
<repo>
{repo_tree.strip()}
</repo>

Rules:
- At least one test per criterion, named `test_ac<m>_<short_slug>` (US-1.AC-2 -> test_ac2_...).
- Black-box through the public interface only: {how}
- Self-contained: tmp_path for files and databases, no network, no other test file; \
only pytest and httpx exist.
- Assert the exact names, outputs, messages and exit codes of the criteria.
- Run `uv run pytest {path}`: tests must FAIL now for the right reason (ImportError, \
AttributeError, failed assertion), never from a SyntaxError or NameError in the test. Only \
behaviour from earlier stories may pass; never bend a test.
- Write only `{path}`: no product code, nothing outside tests/acceptance/.
{_tool_hint(_QA_BASH)}

End your answer with exactly this JSON object, one entry per criterion ({ids}):
{{"tests": [{{"ac_id": "{first}", "nodeids": ["{path}::test_ac1_<slug>"]}}]}}"""


def dev_story(story: Story, *, package: str, profile: Profile | str, repo_tree: str) -> str:
    path = acceptance_file(story.id)
    entry = _DEV_ENTRY[_profile(profile)].replace("{pkg}", package)
    return f"""Implement story {story.id} in this repository (package `{package}`, profile \
{Profile(profile).value}), in TDD. Its acceptance tests are in `{path}`.

{_story_block(story, with_tests=True)}

<repo>
{repo_tree.strip()}
</repo>

Method:
1. Run `uv run pytest {path}` and watch the tests fail.
2. Write focused unit tests in tests/unit/, then the simplest code in `{package}/` that passes.
3. Run the FULL suite `uv run pytest` until all is green (earlier stories too), then refactor \
while green.

Hard rules:
- Never modify, rename or delete anything under tests/acceptance/, never create or edit a \
conftest.py nor the [tool.pytest] section of pyproject.toml: the factory rejects the story.
- Declare every third-party import with `uv add <name>` (never pip): the factory re-runs the \
suite in a clean environment built only from pyproject.toml and uv.lock.
- Keep the public interface exactly as the criteria state it. {entry}
- User-facing strings stay in the language of the criteria.
- No network; leave no server or background process running.
{_tool_hint(_DEV_BASH)}

End your answer with exactly this JSON object:
{{"summary": "<what you built, 1 to 3 sentences>", "dependencies_added": ["<names given to uv add>"]}}"""


def dev_retry(failure: str) -> str:
    tail = failure.strip()[-8000:]
    return f"""The factory's independent verification of your work FAILED (clean environment \
built from pyproject.toml and uv.lock, full suite, acceptance tests fingerprint, every \
criterion covered by a passing test):
<failure>
{tail}
</failure>

Fix the cause, then run the FULL suite `uv run pytest` until green. Hard rules:
- Never modify, rename or delete anything under tests/acceptance/, nor any conftest.py or the \
[tool.pytest] configuration.
- Declare every third-party import with `uv add <name>` (never pip).
- Keep the public interface exactly as the criteria state it.
- No network; leave no server or background process running.
{_tool_hint(_DEV_BASH)}

End your answer with exactly this JSON object:
{{"summary": "<what you fixed, 1 to 3 sentences>", "dependencies_added": ["<names given to uv add>"]}}"""
