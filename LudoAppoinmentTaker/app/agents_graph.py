import logging
import os
from langgraph.graph import StateGraph, END
#
from app.agents.conversation_state_model import ConversationState

# Safe import for agents
try:
    from agents.lead_agent import LeadAgent
    from agents.calendar_agent import CalendarAgent
    from agents.sf_agent import SFAgent
    agents_imported = True
except ImportError as e:
    agents_imported = False
    logger = logging.getLogger(__name__)
    logger.error(f"Error importing agents: {e}")

class AgentsGraph:
    def __init__(self):
        self.create_graph()

    import logging
    import os
    from langgraph.graph import StateGraph, END
    #
    from app.agents.conversation_state_model import ConversationState

    # Safe import for agents
    try:
        from agents.lead_agent import LeadAgent
        from agents.calendar_agent import CalendarAgent
        from agents.sf_agent import SFAgent
        agents_imported = True
    except ImportError as e:
        agents_imported = False
        logger = logging.getLogger(__name__)
        logger.error(f"Error importing agents: {e}")

    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    logger = logging.getLogger(__name__)

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
 
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

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
    """Determines the first agent to handle the query based on the conversation state."""
    call_sid = state.get('call_sid', 'N/A')
    logger.info(f"[{call_sid}] Routing initial query: {state['user_input']}")
    
    # Check if this is a returning user with SF info
    if state.get('agent_scratchpad', {}).get('sf_account_info'):
        logger.info(f"[{call_sid}] Routing to calendar_agent (returning user)")
        return "calendar_agent"
    
    # If we have partial lead information, continue with lead agent
    if state.get('agent_scratchpad', {}).get('lead_extracted_info'):
        logger.info(f"[{call_sid}] Routing to lead_agent (continuing lead collection)")
        return "lead_agent"
    
    # Check phone number to route to SF lookup
    if state.get('caller_phone'):
        logger.info(f"[{call_sid}] Routing to sf_agent for account lookup")
        return "sf_agent"
    
    # Default: Start with Lead Agent
    logger.info(f"[{call_sid}] Default routing to lead_agent")
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


# --- Agent Nodes ---
async def sf_agent_node(state: ConversationState) -> dict:
    """Handles Salesforce account lookup using SFAgent."""
    call_sid = state.get('call_sid', 'N/A')
    phone = state.get('caller_phone', '')
    logger.info(f"[{call_sid}] Entering SF Agent node for phone: {phone}")
    
    if not phone:
        logger.warning(f"[{call_sid}] No phone number available for SF lookup")
        return {"next_agent_needed": "lead_agent"}
    
    try:
        # Initialize SFAgent and look up account
        sf_agent = SFAgent("sf_agent.yaml")
        account_info = sf_agent.get_account_info(phone)
        
        updated_scratchpad = state.get('agent_scratchpad', {})
        
        if account_info:
            # Store account info for future use
            updated_scratchpad['sf_account_info'] = account_info
            
            # Prepare greeting for returning user
            first_name = account_info.get('FirstName', '')
            owner_first_name = account_info.get('OwnerFirstName', '')
            
            response_text = f"""
            Je suis ravi que vous nous contactiez à nouveau {first_name}. {owner_first_name} qui vous accompagne d'habitude n'est pas disponible.
            Je vais donc m'occuper de prendre un rendez-vous avec vous afin que {owner_first_name} puisse vous contacter à son retour.
            Pouvez-vous me donner le jour et le moment de la journée qui vous convient le mieux pour ce rendez-vous ?
            """
            
            updated_scratchpad['next_agent_needed'] = "calendar_agent"
        else:
            # No account found, continue with lead collection
            response_text = """
            Bienvenue chez Studi, l'école 100% en ligne !
            Je suis l'assistant virtuel Stud'IA, je prends le relais lorsque nos conseillers en formation ne sont pas présents.
            Pouvez-vous me laisser vos coordonnées : nom, prénom, email et numéro de téléphone afin qu'un conseiller en formation puisse vous contacter dès son retour ?
            """
            
            updated_scratchpad['next_agent_needed'] = "lead_agent"
        
        return {
            "history": [("AI", response_text)],
            "agent_scratchpad": updated_scratchpad
        }
        
    except Exception as e:
        logger.error(f"[{call_sid}] Error in SF Agent node: {e}", exc_info=True)
        # Default to lead agent in case of error
        return {
            "history": [("AI", "Bienvenue chez Studi. Pouvez-vous me laisser vos coordonnées afin qu'un conseiller puisse vous contacter ?")],
            "agent_scratchpad": {"error": str(e), "next_agent_needed": "lead_agent"}
        }

async def calendar_agent_node(state: ConversationState) -> dict:
    """Handles calendar operations using CalendarAgent."""
    call_sid = state.get('call_sid', 'N/A')
    user_input = state.get('user_input', '')
    logger.info(f"[{call_sid}] Entering Calendar Agent node")
    
    # Get SF account info from scratchpad
    sf_account_info = state.get('agent_scratchpad', {}).get('sf_account_info', {})
    
    if not sf_account_info:
        logger.warning(f"[{call_sid}] No SF account info available for calendar operations")
        return {
            "history": [("Human", user_input), ("AI", "Je n'ai pas trouvé vos informations. Pourriez-vous me donner vos coordonnées à nouveau ?")],
            "agent_scratchpad": {"next_agent_needed": "lead_agent"}
        }
    
    try:
        # Initialize Calendar Agent with user info from SF
        calendar_agent = CalendarAgent(
            first_name=sf_account_info.get('FirstName', ''),
            last_name=sf_account_info.get('LastName', ''),
            email=sf_account_info.get('Email', ''),
            owner_first_name=sf_account_info.get('OwnerFirstName', ''),
            owner_last_name=sf_account_info.get('OwnerLastName', ''),
            owner_email=sf_account_info.get('OwnerEmail', ''),
            config_path="calendar_agent.yaml"
        )
        
        # Process the user's input
        response_text = calendar_agent.analyze_text(user_input)
        
        # Update scratchpad with calendar agent state if needed
        updated_scratchpad = state.get('agent_scratchpad', {})
        
        # If appointment was created, we can end the conversation
        if "J'ai réservé un rendez-vous" in response_text:
            updated_scratchpad['appointment_created'] = True
        
        return {
            "history": [("Human", user_input), ("AI", response_text)],
            "agent_scratchpad": updated_scratchpad
        }
        
    except Exception as e:
        logger.error(f"[{call_sid}] Error in Calendar Agent node: {e}", exc_info=True)
        return {
            "history": [("Human", user_input), ("AI", "Je rencontre un problème pour gérer votre rendez-vous. Pourriez-vous réessayer plus tard ?")],
            "agent_scratchpad": {"error": str(e)}
        }

async def decide_next_step(state: ConversationState) -> str:
    """Determines the next node to visit based on the current state."""
    call_sid = state.get('call_sid', 'N/A')
    logger.info(f"[{call_sid}] Deciding next step")
    
    # Check if next agent is explicitly specified
    next_agent = state.get('agent_scratchpad', {}).get('next_agent_needed')
    if next_agent:
        logger.info(f"[{call_sid}] Explicit routing to: {next_agent}")
        return next_agent
    
    # Check lead agent status
    lead_status = state.get('agent_scratchpad', {}).get('lead_last_status')
    if lead_status:
        if lead_status == "lead_captured":
            logger.info(f"[{call_sid}] Lead captured, ending conversation.")
            return END
        elif lead_status == "api_error":
            logger.warning(f"[{call_sid}] API error occurred, ending conversation.")
            return END
        elif lead_status == "ask_user_for_info":
            logger.info(f"[{call_sid}] Need more lead info from user, ending graph run.")
            return END
    
    # Check calendar agent status
    if state.get('agent_scratchpad', {}).get('appointment_created'):
        logger.info(f"[{call_sid}] Appointment created, ending conversation.")
        return END
    
    # Default behavior
    logger.info(f"[{call_sid}] No specific routing condition met, ending graph run.")
    return END


# --- Build the Graph ---
def create_graph():
    workflow = StateGraph(ConversationState)
    logger.info("Agents graph ongoing creation.")

    # Add nodes
    workflow.add_node("route_initial_query", route_initial_query)
    workflow.add_node("lead_agent", lead_agent_node)
    workflow.add_node("calendar_agent", calendar_agent_node)
    workflow.add_node("sf_agent", sf_agent_node)

    workflow.set_entry_point("route_initial_query")

    # Define transitions
    # After each agent runs, decide where to go next (or end)
    workflow.add_conditional_edges(
        "lead_agent",
        decide_next_step,
        {
            "calendar_agent": "calendar_agent", # Route if needed
            "sf_agent": "sf_agent", # Route if needed
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
    logger.info("Agents graph compiled successfully.")
    return app_graph
