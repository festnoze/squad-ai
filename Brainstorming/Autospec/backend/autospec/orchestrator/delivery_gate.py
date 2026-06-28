"""Definition-of-Done checks for a generated Autospec project.

The regular test runners answer "does the suite that exists pass?". This gate
answers the broader delivery question: "did every planned work item actually
ship, and do the visible acceptance criteria have credible evidence?"  It is
kept small and deterministic so the lifecycle can run it before declaring an
iteration complete.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..models import ProjectState, StoryStatus, TestState, UserStory


@dataclass(frozen=True)
class DeliveryIssue:
    code: str
    message: str
    item_id: str = ""
    severity: str = "blocker"  # blocker | warning


@dataclass(frozen=True)
class DefinitionOfDoneResult:
    ready: bool
    issues: tuple[DeliveryIssue, ...]

    @property
    def blockers(self) -> tuple[DeliveryIssue, ...]:
        return tuple(i for i in self.issues if i.severity == "blocker")

    @property
    def warnings(self) -> tuple[DeliveryIssue, ...]:
        return tuple(i for i in self.issues if i.severity != "blocker")

    def messages(self) -> list[str]:
        return [i.message for i in self.issues]


def _criterion_has_green_evidence(story: UserStory, criterion_id: str) -> bool:
    tests = story.tests_for_criterion(criterion_id)
    if not tests:
        return False
    return all(t.status == TestState.GREEN for t in tests)


def evaluate_definition_of_done(
    state: ProjectState,
    *,
    iteration: int | None = None,
    require_ui_evidence: bool = False,
    strict_criteria: bool = False,
) -> DefinitionOfDoneResult:
    """Evaluate the deterministic delivery gate for one iteration.

    ``strict_criteria`` upgrades missing per-criterion test evidence to blockers.
    With it off, trivial Gherkin-only stories can still pass while the operator
    sees warnings in ``state.delivery_issues``.
    """
    stories = (
        state.stories
        if iteration is None
        else state.stories_of_iteration(iteration)
    )
    issues: list[DeliveryIssue] = []
    if not stories:
        issues.append(
            DeliveryIssue(
                code="no_stories",
                message="Aucune user story n'a été planifiée pour cette livraison.",
            )
        )
        return DefinitionOfDoneResult(ready=False, issues=tuple(issues))

    for story in stories:
        effective = story.effective_status()
        if effective != StoryStatus.DONE:
            issues.append(
                DeliveryIssue(
                    code="story_not_done",
                    item_id=story.id,
                    message=(
                        f"{story.id} n'est pas livrée : statut effectif "
                        f"{effective.value}."
                    ),
                )
            )

        for task in story.tasks:
            if task.status != StoryStatus.DONE:
                issues.append(
                    DeliveryIssue(
                        code="task_not_done",
                        item_id=task.id,
                        message=(
                            f"{task.id} ({story.id}) n'est pas livrée : "
                            f"statut {task.status.value}."
                        ),
                    )
                )

        if not story.acceptance_criteria:
            issues.append(
                DeliveryIssue(
                    code="no_acceptance_criteria",
                    item_id=story.id,
                    severity="warning",
                    message=f"{story.id} n'a aucun critère d'acceptance explicite.",
                )
            )
        elif not story.test_plan and not story.gherkin.strip():
            issues.append(
                DeliveryIssue(
                    code="no_acceptance_evidence",
                    item_id=story.id,
                    severity="blocker" if strict_criteria else "warning",
                    message=(
                        f"{story.id} n'a ni Gherkin ni test plan vérifiable pour "
                        "ses critères d'acceptance."
                    ),
                )
            )
        elif story.test_plan:
            for criterion in story.acceptance_criteria:
                if not _criterion_has_green_evidence(story, criterion.id):
                    issues.append(
                        DeliveryIssue(
                            code="criterion_not_green",
                            item_id=story.id,
                            severity="blocker" if strict_criteria else "warning",
                            message=(
                                f"{story.id}/{criterion.id} n'a pas de preuve "
                                "de test verte reliée au critère."
                            ),
                        )
                    )

        if require_ui_evidence and story.ui and not story.ui_tests:
            issues.append(
                DeliveryIssue(
                    code="ui_tests_missing",
                    item_id=story.id,
                    message=(
                        f"{story.id} est une story UI mais aucun test UI "
                        "rejouable n'a été déclaré."
                    ),
                )
            )

    blockers = [i for i in issues if i.severity == "blocker"]
    return DefinitionOfDoneResult(ready=not blockers, issues=tuple(issues))
