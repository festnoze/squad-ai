---
name: test-generator
description: |
  Generate tests for different component types following project conventions.
  Supports unit tests (router, service), integration tests (repository), and E2E tests.

  Use when:
  - Need to generate unit tests for a router (mock service)
  - Need to generate unit tests for a service (mock repository)
  - Need to generate integration tests for a repository (real DB)
  - Need to generate E2E tests for complete user workflows

  Triggers: "generate tests", "create tests", "add tests", "unit tests",
  "integration tests", "e2e tests", "test router", "test service", "test repository"
---

# Test Generator Skill

Generate tests for SkillForge API components following project conventions and patterns.

## Output Format

```
RESULT:
  Test Type: {unit-router | unit-service | integration-repo | e2e}
  Entity: {entity_name}
  File: {file_path}
  Tests Generated: {count}
  Status: CREATED | UPDATED
```

---

## Workflow

```
1. IDENTIFY component to test
       |
       v
2. DETERMINE test type
       |
       +-- Router --> Unit test (mock service)
       |
       +-- Service --> Unit test (mock repository)
       |
       +-- Repository --> Integration test (real DB)
       |
       +-- Workflow --> E2E test (full stack)
       |
       v
3. CHECK if test file exists
       |
       +-- YES --> Add new tests to existing file
       |
       +-- NO --> Create new test file
       |
       v
4. GENERATE tests following patterns
       |
       v
5. Return created test details
```

---

## Phase 1: Identify Component

Determine what to test:

| Question | Examples |
|----------|----------|
| **Component Type** | Router, Service, Repository, Workflow |
| **Entity** | User, Thread, Message, Notification |
| **Methods to Test** | acreate, aget_by_id, aupdate, adelete |
| **Scenarios** | success, not_found, validation_error, conflict |

---

## Phase 2: Determine Test Type and Location

| Test Type | Location | Pattern | What to Mock |
|-----------|----------|---------|--------------|
| Unit (Router) | `tests/unit/facade/test_{entity}_router.py` | Mock service, test HTTP | Service class |
| Unit (Service) | `tests/unit/application/test_{entity}_service.py` | Mock repo, test logic | Repository class |
| Integration (Repo) | `tests/integration/test_{entity}_repository.py` | Real DB, test queries | Nothing (uses test DB) |
| E2E | `tests/e2e/test_{workflow}.py` | Full stack | Auth only |

---

## Phase 3: Check Existing Tests

### Search for existing test file

```
Glob: tests/unit/facade/test_{entity}_router.py
Glob: tests/unit/application/test_{entity}_service.py
Glob: tests/integration/test_{entity}_*.py
Glob: tests/e2e/test_{workflow}.py
```

### Search for existing test methods

```
Grep: async def test_a{action}_{entity}
```

**If test exists** --> Add new scenarios or skip
**If no test** --> Create new test

---

## Phase 4: Generate Tests

### Naming Convention

**Test functions MUST follow this pattern:**

```
test_a{action}_{entity}_{scenario}
```

**Examples:**
- `test_acreate_notification_success`
- `test_aget_user_not_found`
- `test_aupdate_thread_validation_error`
- `test_adelete_message_unauthorized`

### Common Scenarios to Test

| Scenario | Description |
|----------|-------------|
| `success` | Happy path, operation succeeds |
| `not_found` | Entity doesn't exist |
| `validation_error` | Invalid input data |
| `conflict` | Entity already exists |
| `unauthorized` | Missing/invalid authentication |
| `forbidden` | User doesn't have permission |
| `service_error` | Service/repository throws exception |

---

## Test Templates by Type

### Unit Test - Router

See [references/test-patterns.md](references/test-patterns.md#unit-router) for complete template.

**Key points:**
- Mock the service class
- Override authentication dependency
- Use TestClient from FastAPI
- Test HTTP status codes and response body

### Unit Test - Service

See [references/test-patterns.md](references/test-patterns.md#unit-service) for complete template.

**Key points:**
- Mock the repository class
- Test business logic and error handling
- Verify repository method calls
- Use `@pytest.fixture` for service setup

### Integration Test - Repository

See [references/test-patterns.md](references/test-patterns.md#integration-repo) for complete template.

**Key points:**
- Use `test_{entity}_repository` fixture (uses real test DB)
- Depends on `setup_test_session_manager` fixture
- Test actual database operations
- Clean state between tests (function scope)

### E2E Test

See [references/test-patterns.md](references/test-patterns.md#e2e) for complete template.

**Key points:**
- Use `client` fixture with full dependency chain
- Mock only authentication
- Test complete user flows
- Verify data persistence across steps

---

## Common Fixtures

See [references/fixtures.md](references/fixtures.md) for all available fixtures.

### Key Fixtures by Test Type

| Test Type | Required Fixtures |
|-----------|-------------------|
| Unit (Router) | `app`, `mock_{entity}_service`, `mock_jwt_payload` |
| Unit (Service) | `mock_{entity}_repository`, `service` (custom) |
| Integration | `test_{entity}_repository`, `setup_test_session_manager` |
| E2E | `app`, `client`, `mock_context_filter_request` |

---

## Authentication Mocking

### For Unit Tests (Router)

```python
@pytest.fixture
def mock_jwt_payload(self) -> JWTSkillForgePayload:
    return JWTSkillForgePayload(
        sid="test_session_123",
        client=8888,
        schoolId=1009,
        iss="uat-lms-studi.studi.fr",
        roles=["user"],
    )

# In test
app.dependency_overrides[authentication_required] = lambda: mock_jwt_payload
```

### For E2E Tests

```python
def _create_mock_auth_dependency(self, lms_user_id: int):
    async def mock_auth():
        return JWTSkillForgePayload(client=lms_user_id, exp=9999999999)
    return mock_auth

# In test
app.dependency_overrides[authentication_required] = self._create_mock_auth_dependency(lms_user_id)
```

---

## Error Assertions

### Expected Exceptions

```python
# For repository errors
with pytest.raises(ConflictError):
    await repo.acreate_entity(duplicate_entity)

with pytest.raises(NotFoundError):
    await repo.aupdate_entity(nonexistent_entity)

# For service errors
with pytest.raises(InternalServerException):
    await service.acreate_entity(invalid_data)
```

### HTTP Status Codes

```python
assert response.status_code == 200  # Success
assert response.status_code == 201  # Created
assert response.status_code == 400  # Bad Request / Validation Error
assert response.status_code == 401  # Unauthorized
assert response.status_code == 404  # Not Found
assert response.status_code == 409  # Conflict
assert response.status_code == 422  # Unprocessable Entity (Pydantic validation)
assert response.status_code == 500  # Internal Server Error
```

---

## Running Tests

```bash
# Activate venv first
.venv\Scripts\activate

# Run all tests
uv run python -m pytest

# Run specific test file
uv run python -m pytest tests/unit/application/test_user_service.py

# Run specific test function
uv run python -m pytest tests/unit/application/test_user_service.py::TestUserService::test_acreate_or_update_user_async

# Run with coverage
make test
```

---

## Checklist Before Generating Tests

- [ ] Identify component type (Router/Service/Repository/Workflow)
- [ ] Identify entity name (User/Thread/Message/etc.)
- [ ] Identify methods to test
- [ ] Identify scenarios to cover (success, error cases)
- [ ] Check if test file already exists
- [ ] Generate tests following naming convention
- [ ] Use correct fixtures for test type
- [ ] Mock dependencies appropriately
- [ ] Add proper assertions
