import pytest
from unittest.mock import MagicMock, patch
from tdd_workflow.tdd_workflow_graph import TDDWorkflowGraph
from tdd_workflow.tdd_workflow_state import TDDWorkflowState

class TestTDDWorkflowIntegration:
    
    @pytest.fixture
    def mock_po_agent_run(self):
        """Mock the PO agent's run method"""
        with patch('tdd_workflow.agents.po_agent.POAgent.run') as mock_run:
            def side_effect(state):
                state.user_story = {
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
                state.current_agent = "qa_agent"
                return state
            
            mock_run.side_effect = side_effect
            yield mock_run
    
    @pytest.fixture
    def mock_qa_agent_run(self):
        """Mock the QA agent's run method"""
        with patch('tdd_workflow.agents.qa_agent.QAAgent.run') as mock_run:
            def side_effect(state):
                state.gherkin_scenarios = [
                    """Feature: User Authentication
                      
                      Scenario: Successful login
                        Given the user has a valid account
                        When they enter correct credentials
                        Then they should be logged in successfully
                    """,
                    """Feature: User Authentication
                      
                      Scenario: Failed login
                        Given the user has a valid account
                        When they enter incorrect credentials
                        Then they should see an error message
                    """
                ]
                state.remaining_scenarios = state.gherkin_scenarios.copy()
                state.current_agent = "test_agent"
                return state
            
            mock_run.side_effect = side_effect
            yield mock_run
    
    @pytest.fixture
    def mock_test_agent_run(self):
        """Mock the Test agent's run method"""
        with patch('tdd_workflow.agents.test_agent.TestAgent.run') as mock_run:
            def side_effect(state):
                if not state.remaining_scenarios:
                    state.is_complete = True
                    return state
                
                current_scenario = state.remaining_scenarios[0]
                test_code = """
                def test_successful_login():
                    # Given the user has a valid account
                    user = create_test_user("testuser", "password123")
                    
                    # When they enter correct credentials
                    result = login("testuser", "password123")
                    
                    # Then they should be logged in successfully
                    assert result.success is True
                    assert result.user_id == user.id
                """
                
                state.current_test = test_code
                state.implemented_tests.append(test_code)
                state.remaining_scenarios.pop(0)
                
                if state.remaining_scenarios:
                    state.current_agent = "dev_agent"
                else:
                    state.is_complete = True
                
                return state
            
            mock_run.side_effect = side_effect
            yield mock_run
    
    @pytest.fixture
    def mock_dev_agent_run(self):
        """Mock the Dev agent's run method"""
        with patch('tdd_workflow.agents.dev_agent.DevAgent.run') as mock_run:
            def side_effect(state):
                code = """
                def login(username, password):
                    # In a real implementation, this would check against a database
                    if username == "testuser" and password == "password123":
                        return LoginResult(True, 123)  # Assuming 123 is the user ID
                    return LoginResult(False, None)
                    
                class LoginResult:
                    def __init__(self, success, user_id):
                        self.success = success
                        self.user_id = user_id
                        
                def create_test_user(username, password):
                    # In a real implementation, this would create a user in a test database
                    return User(123, username, password)
                    
                class User:
                    def __init__(self, id, username, password):
                        self.id = id
                        self.username = username
                        self.password = password
                """
                
                state.current_code = code
                module_name = f"module_{len(state.implemented_code) + 1}"
                state.implemented_code[module_name] = code
                state.tests_passed = True
                state.current_agent = "refactor_agent"
                
                return state
            
            mock_run.side_effect = side_effect
            yield mock_run
    
    @pytest.fixture
    def mock_refactor_agent_run(self):
        """Mock the Refactor agent's run method"""
        with patch('tdd_workflow.agents.refactor_agent.RefactorAgent.run') as mock_run:
            def side_effect(state):
                refactored_code = """
                class User:
                    def __init__(self, id, username, password):
                        self.id = id
                        self.username = username
                        self.password = password
                
                class LoginResult:
                    def __init__(self, success, user_id):
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
                
                state.current_code = refactored_code
                
                # Update the implemented code dictionary
                for key in state.implemented_code:
                    state.implemented_code[key] = refactored_code
                    break
                
                state.tests_passed = True
                state.current_agent = "test_agent"
                
                return state
            
            mock_run.side_effect = side_effect
            yield mock_run
    
    @pytest.fixture
    def mock_llm(self):
        """Create a mock LLM for testing"""
        mock_llm = MagicMock()
        return mock_llm
    
    async def test_tdd_workflow_integration(
        self, 
        mock_llm, 
        mock_po_agent_run, 
        mock_qa_agent_run, 
        mock_test_agent_run, 
        mock_dev_agent_run, 
        mock_refactor_agent_run
    ):
        """Test the full TDD workflow integration"""
        # Initialize the workflow graph
        workflow = TDDWorkflowGraph(mock_llm)
        
        # Run the workflow with a user story and acceptance tests
        user_story = "As a user, I need a login system for my web application so that I can securely access my account"
        acceptance_tests = [
            """Feature: User Login
               Scenario: Successful login
                 Given I am on the login page
                 When I enter valid credentials
                 Then I should be logged in successfully""",
            """Feature: User Login
               Scenario: Failed login
                 Given I am on the login page
                 When I enter invalid credentials
                 Then I should see an error message"""
        ]
        result = await workflow.run_async(user_story, acceptance_tests)
        
        # Verify that the workflow completed successfully
        assert result.is_complete is True
        
        # Verify that the user story was created
        assert result.user_story is not None
        assert "title" in result.user_story
        assert "narrative" in result.user_story
        assert "acceptance_criteria" in result.user_story
        
        # Verify that Gherkin scenarios were created
        assert len(result.gherkin_scenarios) > 0
        
        # Verify that tests were implemented
        assert len(result.implemented_tests) > 0
        
        # Verify that code was implemented
        assert len(result.implemented_code) > 0
        
        # Verify that all scenarios were processed
        assert len(result.remaining_scenarios) == 0
        
        # Verify that the tests passed
        assert result.tests_passed is True
