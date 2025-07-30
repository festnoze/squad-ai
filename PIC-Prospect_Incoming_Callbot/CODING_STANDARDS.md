# Coding Standards

This document defines the coding standards and conventions to follow when working on this project.

## Python Type Hints

### Use Built-in Types (Python 3.9+)
**✅ DO:**
```python
def process_data(items: list[str]) -> dict[str, int]:
    result: dict[str, int] = {}
    return result

def get_user(user_id: str) -> tuple[str, int] | None:
    return ("John", 25) if user_id else None
```

**❌ DON'T:**
```python
from typing import List, Dict, Tuple, Optional

def process_data(items: List[str]) -> Dict[str, int]:
    result: Dict[str, int] = {}
    return result

def get_user(user_id: str) -> Optional[Tuple[str, int]]:
    return ("John", 25) if user_id else None
```

### Preferred Type Annotations
- Use `list[T]` instead of `List[T]`
- Use `dict[K, V]` instead of `Dict[K, V]`
- Use `tuple[T, ...]` instead of `Tuple[T, ...]`
- Use `set[T]` instead of `Set[T]`
- Use `X | Y` instead of `Union[X, Y]`
- Use `X | None` instead of `Optional[X]`

## Code Style

### Imports
- Group imports in this order:
  1. Standard library imports
  2. Third-party imports
  3. Local application imports
- Use absolute imports when possible
- Avoid wildcard imports (`from module import *`)

### Naming Conventions
- **Variables and functions**: `snake_case`
- **Classes**: `PascalCase`
- **Constants**: `UPPER_SNAKE_CASE`
- **Private attributes**: prefix with single underscore `_private_var`
- **Protected attributes**: prefix with single underscore `_protected_var`

### Documentation
- Use docstrings for all public functions, classes, and modules
- Follow Google-style docstrings format
- Include type information in docstrings when it adds clarity

### Error Handling
- Use specific exception types rather than generic `Exception`
- Log errors with appropriate context
- Handle exceptions at the appropriate level

### Async/Await
- Use `async`/`await` for I/O-bound operations
- Prefer `asyncio.create_task()` for concurrent operations
- Use `async with` for async context managers

## File Organization

### Directory Structure
- Keep related functionality in the same module
- Use clear, descriptive directory names
- Separate business logic from infrastructure code

### File Naming
- Use `snake_case` for Python file names
- Use descriptive names that indicate the file's purpose
- Avoid abbreviations unless they are widely understood

## Comments and Documentation

### When to Comment
- Explain **why**, not **what**
- Document complex algorithms or business logic
- Add TODO comments for future improvements
- Explain non-obvious code decisions

### When NOT to Comment
- Don't comment obvious code
- Don't leave commented-out code in production
- Avoid redundant comments that just repeat the code

## Testing

### Test Structure
- Use descriptive test method names
- Follow the Arrange-Act-Assert pattern
- One assertion per test when possible
- Use parameterized tests for similar test cases

### Test Naming
```python
def test_should_return_user_when_valid_id_provided():
    # Arrange
    user_id = "123"
    
    # Act
    result = get_user(user_id)
    
    # Assert
    assert result is not None
```

## Performance Considerations

### Memory Management
- Use generators for large datasets
- Close resources properly (use context managers)
- Avoid memory leaks in long-running processes

### Async Best Practices
- Don't block the event loop
- Use connection pooling for database operations
- Handle timeouts appropriately

## Security

### General Rules
- Never commit secrets to version control
- Validate all external inputs
- Use parameterized queries for database operations
- Follow principle of least privilege

### Logging
- Don't log sensitive information
- Use structured logging when possible
- Include correlation IDs for request tracking

## Dependencies

### Package Management
- Pin dependency versions in production
- Use virtual environments
- Keep dependencies minimal and up-to-date
- Document why each dependency is needed

## Code Review Guidelines

### What to Look For
- Code follows these standards
- Logic is clear and correct
- Error handling is appropriate
- Tests cover the new functionality
- Documentation is updated if needed

### Review Process
- Be constructive in feedback
- Explain the reasoning behind suggestions
- Focus on code quality, not personal preferences
- Approve when standards are met

## Enforcement

These standards should be enforced through:
- Code reviews
- Automated linting (pylint, flake8, etc.)
- Type checking (mypy)
- Pre-commit hooks
- CI/CD pipeline checks

---

**Note**: These standards may evolve as the project grows. All team members should be notified of changes and given time to adapt existing code.