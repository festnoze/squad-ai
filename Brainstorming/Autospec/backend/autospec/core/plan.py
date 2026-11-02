"""Parse and validate what the PM, PO, QA and dev agents answer; pick the next story.

Pure and deterministic. Every ``PlanError`` message is written to be sent back to
the agent as is, so it can correct its answer in one round.
"""

from __future__ import annotations

import re

from .jsonx import JsonNotFound, extract_json
from .models import AcceptanceCriterion, AcceptanceTest, Epic, Profile, Story, StoryStatus

_STORY_ID = re.compile(r"^US-([1-9][0-9]*)$")
_PROFILES = ", ".join(p.value for p in Profile)


class PlanError(ValueError):
    """An agent answer the factory cannot use; the message explains what to fix."""


def story_number(story_id: str) -> int:
    """``"US-12"`` -> 12. Raises PlanError for an id that is not ``US-<n>``."""
    match = _STORY_ID.match(story_id)
    if not match:
        raise PlanError(f"story id {story_id!r} must look like US-1, US-2...")
    return int(match.group(1))


def acceptance_file(story_id: str) -> str:
    """Repo-relative POSIX path of the QA acceptance tests of a story."""
    return f"tests/acceptance/test_us_{story_number(story_id)}.py"


def _load(text: str, what: str) -> dict:
    try:
        return extract_json(text)
    except JsonNotFound as exc:
        raise PlanError(f"{what}: {exc}; end the answer with the requested JSON object") from exc


def parse_brief(text: str) -> str:
    """The PM brief: ``{"brief": "<markdown>"}`` with a non-empty string."""
    brief = _load(text, "brief").get("brief")
    if not isinstance(brief, str) or not brief.strip():
        raise PlanError('the JSON object must have a non-empty string field "brief"')
    return brief.strip()


def _text(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""


def _profile(value: object, forced: Profile | str | None) -> Profile:
    if forced is not None:
        return Profile(forced)
    raw = _text(value).lower()
    if not raw:
        raise PlanError(f'missing "profile": one of {_PROFILES}')
    try:
        return Profile(raw)
    except ValueError:
        raise PlanError(f'unknown "profile" {value!r}: expected one of {_PROFILES}') from None


def _priority(value: object) -> int:
    if isinstance(value, bool):
        return 3
    try:
        number = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 3
    return min(5, max(1, number))


def _strings(value: object) -> list[str] | None:
    """A list of strings (a single string is accepted); None when malformed."""
    if value is None:
        return []
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        return None
    return list(dict.fromkeys(v.strip() for v in value if v.strip()))


def _criteria(raw: object, sid: str, errors: list[str]) -> list[AcceptanceCriterion]:
    if not isinstance(raw, list) or not raw:
        errors.append(f'story {sid}: "criteria" must be a non-empty list of strings')
        return []
    criteria = []
    for index, item in enumerate(raw, start=1):
        text = _text(item.get("text") if isinstance(item, dict) else item)
        if not text:
            errors.append(f"story {sid}: criterion {index} is empty or not a string")
        criteria.append(AcceptanceCriterion(id=f"{sid}.AC-{index}", text=text))
    return criteria


def _gherkin(value: object) -> str:
    if isinstance(value, list):
        return "\n".join(str(line) for line in value)
    return value.strip() if isinstance(value, str) else ""


def _parse_epics(raw: object) -> list[Epic]:
    if not isinstance(raw, list) or not raw:
        raise PlanError('"epics" must be a non-empty list of {"id", "title", "description"}')
    epics: list[Epic] = []
    for index, item in enumerate(raw, start=1):
        eid = _text(item.get("id")) if isinstance(item, dict) else ""
        if not eid:
            raise PlanError(f'epic {index} has no "id" (expected EPIC-1, EPIC-2...)')
        if any(e.id == eid for e in epics):
            raise PlanError(f"duplicate epic id {eid}")
        epics.append(Epic(id=eid, title=_text(item.get("title")) or eid,
                          description=_text(item.get("description"))))
    return epics


def _find_cycle(stories: list[Story]) -> list[str]:
    """Return one dependency cycle as a list of ids (first id repeated), or []."""
    deps = {s.id: s.depends_on for s in stories}
    state: dict[str, int] = {}  # 1 = on the current path, 2 = fully explored

    def visit(sid: str, path: list[str]) -> list[str]:
        state[sid] = 1
        for dep in deps.get(sid, []):
            if state.get(dep) == 1:
                return path[path.index(dep):] + [dep]
            if dep in deps and dep not in state:
                cycle = visit(dep, path + [dep])
                if cycle:
                    return cycle
        state[sid] = 2
        return []

    for story in stories:
        if story.id not in state:
            cycle = visit(story.id, [story.id])
            if cycle:
                return cycle
    return []


def parse_plan(text: str, *, profile: Profile | str | None) -> tuple[Profile, list[Epic], list[Story]]:
    """The PO plan. ``profile`` (when not None) wins over the profile in the JSON."""
    data = _load(text, "plan")
    chosen = _profile(data.get("profile"), profile)
    epics = _parse_epics(data.get("epics"))
    epic_ids = [e.id for e in epics]
    raw_stories = data.get("stories")
    if not isinstance(raw_stories, list) or not raw_stories:
        raise PlanError('"stories" must be a non-empty list of story objects')

    errors: list[str] = []
    stories: list[Story] = []
    raw_ids = [_text(r.get("id")) if isinstance(r, dict) else "" for r in raw_stories]
    for index, (raw, sid) in enumerate(zip(raw_stories, raw_ids), start=1):
        if not isinstance(raw, dict):
            errors.append(f"story {index} is not a JSON object")
            continue
        if not _STORY_ID.match(sid):
            errors.append(f'story {index}: "id" {raw.get("id")!r} must look like US-1, US-2...')
            continue
        if raw_ids.count(sid) > 1 and sid in (s.id for s in stories):
            errors.append(f"duplicate story id {sid}")
            continue
        title = _text(raw.get("title"))
        if not title:
            errors.append(f'story {sid}: "title" is empty')
        epic_id = _text(raw.get("epic_id"))
        if epic_id not in epic_ids:
            errors.append(f'story {sid}: "epic_id" {epic_id!r} is not an epic of this plan '
                          f"(epics: {', '.join(epic_ids)})")
        depends_on = _strings(raw.get("depends_on"))
        if depends_on is None:
            errors.append(f'story {sid}: "depends_on" must be a list of story ids')
            depends_on = []
        for dep in depends_on:
            if dep == sid:
                errors.append(f"story {sid}: depends on itself")
            elif dep not in raw_ids:
                errors.append(f'story {sid}: depends_on {dep!r} is not a story of this plan '
                              f"(stories: {', '.join(i for i in raw_ids if i)})")
        stories.append(Story(
            id=sid, epic_id=epic_id, title=title, description=_text(raw.get("description")),
            criteria=_criteria(raw.get("criteria"), sid, errors), gherkin=_gherkin(raw.get("gherkin")),
            depends_on=depends_on, priority=_priority(raw.get("priority", 3)),
        ))
    if not errors:
        cycle = _find_cycle(stories)
        if cycle:
            errors.append(f"dependency cycle: {' -> '.join(cycle)}")
    if errors:
        raise PlanError("invalid plan:\n- " + "\n- ".join(errors))
    return chosen, epics, stories


def parse_qa(text: str, story: Story) -> list[AcceptanceTest]:
    """The QA mapping criterion -> nodeids; every criterion of ``story`` covered."""
    data = _load(text, "QA answer")
    raw_tests = data.get("tests")
    if not isinstance(raw_tests, list) or not raw_tests:
        raise PlanError('"tests" must be a non-empty list of {"ac_id", "nodeids"}')
    expected_file = acceptance_file(story.id)
    known = [c.id for c in story.criteria]
    mapping: dict[str, list[str]] = {}
    errors: list[str] = []
    for index, item in enumerate(raw_tests, start=1):
        ac_id = _text(item.get("ac_id")) if isinstance(item, dict) else ""
        if ac_id.startswith("AC-"):
            ac_id = f"{story.id}.{ac_id}"
        if ac_id not in known:
            errors.append(f"tests[{index}]: ac_id {ac_id!r} is not a criterion of {story.id} "
                          f"(criteria: {', '.join(known)})")
            continue
        nodeids = _strings(item.get("nodeids"))
        if nodeids is None:
            errors.append(f'{ac_id}: "nodeids" must be a list of strings')
            continue
        for nodeid in nodeids:
            nodeid = nodeid.removeprefix("./")
            path, sep, name = nodeid.partition("::")
            if "\\" in path:
                errors.append(f"{ac_id}: nodeid {nodeid!r} must use / (POSIX path)")
            elif not sep or not name:
                errors.append(f"{ac_id}: nodeid {nodeid!r} must look like {expected_file}::test_name")
            elif path != expected_file:
                errors.append(f"{ac_id}: nodeid {nodeid!r} must be in {expected_file}")
            elif nodeid not in mapping.setdefault(ac_id, []):
                mapping[ac_id].append(nodeid)
    missing = [ac for ac in known if not mapping.get(ac)]
    if missing:
        errors.append(f"criteria without any test: {', '.join(missing)}")
    if errors:
        raise PlanError(f"invalid QA answer for {story.id}:\n- " + "\n- ".join(errors))
    return [AcceptanceTest(ac_id=ac, nodeids=mapping[ac]) for ac in known]


def parse_dev(text: str) -> dict:
    """The dev summary. Lenient: the factory verifies the work independently anyway."""
    try:
        data = extract_json(text)
    except JsonNotFound:
        data = {}
    summary = data.get("summary")
    deps = _strings(data.get("dependencies_added"))
    return {"summary": summary.strip() if isinstance(summary, str) else "",
            "dependencies_added": deps or []}


def _order(story: Story) -> tuple[int, int, str]:
    match = _STORY_ID.match(story.id)
    return story.priority, int(match.group(1)) if match else 1 << 30, story.id


def next_ready(stories: list[Story]) -> Story | None:
    """The TODO story to build next: all its dependencies DONE, lowest priority
    number first, then lowest story number (US-2 before US-10). None when none is ready."""
    done = {s.id for s in stories if s.status == StoryStatus.DONE}
    ready = [s for s in stories
             if s.status == StoryStatus.TODO and all(d in done for d in s.depends_on)]
    return min(ready, key=_order) if ready else None
