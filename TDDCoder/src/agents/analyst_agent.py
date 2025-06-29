import logging
import os
from langchain.tools import tool
from langchain.agents import AgentExecutor, create_tool_calling_agent
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from agents.shared_tools import run_linter, run_tests

class AnalystAgent:
    def __init__(self, llm):
        self.logger = logging.getLogger(__name__)
        
        # Define the tools for the Analyst Agent
        self.tools = [
            self.analyze_requirements,
            self.prioritize_next_steps,
            run_linter,
            run_tests
        ]
        
        # Load the prompt from file
        prompt_text = self.load_analyst_prompt()
        
        # Define the prompt for the Analyst Agent
        prompt = ChatPromptTemplate.from_messages([
            ("system", prompt_text),
            MessagesPlaceholder(variable_name="chat_history"),
            ("user", "{input}"),
            MessagesPlaceholder(variable_name="agent_scratchpad"),
        ])
        
        # Create the agent
        self.agent = create_tool_calling_agent(llm, self.tools, prompt)
        self.agent_executor = AgentExecutor(agent=self.agent, tools=self.tools, verbose=True)
    
    def load_analyst_prompt(self) -> str:
        """Load the analyst prompt from a text file."""
        prompt_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "prompts", "analyst_prompt.txt")
        try:
            with open(prompt_path, "r") as file:
                return file.read()
        except FileNotFoundError:
            self.logger.error(f"Prompt file not found: {prompt_path}")
            raise
    
    @tool
    def analyze_requirements(self, requirements: dict[str, any]) -> dict[str, any]:
        """Analyze requirements and break them down into implementable steps.
        
        Args:
            requirements: A dictionary containing requirements information such as user stories or BDD scenarios.
            
        Returns:
            A dictionary containing the analyzed requirements broken down into steps.
        """
        # This will be implemented using the LLM's reasoning capabilities
        return {"steps": [], "message": "Requirements analysis placeholder"}
    
    @tool
    def prioritize_next_steps(self, current_state: dict[str, any]) -> dict[str, any]:
        """Determine the next test or code to implement based on the current state.
        
        Args:
            current_state: A dictionary containing the current state of the workflow, including implemented tests and code.
            
        Returns:
            A dictionary containing the next step to implement or a signal to end the workflow.
        """
        # This will be implemented using the LLM's reasoning capabilities
        return {"next_step": "", "is_complete": False, "message": "Next step prioritization placeholder"}
    
    def run(self, state):
        """Run the Analyst Agent with the given state.
        
        Args:
            state: The current state of the TDD workflow.
            
        Returns:
            The updated state after the Analyst Agent has processed it.
        """
        self.logger.info("Running Analyst Agent...")
        
        # Prepare the input for the agent
        agent_input = {
            "input": f"Analyze the following requirements and determine the next steps:\n\nUser Story: {state.user_story}\n\nScenarios: {state.scenarios}\n\nRemaining Scenarios: {state.remaining_scenarios}\n\nCurrent Scenario: {state.current_scenario}\n\nTests: {state.tests}\n\nCode: {state.code}",
            "chat_history": state.conversation_history
        }
        
        try:
            # Run the agent
            result = self.agent_executor.invoke(agent_input)
            
            # Extract the analysis results
            # For now, we'll just log the output and return the state as is
            self.logger.info(f"Analyst Agent result: {result['output']}")
            
            # In a real implementation, we would update the state based on the agent's output
            # For example, updating the next scenario to implement or marking the workflow as complete
            
            return state
            
        except Exception as e:
            self.logger.error(f"Error in Analyst Agent: {str(e)}")
            state.error = True
            state.error_message = f"Analyst Agent error: {str(e)}"
            return state
