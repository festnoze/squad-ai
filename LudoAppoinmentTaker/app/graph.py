import operator
import logging
import os
import json
from typing import TypedDict, Annotated, Sequence, List, Dict, Any
from langgraph.graph import StateGraph, END

# --- IMPORTANT ---
# Ensure you have moved lead_agent.py, calendar_agent.py, and sf_agent.py
# into the app/agents/ directory for these imports to work.
try:
    from agents.lead_agent import LeadAgent
    # from app.agents.calendar_agent import CalendarAgent # Import when ready
    # from app.agents.sf_agent import SFAgent # Import when ready
except ImportError as e:
    print(f"Error importing agents. Make sure they are in app/agents/: {e}")
    # Define dummy classes if import fails, so the graph can still be defined
    class LeadAgent: # Dummy
        def __init__(self, config_path=""): pass
        def _extract_info_with_llm(self, text): return {"error": "LeadAgent not found"}
        def _get_missing_fields(self, info): return [{"description": "Agent not loaded"}]
        def _format_request(self, info): return {"error": "Agent not loaded"}
        def _validate_request(self, data): return False, "Agent not loaded"
        def send_request(self, data): raise NotImplementedError("Dummy Agent")

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- State Definition ---
class ConversationState(TypedDict):
    """Represents the state of the conversation at any point."""
    call_sid: str
    user_input: str
    history: Annotated[Sequence[tuple[str, str]], operator.add]
    agent_scratchpad: Dict[str, Any] # Store agent-specific data like extracted info
    # Example additions:
    # lead_info: dict | None
    # appointment_details: dict | None
    # next_agent_needed: str | None # Hint for routing

# --- Agent Initialization ---
# Determine config path relative to project root
# (Adjust if lid_api_config.yaml is elsewhere)
CONFIG_PATH = os.path.join(os.path.dirname(__file__), '..', 'lid_api_config.yaml') # Assumes graph.py is in app/ and config is in root
try:
    lead_agent_instance = LeadAgent(config_path=CONFIG_PATH)
    logger.info(f"LeadAgent initialized with config: {CONFIG_PATH}")
except Exception as e:
    logger.error(f"Failed to initialize LeadAgent: {e}", exc_info=True)
    lead_agent_instance = None # Handle inability to load agent

# --- Node Functions ---

async def route_initial_query(state: ConversationState) -> str:
    """Determines the first agent to handle the query."""
    logger.info(f"[{state.get('call_sid', 'N/A')}] Routing initial query: {state['user_input']}")
    # Always start with Lead Agent for now
    return "lead_agent"

async def lead_agent_node(state: ConversationState) -> dict:
    """Handles lead qualification and information gathering using LeadAgent."""
    call_sid = state.get('call_sid', 'N/A')
    logger.info(f"[{call_sid}] Entering Lead Agent node")
    user_input = state['user_input']
    # Retrieve previously extracted info from scratchpad if continuing interaction
    current_extracted_info = state.get('agent_scratchpad', {}).get('lead_extracted_info', {})

    if not lead_agent_instance:
        logger.error(f"[{call_sid}] LeadAgent not initialized. Cannot process.")
        response_text = "Je rencontre un problème technique avec l'agent de contact."
        return {"history": [("Human", user_input), ("AI", response_text)], "agent_scratchpad": {"error": "LeadAgent not initialized"}}

    try:
        # 1. Extract info using LLM (based on LeadAgent logic)
        # Use latest user input + potentially context from history if needed
        logger.debug(f"[{call_sid}] Extracting info from: {user_input}")
        # Ensure the agent method handles potential errors gracefully
        new_extracted_info = {}
        try:
             new_extracted_info = lead_agent_instance._extract_info_with_llm(user_input)
        except Exception as llm_exc:
             logger.error(f"[{call_sid}] Error during _extract_info_with_llm: {llm_exc}", exc_info=True)
             # Handle error, maybe return a specific state or default info

        logger.debug(f"[{call_sid}] Newly extracted info: {new_extracted_info}")

        # Merge new info with existing info from scratchpad
        combined_info = {**current_extracted_info, **new_extracted_info}
        logger.debug(f"[{call_sid}] Combined extracted info: {combined_info}")

        # 2. Identify missing fields (based on LeadAgent logic)
        missing_fields = lead_agent_instance._get_missing_fields(combined_info)
        logger.debug(f"[{call_sid}] Missing fields: {missing_fields}")

        # 3. Format request data (based on LeadAgent logic)
        request_data = lead_agent_instance._format_request(combined_info)
        logger.debug(f"[{call_sid}] Formatted request data: {request_data}")

        # 4. Validate request (based on LeadAgent logic)
        is_valid, validation_error = lead_agent_instance._validate_request(request_data)
        logger.info(f"[{call_sid}] Request validation - Valid: {is_valid}, Error: {validation_error}")

        # 5. Determine response and next step
        if not is_valid:
            missing_desc = ", ".join([f['description'] for f in missing_fields])
            response_text = f"Pourriez-vous me donner les informations manquantes, s'il vous plaît ? Il me manque : {missing_desc}"
            next_step = "ask_user_for_info" # Indicate we need more info
        else:
            # Attempt to send the lead data
            try:
                logger.info(f"[{call_sid}] Sending valid lead data: {request_data}")
                # NOTE: send_request is synchronous in the original agent.
                # Consider making it async or running in a thread pool if it's slow.
                # For now, assume it's acceptable to run synchronously within the async node.
                result = lead_agent_instance.send_request(request_data)
                logger.info(f"[{call_sid}] Lead injection API response status: {result.status_code}")

                # Check response status code
                if 200 <= result.status_code < 300:
                    response_text = "Vous êtes bien enregistré. Un conseiller en formation va vous rappeler au plus vite. Passez une bonne journée de la part de Studi."
                    next_step = "lead_captured" # Indicate success
                else:
                    # Attempt to get error detail from response body if possible
                    error_detail = result.text[:100] if hasattr(result, 'text') else 'No details'
                    response_text = f"Désolé, une erreur est survenue ({result.status_code}: {error_detail}) lors de la création de votre fiche. Veuillez réessayer plus tard."
                    next_step = "api_error"
            except Exception as api_exc:
                logger.error(f"[{call_sid}] Error sending lead data: {api_exc}", exc_info=True)
                response_text = "Désolé, une erreur technique est survenue lors de l'enregistrement. Veuillez réessayer plus tard."
                next_step = "api_error"

        # Update state
        updated_scratchpad = state.get('agent_scratchpad', {})
        updated_scratchpad['lead_extracted_info'] = combined_info
        updated_scratchpad['lead_missing_fields'] = missing_fields
        updated_scratchpad['lead_last_status'] = next_step

        return {
            "history": [("Human", user_input), ("AI", response_text)],
            "agent_scratchpad": updated_scratchpad
        }

    except Exception as e:
        logger.error(f"[{call_sid}] Error in Lead Agent node: {e}", exc_info=True)
        response_text = "Je rencontre un problème pour traiter votre demande."
        # Include the error in the scratchpad for debugging if needed
        error_scratchpad = state.get('agent_scratchpad', {})
        error_scratchpad['error'] = str(e)
        return {"history": [("Human", user_input), ("AI", response_text)], "agent_scratchpad": error_scratchpad}


# --- Placeholder Nodes ---
# Define placeholders for other agents if they exist, otherwise remove
# async def calendar_agent_node(state: ConversationState) -> dict: ...
# async def sf_agent_node(state: ConversationState) -> dict: ...

async def decide_next_step(state: ConversationState) -> str:
    """Determines the next node to visit based on the current state."""
    call_sid = state.get('call_sid', 'N/A')
    logger.info(f"[{call_sid}] Deciding next step")
    last_status = state.get('agent_scratchpad', {}).get('lead_last_status')

    # Simple routing based on lead agent status
    if last_status == "lead_captured":
        logger.info(f"[{call_sid}] Lead captured, ending conversation.")
        # TODO: Potentially transition to Calendar or SF agent if needed based on extracted info
        return END
    elif last_status == "api_error":
         logger.warning(f"[{call_sid}] API error occurred, ending conversation.")
         return END
    elif last_status == "ask_user_for_info":
         logger.info(f"[{call_sid}] Need more info from user. Ending graph run, waiting for next input.")
         # The graph run ends here. The next user input will trigger a new graph invocation
         # starting from route_initial_query, which will hopefully hit lead_agent again.
         # The state (including partially extracted info) is preserved in stream_states in logic.py.
         return END
    else: # Default or unknown status
        logger.info(f"[{call_sid}] Defaulting to end conversation (status: {last_status}).")
        return END


# --- Build the Graph ---
def create_graph():
    workflow = StateGraph(ConversationState)

    # Add nodes
    workflow.add_node("lead_agent", lead_agent_node)
    # workflow.add_node("calendar_agent", calendar_agent_node) # Add when implemented
    # workflow.add_node("sf_agent", sf_agent_node) # Add when implemented

    # Define entry point
    # For now, always start with lead_agent
    workflow.set_entry_point("lead_agent")

    # Define transitions
    # After lead_agent runs, decide where to go next (or end)
    workflow.add_conditional_edges(
        "lead_agent",
        decide_next_step,
        {
            # "calendar_agent": "calendar_agent", # Route if needed
            # "sf_agent": "sf_agent", # Route if needed
            END: END # Route to END based on decide_next_step logic
        }
    )

    # Add transitions for other nodes when they are implemented
    # workflow.add_conditional_edges("calendar_agent", decide_next_step, ...)
    # workflow.add_conditional_edges("sf_agent", decide_next_step, ...)

    # Compile the graph
    # Add checkpointer if state needs to be persisted (e.g., using SQLite)
    # checkpointer = MemorySaver() # Example using in-memory checkpointer
    # app_graph = workflow.compile(checkpointer=checkpointer)
    app_graph = workflow.compile() # Compile without checkpointer for now
    logger.info("LangGraph compiled.")
    return app_graph
