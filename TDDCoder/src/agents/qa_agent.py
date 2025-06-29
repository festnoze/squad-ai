import logging
from langchain.tools import tool
from langchain.agents import AgentExecutor, create_tool_calling_agent
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

class QAAgent:
    def __init__(self, llm):
        self.logger = logging.getLogger(__name__)
        self.llm = llm
        
        # Define tools
        self.tools = [
            self.create_gherkin_scenarios,
            self.identify_edge_cases
        ]
        
        # Create prompt
        prompt = self._load_prompt()
        prompts = ChatPromptTemplate.from_messages([
            ("system", prompt),
            ("human", "{user_story}"),
            MessagesPlaceholder(variable_name="agent_scratchpad"),
        ])
        
        # Create agent
        agent = create_tool_calling_agent(self.llm, self.tools, prompts)
        self.agent_executor = AgentExecutor(agent=agent, tools=self.tools, verbose=True)
    
    def _load_prompt(self) -> str:
        return """You are a QA Agent responsible for creating Gherkin/BDD scenarios from a User Story.

Your task is to analyze the User Story and create comprehensive Gherkin scenarios that cover both the main functionality and edge cases.

A good Gherkin scenario follows this format:
```gherkin
Feature: [Feature name]

  Scenario: [Scenario name]
    Given [precondition]
    When [action]
    Then [expected result]
```

For edge cases, consider:
- Invalid inputs
- Boundary conditions
- Error handling
- Performance considerations
- Security aspects

Use the provided tools to create Gherkin scenarios and identify edge cases.
"""
    
    @tool
    def create_gherkin_scenarios(self, user_story: dict[str, any]) -> list[str]:
        """Create Gherkin scenarios from the user story"""
        # Implementation would use the LLM to create Gherkin scenarios
        # For now, we'll return placeholders
        return [
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
    
    @tool
    def identify_edge_cases(self, user_story: dict[str, any]) -> list[str]:
        """Identify edge cases for the user story"""
        # Implementation would use the LLM to identify edge cases
        # For now, we'll return placeholders
        return [
            """Feature: User Authentication
              
              Scenario: Account lockout
                Given the user has a valid account
                When they enter incorrect credentials 5 times
                Then their account should be temporarily locked
            """,
            """Feature: User Authentication
              
              Scenario: Password reset
                Given the user has forgotten their password
                When they request a password reset
                Then they should receive a reset link via email
            """
        ]
    
    def run(self, state):
        """Run the QA Agent to create Gherkin scenarios"""
        try:
            # Extract the user story from the state
            user_story = state.user_story
            
            # Invoke the agent
            result = self.agent_executor.invoke({
                "user_story": user_story
            })
            
            # Update the state with the Gherkin scenarios
            main_scenarios = result.get("create_gherkin_scenarios", [])
            edge_cases = result.get("identify_edge_cases", [])
            
            # Combine all scenarios
            all_scenarios = main_scenarios + edge_cases
            
            state.gherkin_scenarios = all_scenarios
            state.remaining_scenarios = all_scenarios.copy()  # Copy for tracking
            state.current_agent = "test_agent"  # Move to the next agent
            
            return state
        except Exception as e:
            self.logger.error(f"Error in QA Agent: {str(e)}")
            state.error_message = f"Error in QA Agent: {str(e)}"
            return state
