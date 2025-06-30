import pytest
import os
import json
from unittest.mock import MagicMock, patch
from tdd_workflow.tdd_workflow_graph import TDDWorkflowGraph
from tdd_workflow.tdd_workflow_state import TDDWorkflowState

class TestImplementationWorkflowIntegration:
    
    @pytest.fixture
    def mock_analyst_agent_run(self):
        """Mock the Analyst agent's run method"""
        with patch('agents.analyst_agent.AnalystAgent.run') as mock_run:
            def side_effect(state):
                # Analyze requirements and create implementation steps
                state.implementation_steps = [
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
                state.current_step_index = 0
                state.is_implementation_complete = False
                return state
            
            mock_run.side_effect = side_effect
            yield mock_run
    
    @pytest.fixture
    def mock_test_agent_run(self):
        """Mock the Test agent's run method"""
        with patch('agents.unit_test_agent.UnitTestAgent.run') as mock_run:
            def side_effect(state):
                # Generate test code based on current implementation step
                current_step = state.implementation_steps[state.current_step_index]
                
                if current_step["id"] == "step1":
                    state.tests = """
                    import pytest

                    def test_successful_login():
                        # Given the user has a valid account
                        user = create_test_user("testuser", "password123")
                        
                        # When they enter correct credentials
                        result = login("testuser", "password123")
                        
                        # Then they should be logged in successfully
                        assert result.success is True
                        assert result.user_id == user.id
                    """
                elif current_step["id"] == "step2":
                    state.tests = """
                    import pytest

                    def test_failed_login():
                        # Given the user has a valid account
                        user = create_test_user("testuser", "password123")
                        
                        # When they enter incorrect credentials
                        result = login("testuser", "wrong_password")
                        
                        # Then they should see an error message
                        assert result.success is False
                        assert result.user_id is None
                    """
                
                return state
            
            mock_run.side_effect = side_effect
            yield mock_run
    
    @pytest.fixture
    def mock_dev_agent_run(self):
        """Mock the Dev agent's run method"""
        with patch('agents.dev_agent.DevAgent.run') as mock_run:
            def side_effect(state):
                # Implement code based on tests
                current_step = state.implementation_steps[state.current_step_index]
                
                if current_step["id"] == "step1" or current_step["id"] == "step2":
                    state.code = """
                    class User:
                        def __init__(self, user_id, username, password):
                            self.id = user_id
                            self.username = username
                            self.password = password
                    
                    class LoginResult:
                        def __init__(self, success, user_id=None):
                            self.success = success
                            self.user_id = user_id
                    
                    def create_test_user(username, password):
                        # Create a test user for authentication testing.
                        return User(123, username, password)
                    
                    def login(username, password):
                        # Authenticate a user with the given credentials.
                        # 
                        # Args:
                        #     username: The user's username
                        #     password: The user's password
                        #     
                        # Returns:
                        #     LoginResult: Object containing authentication result and user ID if successful
                        
                        # In a real implementation, this would check against a database
                        if username == "testuser" and password == "password123":
                            return LoginResult(True, 123)  # Assuming 123 is the user ID
                        return LoginResult(False, None)
                    """
                
                # Set tests_passed to True to simulate successful implementation
                state.tests_passed = True
                
                return state
            
            mock_run.side_effect = side_effect
            yield mock_run
    
    @pytest.fixture
    def mock_refactor_agent_run(self):
        """Mock the Refactor agent's run method"""
        with patch('agents.refactor_agent.RefactorAgent.run') as mock_run:
            def side_effect(state):
                # Refactor the code
                state.refactored_code = state.code  # In this mock, we don't actually refactor
                
                # Increment step index to move to next step
                state.current_step_index += 1
                
                # Check if we've completed all steps
                if state.current_step_index >= len(state.implementation_steps):
                    state.is_implementation_complete = True
                
                return state
            
            mock_run.side_effect = side_effect
            yield mock_run
    
    @pytest.fixture
    def mock_conception_output(self, tmp_path):
        """Create a mock conception output file"""
        conception_data = {
            "user_story": {
                "role": "web user",
                "goal": "log in to the application",
                "benefit": "access my personal dashboard"
            },
            "scenarios": [
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
        }
        
        # Create a temporary file
        output_file = tmp_path / "conception_output.json"
        with open(output_file, 'w') as f:
            json.dump(conception_data, f)
        
        return str(output_file)
    
    @pytest.fixture
    def mock_llm(self):
        """Create a mock LLM for testing"""
        mock_llm = MagicMock()
        return mock_llm
    
    async def test_implementation_workflow_integration(self, mock_llm, mock_conception_output):
        """Test the full implementation workflow integration."""
        # Initialize the workflow graph
        workflow = TDDWorkflowGraph(mock_llm)
        
        # Extract user story and acceptance tests from mock conception output
        with open(mock_conception_output, 'r') as f:
            conception_data = json.load(f)
            
        user_story_spec = conception_data.get("user_story", {}).get("description", "")
        acceptance_tests_gherkin = conception_data.get("scenarios", [])
        
        # Run the workflow with the user story and acceptance tests
        result = await workflow.run_async(user_story_spec, acceptance_tests_gherkin)
        
        # Verify that the workflow completed successfully
        assert result.is_implementation_complete is True
        
        # Verify that the user story was loaded
        assert result.user_story is not None
        assert "role" in result.user_story
        assert "goal" in result.user_story
        assert "benefit" in result.user_story
        
        # Verify that scenarios were loaded
        assert len(result.scenarios) > 0
        
        # Verify that implementation steps were created
        assert len(result.implementation_steps) > 0
        
        # Verify that tests were implemented
        assert result.tests is not None and result.tests != ""
        
        # Verify that code was implemented
        assert result.code is not None and result.code != ""
        
        # Verify that code was refactored
        assert result.refactored_code is not None and result.refactored_code != ""
