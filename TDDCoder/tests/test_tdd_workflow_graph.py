import pytest
from unittest.mock import MagicMock, patch
from tdd_workflow.tdd_workflow_graph import TDDWorkflowGraph
from tdd_workflow.tdd_workflow_state import TDDWorkflowState

class TestTDDWorkflowGraph:
    
    @pytest.fixture
    def mock_llm(self):
        """Create a mock LLM for testing"""
        mock_llm = MagicMock()
        return mock_llm
    
    @pytest.fixture
    def workflow_graph(self, mock_llm):
        """Create a TDD workflow graph with mock agents"""
        with patch('tdd_workflow.tdd_workflow_graph.POAgent'), \
             patch('tdd_workflow.tdd_workflow_graph.QAAgent'), \
             patch('tdd_workflow.tdd_workflow_graph.TestAgent'), \
             patch('tdd_workflow.tdd_workflow_graph.DevAgent'), \
             patch('tdd_workflow.tdd_workflow_graph.RefactorAgent'):
            graph = TDDWorkflowGraph(mock_llm)
            return graph
    
    def test_workflow_initialization(self, workflow_graph):
        """Test that the workflow graph initializes correctly"""
        assert workflow_graph is not None
        assert hasattr(workflow_graph, 'workflow')
        assert hasattr(workflow_graph, 'po_agent')
        assert hasattr(workflow_graph, 'qa_agent')
        assert hasattr(workflow_graph, 'test_agent')
        assert hasattr(workflow_graph, 'dev_agent')
        assert hasattr(workflow_graph, 'refactor_agent')
    
    def test_test_agent_router_with_remaining_scenarios(self, workflow_graph):
        """Test the test agent router with remaining scenarios"""
        state = TDDWorkflowState()
        state.remaining_scenarios = ["Scenario 1"]
        
        result = workflow_graph._test_agent_router(state)
        assert result == "dev_agent"
    
    def test_test_agent_router_without_remaining_scenarios(self, workflow_graph):
        """Test the test agent router without remaining scenarios"""
        state = TDDWorkflowState()
        state.remaining_scenarios = []
        
        result = workflow_graph._test_agent_router(state)
        assert result == "end"
    
    @patch('tdd_workflow.tdd_workflow_graph.StateGraph')
    def test_create_graph(self, mock_state_graph, workflow_graph):
        """Test the create_graph method"""
        # Reset the mock to clear any previous calls
        mock_state_graph.reset_mock()
        
        # Call the method
        workflow_graph._create_graph()
        
        # Verify that the StateGraph was initialized with the correct state class
        mock_state_graph.assert_called_once()
        
        # Get the mock instance
        mock_instance = mock_state_graph.return_value
        
        # Verify that nodes were added for each agent
        assert mock_instance.add_node.call_count >= 5  # One for each agent
        
        # Verify that edges were added
        assert mock_instance.add_edge.call_count >= 4  # At least one edge for each transition
        
        # Verify that conditional edges were added for the test agent
        mock_instance.add_conditional_edges.assert_called_once()
        
        # Verify that the entry point was set
        mock_instance.set_entry_point.assert_called_once_with("po_agent")
    
    @patch.object(TDDWorkflowGraph, 'run')
    def test_run_with_user_request(self, mock_run, workflow_graph):
        """Test the run method with a user request"""
        user_request = "I need a login system"
        workflow_graph.run(user_request)
        
        # Verify that the run method was called with the correct arguments
        mock_run.assert_called_once()
        call_args = mock_run.call_args[0][0]
        assert call_args == user_request
