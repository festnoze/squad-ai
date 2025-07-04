import logging
import os
from langchain.tools import tool
from langchain.agents import AgentExecutor, create_tool_calling_agent
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
#
from tdd_workflow.tdd_workflow_state import TDDWorkflowState
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
    def create_unit_test(self, scenario: dict[str, str]) -> str:
        """Create a unit test based on a Gherkin scenario
        
        Args:
            scenario: A dictionary containing Gherkin scenario with keys like 'title', 'given', 'when', 'then'
            
        Returns:
            A string containing a pytest test function
        """
        # Extract scenario components
        title = scenario.get('title', 'Unknown Scenario')
        given = scenario.get('given', '')
        when = scenario.get('when', '')
        then = scenario.get('then', '')
        
        # Convert title to a valid function name
        test_name = f"test_{title.lower().replace(' ', '_')}"
        
        # Create the test function with Arrange-Act-Assert pattern
        test_code = f"""def {test_name}() -> None:
    # Arrange (Given: {given})
    # Here we set up the test preconditions
    # Example implementation based on the Given statement:
    """ 
        
        # Add arrange code based on the 'given' part
        if 'valid account' in given.lower() or 'registered user' in given.lower():
            test_code += """    # Create a test user
    user = create_test_user("testuser", "password123")
    """
        elif 'product' in given.lower() or 'item' in given.lower():
            test_code += """    # Create a test product
    product = create_test_product("Test Product", 10.99)
    """
        else:
            test_code += """    # TODO: Implement specific setup for this scenario
    pass
    """
            
        # Add act code based on the 'when' part
        test_code += f"""
    # Act (When: {when})
    # Here we perform the action being tested
    # Example implementation based on the When statement:
    """
        
        if 'login' in when.lower() or 'credentials' in when.lower():
            test_code += """    result = login("testuser", "password123")
    """
        elif 'add' in when.lower() and ('cart' in when.lower() or 'basket' in when.lower()):
            test_code += """    result = add_to_cart(user_id=user.id, product_id=product.id)
    """
        else:
            test_code += """    # TODO: Implement specific action for this scenario
    result = None
    """
            
        # Add assert code based on the 'then' part
        test_code += f"""
    # Assert (Then: {then})
    # Here we verify the expected outcomes
    # Example assertions based on the Then statement:
    """
        
        if 'success' in then.lower() or 'logged in' in then.lower():
            test_code += """    assert result.success is True
    assert result.user_id is not None
    """
        elif 'error' in then.lower() or 'fail' in then.lower():
            test_code += """    assert result.success is False
    assert result.error_message is not None
    """
        elif 'added' in then.lower() and ('cart' in then.lower() or 'basket' in then.lower()):
            test_code += """    assert result.success is True
    assert len(get_cart_items(user.id)) > 0
    """
        else:
            test_code += """    # TODO: Implement specific assertions for this scenario
    assert True  # Replace with actual assertions
    """
            
        return test_code
    
    @tool
    def check_test_coverage(self, scenarios: list[str], implemented_tests: list[str]) -> dict[str, str]:
        """Check if all scenarios are covered by tests"""
        # Implementation would use the LLM to check coverage
        # For now, we'll return a placeholder
        return {
            "all_covered": len(implemented_tests) >= len(scenarios),
            "coverage_percentage": min(100, int(len(implemented_tests) / max(1, len(scenarios)) * 100)),
            "uncovered_scenarios": [] if len(implemented_tests) >= len(scenarios) else ["Some scenario"]
        }
    
    def run(self, state: TDDWorkflowState):
        """Run the Test Agent to create a unit test"""
        try:
            # Chcek if there are remaining scenarios to test
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
