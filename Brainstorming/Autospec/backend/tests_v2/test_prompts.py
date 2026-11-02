"""Unit tests of core/prompts.py: content, hard rules, final JSON and size budget."""

import pytest

from autospec.core import prompts
from autospec.core.jsonx import extract_json
from autospec.core.models import AcceptanceCriterion, AcceptanceTest, Profile, Story
from autospec.core.plan import parse_dev, parse_plan, parse_qa

BUDGET = 1_500  # static characters per builder (docs/REFONTE_V2.md 4.2)
EM_DASH = chr(0x2014)
PROFILES = [Profile.LIB, Profile.CLI, Profile.API]


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
    built = [prompts.pm_brief("Une CLI de todo"), prompts.dev_retry("FAILED x")]
    built += [prompts.po_plan("# Brief", package="todo", profile=p) for p in [None, *PROFILES]]
    for profile in [*PROFILES, Profile.FULLSTACK]:
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
                 "already the project root", "not a reason to stop"):
        assert part in persona
    for part in denied:
        assert part not in persona


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
    ("retry", lambda p: prompts.dev_retry("f")),
])
@pytest.mark.parametrize("profile", [*PROFILES, Profile.FULLSTACK])
def test_static_text_stays_under_budget(name, build, profile):
    assert len(build(profile)) <= BUDGET, name


# --------------------------------------------------------------------------- pm


def test_pm_brief_content():
    text = prompts.pm_brief("  Une CLI de todo en français  ")
    assert "<goal>\nUne CLI de todo en français\n</goal>" in text
    for part in ("Public interface", "contract", "exit codes", "language of the goal",
                 "lib, cli or api", "Do not ask questions"):
        assert part in text
    assert set(extract_json(text)) == {"brief"}


# --------------------------------------------------------------------------- po


def test_po_plan_content_and_rules():
    text = prompts.po_plan("# Todo\nUne CLI.", package="todo_cli", profile=Profile.CLI)
    assert "<brief>\n# Todo\nUne CLI.\n</brief>" in text
    assert "`todo_cli`" in text and "Profile `cli` (fixed)" in text and "python -m todo_cli" in text
    for part in ("verbatim", "never rename", "Vertical slices", "1 to 7 stories", "2 to 5 criteria",
                 "US-1 creates the entry point", "observable", "depends_on", "gherkin", "priority",
                 "brief's language"):
        assert part in text
    assert set(extract_json(text)) == {"profile", "epics", "stories"}


def test_po_plan_lets_the_po_choose_the_profile():
    text = prompts.po_plan("b", package="pkg", profile=None)
    assert "Choose the profile" in text and '"profile": "lib|cli|api"' in text
    assert "(fixed)" not in text


@pytest.mark.parametrize("profile", PROFILES)
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


def test_qa_tests_example_json_is_accepted_by_the_parser():
    story = _minimal_story()
    tests = parse_qa(prompts.qa_tests(story, package="p", profile="lib", repo_tree=""), story)
    assert tests[0].ac_id == "US-1.AC-1"
    assert tests[0].nodeids[0].startswith("tests/acceptance/test_us_1.py::test_ac1_")


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
    assert "`import todo` keeps working" in lib
    assert "`python -m todo --help` exits 0" in cli
    assert "create_app()" in api and "GET /health" in api and "$PORT" in api


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


def test_dev_retry_keeps_the_tail_of_a_long_failure():
    failure = "HEAD" + "x" * 20_000 + "THE END"
    text = prompts.dev_retry(failure)
    assert "THE END" in text and "HEAD" not in text and len(text) < 10_000
