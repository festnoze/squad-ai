# Conception Workflow

The Conception Workflow is the first part of the TDD process, focusing on requirements gathering and scenario creation. It consists of two main agents:

1. **Product Owner (PO) Agent**: Extracts requirements and creates user stories from user input
2. **QA Agent**: Creates BDD/Gherkin scenarios from user stories

## How It Works

1. The user provides a feature request
2. The PO Agent extracts requirements and creates a user story
3. The QA Agent creates BDD scenarios based on the user story
4. The output is saved to a JSON file that can be used as input for the Implementation Workflow

## Running the Conception Workflow

```bash
python src/conception_workflow/run_conception_workflow.py
```

You will be prompted to enter your feature request. The workflow will then process your request and generate a user story and BDD scenarios.

## Output

The workflow outputs a JSON file containing:
- User story (role, goal, benefit)
- BDD scenarios (title, given, when, then)

This file can then be used as input for the Implementation Workflow.

## Example

```bash
# Run the conception workflow
python src/conception_workflow/run_conception_workflow.py

# Use the output for the implementation workflow
python src/tdd_workflow/run_tdd_workflow.py --input conception_output.json
```
