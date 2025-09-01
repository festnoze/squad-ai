# Contributing

Thank you for considering contributing to the PIC Prospect Incoming Callbot! This document provides guidelines and information for contributors.

## Development Workflow

### 1. Code Quality

We use several tools to maintain code quality:

```bash
# Lint and format code with Ruff
ruff check app/                    # Check for issues
ruff check --fix app/             # Auto-fix issues
ruff format app/                  # Format code

# Run tests with coverage
pytest --cov=app tests/

# Check dependencies
deptry .

# Build documentation
mkdocs serve
```

### 2. Testing

- Write tests for new functionality
- Ensure all tests pass before submitting PR
- Maintain or improve test coverage
- Use async tests for async code

```bash
# Run all tests
pytest

# Run with coverage report
pytest --cov=app --cov-report=html tests/

# Run specific test file
pytest tests/test_specific.py
```

### 3. Code Style

- Follow PEP 8 guidelines
- Use type hints for function parameters and return values
- Write clear docstrings using Google style
- Keep line length under 120 characters
- Use meaningful variable and function names

### 4. Commit Messages

Use clear, descriptive commit messages:

```
Add calendar integration for appointment scheduling

- Implement CalendarAgent with LangGraph
- Add Google Calendar API integration
- Update phone call workflow to handle bookings
- Add tests for calendar functionality
```

### 5. Pull Request Process

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/your-feature-name`
3. Make your changes
4. Run the quality checks:
   ```bash
   ruff check --fix app/
   ruff format app/
   pytest --cov=app tests/
   ```
5. Commit your changes
6. Push to your fork
7. Create a pull request

## Architecture Guidelines

### Agent Development

- Use LangGraph for agent orchestration
- Implement proper state management
- Add comprehensive error handling
- Write unit tests for agent logic

### API Development

- Use FastAPI best practices
- Implement proper request/response models
- Add comprehensive error handling
- Document endpoints with OpenAPI

### Audio Processing

- Handle WebSocket connections gracefully
- Implement proper buffering and streaming
- Add error recovery mechanisms
- Test with various audio formats

## Documentation

- Update documentation for new features
- Use docstrings for all public functions
- Add examples to complex functionality
- Keep the API reference up to date

## Getting Help

- Create an issue for bugs or feature requests
- Ask questions in discussions
- Check existing documentation first
- Provide clear reproduction steps for bugs