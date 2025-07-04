import pytest
from unittest.mock import MagicMock
from agents.analyst_agent import AnalystAgent
from tdd_workflow.tdd_workflow_state import TDDWorkflowState

@pytest.fixture
def mock_llm():
    """Create a mock LLM for testing."""
    return MagicMock()

@pytest.fixture
def analyst_agent(mock_llm) -> AnalystAgent:
    """Create an analyst agent for testing."""
    return AnalystAgent(mock_llm)

@pytest.fixture
def initial_state() -> TDDWorkflowState:
    """Create a sample workflow state for testing."""
    return TDDWorkflowState(
        user_story={
            'description': 'A user wants to calculate their bowling score.'
        },
        gherkin_scenarios=[
            {'title': 'All Zeros', 'given': 'A new game', 'when': 'All rolls are 0', 'then': 'The score should be 0'},
            {'title': 'All Ones', 'given': 'A new game', 'when': 'All rolls are 1', 'then': 'The score should be 20'}
        ]
    )

def test_run_creates_implementation_steps(analyst_agent: AnalystAgent, initial_state: TDDWorkflowState):
    """Test that the run method creates implementation steps if they don't exist."""
    result_state = analyst_agent.run(initial_state)
    
    assert len(result_state.implementation_steps) == 2
    assert result_state.implementation_steps[0]['description'] == "Implement the 'All Zeros' scenario."
    assert result_state.implementation_steps[1]['description'] == "Implement the 'All Ones' scenario."
    assert 'scenario' in result_state.implementation_steps[0]

def test_run_sets_current_scenario(analyst_agent: AnalystAgent, initial_state: TDDWorkflowState):
    """Test that the run method sets the current scenario correctly."""
    result_state = analyst_agent.run(initial_state)
    
    assert result_state.current_step_index == 0
    assert result_state.current_scenario is not None
    assert result_state.current_scenario['description'] == "Implement the 'All Zeros' scenario."
    
    expected_scenario_text = (
        "Title: All Zeros\n"
        "Given: A new game\n"
        "When: All rolls are 0\n"
        "Then: The score should be 0"
    )
    assert result_state.current_scenario['scenario_text'] == expected_scenario_text

def test_run_handles_completion(analyst_agent: AnalystAgent, initial_state: TDDWorkflowState):
    """Test that the run method correctly identifies when all steps are complete."""
    # Set the state to the last step
    initial_state.current_step_index = 2
    initial_state.implementation_steps = [
        {"step_id": 1, "description": "Step 1", "scenario": {}},
        {"step_id": 2, "description": "Step 2", "scenario": {}}
    ]
    
    result_state = analyst_agent.run(initial_state)
    
    assert result_state.is_implementation_complete is True

def test_run_with_existing_steps(analyst_agent: AnalystAgent, initial_state: TDDWorkflowState):
    """Test that the run method uses existing steps and increments the index (in the graph)."""
    initial_state.implementation_steps = [
        {"step_id": 1, "description": "Existing Step 1", "scenario": {'title': 'Existing 1'}},
        {"step_id": 2, "description": "Existing Step 2", "scenario": {'title': 'Existing 2'}}
    ]
    initial_state.current_step_index = 1
    
    result_state = analyst_agent.run(initial_state)
    
    # The agent should not re-create the steps
    assert len(result_state.implementation_steps) == 2
    assert result_state.implementation_steps[0]['description'] == "Existing Step 1"
    
    # It should set the current scenario based on the current_step_index
    assert result_state.current_scenario['description'] == "Existing Step 2"
