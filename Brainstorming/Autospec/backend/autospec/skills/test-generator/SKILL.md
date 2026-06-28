---
name: test-generator
description: |
  Generate tests for generated apps following project conventions, by component
  type and layer: unit tests (router → mock service; service → mock repository),
  integration tests (repository → real in-memory DB), and end-to-end tests (full
  stack, mock only auth). Encodes pytest/pytest-bdd patterns, async fixtures, the
  `test_a{action}_{entity}_{scenario}` naming, and the standard failure scenarios.

  Use when:
  - Writing unit tests for a router or a service
  - Writing integration tests for a repository
  - Writing an end-to-end test for a full user workflow
  - Choosing what scenarios (success/not-found/validation/conflict/error) to cover

  Triggers: generate tests, create tests, add tests, unit tests, integration
  tests, e2e tests, test router, test service, test repository, pytest, fixture
---

# Test generation by layer

Tests run with `uv run pytest`. Async tests use `@pytest.mark.asyncio`; mock async
collaborators with `unittest.mock.AsyncMock`.

| Layer | File | Mocks | Storage |
|---|---|---|---|
| router (unit) | `tests/unit/facade/test_{entity}_router.py` | the service | none |
| service (unit) | `tests/unit/application/test_{entity}_service.py` | the repository | none |
| repository (integ.) | `tests/integration/test_{entity}_repository.py` | nothing | in-memory DB |
| workflow (e2e) | `tests/e2e/test_{workflow}.py` | auth only | real test DB |

## Naming
`test_a{action}_{entity}_{scenario}` — e.g. `test_acreate_user_success`,
`test_aget_user_not_found`, `test_aupdate_thread_validation_error`.

## Scenarios to cover (pick those that apply)
- `_success` / `_returns_*` — happy path (200/201)
- `_not_found` — entity missing (404)
- `_validation_error` — bad input (400/422)
- `_conflict` / `_already_exists` — duplicate (409)
- `_unauthorized` / `_forbidden` — auth (401/403)
- `_raises_*` — a dependency errors (500)

## Arrange–Act–Assert skeleton (service unit test)
```python
@pytest.mark.asyncio
async def test_aget_user_success(service, mock_repository, sample_user):
    mock_repository.aget_user_by_id.return_value = sample_user      # Arrange
    result = await service.aget_user_by_id(sample_user.id)          # Act
    assert result == sample_user                                    # Assert
    mock_repository.aget_user_by_id.assert_awaited_once_with(sample_user.id)
```

## Error assertions
```python
with pytest.raises(NotFoundError) as exc:
    await service.aget_user_by_id(unknown_id)
assert "NOT_FOUND" in str(exc.value.code)
# endpoints:
assert response.status_code == 404
```

For acceptance-driven outside-in decomposition of a Gherkin scenario into the
per-layer unit tests above, pair this with the `bdd-gherkin` skill. See
`references/test-patterns.md` and `references/fixtures.md` for fuller templates.
