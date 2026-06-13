from autospec.models import (
    AcceptanceCriterion,
    FeatureHypothesis,
    PlannedTest,
    StoryStatus,
    TestState,
    UserStory,
)


def make_story(tests, status=StoryStatus.IN_PROGRESS) -> UserStory:
    return UserStory(
        id="US-1",
        epic_id="EPIC-1",
        title="s",
        acceptance_criteria=[AcceptanceCriterion(id="AC-1", text="x")],
        test_plan=tests,
        status=status,
    )


def test_criterion_nonexistent_without_tests():
    story = make_story([])
    assert story.criterion_state("AC-1") == TestState.NONEXISTENT


def test_criterion_nonexistent_when_tests_not_written():
    story = make_story([PlannedTest(id="UT-1", criteria=["AC-1"])])
    assert story.criterion_state("AC-1") == TestState.NONEXISTENT


def test_criterion_red_if_any_test_red():
    story = make_story([
        PlannedTest(id="UT-1", criteria=["AC-1"], status=TestState.GREEN),
        PlannedTest(id="UT-2", criteria=["AC-1"], status=TestState.RED),
    ])
    assert story.criterion_state("AC-1") == TestState.RED


def test_criterion_green_only_when_all_green():
    story = make_story([
        PlannedTest(id="UT-1", criteria=["AC-1"], status=TestState.GREEN),
        PlannedTest(id="UT-2", criteria=["AC-1"], status=TestState.GREEN),
    ])
    assert story.criterion_state("AC-1") == TestState.GREEN


def test_criterion_not_green_if_one_missing():
    story = make_story([
        PlannedTest(id="UT-1", criteria=["AC-1"], status=TestState.GREEN),
        PlannedTest(id="UT-2", criteria=["AC-1"], status=TestState.NONEXISTENT),
    ])
    assert story.criterion_state("AC-1") == TestState.NONEXISTENT


def test_done_story_is_green_even_without_tests():
    story = make_story([], status=StoryStatus.DONE)
    assert story.criterion_state("AC-1") == TestState.GREEN


def test_hypothesis_scores_clamped_to_1_5():
    h = FeatureHypothesis(id="FH-1", title="t", value=42, complexity=0, rank=-3)
    assert h.value == 5
    assert h.complexity == 1
    assert h.rank == 1
    assert h.score == 5.0


def test_story_priority_clamped_to_1_5():
    low = make_story([]).model_dump()
    low["priority"] = 0
    assert UserStory.model_validate(low).priority == 1
    low["priority"] = 99
    assert UserStory.model_validate(low).priority == 5
