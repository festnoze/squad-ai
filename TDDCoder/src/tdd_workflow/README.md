# TDD Workflow LangGraph

This project implements a Test-Driven Development (TDD) workflow using LangGraph. The workflow consists of several agents working together to implement features based on user requirements.

## Workflow Overview

1. **Product Owner (PO) Agent**: Converts user requirements into a formal User Story
2. **QA Agent**: Creates Gherkin/BDD scenarios from the User Story
3. **Test Agent**: Writes pytest unit tests based on the Gherkin scenarios
4. **Dev Agent**: Implements Python code to make the tests pass
5. **Refactor Agent**: Improves the code quality while maintaining test passing

The workflow loops between Test, Dev, and Refactor agents until all scenarios are covered with tests and implementation.

### Python-Specific Implementation

This TDD workflow is specifically designed for Python development:

- **Test Agent** creates pytest-only tests following pytest best practices
- **Dev Agent** writes Python-only code following PEP 8 guidelines
- Both agents have access to shared tools for linting and test execution

## Project Structure

```
tdd_workflow/
├── __init__.py
├── tdd_workflow_state.py      # State model for the workflow
├── tdd_workflow_graph.py      # Main graph implementation
├── run_tdd_workflow.py        # Script to run the workflow
├── requirements.txt           # Project dependencies
├── agents/
│   ├── __init__.py
│   ├── po_agent.py            # Product Owner agent
│   ├── qa_agent.py            # QA agent
│   ├── unit_test_agent.py     # Unit Test agent (pytest-specific)
│   ├── dev_agent.py           # Dev agent (Python-specific)
│   ├── refactor_agent.py      # Refactor agent
│   └── shared_tools.py        # Shared tools for linting and testing
└── tests/
    ├── __init__.py
    ├── test_po_agent.py       # Tests for the PO agent
    ├── test_tdd_workflow_graph.py # Tests for the workflow graph
    └── test_integration.py    # Integration tests
```

## Requirements

- Python 3.9+
- LangGraph
- LangChain
- pytest (for running tests)
- flake8 (for linting Python code)
- pytest-cov (for test coverage reporting)

## Setup

1. Install the required packages:
   ```
   pip install langgraph langchain langchain_openai pytest
   ```

2. Set up your OpenAI API key:
   ```
   # On Linux/Mac
   export OPENAI_API_KEY='your-api-key'
   
   # On Windows
   set OPENAI_API_KEY=your-api-key
   ```

## Running the Workflow

To run the TDD workflow with a sample feature request:

```
python run_tdd_workflow.py "I need a login system for my web application"
```

You can replace the quoted text with any feature request you want to implement.

## Running Tests

To run the tests for the TDD workflow:

```bash
pytest tests/
```

To run a specific test file:

```bash
pytest tests/test_po_agent.py
```

## Shared Tools

The Dev and Test agents have access to shared tools for linting and testing:

### run_linter

This tool runs flake8 on Python code to ensure code quality:

```python
result = run_linter("path/to/file.py")
# Returns: {"success": True/False, "message": "...", "issues": [...]}
```

### run_tests

This tool runs pytest tests on specified files or test names:

```python
# Run all tests
result = run_tests()

# Run tests in a specific file
result = run_tests(test_path="tests/test_module.py")

# Run a specific test
result = run_tests(test_name="tests/test_module.py::test_function")

# Returns: {"success": True/False, "message": "...", "output": [...], "return_code": 0}
```

These tools help ensure that the code produced by the Dev agent passes both linting checks and tests written by the Test agent.

## Extending the Workflow

You can extend this workflow by:

1. Enhancing the agents with more sophisticated tools
2. Adding more detailed prompts
3. Implementing actual code execution for tests
4. Adding more agents for additional steps in the development process

## License

MIT
