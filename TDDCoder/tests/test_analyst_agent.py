import pytest
from unittest.mock import MagicMock, patch
from agents.analyst_agent import AnalystAgent
from tdd_workflow.tdd_workflow_state import TDDWorkflowState
from langchain_core.messages import HumanMessage, AIMessage
from llms.langchain_factory import LangChainFactory, LangChainAdapterType

class TestAnalystAgent:
    
    @pytest.fixture
    def mock_llm(self):
        """Create a mock LLM for testing"""
        mock_llm = MagicMock()
        return mock_llm
    
    @pytest.fixture
    def analyst_agent(self, mock_llm):
        """Create an analyst agent for testing"""
        return AnalystAgent(mock_llm)
    
    @pytest.fixture
    def sample_state(self):
        """Create a sample workflow state for testing"""
        return TDDWorkflowState(
            user_story={
                "role": "web user",
                "goal": "log in to the application",
                "benefit": "access my personal dashboard",
                "llm_model_name": "gpt-4"
            },
            scenarios=[
                {
                    "title": "Successful login",
                    "given": "the user has a valid account",
                    "when": "they enter correct credentials",
                    "then": "they should be logged in successfully"
                },
                {
                    "title": "Failed login",
                    "given": "the user has a valid account",
                    "when": "they enter incorrect credentials",
                    "then": "they should see an error message"
                }
            ],
            remaining_scenarios=[
                {
                    "title": "Successful login",
                    "given": "the user has a valid account",
                    "when": "they enter correct credentials",
                    "then": "they should be logged in successfully"
                },
                {
                    "title": "Failed login",
                    "given": "the user has a valid account",
                    "when": "they enter incorrect credentials",
                    "then": "they should see an error message"
                }
            ]
        )
    
    @patch('agents.analyst_agent.AnalystAgent.analyze_requirements')
    @patch('agents.analyst_agent.AnalystAgent.prioritize_next_steps')
    def test_run_method(self, mock_prioritize, mock_analyze, analyst_agent, sample_state):
        """Test the run method of the AnalystAgent"""
        # Setup mock return values
        mock_analyze.return_value = [
            {
                "id": "step1",
                "description": "Implement user authentication function",
                "test_description": "Test successful login with valid credentials",
                "code_description": "Create login function that validates username and password"
            },
            {
                "id": "step2",
                "description": "Implement failed login handling",
                "test_description": "Test failed login with invalid credentials",
                "code_description": "Add error handling to login function for invalid credentials"
            }
        ]
        mock_prioritize.return_value = (0, False)
        
        # Run the agent
        result = analyst_agent.run(sample_state)
        
        # Verify that analyze_requirements was called
        mock_analyze.assert_called_once()
        
        # Verify that prioritize_next_steps was called
        mock_prioritize.assert_called_once()
        
        # Verify that the state was updated correctly
        assert len(result.implementation_steps) > 0
        assert result.current_step_index == 0
        assert result.is_implementation_complete is False
    
    def test_analyze_requirements(self, analyst_agent, sample_state):
        """Test the analyze_requirements method"""
        # This is a placeholder test since the actual implementation will use an LLM
        # In a real test, we would mock the LLM response
        steps = analyst_agent.analyze_requirements(sample_state)
        
        # For now, just verify that it returns a list (even if empty)
        assert isinstance(steps, list)
    
    def test_prioritize_next_steps(self, analyst_agent, sample_state):
        """Test the prioritize_next_steps method"""
        # This is a placeholder test since the actual implementation will use an LLM
        # In a real test, we would mock the LLM response
        sample_state.implementation_steps = [
            {
                "id": "step1",
                "description": "Implement user authentication function"
            },
            {
                "id": "step2",
                "description": "Implement failed login handling"
            }
        ]
        sample_state.current_step_index = 0
        
        next_index, is_complete = analyst_agent.prioritize_next_steps(sample_state)
        
        # For now, just verify the return types
        assert isinstance(next_index, int)
        assert isinstance(is_complete, bool)
