"""Unit tests of core/prompts.py: content, hard rules, final JSON and size budget."""

import pytest

from autospec.core import prompts
from autospec.core.jsonx import extract_json
from autospec.core.models import AcceptanceCriterion, AcceptanceTest, Profile, Story
from autospec.core.plan import PlanError, parse_dev, parse_plan, parse_qa

BUDGET = 1_500  # static characters per builder (docs/REFONTE_V2.md 4.2)
# Fullstack QA and dev prompts carry a second toolchain (vitest, npm): raised, capped at 1,900.
FULLSTACK_BUDGET = 1_900
EM_DASH = chr(0x2014)
PROFILES = [Profile.LIB, Profile.CLI, Profile.API]
ALL_PROFILES = [*PROFILES, Profile.FULLSTACK]
PY3 = "tests/acceptance/test_us_3.py"
UI3 = "frontend/src/acceptance/us_3.test.tsx"
NPM_COMMANDS = ("`npm --prefix frontend install <pkg>`", "`npm --prefix frontend test`",
                "`npm --prefix frontend run build`")


def _story(sid="US-3", tests=False) -> Story:
    criteria = [
        AcceptanceCriterion(id=f"{sid}.AC-1", text='`python -m todo add "lait"` affiche "Tâche ajoutée : lait"'),
        AcceptanceCriterion(id=f"{sid}.AC-2", text="GET /todos returns {\"items\": []} with status 200"),
    ]
    mapping = [AcceptanceTest(ac_id=f"{sid}.AC-1", nodeids=["tests/acceptance/test_us_3.py::test_ac1_add"])]
    return Story(id=sid, epic_id="EPIC-1", title="Ajouter une tâche", description="En tant que...",
                 criteria=criteria, gherkin="Feature: ajout\n  Scenario: ajout simple",
                 acceptance_tests=mapping if tests else [])


def _minimal_story() -> Story:
    return Story(id="US-1", epic_id="E", title="t", criteria=[AcceptanceCriterion(id="US-1.AC-1", text="c")])


def _all_prompts() -> list[str]:
    story = _story(tests=True)
    built = [prompts.pm_brief("Une CLI de todo"), prompts.dev_retry("FAILED x"),
             prompts.dev_retry("FAILED x", profile=Profile.FULLSTACK)]
    built += [prompts.po_plan("# Brief", package="todo", profile=p) for p in [None, *ALL_PROFILES]]
    for profile in ALL_PROFILES:
        built.append(prompts.qa_tests(story, package="todo", profile=profile, repo_tree="todo/"))
        built.append(prompts.dev_story(story, package="todo", profile=profile, repo_tree="todo/"))
    return built + list(prompts.SYSTEM.values())


# --------------------------------------------------------------------------- global rules


def test_system_personas():
    assert set(prompts.SYSTEM) == {"pm", "po", "qa", "dev"}
    for persona in prompts.SYSTEM.values():
        assert 2 <= len(persona.splitlines()) <= 5 and len(persona) < 800


NO_CHAINING = ("one command per call", "`;`", "`&&`", "`|`", "redirections")
DEV_COMMANDS = ("`uv run pytest", "`uv add <pkg>`", "`uv remove <pkg>`", "`uv sync`", "`uv lock`")


@pytest.mark.parametrize("role,allowed,denied", [
    ("qa", ("`uv run pytest",), ("uv add", "uv remove", "uv sync", "uv lock")),
    ("dev", DEV_COMMANDS, ()),
])
def test_system_prompts_state_the_bash_allowlist(role, allowed, denied):
    """A real session ran `pwd; ls`, got denied and stopped without running pytest."""
    persona = prompts.SYSTEM[role]
    for part in (*allowed, *NO_CHAINING, "Read, Glob and Grep", "never ls, cat, find or pwd",
                 "already the project root", "not a reason to stop",
                 # CONTRACTS.md 8.1: the runner allows `npm --prefix frontend:*` to QA and dev.
                 "`npm --prefix frontend ...` (never cd) if there is a frontend/"):
        assert part in persona
    for part in denied:
        assert part not in persona


def test_system_prompts_guard_the_frontend_acceptance_tests():
    assert "vitest" in prompts.SYSTEM["qa"] and "acceptance files you are given" in prompts.SYSTEM["qa"]
    assert "tests/acceptance/ nor frontend/src/acceptance/" in prompts.SYSTEM["dev"]


def test_builders_repeat_the_tool_hint():
    story = _story(tests=True)
    qa = prompts.qa_tests(story, package="todo", profile="cli", repo_tree="")
    dev = prompts.dev_story(story, package="todo", profile="cli", repo_tree="")
    retry = prompts.dev_retry("FAILED")
    for text in (qa, dev, retry):
        assert "Read, Glob, Grep" in text and "one command per call, no chaining" in text
        assert "no reason to stop" in text
    assert "Bash only for `uv run pytest ...`, one command" in qa and "uv add <pkg>" not in qa
    for text in (dev, retry):
        assert all(command in text for command in DEV_COMMANDS)


def test_fullstack_builders_add_npm_to_the_tool_hint():
    story = _story(tests=True)
    qa = prompts.qa_tests(story, package="todo", profile="fullstack", repo_tree="")
    dev = prompts.dev_story(story, package="todo", profile="fullstack", repo_tree="")
    retry = prompts.dev_retry("FAILED", profile="fullstack")
    assert "Bash only for `uv run pytest ...`, `npm --prefix frontend ...`, one command per call" in qa
    assert "uv add <pkg>" not in qa
    for text in (dev, retry):
        assert all(command in text for command in DEV_COMMANDS)
        assert "`uv lock`, `npm --prefix frontend ...`, one command per call, no chaining" in text


@pytest.mark.parametrize("profile", PROFILES)
def test_python_profiles_never_mention_the_frontend(profile):
    """lib, cli and api user prompts are unchanged by the fullstack profile."""
    story = _story(tests=True)
    for text in (prompts.qa_tests(story, package="todo", profile=profile, repo_tree=""),
                 prompts.dev_story(story, package="todo", profile=profile, repo_tree=""),
                 prompts.dev_retry("FAILED", profile=profile), prompts.dev_retry("FAILED")):
        for word in ("npm", "frontend", "vitest", "React"):
            assert word not in text


def test_no_em_dash_anywhere():
    assert not [p for p in _all_prompts() if EM_DASH in p]


def test_every_prompt_ends_with_its_json_object():
    for text in _all_prompts()[:-4]:
        assert text.rstrip().endswith("}")
        assert extract_json(text)


@pytest.mark.parametrize("name,build", [
    ("pm", lambda p: prompts.pm_brief("g")),
    ("po", lambda p: prompts.po_plan("b", package="p", profile=p)),
    ("po-choose", lambda p: prompts.po_plan("b", package="p", profile=None)),
    ("qa", lambda p: prompts.qa_tests(_minimal_story(), package="p", profile=p, repo_tree="")),
    ("dev", lambda p: prompts.dev_story(_minimal_story(), package="p", profile=p, repo_tree="")),
    ("retry", lambda p: prompts.dev_retry("f", profile=p)),
    ("retry-default", lambda p: prompts.dev_retry("f")),
])
@pytest.mark.parametrize("profile", ALL_PROFILES)
def test_static_text_stays_under_budget(name, build, profile):
    budget = FULLSTACK_BUDGET if profile is Profile.FULLSTACK and name in ("qa", "dev") else BUDGET
    assert len(build(profile)) <= budget, name


@pytest.mark.parametrize("build", [
    lambda p: prompts.qa_tests(_minimal_story(), package="p", profile=p, repo_tree=""),
    lambda p: prompts.dev_story(_minimal_story(), package="p", profile=p, repo_tree=""),
])
def test_fullstack_overhead_is_bounded(build):
    """The second toolchain costs at most 450 characters over the api prompt."""
    assert len(build(Profile.FULLSTACK)) - len(build(Profile.API)) <= 450


# --------------------------------------------------------------------------- pm


def test_pm_brief_content():
    text = prompts.pm_brief("  Une CLI de todo en français  ")
    assert "<goal>\nUne CLI de todo en français\n</goal>" in text
    for part in ("Public interface", "contract", "exit codes", "language of the goal",
                 "lib, cli, api or fullstack", "smallest that fits", "Do not ask questions"):
        assert part in text
    assert set(extract_json(text)) == {"brief"}


# --------------------------------------------------------------------------- po


def test_po_plan_content_and_rules():
    text = prompts.po_plan("# Todo\nUne CLI.", package="todo_cli", profile=Profile.CLI)
    assert "<brief>\n# Todo\nUne CLI.\n</brief>" in text
    assert "`todo_cli`" in text and "Profile `cli` (fixed)" in text and "python -m todo_cli" in text
    for part in ("verbatim", "never rename", "observable", "depends_on", "gherkin", "priority",
                 "brief's language"):
        assert part in text
    assert set(extract_json(text)) == {"profile", "epics", "stories"}


ADAPTIVE_SIZING = (
    # One session built the whole B5 product (about 57 criteria) in 16 min (REFONTE_V2.md 11.2).
    "ONE story with every criterion when the product fits one focused agent session",
    "most small and medium products: up to ~30 source files or 25 criteria",
    # Beyond: a few large stories along the brief's own structure, not 20 thin slices.
    "AT MOST 7 stories, one per natural feature area of the brief (its sections or lots)",
    "each up to ~20 criteria", "US-1 creating the entry point",
    "Never split one resource's CRUD by verb",
    "`depends_on`: only stories whose code this one truly needs",
)
# The pre-recalibration rules that split B5 into 20 stories (3 min of verification each).
RETIRED_SIZING = ("8 source files", "8 public operations", "2 to 5 criteria", "small vertical slices",
                  "up to 15 criteria", "1 to 7 stories", "every story whose code")


@pytest.mark.parametrize("profile", [None, *ALL_PROFILES])
def test_po_plan_sizes_adaptively(profile):
    """REFONTE_V2.md 11 to 11.2 and CONTRACTS.md 8.4: one story unless the product exceeds a
    session, then at most 7 feature-area stories with real dependencies only."""
    text = prompts.po_plan("b", package="p", profile=profile)
    for part in ADAPTIVE_SIZING:
        assert part in text
    for part in RETIRED_SIZING:
        assert part not in text
    assert "as few user stories as it needs" in prompts.SYSTEM["po"]


def test_po_plan_tells_the_po_that_stories_are_built_without_the_brief():
    """Big stories must carry everything: their criteria are all the QA and dev agents get."""
    assert "tested and built from its criteria alone: no agent sees the brief" in prompts.po_plan(
        "b", package="p", profile=Profile.API)


def test_po_plan_lets_the_po_choose_the_profile():
    text = prompts.po_plan("b", package="pkg", profile=None)
    assert "Choose the profile" in text and '"profile": "lib|cli|api|fullstack"' in text
    assert "fullstack (API + React page)" in text and "(fixed)" not in text


def test_po_plan_fullstack_kind():
    text = prompts.po_plan("b", package="counter_app", profile=Profile.FULLSTACK)
    assert "Profile `fullstack` (fixed)" in text and "`counter_app/app.py`" in text
    assert "create_app()" in text and "/api/" in text and "React page of frontend/" in text


@pytest.mark.parametrize("profile", ALL_PROFILES)
def test_po_plan_example_json_is_a_valid_plan(profile):
    """The example the PO copies must pass the parser that reads its answer."""
    parsed_profile, epics, stories = parse_plan(prompts.po_plan("b", package="p", profile=profile),
                                                profile=None)
    assert parsed_profile is profile and epics[0].id == "EPIC-1" and stories[0].id == "US-1"


# --------------------------------------------------------------------------- qa


@pytest.mark.parametrize("profile", PROFILES)
def test_qa_tests_content(profile):
    story = _story()
    text = prompts.qa_tests(story, package="todo", profile=profile, repo_tree="pyproject.toml\ntodo/")
    assert "US-3" in text and "Ajouter une tâche" in text and "En tant que..." in text
    for criterion in story.criteria:
        assert f"- {criterion.id}: {criterion.text}" in text
    assert "Feature: ajout\n  Scenario: ajout simple" in text
    assert "<repo>\npyproject.toml\ntodo/\n</repo>" in text
    assert f"profile {profile.value}" in text and "`todo`" in text
    assert "tests/acceptance/test_us_3.py" in text and "test_ac<m>_" in text
    for part in ("Black-box", "tmp_path", "no network", "FAIL now", "ImportError", "SyntaxError",
                 "no product code", "nothing outside tests/acceptance/", "uv run pytest"):
        assert part in text
    assert "(US-3.AC-1, US-3.AC-2)" in text
    assert set(extract_json(text)) == {"tests"}


def test_qa_tests_profile_specific_instructions():
    story = _story()
    lib = prompts.qa_tests(story, package="todo", profile="lib", repo_tree="")
    cli = prompts.qa_tests(story, package="todo", profile="cli", repo_tree="")
    api = prompts.qa_tests(story, package="todo", profile="api", repo_tree="")
    full = prompts.qa_tests(story, package="todo", profile="fullstack", repo_tree="")
    assert "from todo import" in lib and "subprocess" not in lib
    assert '[sys.executable, "-m", "todo", ...]' in cli and "cwd=tmp_path" in cli and "timeout=" in cli
    assert "from todo.app import create_app" in api and "TestClient(create_app())" in api
    assert "monkeypatch" in api
    assert "TestClient(create_app())" in full and "profile fullstack" in full
    assert "from todo.app import create_app" in full and "monkeypatch.setenv" in full


def test_qa_tests_fullstack_content():
    story = _story()
    text = prompts.qa_tests(story, package="todo", profile=Profile.FULLSTACK, repo_tree="todo/\nfrontend/")
    assert f"in `{PY3}` and `{UI3}`" in text and "profile fullstack" in text
    for criterion in story.criteria:
        assert f"- {criterion.id}: {criterion.text}" in text
    # API criteria in pytest, UI criteria in vitest + testing-library rendering <App /> (CONTRACTS.md 8.4).
    for part in ("pytest for API criteria", "TestClient(create_app())", "vitest for UI criteria",
                 "@testing-library/react", "`render(<App />)` from `../App` only", "`globalThis.fetch = vi.fn(",
                 "new Response(JSON.stringify(body))", "afterEach(cleanup)", "no jest-dom",
                 "assert visible text and fetch calls"):
        assert part in text
    assert f"Run `uv run pytest {PY3}` and `npm --prefix frontend test -- src/acceptance/us_3.test.tsx`" in text
    for part in ("FAIL now", "never bend a test", "Write only these two files, no product code",
                 "install nothing", "Black-box", "tmp_path", "no network"):
        assert part in text
    assert "only pytest and httpx exist" not in text and "nothing outside tests/acceptance/" not in text
    nodeids = extract_json(text)["tests"][0]["nodeids"]
    assert nodeids == [f"{PY3}::test_ac1_<slug>", f"{UI3}::<describe> > ac1 <test title>"]


@pytest.mark.parametrize("profile", ALL_PROFILES)
def test_qa_tests_example_json_is_accepted_by_the_parser(profile):
    story = _minimal_story()
    tests = parse_qa(prompts.qa_tests(story, package="p", profile=profile, repo_tree=""), story,
                     profile=profile)
    assert tests[0].ac_id == "US-1.AC-1"
    assert tests[0].nodeids[0].startswith("tests/acceptance/test_us_1.py::test_ac1_")
    frontend = [n for n in tests[0].nodeids if n.startswith("frontend/")]
    assert len(frontend) == (profile is Profile.FULLSTACK)


def test_qa_fullstack_example_needs_the_profile_to_parse():
    """The pipeline must pass profile= to parse_qa, or a fullstack answer is rejected."""
    story = _minimal_story()
    text = prompts.qa_tests(story, package="p", profile=Profile.FULLSTACK, repo_tree="")
    with pytest.raises(PlanError, match="fullstack"):
        parse_qa(text, story)


# --------------------------------------------------------------------------- dev


@pytest.mark.parametrize("profile", PROFILES)
def test_dev_story_content(profile):
    story = _story(tests=True)
    text = prompts.dev_story(story, package="todo", profile=profile, repo_tree="todo/__init__.py")
    assert "US-3" in text and "Ajouter une tâche" in text
    for criterion in story.criteria:
        assert f"- {criterion.id}: {criterion.text}" in text
    assert "  tests: tests/acceptance/test_us_3.py::test_ac1_add" in text
    assert "<repo>\ntodo/__init__.py\n</repo>" in text
    assert f"profile {profile.value}" in text and "`todo/`" in text
    for part in ("TDD", "uv run pytest tests/acceptance/test_us_3.py", "tests/unit/", "FULL suite",
                 "refactor", "Never modify, rename or delete anything under tests/acceptance/",
                 "conftest.py", "[tool.pytest]", "`uv add <name>`", "never pip", "pyproject.toml and uv.lock",
                 "public interface exactly", "No network", "language of the criteria"):
        assert part in text
    assert set(extract_json(text)) == {"summary", "dependencies_added"}


def test_dev_story_entry_point_per_profile():
    story = _story()
    lib = prompts.dev_story(story, package="todo", profile="lib", repo_tree="")
    cli = prompts.dev_story(story, package="todo", profile="cli", repo_tree="")
    api = prompts.dev_story(story, package="todo", profile="api", repo_tree="")
    full = prompts.dev_story(story, package="todo", profile="fullstack", repo_tree="")
    assert "`import todo` keeps working" in lib
    assert "`python -m todo --help` exits 0" in cli
    assert "create_app()" in api and "GET /health" in api and "$PORT" in api
    assert "`todo/app.py` keeps `create_app()`, GET /health and serves the built frontend/dist" in full
    assert "(GET / and its assets)" in full and "$PORT" in full


def test_dev_story_fullstack_content():
    story = _story(tests=True)
    story.acceptance_tests[0].nodeids.append(f"{UI3}::counter > ac1 shows 0")
    text = prompts.dev_story(story, package="todo", profile=Profile.FULLSTACK, repo_tree="todo/\nfrontend/")
    assert f"Its acceptance tests are in `{PY3}` and `{UI3}`." in text and "profile fullstack" in text
    assert f"  tests: {PY3}::test_ac1_add, {UI3}::counter > ac1 shows 0" in text
    assert f"1. Run `uv run pytest {PY3}` and `npm --prefix frontend test -- src/acceptance/us_3.test.tsx`" in text
    assert "code in `todo/` and frontend/src/" in text
    assert ("FULL suite `uv run pytest`, `npm --prefix frontend test` and `npm --prefix frontend run build` "
            "(must pass)") in text
    assert all(command in text for command in NPM_COMMANDS)
    for part in ("TDD", "tests/unit/", "refactor",
                 "Never modify, rename or delete anything under tests/acceptance/ or frontend/src/acceptance/",
                 "vitest test file selection", "conftest.py", "[tool.pytest]", "`uv add <name>`", "never pip",
                 "clean environment (uv.lock, npm ci)", "public interface exactly", "No network",
                 "language of the criteria"):
        assert part in text
    assert set(extract_json(text)) == {"summary", "dependencies_added"}


def test_dev_story_without_qa_mapping_lists_criteria_only():
    text = prompts.dev_story(_story(), package="todo", profile="cli", repo_tree="")
    assert "  tests:" not in text and "US-3.AC-2" in text


def test_dynamic_text_is_kept_verbatim():
    story = _story()
    story.criteria[0].text = "prints {name} and ``` fences"
    text = prompts.dev_story(story, package="todo", profile="cli", repo_tree="")
    assert "prints {name} and ``` fences" in text


# --------------------------------------------------------------------------- dev_retry


def test_dev_retry_content():
    text = prompts.dev_retry("FAILED tests/unit/test_store.py::test_add - KeyError")
    assert "<failure>\nFAILED tests/unit/test_store.py::test_add - KeyError\n</failure>" in text
    for part in ("tests/acceptance/", "`uv add <name>`", "never pip", "public interface",
                 "No network", "uv run pytest"):
        assert part in text
    assert parse_dev(text) == {"summary": "<what you fixed, 1 to 3 sentences>",
                               "dependencies_added": ["<names given to uv add>"]}


@pytest.mark.parametrize("profile", [None, *PROFILES])
def test_dev_retry_python_wording_is_the_default(profile):
    assert prompts.dev_retry("F", profile=profile) == prompts.dev_retry("F")


def test_dev_retry_fullstack_content():
    text = prompts.dev_retry("FAILED vitest", profile="fullstack")
    assert "<failure>\nFAILED vitest\n</failure>" in text
    for part in ("pyproject.toml, uv.lock and npm ci",
                 "FULL suite `uv run pytest`, `npm --prefix frontend test` and `npm --prefix frontend run build`",
                 "Never modify, rename or delete anything under tests/acceptance/ or frontend/src/acceptance/",
                 "`uv add <name>`", "never pip", "public interface", "No network"):
        assert part in text
    assert parse_dev(text)["dependencies_added"] == ["<names given to uv add>"]


def test_dev_retry_keeps_the_tail_of_a_long_failure():
    failure = "HEAD" + "x" * 20_000 + "THE END"
    text = prompts.dev_retry(failure)
    assert "THE END" in text and "HEAD" not in text and len(text) < 10_000
