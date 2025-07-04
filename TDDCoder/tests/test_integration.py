import pytest
from unittest.mock import MagicMock, patch
from tdd_workflow.tdd_workflow_graph import TDDWorkflowGraph
from tdd_workflow.tdd_workflow_state import TDDWorkflowState

class TestTDDWorkflowIntegration:

    @pytest.fixture
    def mock_llm(self):
        """Create a mock LLM for testing"""
        return MagicMock()

    @pytest.fixture
    def mock_analyst_agent_run(self):
        """Mock the Analyst agent's run method"""
        with patch('tdd_workflow.tdd_workflow_graph.AnalystAgent.run') as mock_run:
            def side_effect(state):
                state.user_story = {"title": "Implement User Login"}
                state.gherkin_scenarios = [{"title": "Successful login"}, {"title": "Failed login"}]
                state.implementation_steps = [
                    {"step_id": 1, "description": "Implement successful login", "scenario": state.gherkin_scenarios[0]},
                    {"step_id": 2, "description": "Implement failed login", "scenario": state.gherkin_scenarios[1]}
                ]

                return state
            mock_run.side_effect = side_effect
            yield mock_run

    @pytest.fixture
    def mock_unit_test_agent_run(self):
        """Mock the Unit Test agent's run method"""
        with patch('tdd_workflow.tdd_workflow_graph.UnitTestAgent.run') as mock_run:
            def side_effect(state):
                current_step = state.current_step
                test_code = f"# Test for {current_step['description']}\ndef test_step_{current_step['step_id']}():\n    assert True"
                state.current_test = test_code
                state.implemented_tests.append(test_code)
                return state
            mock_run.side_effect = side_effect
            yield mock_run

    @pytest.fixture
    def mock_dev_agent_run(self):
        """Mock the Dev agent's run method"""
        with patch('tdd_workflow.tdd_workflow_graph.DevAgent.run') as mock_run:
            def side_effect(state):
                current_step = state.current_step
                code = f"# Code for {current_step['description']}\ndef feature_step_{current_step['step_id']}():\n    return True"
                state.current_code = code
                module_name = f"module_{current_step['step_id']}"
                state.implemented_code[module_name] = code
                state.tests_passed = True
                return state
            mock_run.side_effect = side_effect
            yield mock_run

    @pytest.fixture
    def mock_refactor_agent_run(self):
        """Mock the Refactor agent's run method"""
        with patch('tdd_workflow.tdd_workflow_graph.RefactorAgent.run') as mock_run:
            def side_effect(state):
                state.refactored_code = state.current_code + "\n# Refactored"
                return state
            mock_run.side_effect = side_effect
            yield mock_run

    @pytest.mark.asyncio
    async def test_tdd_workflow_full_integration(
        self,
        mock_llm,
        mock_analyst_agent_run,
        mock_unit_test_agent_run,
        mock_dev_agent_run,
        mock_refactor_agent_run
    ):
        """Test the full TDD workflow integration with proper mocks."""
        workflow = TDDWorkflowGraph(mock_llm)
        user_request = "I need a login system for my web application"
        result_state = await workflow.run_async(user_request)

        # Assertions to verify the workflow ran through the mocked agents
        assert result_state['is_implementation_complete'] is True
        assert result_state['error'] is False
        assert result_state['user_story'] is not None
        assert len(result_state['gherkin_scenarios']) == 2
        assert len(result_state['implemented_tests']) == 2
        assert len(result_state['implemented_code']) == 2

        assert result_state['tests_passed'] is True
        
        # Verify that Gherkin scenarios were created
        assert len(result['gherkin_scenarios']) > 0
        
        # Verify that tests were implemented
        assert len(result['implemented_tests']) > 0
        
        # Verify that code was implemented
        assert len(result['implemented_code']) > 0
        
        # Verify that all scenarios were processed
        assert len(result['remaining_scenarios']) == 0
        
        # Verify that the tests passed
        assert result['tests_passed'] is True
