---
name: bdd-gherkin
description: |
  Decompose a Gherkin acceptance scenario into per-layer unit tests, outside-in
  (London school), BEFORE implementation — then wire the pytest-bdd step
  definitions and link each planned test to the exact pytest node ids. This is the
  QA architect's method: the Gherkin keeps the end-to-end functional vision, and
  under it each architecture layer gets its own test that mocks its direct
  collaborators.

  Use when:
  - Turning a `.feature` scenario into a plan of unit tests
  - Writing pytest-bdd step definitions for a Given/When/Then
  - Deciding the granularity of test decomposition for a story
  - Mapping planned tests (UT-x) to the pytest node ids actually written

  Triggers: gherkin, BDD, acceptance test, outside-in, London school, pytest-bdd,
  step definitions, scenario, decompose tests, test plan, given when then
---

# Outside-in BDD decomposition

The Gherkin scenario is the contract; do NOT modify it. Work top-down.

## 1. Decompose (QA, before any code)
Walk the architecture layers from the outside in and give each its own unit test;
each test mocks its DIRECT collaborators only:
- facade calls the service? → router test mocking the service
- service calls the repository / another service / a client? → service test
  mocking those
- repository/domain logic? → focused test at that layer

Adapt granularity to the story: a trivial pure function needs 0–2 tests; a
medium/large story decomposes layer by layer (api → facade → service →
repository → domain). Order tests from most-external to most-internal (the write
order). Attach each test to the acceptance-criterion id(s) it covers; every
criterion must be covered by at least one test.

## 2. Wire pytest-bdd (Dev, red first)
Bind every Given/When/Then to a step in `tests/steps/test_{story}.py`:
```python
from pytest_bdd import scenarios, given, when, then, parsers
scenarios("../../<feature_rel_path>")

@given(parsers.parse("le nombre {n:d}"), target_fixture="a")
def _a(n): return n

@when("je les additionne", target_fixture="result")
def _sum(a, b): return add(a, b)

@then(parsers.parse("j'obtiens {expected:d}"))
def _check(result, expected): assert result == expected
```
Write the planned unit tests in `tests/unit/` (respect each `file_hint`), mock the
listed collaborators with `unittest.mock`, and run `uv run pytest` to confirm RED
before implementing. Then implement top-down until the whole suite is green.

## 3. Report node ids
For each planned test `UT-x`, report the EXACT pytest node ids you wrote
(`path/to/file.py::test_name`) so the orchestrator can read real outcomes from the
JSON report. Pair with `test-generator` for the per-layer test templates and
`architecture` for where each layer lives.
