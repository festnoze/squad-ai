# TDD Workflow Tests

This directory contains tests for the TDD Workflow project.

## Running Tests

To run all tests:

```bash
pytest
```

To run a specific test file:

```bash
pytest tests/test_linter.py
```

## Linter Tests

The `test_linter.py` file contains tests that run the linter on the project's Python files. These tests demonstrate how to use the shared linting tools from the TDD workflow.

### Running the Linter Tests

To run just the linter tests:

```bash
pytest tests/test_linter.py -v
```

This will:
1. Check all Python files in the project for linting issues using flake8
2. Display a summary of any issues found
3. Provide a detailed report of each file and its linting status

### Understanding the Results

The linter tests will output:
- Which files were checked
- Any issues found per file
- A summary of total issues

By default, the test will not fail even if linting issues are found. This behavior can be modified by uncommenting the assertion line in `test_linter_on_project()`.
