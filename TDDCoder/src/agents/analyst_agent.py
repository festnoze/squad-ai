import logging
from langchain.tools import tool
from langchain_core.prompts import ChatPromptTemplate
from tdd_workflow.tdd_workflow_state import TDDWorkflowState

class AnalystAgent:
    def __init__(self, llm):
        self.logger = logging.getLogger(__name__)
        self.llm = llm
        self.tools = [self.create_implementation_steps]

    def load_analyst_prompt(self):
        with open("src/prompts/analyst_prompt.txt", "r") as f:
            return f.read()

    @tool
    def create_implementation_steps(self, user_story: str, scenarios: list[dict[str, str]]) -> list[dict[str, str]]:
        """Analyzes the user story and BDD scenarios to create a list of implementation steps."""
        self.logger.info("Creating mocked implementation steps based on scenarios.")
        steps = []
        for i, scenario in enumerate(scenarios, 1):
            steps.append({
                "step_id": i,
                "description": f"Implement the '{scenario.get('title', f'scenario {i}')}' scenario.",
                "scenario": scenario
            })
        return steps

    def run(self, state: TDDWorkflowState) -> TDDWorkflowState:
        """Runs the analyst agent to determine the next steps."""
        self.logger.info("--- ANALYST AGENT ---")

        try:
            # If implementation steps haven't been created yet, create them.
            if not state.implementation_steps:
                self.logger.info("Creating implementation plan...")
                # Note: In a real implementation, the user_story would be a string, not a dict.
                # We are accessing the 'description' key based on the provided bowling_scoring.json.
                state.implementation_steps = self.create_implementation_steps(
                    user_story=state.user_story.get('description', ''),
                    scenarios=state.scenarios
                )

            # Determine if the implementation is complete.
            if state.current_step_index >= len(state.implementation_steps):
                self.logger.info("All implementation steps are complete.")
                state.is_implementation_complete = True
                return state

            # Set the current scenario for the next agent.
            current_step = state.implementation_steps[state.current_step_index]
            # Format the scenario dict into a readable string
            scenario_dict = current_step['scenario']
            scenario_text = (
                f"Title: {scenario_dict.get('title', 'N/A')}\n"
                f"Given: {scenario_dict.get('given', 'N/A')}\n"
                f"When: {scenario_dict.get('when', 'N/A')}\n"
                f"Then: {scenario_dict.get('then', 'N/A')}"
            )
            state.current_scenario = {
                'description': current_step['description'],
                'scenario_text': scenario_text
            }
            self.logger.info(f"Next step ({current_step['step_id']}/{len(state.implementation_steps)}): {current_step['description']}")

        except Exception as e:
            self.logger.error(f"Error in Analyst Agent: {e}", exc_info=True)
            state.error = True
            state.error_message = f"An unexpected error occurred in the Analyst Agent: {e}"

        return state
