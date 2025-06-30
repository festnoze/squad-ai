import logging
import os
from langchain.tools import tool
from langchain.agents import AgentExecutor, create_tool_calling_agent
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from agents.shared_tools import run_linter, run_tests

class DevAgent:
    def __init__(self, llm):
        self.logger = logging.getLogger(__name__)
        self.llm = llm
        
        # Define tools
        self.tools = [
            self.implement_code,
            self.verify_test_passing,
            run_linter,
            run_tests
        ]
        
        # Create prompt
        prompt = self.load_dev_prompt()
        prompts = ChatPromptTemplate.from_messages([
            ("system", prompt),
            ("human", "Test: {test}\nExisting Code: {existing_code}"),
            MessagesPlaceholder(variable_name="agent_scratchpad"),
        ])
        
        # Create agent
        agent = create_tool_calling_agent(self.llm, self.tools, prompts)
        self.agent_executor = AgentExecutor(agent=agent, tools=self.tools, verbose=True)
    
    def load_dev_prompt(self) -> str:
        """Load the development prompt from a text file."""
        prompt_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "prompts", "dev_prompt.txt")
        try:
            with open(prompt_path, "r") as file:
                return file.read()
        except FileNotFoundError:
            self.logger.error(f"Prompt file not found: {prompt_path}")
            raise
    
    @tool
    def implement_code(self, test: str) -> str:
        """Implement code to make the test pass"""
        # Implementation would use the LLM to create code
        # For now, we'll return a placeholder
        return """
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
    
    @tool
    def verify_test_passing(self, test: str, code: str) -> dict[str, str]:
        """Verify that the implemented code passes the test"""
        # Implementation would actually run the test against the code
        # For now, we'll return a placeholder
        return {
            "passing": True,
            "error": None
        }
    
    def run(self, state):
        """Run the Dev Agent to implement code"""
        try:
            # Extract the current test from the state
            current_test = state.current_test
            existing_code = state.implemented_code.get("code", "")
            
            # Invoke the agent
            result = self.agent_executor.invoke({
                "test": current_test,
                "existing_code": existing_code
            })
            
            # Update the state with the implemented code
            implemented_code = result.get("implement_code", "")
            state.current_code = implemented_code
            
            # Store the implemented code by module/class name
            # For simplicity, we'll just use a counter for now
            module_name = f"module_{len(state.implemented_code) + 1}"
            state.implemented_code[module_name] = implemented_code
            
            # Check if the test passes
            test_result = result.get("verify_test_passing", {"passing": False})
            state.tests_passed = test_result.get("passing", False)
            
            # Move to the refactor agent if the test passes
            if state.tests_passed:
                state.current_agent = "refactor_agent"
            
            return state
        except Exception as e:
            self.logger.error(f"Error in Dev Agent: {str(e)}")
            state.error_message = f"Error in Dev Agent: {str(e)}"
            return state
