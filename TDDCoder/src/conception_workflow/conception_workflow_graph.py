import logging
from typing import Dict, Any, List, Tuple, Union, Callable, TypedDict, cast

from langchain_core.runnables import RunnableConfig
from langgraph.graph import StateGraph, END

from conception_workflow.conception_workflow_state import ConceptionWorkflowState

# Import agents
from agents.po_agent import POAgent
from agents.qa_agent import QAAgent

class ConceptionWorkflowGraph:
    def __init__(self, llm):
        self.logger = logging.getLogger(__name__)
        
        # Initialize agents
        self.po_agent = POAgent(llm)
        self.qa_agent = QAAgent(llm)
        
        # Create the graph
        self.workflow = self._create_graph()
    
    def _create_graph(self) -> StateGraph:
        # Initialize the graph with our state
        graph = StateGraph(ConceptionWorkflowState)
        
        # Add nodes for each agent
        graph.add_node("po_agent", self.po_agent.run)
        graph.add_node("qa_agent", self.qa_agent.run)
        
        # Define conditional edges for all transitions to handle potential errors
        
        # PO Agent -> QA Agent (when user story is complete)
        # PO Agent -> END (if there's an error)
        graph.add_conditional_edges(
            "po_agent",
            self._po_agent_router,
            {"qa_agent": "qa_agent", END: END}
        )
        
        # QA Agent -> END (always, as it's the last step in conception)
        graph.add_edge("qa_agent", END)
        
        # Set the entry point
        graph.set_entry_point("po_agent")
        
        return graph
    
    def _po_agent_router(self, state: ConceptionWorkflowState) -> str:
        """Router for the PO Agent node."""
        if state.error:
            self.logger.error(f"Error in PO Agent: {state.error_message}")
            return END
        return "qa_agent"
    
    def run(self, user_request: str, config: RunnableConfig = None) -> ConceptionWorkflowState:
        """Run the conception workflow with the given user request."""
        # Initialize the state with the user request
        state = ConceptionWorkflowState(user_request=user_request)
        
        # Run the workflow
        self.logger.info("Starting conception workflow...")
        result = self.workflow.invoke(state, config)
        self.logger.info("Conception workflow completed.")
        
        return result
