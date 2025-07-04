import pytest
from unittest.mock import MagicMock, patch
from langchain.agents import AgentExecutor
from agents.po_agent import POAgent
from tdd_workflow.tdd_workflow_state import TDDWorkflowState

class TestPOAgent:
    
    @pytest.fixture
    def mock_llm(self):
        """Create a mock LLM for testing"""
        mock_llm = MagicMock()
        return mock_llm
    
    @pytest.fixture
    def po_agent(self, mock_llm) -> POAgent:
        """Create a PO agent with a mock LLM"""
        return POAgent(mock_llm)
    
    @pytest.fixture
    def initial_state(self) -> TDDWorkflowState:
        """Create an initial state for testing"""
        return TDDWorkflowState(
            user_request="I need a login system for my web application"
        )
    
    def test_po_agent_initialization(self, po_agent: POAgent):
        """Test that the PO agent initializes correctly"""
        assert po_agent is not None
        assert isinstance(po_agent, POAgent)
        assert hasattr(po_agent, 'agent_executor')
        assert isinstance(po_agent.agent_executor, AgentExecutor)
        assert len(po_agent.tools) == 2
    
    def test_extract_requirements_tool(self, po_agent: POAgent):
        """Test the extract_requirements tool"""
        user_input = "I need a login system for my web application"
        result = po_agent.extract_requirements.func(po_agent, user_input)
        
        assert isinstance(result, dict)
        assert 'user_type' in result
        assert 'action' in result
        assert 'benefit' in result
    
    def test_create_user_story_tool(self, po_agent: POAgent):
        """Test the create_user_story tool"""
        requirements = {
            "user_type": "web user",
            "action": "log in to the application",
            "benefit": "access my personal dashboard"
        }
        result = po_agent.create_user_story.func(po_agent, requirements)
        
        assert isinstance(result, dict)
        assert 'title' in result
        assert 'narrative' in result
        assert 'acceptance_criteria' in result
        assert 'technical_notes' in result
        assert 'priority' in result
    
    @patch.object(AgentExecutor, 'invoke')
    def test_run_success(self, mock_invoke, po_agent: POAgent, initial_state: TDDWorkflowState):
        """Test the run method with a successful execution"""
        # Mock the agent executor's invoke method
        user_story_mock = {
            "title": "Implement User Login",
            "narrative": "As a web user, I want to log in to the application so that I can access my personal dashboard",
            "acceptance_criteria": [
                "User can enter username and password",
                "System validates credentials",
                "User is redirected to dashboard on success",
                "User sees error message on failure"
            ],
            "technical_notes": ["Use secure authentication"],
            "priority": "High"
        }

        mock_invoke.return_value = {
            "output": "I've created a user story for your login system.",
            "intermediate_steps": [
                (MagicMock(tool='create_user_story'), user_story_mock)
            ]
        }
        
        # Run the agent
        result_state = po_agent.run(initial_state)
        
        # Verify the state was updated correctly
        assert result_state.user_story == user_story_mock
        assert result_state.current_agent == "qa_agent"
        assert len(result_state.chat_history) == 1
        assert result_state.chat_history[0]["role"] == "assistant"
        assert result_state.chat_history[0]["content"] == mock_invoke.return_value["output"]
    
    @patch.object(AgentExecutor, 'invoke')
    def test_run_error(self, mock_invoke, po_agent: POAgent, initial_state: TDDWorkflowState):
        """Test the run method with an error"""
        # Mock the agent executor's invoke method to raise an exception
        mock_invoke.side_effect = Exception("Test error")
        
        # Run the agent
        result_state = po_agent.run(initial_state)
        
        # Verify the error was handled correctly
        assert result_state.error_message is not None
        assert "Error in PO Agent" in result_state.error_message
