"""Unit tests of core/plan.py: parsing and validation of agent answers, story ordering."""

import json

import pytest

from autospec.core.models import AcceptanceCriterion, Profile, Story, StoryStatus
from autospec.core.plan import (
    PlanError,
    acceptance_file,
    next_ready,
    parse_brief,
    parse_dev,
    parse_plan,
    parse_qa,
    story_number,
)


def _story_dict(sid="US-1", **fields):
    base = {"id": sid, "epic_id": "EPIC-1", "title": f"Title {sid}", "description": "As a user...",
            "criteria": ["first", "second"], "gherkin": "Feature: f", "depends_on": [], "priority": 2}
    base.update(fields)
    return base


def _plan_text(stories=None, epics=None, profile="cli", **extra):
    data = {"profile": profile,
            "epics": epics if epics is not None else [{"id": "EPIC-1", "title": "Core", "description": "d"}],
            "stories": stories if stories is not None else [_story_dict()]}
    data.update(extra)
    return "Here is the plan.\n```json\n" + json.dumps(data) + "\n```"


def _error(text, profile=None) -> str:
    with pytest.raises(PlanError) as info:
        parse_plan(text, profile=profile)
    return str(info.value)


# --------------------------------------------------------------------------- helpers


def test_story_number_and_acceptance_file():
    assert story_number("US-12") == 12
    assert acceptance_file("US-3") == "tests/acceptance/test_us_3.py"
    for bad in ("US-0", "us-1", "US1", "STORY-1", "US-01", ""):
        with pytest.raises(PlanError):
            story_number(bad)


# --------------------------------------------------------------------------- parse_brief


def test_parse_brief_fenced_and_bare():
    assert parse_brief('Done.\n```json\n{"brief": "  # Todo\\nA CLI.  "}\n```') == "# Todo\nA CLI."
    assert parse_brief('I wrote it: {"brief": "# Slugify"}') == "# Slugify"


@pytest.mark.parametrize("text", [
    '{"summary": "x"}', '{"brief": ""}', '{"brief": "   "}', '{"brief": 3}', '{"brief": ["a"]}',
])
def test_parse_brief_rejects_missing_or_empty(text):
    with pytest.raises(PlanError, match='"brief"'):
        parse_brief(text)


@pytest.mark.parametrize("text", ["# Brief without JSON", "", None])
def test_parse_brief_without_json(text):
    with pytest.raises(PlanError, match="JSON"):
        parse_brief(text)


# --------------------------------------------------------------------------- parse_plan


def test_parse_plan_happy_path():
    stories = [
        _story_dict("US-1", criteria=["create works", {"text": "  list works "}], priority=1),
        _story_dict("US-2", depends_on=["US-1"], gherkin=["Feature: g", "  Scenario: s"]),
    ]
    profile, epics, parsed = parse_plan(_plan_text(stories), profile=None)
    assert profile is Profile.CLI
    assert [(e.id, e.title, e.description) for e in epics] == [("EPIC-1", "Core", "d")]
    first, second = parsed
    assert isinstance(first, Story) and first.status is StoryStatus.TODO
    assert [(c.id, c.text) for c in first.criteria] == [("US-1.AC-1", "create works"),
                                                         ("US-1.AC-2", "list works")]
    assert [c.id for c in second.criteria] == ["US-2.AC-1", "US-2.AC-2"]
    assert first.priority == 1 and second.priority == 2
    assert second.depends_on == ["US-1"]
    assert second.gherkin == "Feature: g\n  Scenario: s"
    assert first.description == "As a user..." and first.epic_id == "EPIC-1"


def test_parse_plan_profile_argument_wins():
    assert parse_plan(_plan_text(profile="lib"), profile=Profile.API)[0] is Profile.API
    assert parse_plan(_plan_text(profile="nonsense"), profile="cli")[0] is Profile.CLI
    assert parse_plan(_plan_text(profile=None), profile=Profile.LIB)[0] is Profile.LIB


def test_parse_plan_profile_from_json():
    assert parse_plan(_plan_text(profile=" CLI "), profile=None)[0] is Profile.CLI
    assert parse_plan(_plan_text(profile="fullstack"), profile=None)[0] is Profile.FULLSTACK


@pytest.mark.parametrize("value", [None, "", 3])
def test_parse_plan_missing_profile(value):
    assert 'missing "profile"' in _error(_plan_text(profile=value))


def test_parse_plan_unknown_profile():
    message = _error(_plan_text(profile="desktop"))
    assert "desktop" in message and "lib, cli, api" in message


def test_parse_plan_without_json():
    assert "JSON" in _error("I could not do it.")


@pytest.mark.parametrize("epics", [[], "EPIC-1", None])
def test_parse_plan_rejects_missing_epics(epics):
    data = {"profile": "cli", "stories": [_story_dict()]}
    if epics is not None:
        data["epics"] = epics
    assert '"epics"' in _error(json.dumps(data))


@pytest.mark.parametrize("epic", [{"title": "no id"}, {"id": "  "}, "EPIC-1"])
def test_parse_plan_rejects_epic_without_id(epic):
    assert "epic 1" in _error(_plan_text(epics=[epic]))


def test_parse_plan_rejects_duplicate_epic():
    epics = [{"id": "EPIC-1", "title": "a"}, {"id": "EPIC-1", "title": "b"}]
    assert "duplicate epic id EPIC-1" in _error(_plan_text(epics=epics))


def test_parse_plan_epic_title_defaults_to_id():
    _, epics, _ = parse_plan(_plan_text(epics=[{"id": "EPIC-1"}]), profile=None)
    assert epics[0].title == "EPIC-1" and epics[0].description == ""


@pytest.mark.parametrize("stories", [[], None, {"id": "US-1"}])
def test_parse_plan_rejects_missing_stories(stories):
    data = {"profile": "cli", "epics": [{"id": "EPIC-1", "title": "t"}]}
    if stories is not None:
        data["stories"] = stories
    assert '"stories"' in _error(json.dumps(data))


def test_parse_plan_rejects_story_not_object():
    assert "story 2 is not a JSON object" in _error(_plan_text([_story_dict(), "US-2"]))


@pytest.mark.parametrize("sid", ["US1", "us-1", "US-0", "STORY-1", "US-01", "", 1])
def test_parse_plan_rejects_bad_story_id(sid):
    assert "must look like US-1" in _error(_plan_text([_story_dict(sid)]))


def test_parse_plan_rejects_duplicate_story():
    assert "duplicate story id US-1" in _error(_plan_text([_story_dict(), _story_dict()]))


def test_parse_plan_rejects_unknown_epic():
    message = _error(_plan_text([_story_dict(epic_id="EPIC-9")]))
    assert "US-1" in message and "EPIC-9" in message and "EPIC-1" in message


def test_parse_plan_rejects_missing_epic_id():
    story = _story_dict()
    del story["epic_id"]
    assert '"epic_id"' in _error(_plan_text([story]))


@pytest.mark.parametrize("title", ["", "   ", None])
def test_parse_plan_rejects_empty_title(title):
    assert 'story US-1: "title" is empty' in _error(_plan_text([_story_dict(title=title)]))


@pytest.mark.parametrize("criteria", [[], None, "one criterion", {"text": "x"}])
def test_parse_plan_rejects_missing_criteria(criteria):
    assert 'story US-1: "criteria" must be a non-empty list' in _error(
        _plan_text([_story_dict(criteria=criteria)]))


@pytest.mark.parametrize("bad", ["", "  ", {"text": ""}, {"description": "x"}, 3, None])
def test_parse_plan_rejects_empty_criterion(bad):
    message = _error(_plan_text([_story_dict(criteria=["ok", bad])]))
    assert "story US-1: criterion 2 is empty" in message


def test_parse_plan_rejects_unknown_dependency():
    message = _error(_plan_text([_story_dict(depends_on=["US-7"])]))
    assert "US-7" in message and "not a story of this plan" in message


def test_parse_plan_rejects_self_dependency():
    assert "story US-1: depends on itself" in _error(_plan_text([_story_dict(depends_on=["US-1"])]))


@pytest.mark.parametrize("deps", [3, [1], {"id": "US-1"}])
def test_parse_plan_rejects_malformed_depends_on(deps):
    message = _error(_plan_text([_story_dict(), _story_dict("US-2", depends_on=deps)]))
    assert 'story US-2: "depends_on" must be a list' in message


def test_parse_plan_depends_on_lenient_forms():
    stories = [_story_dict(), _story_dict("US-2", depends_on="US-1"),
               _story_dict("US-3", depends_on=["US-1", " US-2 ", "US-1"]),
               _story_dict("US-4", depends_on=None)]
    _, _, parsed = parse_plan(_plan_text(stories), profile=None)
    assert [s.depends_on for s in parsed] == [[], ["US-1"], ["US-1", "US-2"], []]


def test_parse_plan_rejects_two_cycle():
    stories = [_story_dict("US-1", depends_on=["US-2"]), _story_dict("US-2", depends_on=["US-1"])]
    assert "dependency cycle: US-1 -> US-2 -> US-1" in _error(_plan_text(stories))


def test_parse_plan_rejects_longer_cycle_behind_a_valid_story():
    stories = [_story_dict("US-1"), _story_dict("US-2", depends_on=["US-1", "US-4"]),
               _story_dict("US-3", depends_on=["US-2"]), _story_dict("US-4", depends_on=["US-3"])]
    assert "dependency cycle: US-2 -> US-4 -> US-3 -> US-2" in _error(_plan_text(stories))


def test_parse_plan_accepts_diamond_dependencies():
    stories = [_story_dict("US-1"), _story_dict("US-2", depends_on=["US-1"]),
               _story_dict("US-3", depends_on=["US-1"]), _story_dict("US-4", depends_on=["US-2", "US-3"])]
    assert len(parse_plan(_plan_text(stories), profile=None)[2]) == 4


@pytest.mark.parametrize("value,expected", [
    (1, 1), (5, 5), (0, 1), (-3, 1), (9, 5), ("2", 2), ("high", 3), (None, 3), (True, 3), (2.7, 2),
])
def test_parse_plan_priority_is_clamped(value, expected):
    _, _, parsed = parse_plan(_plan_text([_story_dict(priority=value)]), profile=None)
    assert parsed[0].priority == expected


def test_parse_plan_priority_defaults_to_3():
    story = _story_dict()
    del story["priority"]
    assert parse_plan(_plan_text([story]), profile=None)[2][0].priority == 3


def test_parse_plan_reports_every_error_at_once():
    stories = [_story_dict(title="", criteria=[]), _story_dict("US-2", epic_id="X", depends_on=["US-9"])]
    message = _error(_plan_text(stories))
    assert message.startswith("invalid plan:")
    for part in ('"title" is empty', '"criteria" must be', "'X' is not an epic", "'US-9'"):
        assert part in message


def test_parse_plan_optional_fields_default():
    story = {"id": "US-1", "epic_id": "EPIC-1", "title": "t", "criteria": ["c"]}
    parsed = parse_plan(_plan_text([story]), profile=None)[2][0]
    assert (parsed.description, parsed.gherkin, parsed.depends_on, parsed.priority) == ("", "", [], 3)


# --------------------------------------------------------------------------- parse_qa


def _story(sid="US-1", n=2) -> Story:
    return Story(id=sid, epic_id="EPIC-1", title="t",
                 criteria=[AcceptanceCriterion(id=f"{sid}.AC-{i}", text=f"c{i}") for i in range(1, n + 1)])


def _qa(*entries) -> str:
    return "Tests written and failing.\n" + json.dumps({"tests": list(entries)})


F1 = "tests/acceptance/test_us_1.py"


def test_parse_qa_happy_path_orders_merges_and_dedupes():
    text = _qa({"ac_id": "US-1.AC-2", "nodeids": [f"{F1}::test_ac2_b"]},
               {"ac_id": "US-1.AC-1", "nodeids": [f"{F1}::test_ac1_a", f"{F1}::test_ac1_a"]},
               {"ac_id": "AC-1", "nodeids": [f"./{F1}::test_ac1_c[case-1]"]})
    tests = parse_qa(text, _story())
    assert [(t.ac_id, t.nodeids) for t in tests] == [
        ("US-1.AC-1", [f"{F1}::test_ac1_a", f"{F1}::test_ac1_c[case-1]"]),
        ("US-1.AC-2", [f"{F1}::test_ac2_b"]),
    ]


def test_parse_qa_accepts_single_nodeid_string():
    tests = parse_qa(_qa({"ac_id": "US-1.AC-1", "nodeids": f"{F1}::test_ac1_a"}), _story(n=1))
    assert tests[0].nodeids == [f"{F1}::test_ac1_a"]


def test_parse_qa_rejects_missing_criterion():
    message = str(pytest.raises(PlanError, parse_qa,
                                _qa({"ac_id": "US-1.AC-1", "nodeids": [f"{F1}::test_ac1_a"]}), _story()).value)
    assert "criteria without any test: US-1.AC-2" in message


def test_parse_qa_rejects_criterion_with_empty_nodeids():
    text = _qa({"ac_id": "US-1.AC-1", "nodeids": []})
    with pytest.raises(PlanError, match="criteria without any test: US-1.AC-1"):
        parse_qa(text, _story(n=1))


def test_parse_qa_rejects_unknown_ac_id():
    text = _qa({"ac_id": "US-1.AC-1", "nodeids": [f"{F1}::test_ac1_a"]},
               {"ac_id": "US-2.AC-1", "nodeids": [f"{F1}::test_x"]})
    with pytest.raises(PlanError, match=r"'US-2\.AC-1' is not a criterion of US-1"):
        parse_qa(text, _story(n=1))


@pytest.mark.parametrize("nodeid,reason", [
    ("tests\\acceptance\\test_us_1.py::test_ac1_a", "POSIX"),
    (F1, "must look like"),
    (f"{F1}::", "must look like"),
    ("tests/acceptance/test_us_2.py::test_ac1_a", f"must be in {F1}"),
    ("tests/unit/test_us_1.py::test_ac1_a", f"must be in {F1}"),
    ("test_us_1.py::test_ac1_a", f"must be in {F1}"),
])
def test_parse_qa_rejects_bad_nodeids(nodeid, reason):
    with pytest.raises(PlanError, match=reason):
        parse_qa(_qa({"ac_id": "US-1.AC-1", "nodeids": [nodeid]}), _story(n=1))


def test_parse_qa_story_ten_does_not_accept_story_one_file():
    story = _story("US-10", n=1)
    ok = parse_qa(_qa({"ac_id": "US-10.AC-1", "nodeids": ["tests/acceptance/test_us_10.py::t"]}), story)
    assert ok[0].nodeids == ["tests/acceptance/test_us_10.py::t"]
    with pytest.raises(PlanError, match="test_us_10.py"):
        parse_qa(_qa({"ac_id": "US-10.AC-1", "nodeids": [f"{F1}::t"]}), story)


@pytest.mark.parametrize("text", [
    '{"tests": []}', '{"tests": "x"}', '{"summary": "x"}',
])
def test_parse_qa_rejects_missing_tests(text):
    with pytest.raises(PlanError, match='"tests"'):
        parse_qa(text, _story())


def test_parse_qa_rejects_malformed_nodeids_and_entries():
    text = _qa({"ac_id": "US-1.AC-1", "nodeids": 3}, "US-1.AC-1")
    message = str(pytest.raises(PlanError, parse_qa, text, _story(n=1)).value)
    assert '"nodeids" must be a list' in message and "tests[2]" in message


def test_parse_qa_without_json():
    with pytest.raises(PlanError, match="JSON"):
        parse_qa("The tests are written.", _story())


# --------------------------------------------------------------------------- parse_dev


def test_parse_dev_full_answer():
    text = 'All green.\n```json\n{"summary": " Built it. ", "dependencies_added": ["argon2-cffi", " x ", "x"]}\n```'
    assert parse_dev(text) == {"summary": "Built it.", "dependencies_added": ["argon2-cffi", "x"]}


@pytest.mark.parametrize("text", ["no json at all", "", None, "{not json"])
def test_parse_dev_defaults_without_json(text):
    assert parse_dev(text) == {"summary": "", "dependencies_added": []}


@pytest.mark.parametrize("data,expected", [
    ({"summary": 3, "dependencies_added": "httpx"}, {"summary": "", "dependencies_added": ["httpx"]}),
    ({"dependencies_added": [1, 2]}, {"summary": "", "dependencies_added": []}),
    ({"summary": "s", "dependencies_added": None}, {"summary": "s", "dependencies_added": []}),
    ({"other": True}, {"summary": "", "dependencies_added": []}),
])
def test_parse_dev_is_lenient(data, expected):
    assert parse_dev(json.dumps(data)) == expected


# --------------------------------------------------------------------------- next_ready


def _s(sid, priority=3, status=StoryStatus.TODO, deps=()):
    return Story(id=sid, epic_id="E", title=sid, priority=priority, status=status,
                 depends_on=list(deps), criteria=[AcceptanceCriterion(id=f"{sid}.AC-1", text="c")])


def test_next_ready_empty_and_all_done():
    assert next_ready([]) is None
    assert next_ready([_s("US-1", status=StoryStatus.DONE)]) is None


def test_next_ready_lowest_priority_number_first():
    stories = [_s("US-1", priority=3), _s("US-2", priority=1), _s("US-3", priority=2)]
    assert next_ready(stories).id == "US-2"


def test_next_ready_numeric_story_order_on_ties():
    stories = [_s("US-10"), _s("US-2"), _s("US-11")]
    assert next_ready(stories).id == "US-2"


def test_next_ready_waits_for_dependencies():
    stories = [_s("US-1", priority=5), _s("US-2", priority=1, deps=["US-1"])]
    assert next_ready(stories).id == "US-1"
    stories[0].status = StoryStatus.DONE
    assert next_ready(stories).id == "US-2"


def test_next_ready_skips_non_todo_stories():
    stories = [_s("US-1", status=StoryStatus.IN_PROGRESS), _s("US-2", status=StoryStatus.FAILED),
               _s("US-3", status=StoryStatus.DONE), _s("US-4", priority=4)]
    assert next_ready(stories).id == "US-4"


def test_next_ready_none_when_blocked():
    stories = [_s("US-1", status=StoryStatus.FAILED), _s("US-2", deps=["US-1"]), _s("US-3", deps=["US-9"])]
    assert next_ready(stories) is None
