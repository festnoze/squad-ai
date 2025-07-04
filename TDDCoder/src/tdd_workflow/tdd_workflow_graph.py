import logging
import uuid
from langchain_core.runnables import RunnableConfig
from langgraph.graph import StateGraph, END

from tdd_workflow.tdd_workflow_state import TDDWorkflowState

# Implementation Agents
from agents.analyst_agent import AnalystAgent
from agents.unit_test_agent import UnitTestAgent
from agents.dev_agent import DevAgent
from agents.refactor_agent import RefactorAgent

class TDDWorkflowGraph:
    def __init__(self, llm):
        self.logger = logging.getLogger(__name__)
        
        # Initialize implementation agents
        self.analyst_agent = AnalystAgent(llm)
        self.unit_test_agent = UnitTestAgent(llm)
        self.dev_agent = DevAgent(llm)
        self.refactor_agent = RefactorAgent(llm)
        
        # Create the graph
        self.workflow = self._create_graph()
    
    def _create_graph(self) -> StateGraph:
        # Initialize the graph with our state
        graph = StateGraph(TDDWorkflowState)
        
        # Add nodes for each implementation agent
        graph.add_node("analyst_agent", self.analyst_agent.run)
        graph.add_node("unit_test_agent", self.unit_test_agent.run)
        graph.add_node("dev_agent", self.dev_agent.run)
        graph.add_node("refactor_agent", self.refactor_agent.run)
        
        # Define conditional edges for all transitions to handle potential errors
        
        # Analyst Agent -> Test Agent (when analysis is complete and there are steps to implement)
        # Analyst Agent -> END (if implementation is complete or there's an error)
        graph.add_conditional_edges(
            "analyst_agent",
            self._analyst_agent_router,
            {"unit_test_agent": "unit_test_agent", END: END}
        )
        
        # Test Agent -> Dev Agent (when test is written)
        # Test Agent -> Analyst Agent (to re-analyze after completing a step)
        # Test Agent -> END (if there's an error)
        graph.add_conditional_edges(
            "unit_test_agent",
            self._unit_test_agent_router,
            {"dev_agent": "dev_agent", "analyst_agent": "analyst_agent", END: END}
        )
        
        # Dev Agent -> Refactor Agent (when code is implemented and tests pass)
        # Dev Agent -> Test Agent (if tests fail)
        # Dev Agent -> END (if there's an error)
        graph.add_conditional_edges(
            "dev_agent",
            self._dev_agent_router,
            {"refactor_agent": "refactor_agent", "unit_test_agent": "unit_test_agent", END: END}
        )
        
        # Refactor Agent -> Analyst Agent (after refactoring to determine next steps)
        # Refactor Agent -> END (if there's an error)
        graph.add_conditional_edges(
            "refactor_agent",
            self._refactor_agent_router,
            {"analyst_agent": "analyst_agent", END: END}
        )
        
        # Set the entry point
        graph.set_entry_point("analyst_agent")
        
        return graph.compile()
    
    def _analyst_agent_router(self, state: TDDWorkflowState) -> str:
        """Router for the Analyst Agent node."""
        if state.error:
            self.logger.error(f"Error in Analyst Agent: {state.error_message}")
            return END
        
        if state.is_implementation_complete:
            self.logger.info("Analyst has determined that implementation is complete. Workflow complete.")
            return END
        
        return "unit_test_agent"
    
    def _unit_test_agent_router(self, state: TDDWorkflowState) -> str:
        """Router for the Unit Test Agent node."""
        if state.error:
            self.logger.error(f"Error in Unit Test Agent: {state.error_message}")
            return END
        
        # If the analyst has determined there are no more steps, go back to the analyst.
        # The analyst will then set the 'is_implementation_complete' flag.
        if any(state.implementation_steps) and state.current_step_index >= len(state.implementation_steps):
            self.logger.info("All implementation steps are complete. Returning to Analyst.")
            return "analyst_agent"

        # If the test agent didn't produce a current test, go back to the analyst to re-analyze.
        if not state.current_test:
            state.error = True
            state.error_message = "Test Agent failed to produce tests for the current step."
            self.logger.error(state.error_message)
            return "analyst_agent"

        # Otherwise, proceed to the dev agent.
        return "dev_agent"
    
    def _dev_agent_router(self, state: TDDWorkflowState) -> str:
        """Router for the Dev Agent node."""
        if state.error:
            self.logger.error(f"Error in Dev Agent: {state.error_message}")
            return END
        
        if not state.tests_passed:
            self.logger.info("Tests failed. Going back to Test Agent.")
            return "unit_test_agent"
        
        return "refactor_agent"
    
    def _refactor_agent_router(self, state: TDDWorkflowState) -> str:
        """Router for the Refactor Agent node."""
        if state.error:
            self.logger.error(f"Error in Refactor Agent: {state.error_message}")
            return END
        
        # After refactoring, go back to the analyst to determine the next steps
        self.logger.info("Refactoring complete. Going back to Analyst for next steps.")
        return "analyst_agent"
    
    async def run_async(self, user_story_spec: str, acceptance_tests_gherkin: list[str] = [], project_name:str = None, config: RunnableConfig = None) -> TDDWorkflowState:
        """Run the TDD implementation workflow with the user story and acceptance tests.
        
        Args:
            user_story_spec: String containing the user story specification
            acceptance_tests_gherkin: list of acceptance tests in Gherkin format
            config: Optional runnable configuration
            
        Returns:
            The final state of the workflow
        """
        # Initialize project and state
        state = self._init_state(user_story_spec, acceptance_tests_gherkin, project_name)
        
        # Run the workflow
        self.logger.info("Starting TDD implementation workflow...")
        result = await self.workflow.ainvoke(state, config)
        self.logger.info("TDD implementation workflow completed.")
        
        return result

    def _init_state(self, user_story_spec: str, acceptance_tests_gherkin: list[str], project_name: str | None) -> TDDWorkflowState:
        """Initialize the TDDWorkflowState with user story and acceptance tests."""
        # Initialize project
        if not project_name:
            project_name = "Project_" + str(uuid.uuid4())
        import os

        projects_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "projects")
        os.makedirs(os.path.join(projects_dir, project_name), exist_ok=True)
        
        # Initialize the state with the user story and acceptance tests
        scenarios_as_dicts = [{"description": s} for s in acceptance_tests_gherkin]
        state: TDDWorkflowState = TDDWorkflowState(
            user_story={"description": user_story_spec},
            gherkin_scenarios=scenarios_as_dicts,
            remaining_scenarios=scenarios_as_dicts.copy(),
            implementation_steps=[],
            current_step_index=0,
            is_implementation_complete=False,
            is_complete=False
        )
        
        return state
        
    async def run_wo_graph_async(self, user_story_spec: str, acceptance_tests_gherkin: list[str] = [], project_name: str | None = None, config: RunnableConfig = None) -> TDDWorkflowState:      
        state: TDDWorkflowState = self._init_state(user_story_spec, acceptance_tests_gherkin, project_name)
        while not state.is_complete:
            state = self.analyst_agent.run(state)
            state = self.unit_test_agent.run(state)
            state = self.dev_agent.run(state)
            state = self.refactor_agent.run(state)
        return state
        
        
