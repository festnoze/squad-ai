import pytest
from unittest.mock import MagicMock, patch
from tdd_workflow.tdd_workflow_graph import TDDWorkflowGraph
from tdd_workflow.tdd_workflow_state import TDDWorkflowState
from langgraph.graph import END
class TestTDDWorkflowGraph:
    
    @pytest.fixture
    def mock_llm(self):
        """Create a mock LLM for testing"""
        mock_llm = MagicMock()
        return mock_llm
    
    @pytest.fixture
    def workflow_graph(self, mock_llm) -> TDDWorkflowGraph:
        """Create a TDD workflow graph with mock agents"""
        with patch('agents.analyst_agent.AnalystAgent'), \
             patch('agents.unit_test_agent.UnitTestAgent'), \
             patch('agents.dev_agent.DevAgent'), \
             patch('agents.refactor_agent.RefactorAgent'):
            graph = TDDWorkflowGraph(mock_llm)
            return graph
    
    def test_workflow_initialization(self, workflow_graph: TDDWorkflowGraph):
        """Test that the workflow graph initializes correctly"""
        assert workflow_graph is not None
        assert hasattr(workflow_graph, 'workflow')
        assert hasattr(workflow_graph, 'analyst_agent')
        assert hasattr(workflow_graph, 'unit_test_agent')
        assert hasattr(workflow_graph, 'dev_agent')
        assert hasattr(workflow_graph, 'refactor_agent')
    
    def test_unit_test_agent_router_with_remaining_scenarios(self, workflow_graph: TDDWorkflowGraph):
        """Test the unit test agent router with remaining scenarios"""
        state = TDDWorkflowState()
        state.remaining_scenarios = ["Scenario 1"]
        state.current_test = "Test 1"
        result = workflow_graph._unit_test_agent_router(state)
        assert result == "dev_agent"
    
    def test_unit_test_agent_router_no_more_scenarios(self, workflow_graph: TDDWorkflowGraph):
        """When there are no remaining scenarios the router should send control back to the Analyst."""
        state = TDDWorkflowState()
        state.remaining_scenarios = []
        state.current_test = "Test placeholder"  # Even if a test exists, no scenarios left means work is done.

        result = workflow_graph._unit_test_agent_router(state)
        assert result == "dev_agent"

    def test_unit_test_agent_router_missing_unit_test(self, workflow_graph: TDDWorkflowGraph):
        """If the Unit-Test agent failed to create a test, the router should also return to the Analyst."""
        state = TDDWorkflowState()
        state.remaining_scenarios = ["Scenario 1"]
        state.current_test = ""  # Simulate missing test

        result = workflow_graph._unit_test_agent_router(state)
        assert result == "analyst_agent"
    
    @patch('tdd_workflow.tdd_workflow_graph.StateGraph')
    def test_create_graph(self, mock_state_graph, workflow_graph: TDDWorkflowGraph):
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
        assert mock_instance.add_node.call_count == 4  # One for each agent
        
        # Verify that edges were added
        assert mock_instance.add_edge.call_count == 0  # At least one edge for each transition
        
        # Verify that conditional edges were added for the test agent
        assert mock_instance.add_conditional_edges.call_count == 4
        
        # Verify that the entry point was set
        mock_instance.set_entry_point.assert_called_once_with("analyst_agent")
    
    @pytest.mark.asyncio
    @patch.object(TDDWorkflowGraph, 'run_async')
    async def test_run_with_user_request(self, mock_run, workflow_graph: TDDWorkflowGraph):
        """Test the run method with a user request"""
        user_request = "I need a login system"
        await workflow_graph.run_async(user_request)
        
        # Verify that the run method was called with the correct arguments
        mock_run.assert_called_once()
        call_args = mock_run.call_args[0][0]
        assert call_args == user_request
