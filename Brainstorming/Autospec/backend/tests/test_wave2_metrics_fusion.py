"""Wave 2 / GENERATION_FUSION_REVIEW P3, agent M: the fusion-loop counters that
S3 wrote into ``PlanCalibration`` are now READABLE from outside the pipeline.

Two exposure points are pinned here:
  * ``metrics.compute_metrics`` gains a ``fusion`` block aggregated over every
    project AND every iteration (``ProjectState.calibration`` is a
    ``dict[int, PlanCalibration]``), served as-is by ``GET /api/metrics``;
  * ``prompts.retro_review`` injects the same counters for the CURRENT
    iteration, plus the instruction that tells the retrospective agent to read
    an infra-dominated fusion loop as an environment problem and never as a
    code lesson.
"""

import json
from types import SimpleNamespace

from autospec.agents import prompts
from autospec.metrics import compute_metrics, fusion_snapshot
from autospec.models import PlanCalibration, ProjectState, StoryStatus, UserStory

FUSION_KEYS = {
    "suite_runs",
    "items_delivered",
    "suites_per_item",
    "canary_verdicts",
    "canary_reverts",
    "canary_batches",
    "canary_bisect_reverts",
    "merge_requeues",
    "requeue_refunds",
    "infra_retries",
    "p2b_resumes",
    "orphan_resets",
}


def _state(sid: str, calibration: dict | None = None) -> ProjectState:
    state = ProjectState(id=sid, name=sid, goal="g")
    if calibration:
        state.calibration = calibration
    return state


def test_compute_metrics_aggregates_fusion_over_projects_and_iterations():
    """Two projects, three iterations: every scalar is summed, the verdict
    histogram is merged key by key, and the ratio is recomputed from the SUMS
    (not averaged from the per-iteration model property)."""
    first = _state(
        "p1",
        {
            1: PlanCalibration(
                suite_runs=40,
                items_delivered=5,
                canary_reverts=2,
                canary_batches=1,
                merge_requeues=3,
                infra_retries=4,
                canary_verdicts={"green": 4, "semantic": 2, "infra_healed": 1},
            ),
            2: PlanCalibration(
                suite_runs=20,
                items_delivered=3,
                canary_bisect_reverts=1,
                requeue_refunds=2,
                p2b_resumes=1,
                orphan_resets=1,
                canary_verdicts={"green": 3, "infra_healed": 2},
            ),
        },
    )
    second = _state(
        "p2",
        {
            1: PlanCalibration(
                suite_runs=10,
                items_delivered=2,
                canary_batches=2,
                canary_verdicts={"batch_green": 2},
            )
        },
    )

    fusion = compute_metrics([first, second])["fusion"]

    assert set(fusion) == FUSION_KEYS
    assert fusion["suite_runs"] == 70
    assert fusion["items_delivered"] == 10
    # 70 / 10, computed on the totals: iteration-by-iteration the ratios are
    # 8.0, 6.67 and 5.0, whose mean (6.56) would be a different number.
    assert fusion["suites_per_item"] == 7.0
    assert fusion["canary_reverts"] == 2
    assert fusion["canary_batches"] == 3
    assert fusion["canary_bisect_reverts"] == 1
    assert fusion["merge_requeues"] == 3
    assert fusion["requeue_refunds"] == 2
    assert fusion["infra_retries"] == 4
    assert fusion["p2b_resumes"] == 1
    assert fusion["orphan_resets"] == 1
    assert fusion["canary_verdicts"] == {
        "green": 7,
        "semantic": 2,
        "infra_healed": 3,
        "batch_green": 2,
    }


def test_compute_metrics_without_any_calibration_reports_zeros():
    """A project built before P3 (or one that never merged anything) must not
    make the block disappear, and must not divide by zero."""
    plain = _state("p1")
    plain.stories = [
        UserStory(id="US-1", epic_id="E", title="t", status=StoryStatus.DONE, attempts=1)
    ]

    for metrics in (compute_metrics([plain]), compute_metrics([])):
        fusion = metrics["fusion"]
        assert set(fusion) == FUSION_KEYS
        assert fusion["suites_per_item"] == 0.0
        assert fusion["canary_verdicts"] == {}
        assert all(
            fusion[key] == 0 for key in FUSION_KEYS - {"canary_verdicts", "suites_per_item"}
        )


def test_fusion_snapshot_tolerates_a_calibration_missing_the_new_fields():
    """The aggregation reads every counter with a getattr default, so a state
    deserialized by an older model (or a future one missing a counter) degrades
    to zero instead of raising."""
    legacy = SimpleNamespace(suite_runs=6, merge_requeues=1)

    fusion = fusion_snapshot([legacy, PlanCalibration(suite_runs=4, items_delivered=2)])

    assert fusion["suite_runs"] == 10
    assert fusion["merge_requeues"] == 1
    assert fusion["items_delivered"] == 2
    assert fusion["suites_per_item"] == 5.0
    assert fusion["canary_verdicts"] == {}


def test_a_delivered_item_without_a_single_suite_keeps_the_ratio_at_zero():
    """Guard on the floor: the denominator floors at 1, the numerator does not
    get a floor, so an item delivered without any suite reads 0.0 and not 1.0."""
    fusion = fusion_snapshot([PlanCalibration(items_delivered=3)])

    assert fusion["items_delivered"] == 3
    assert fusion["suites_per_item"] == 0.0


def test_retro_review_carries_the_fusion_block_of_the_current_iteration():
    """The retrospective sees the counters of the iteration that just ended,
    not those of the previous ones."""
    state = _state("p1")
    state.iteration = 2
    state.calibration = {
        1: PlanCalibration(suite_runs=99, items_delivered=1, canary_verdicts={"green": 99}),
        2: PlanCalibration(
            suite_runs=12,
            items_delivered=4,
            merge_requeues=2,
            infra_retries=5,
            canary_verdicts={"green": 2, "infra_persistent": 3},
        ),
    }

    prompt = prompts.retro_review(state)
    signals = json.loads(prompt.split("\n\n")[0].splitlines()[-1])

    assert set(signals["fusion"]) == FUSION_KEYS
    assert signals["fusion"]["suite_runs"] == 12
    assert signals["fusion"]["items_delivered"] == 4
    assert signals["fusion"]["suites_per_item"] == 3.0
    assert signals["fusion"]["merge_requeues"] == 2
    assert signals["fusion"]["infra_retries"] == 5
    assert signals["fusion"]["canary_verdicts"] == {"green": 2, "infra_persistent": 3}
    # The iteration-1 counters must not leak into the iteration-2 retro.
    assert '"suite_runs": 99' not in prompt


def test_retro_review_reports_zeros_without_creating_a_calibration_bucket():
    """Building a prompt is a read: it must not materialize an empty
    calibration for the current iteration (``calibration_for`` would)."""
    state = _state("p1")

    prompt = prompts.retro_review(state)

    assert state.calibration == {}
    assert '"suite_runs": 0' in prompt
    assert '"suites_per_item": 0.0' in prompt


def test_retro_review_forbids_turning_an_infra_fusion_loop_into_a_code_lesson():
    """The instruction that makes the block actionable: a costly loop or
    infra-dominated verdicts are factory settings, not code."""
    state = _state("p1")

    prompt = prompts.retro_review(state)

    assert "fusion" in prompt
    assert "suites_per_item" in prompt
    assert "canary_verdicts" in prompt
    assert "infra_persistent" in prompt
    assert "ENVIRONNEMENT" in prompt
    assert "canari par rafale" in prompt
    # French prompt, and the em dash (U+2014) stays banned in produced content.
    assert chr(0x2014) not in prompt
