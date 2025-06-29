import logging
import os
from langchain.tools import tool
from langchain.agents import AgentExecutor, create_tool_calling_agent
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from agents.shared_tools import run_linter, run_tests

class UnitTestAgent:
    def __init__(self, llm):
        self.logger = logging.getLogger(__name__)
        self.llm = llm
        
        # Define tools
        self.tools = [
            self.create_unit_test,
            self.check_test_coverage,
            run_linter,
            run_tests
        ]
        
        # Create prompt
        prompt = self.load_test_prompt()
        prompts = ChatPromptTemplate.from_messages([
            ("system", prompt),
            ("human", "Scenario: {scenario}\nImplemented Code: {implemented_code}"),
            MessagesPlaceholder(variable_name="agent_scratchpad"),
        ])
        
        # Create agent
        agent = create_tool_calling_agent(self.llm, self.tools, prompts)
        self.agent_executor = AgentExecutor(agent=agent, tools=self.tools, verbose=True)
    
    def load_test_prompt(self) -> str:
        """Load the test prompt from a text file."""
        prompt_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "prompts", "test_prompt.txt")
        try:
            with open(prompt_path, "r") as file:
                return file.read()
        except FileNotFoundError:
            self.logger.error(f"Prompt file not found: {prompt_path}")
            raise
    
    @tool
    def create_unit_test(self, scenario: str) -> str:
        """Create a unit test based on a Gherkin scenario"""
        # Implementation would use the LLM to create a unit test
        # For now, we'll return a placeholder
        return """
        def test_successful_login():
            # Given the user has a valid account
            user = create_test_user("testuser", "password123")
            
            # When they enter correct credentials
            result = login("testuser", "password123")
            
            # Then they should be logged in successfully
            assert result.success is True
            assert result.user_id == user.id
        """
    
    @tool
    def check_test_coverage(self, scenarios: list[str], implemented_tests: list[str]) -> dict[str, any]:
        """Check if all scenarios are covered by tests"""
        # Implementation would use the LLM to check coverage
        # For now, we'll return a placeholder
        return {
            "all_covered": len(implemented_tests) >= len(scenarios),
            "coverage_percentage": min(100, int(len(implemented_tests) / max(1, len(scenarios)) * 100)),
            "uncovered_scenarios": [] if len(implemented_tests) >= len(scenarios) else ["Some scenario"]
        }
    
    def run(self, state):
        """Run the Test Agent to create a unit test"""
        try:
            # Check if there are remaining scenarios to test
            if not state.remaining_scenarios:
                # All scenarios are covered, we're done
                state.is_complete = True
                return state
            
            # Get the next scenario to test
            current_scenario = state.remaining_scenarios[0]
            
            # Invoke the agent
            result = self.agent_executor.invoke({
                "scenario": current_scenario,
                "implemented_code": state.implemented_code
            })
            
            # Update the state with the new test
            current_test = result.get("create_unit_test", "")
            state.current_test = current_test
            state.implemented_tests.append(current_test)
            
            # Remove the scenario from the remaining list
            state.remaining_scenarios.pop(0)
            
            # Check if we should continue or end
            if state.remaining_scenarios:
                state.current_agent = "dev_agent"  # Move to the dev agent
            else:
                state.is_complete = True  # We're done with all scenarios
            
            return state
        except Exception as e:
            self.logger.error(f"Error in Test Agent: {str(e)}")
            state.error_message = f"Error in Test Agent: {str(e)}"
            return state
