import logging
import os
import uuid
from uuid import UUID
from langgraph.graph import StateGraph, END

# Models
from app.agents.phone_conversation_state_model import PhoneConversationState
from app.api_client.request_models.user_request_model import UserRequestModel, DeviceInfoRequestModel
from app.api_client.request_models.conversation_request_model import ConversationRequestModel
from app.api_client.request_models.query_asking_request_model import QueryAskingRequestModel

# Agents
from app.agents.lead_agent import LeadAgent
from app.agents.calendar_agent import CalendarAgent
from app.agents.sf_agent import SFAgent

# Clients
from app.api_client.studi_rag_inference_api_client import StudiRAGInferenceApiClient
from app.api_client.salesforce_api_client import SalesforceApiClient
from app.managers.outgoing_manager import OutgoingManager
from llms.llm_info import LlmInfo
from llms.langchain_factory import LangChainFactory
from llms.langchain_adapter_type import LangChainAdapterType

class AgentsGraph:
    welcome_text = ""
    salesforce_api_client : SalesforceApiClient = SalesforceApiClient()
    def __init__(self, outgoing_manager: OutgoingManager, studi_rag_client: StudiRAGInferenceApiClient, call_sid: str):
        logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        self.logger = logging.getLogger(__name__)
        self.call_sid = call_sid
        self.logger.info(f"[{self.call_sid}] Agents graph initialization")
        
        self.studi_rag_inference_api_client = studi_rag_client

        self.outgoing_manager: OutgoingManager = outgoing_manager
        
        lid_config_file_path = os.path.join(os.path.dirname(__file__), 'configs', 'lid_api_config.yaml')
        self.lead_agent_instance = LeadAgent(config_path=lid_config_file_path)
        self.logger.info(f"Initialize Lead Agent succeed with config: {lid_config_file_path}")
        
        self.llm = LangChainFactory.create_llm_from_info(LlmInfo(type=LangChainAdapterType.OpenAI, model="gpt-4.1-mini", timeout=50, temperature=0.1, api_key=os.getenv("OPENAI_API_KEY")))
        
        self.calendar_agent_instance = CalendarAgent(llm_or_chain=self.llm)
        self.logger.info("Initialize Calendar Agent succeed")
        
        self.sf_agent_instance = SFAgent()
        self.logger.info("Initialize SF Agent succeed")
        self.graph = self._build_graph()
        
    def _build_graph(self):
        workflow = StateGraph(PhoneConversationState)
        self.logger.info(f"[{self.call_sid}] Agents graph ongoing creation.")

        # Add nodes & fixed edges
        workflow.set_entry_point("router")

        workflow.add_node("router", self.router)
        workflow.add_node("conversation_start", self.send_begin_of_welcome_message_node)
        workflow.add_edge("conversation_start", "init_conversation")
        workflow.add_node("init_conversation", self.init_conversation_node)
        workflow.add_edge("init_conversation", "user_identification")
        workflow.add_node("user_identification", self.user_identification_node)
        workflow.add_edge("user_identification", "conversation_start_end")
        workflow.add_node("conversation_start_end", self.send_end_of_welcome_message_node)
        workflow.add_node("wait_for_user_input", self.wait_for_user_input_node)
        workflow.add_edge("wait_for_user_input", END)

        workflow.add_node("lead_agent", self.lead_agent_node)
        workflow.add_node("calendar_agent", self.calendar_agent_node)
        workflow.add_node("rag_course_agent", self.query_rag_api_about_trainings_agent_node)

        # Add conditional edges
        workflow.add_conditional_edges(
            "router",
            self.decide_next_step,
            {
                "conversation_start": "conversation_start",
                "lead_agent": "lead_agent",
                "calendar_agent": "calendar_agent",
                "rag_course_agent": "rag_course_agent",
                "wait_for_user_input": "wait_for_user_input",
                END: END
            }
        )

        workflow.add_edge("calendar_agent", END)
        workflow.add_edge("rag_course_agent", END)

        # Add checkpointer if state needs to be persisted (e.g., using SQLite)
        # checkpointer = MemorySaver() # Example using in-memory checkpointer
        # app_graph = workflow.compile(checkpointer=checkpointer)

        app_graph = workflow.compile() # Compile w/o checkpointer
        self.logger.info(f"[{self.call_sid}] Agents graph compiled successfully.")
        return app_graph

    async def router(self, state: PhoneConversationState) -> dict:
        if not state.get('agent_scratchpad', None):
            state['agent_scratchpad'] = {}
        
        user_input = state.get('user_input')
        if not state.get('agent_scratchpad', {}).get('conversation_id', None):
            state['agent_scratchpad']["next_agent_needed"] = "conversation_start"
            return state

        if user_input:       
            state['history'].append(("Human", user_input))
            feedback_text = f"Très bien, vous avez demandé : \"{user_input}\". Un instant, j'analyse votre demande."
            await self.outgoing_manager.enqueue_text(feedback_text)

            category = await self.analyse_user_input_for_dispatch_async(user_input)
            if category == "schedule_calendar_appointment":
                state['agent_scratchpad']["next_agent_needed"] = "calendar_agent"
            elif category == "training_course_query":
                state['agent_scratchpad']["next_agent_needed"] = "rag_course_agent"
            elif category == "others":
                state['agent_scratchpad']["next_agent_needed"] = "conversation_start"
            return state
        state['agent_scratchpad']["next_agent_needed"] = "wait_for_user_input"
        return state


    async def analyse_user_input_for_dispatch_async(self, user_input: str) -> str:
        """Analyse the user input and dispatch to the right agent"""
        prompt = ("### Instructions ###"
                "Your aim is to analyse the following user query and return a single word corresponding to the category it belongs to."
                "The allowed values for categories are: ['schedule_calendar_appointment', 'training_course_query', 'others']."
                "'schedule_calendar_appointment' category matches if the user query is related to scheduling a calendar appointment."
                "'training_course_query' category matches if the user query is related to a training course or its informations, like access conditions, fundings, ..."
                "'others' category matches if the user query is not related to none of the previous categories."
                ""
                "### User query ###"
                f"The user query to analyse is: {user_input}")
        response = await self.llm.ainvoke(prompt)
        return response.content

    async def send_begin_of_welcome_message_node(self, state: PhoneConversationState) -> dict:
        """Send the begin of welcome message to the user"""
        call_sid = state.get('call_sid', 'N/A')
        phone_number = state.get('caller_phone', 'N/A')
        self.welcome_text = "Bonjour, je suis Stud'IA, l'assistante virtuelle de Studi."
        
        await self.outgoing_manager.enqueue_text(self.welcome_text)
        self.logger.info(f"[{call_sid}] Sent begin of welcome message to {phone_number}")
        return state

    async def init_conversation_node(self, state: PhoneConversationState) -> dict:
        """Initializes the conversation in the backend API."""
        if state.get('agent_scratchpad', {}).get('conversation_id', None) is not None:
            return state
        
        self.logger.info(f"Start init. RAG API for caller (User and a new conversation): {state.get('caller_phone')}") 
        conversation_id = await self.init_user_and_new_conversation_in_backend_api_async(state.get('caller_phone'), state.get('call_sid'))     
        self.logger.info(f"End init. RAG API for caller (User and a new conversation): {state.get('caller_phone')}")

        state['history'] = []
        
        if state.get('agent_scratchpad') is None: 
            state['agent_scratchpad'] = {}
        state['agent_scratchpad']['conversation_id'] = conversation_id
        self.logger.info(f"Created conversation of id: {conversation_id}, sent welcome message.")
        return state

    async def user_identification_node(self, state: PhoneConversationState) -> dict:        
        self.logger.info(f"Initializing SF Agent")
        call_sid = state.get('call_sid', 'N/A')
        phone_number = state.get('caller_phone', 'N/A')
        #accounts = await AgentsGraph.salesforce_api_client.get_persons_async()
        sf_account_info = await AgentsGraph.salesforce_api_client.get_person_by_phone_async(phone_number)
        leads_info = await AgentsGraph.salesforce_api_client.get_leads_by_details_async(phone_number)
        state['agent_scratchpad']['sf_account_info'] = sf_account_info.get('data', {}) if sf_account_info else {}
        state['agent_scratchpad']['sf_leads_info'] = leads_info[0] if any(leads_info) else {}
        self.logger.info(f"[{call_sid}] Stored sf_account_info: {sf_account_info.get('data', {})} in agent_scratchpad")
        return state

    async def send_end_of_welcome_message_node(self, state: PhoneConversationState) -> dict:
        """Send the end of welcome message to the user"""
        call_sid = state.get('call_sid', 'N/A')
        phone_number = state.get('caller_phone', 'N/A')

        sf_account = state.get('agent_scratchpad', {}).get('sf_account_info', {})
        leads_info = state.get('agent_scratchpad', {}).get('sf_leads_info', {})
        
        if sf_account:
            civility = sf_account.get('Salutation', '').replace("Mme", "Madame").replace("Melle", "Mademoiselle").replace("Mr.", "Monsieur")
            first_name = sf_account.get('FirstName', '')
            last_name = sf_account.get('LastName', '')
            owner_first_name = sf_account.get('Owner', {}).get('Name', '')
            
            end_welcome_text = f"""
            Merci de nous recontacter {civility} {first_name} {last_name}. 
            Je suis là pour vous aider en l'absence de votre conseiller, {owner_first_name}, qui vous accompagne habituellement.
            Je vous propose de prendre un rendez-vous avec {owner_first_name} afin de vous permettre d'échanger directement avec lui.
            Avez-vous un jour ou un moment de la journée qui vous convient le mieux pour ce rendez-vous ?
            """
        else:
            end_welcome_text = "Je suis là pour vous aider en l'absence de nos conseillers. Avez-vous des questions sur nos formations, ou souhaitez-vous prendre rendez-vous avec un conseiller ?"
                
        await self.outgoing_manager.enqueue_text(end_welcome_text)

        full_welcome_text = self.welcome_text + "\n" + end_welcome_text
        state['history'].append(("AI", full_welcome_text))
        conv_id = state['agent_scratchpad'].get('conversation_id', None)
        if conv_id:
            await self.studi_rag_inference_api_client.add_external_ai_message_to_conversation_async(conv_id, full_welcome_text)
        else:
            self.logger.warning("/!\\ ERROR: No conversation ID found in state. Unable to add welcome msg to conversation properly.")
        self.logger.info(f"[{call_sid}] Sent end of welcome message to {phone_number}")
        return state
    
    async def wait_for_user_input_node(self, state: PhoneConversationState) -> dict:
        """Wait for user input"""
        return state
    
    async def init_user_and_new_conversation_in_backend_api_async(self, calling_phone_number: str, call_sid: str):
        """ Initialize the user session in the backend API: create user and conversation"""
        user_name_val = "Twilio incoming call " + (calling_phone_number or "Unknown User")
        ip_val = calling_phone_number or "Unknown IP"
        user_RM = UserRequestModel(
            user_id=None,
            user_name=user_name_val,
            IP=ip_val,
            device_info=DeviceInfoRequestModel(user_agent="twilio", platform="phone", app_version="", os="", browser="", is_mobile=True)
        )
        try:
            await self.studi_rag_inference_api_client.test_client_connection_async()
            user = await self.studi_rag_inference_api_client.create_or_retrieve_user_async(user_RM)
            user_id = UUID(user['id'])
            new_conversation = ConversationRequestModel(user_id=user_id, messages=[])
            self.logger.info(f"Creating new conversation for user: {user_id}")
            new_conversation = await self.studi_rag_inference_api_client.create_new_conversation_async(new_conversation)
            return new_conversation['id']

        except Exception as e:
            self.logger.error(f"Error creating conversation: {str(e)}")
            return str(uuid.uuid4())

    async def lead_agent_node(self, state: PhoneConversationState) -> dict:
        """Handles lead qualification and information gathering using LeadAgent."""
        call_sid = state.get('call_sid', 'N/A')
        self.logger.info(f"[{call_sid}] Entering Lead Agent node")
        user_input = state['user_input']
        # Retrieve previously extracted info from scratchpad if continuing interaction
        current_extracted_info = state.get('agent_scratchpad', {}).get('lead_extracted_info', {})

        if not self.lead_agent_instance:
            self.logger.error(f"[{call_sid}] LeadAgent not initialized. Cannot process.")
            response_text = "Je rencontre un problème technique avec l'agent de contact."
            await self.outgoing_manager.enqueue_text(response_text)
            return {"history": [("Human", user_input), ("AI", response_text)], "agent_scratchpad": {"error": "LeadAgent not initialized"}}

        try:
            # 1. Extract info using LLM (based on LeadAgent logic)
            # Use latest user input + potentially context from history if needed
            self.logger.debug(f"[{call_sid}] Extracting info from: {user_input}")
            # Ensure the agent method handles potential errors gracefully
            new_extracted_info = {}
            try:
                new_extracted_info = self.lead_agent_instance._extract_info_with_llm(user_input)
            except Exception as llm_exc:
                self.logger.error(f"[{call_sid}] Error during _extract_info_with_llm: {llm_exc}", exc_info=True)
                # Handle error, maybe return a specific state or default info

            self.logger.debug(f"[{call_sid}] Newly extracted info: {new_extracted_info}")

            # Merge new info with existing info from scratchpad
            combined_info = {**current_extracted_info, **new_extracted_info}
            self.logger.debug(f"[{call_sid}] Combined extracted info: {combined_info}")

            # 2. Identify missing fields (based on LeadAgent logic)
            missing_fields = self.lead_agent_instance._get_missing_fields(combined_info)
            self.logger.debug(f"[{call_sid}] Missing fields: {missing_fields}")

            # 3. Format request data (based on LeadAgent logic)
            request_data = self.lead_agent_instance._format_request(combined_info)
            self.logger.debug(f"[{call_sid}] Formatted request data: {request_data}")

            # 4. Validate request (based on LeadAgent logic)
            is_valid, validation_error = self.lead_agent_instance._validate_request(request_data)
            self.logger.info(f"[{call_sid}] Request validation - Valid: {is_valid}, Error: {validation_error}")

            # 5. Determine response and next step
            if not is_valid:
                missing_desc = ", ".join([f['description'] for f in missing_fields])
                response_text = f"Pourriez-vous me donner les informations manquantes, s'il vous plaît ? Il me manque : {missing_desc}"
                next_step = "ask_user_for_info" # Indicate we need more info
            else:
                # Attempt to send the lead data
                try:
                    self.logger.info(f"[{call_sid}] Sending valid lead data: {request_data}")
                    # NOTE: send_request is synchronous in the original agent.
                    # Consider making it async or running in a thread pool if it's slow.
                    # For now, assume it's acceptable to run synchronously within the async node.
                    result = self.lead_agent_instance.send_request(request_data)
                    self.logger.info(f"[{call_sid}] Lead injection API response status: {result.status_code}")

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
                    self.logger.error(f"[{call_sid}] Error sending lead data: {api_exc}", exc_info=True)
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
            self.logger.error(f"[{call_sid[-4:]}] Error in Lead Agent node: {e}", exc_info=True)
            response_text = "Je rencontre un problème pour traiter votre demande."
            # Include the error in the scratchpad for debugging if needed
            error_scratchpad = state.get('agent_scratchpad', {})
            error_scratchpad['error'] = str(e)
            return {"history": [("Human", user_input), ("AI", response_text)], "agent_scratchpad": error_scratchpad}

    async def old_user_identification_node(self, state: PhoneConversationState) -> dict:
        """Handles Salesforce account lookup using SFAgent."""
        call_sid = state.get('call_sid', 'N/A')
        phone = state.get('caller_phone', 'N/A')
        self.logger.info(f"[{call_sid}] Entering SF Agent node for phone: {phone}")
        
        if not phone:
            self.logger.warning(f"[{call_sid}] No phone number available for SF lookup")
            return {"next_agent_needed": "lead_agent"}
        
        try:
            # Initialize SFAgent and look up account
            sf_agent = SFAgent()
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
            self.logger.error(f"[{call_sid[-4:]}] Error in SF Agent node: {e}", exc_info=True)
            # Default to Lead Agent in case of error
            return {
                "history": [("AI", "Bienvenue chez Studi. Pouvez-vous me laisser vos coordonnées afin qu'un conseiller puisse vous contacter ?")],
                "agent_scratchpad": {"error": str(e), "next_agent_needed": "lead_agent"}
            }

    async def calendar_agent_node(self, state: PhoneConversationState) -> dict:
        """Handles calendar operations using CalendarAgent."""
        call_sid = state.get('call_sid', 'N/A')
        user_input = state.get('user_input', '')
        self.logger.info(f"[{call_sid}] Entering Calendar Agent node")
        
        # Get SF account info from scratchpad
        sf_account_info = state.get('agent_scratchpad', {}).get('sf_account_info', {})
        
        if sf_account_info:        
            try:
                # Initialize Calendar Agent with user info from SF
                self.calendar_agent_instance.set_user_info(
                    first_name=sf_account_info.get('FirstName', ''),
                    last_name=sf_account_info.get('LastName', ''),
                    email=sf_account_info.get('Email', ''),
                    owner_name=sf_account_info.get('Owner').get('Name', '')
                )
                chat_history = state.get('agent_scratchpad', {}).get('chat_history', [])
                await self.calendar_agent_instance.run_async(user_input, chat_history)
                
                # Process the user's input
                response_text = self.calendar_agent_instance.analyze_text(user_input)
                
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
                self.logger.error(f"[{call_sid[-4:]}] Error in Calendar Agent node: {e}", exc_info=True)
                return {
                    "history": [("Human", user_input), ("AI", "Je rencontre un problème pour gérer votre rendez-vous. Pourriez-vous réessayer plus tard ?")],
                    "agent_scratchpad": {"error": str(e)}
                }

    async def decide_next_step(self, state: PhoneConversationState) -> str:
        """Determines the next node to visit based on the current state."""
        call_sid = state.get('call_sid', 'N/A')
        self.logger.info(f"[~{call_sid[-4:]}] Deciding next step")
        
        # Check if next agent is explicitly specified
        next_agent = state.get('agent_scratchpad', {}).get('next_agent_needed')
        if next_agent:
            self.logger.info(f"[~{call_sid[-4:]}] Explicit routing to: {next_agent}")
            return next_agent
        
        # Check Lead Agent status
        lead_status = state.get('agent_scratchpad', {}).get('lead_last_status')
        if lead_status:
            if lead_status == "lead_captured":
                self.logger.info(f"[~{call_sid[-4:]}] Lead captured, ending conversation.")
                return END
            elif lead_status == "api_error":
                self.logger.warning(f"[~{call_sid[-4:]}] API error occurred, ending conversation.")
                return END
            elif lead_status == "ask_user_for_info":
                self.logger.info(f"[~{call_sid[-4:]}] Need more lead info from user, ending graph run.")
                return END
        
        # Check calendar agent status
        if state.get('agent_scratchpad', {}).get('appointment_created'):
            self.logger.info(f"[~{call_sid[-4:]}] Appointment created, ending conversation.")
            return END
        
        # Default behavior
        self.logger.info(f"[~{call_sid[-4:]}] No specific routing condition met, ending graph run.")
        return END

    async def query_rag_api_about_trainings_agent_node(self, state: PhoneConversationState) -> dict:
        """Handle the course agent node."""
        call_sid = state.get('call_sid', 'N/A')
        user_query = state.get('user_input', '')
        self.logger.info(f"> Ongoing RAG query on training course information. User request: '{user_query}' for: [{call_sid[-4:]}].")
        
        conversation_id=state.get('agent_scratchpad', {}).get('conversation_id', None)
        if not conversation_id:
            self.logger.error(f"[~{call_sid[-4:]}] No conversation ID found, ending graph run.")
            return END
        
        try:
            self.rag_interrupt_flag = {"interrupted": False} # Reset the interrupt flag before starting new streaming

            rag_query_RM = QueryAskingRequestModel(
                conversation_id=conversation_id,
                user_query_content= user_query,
                display_waiting_message=False
            )

            # Call but not await the RAG API to get the streaming response
            response = self.studi_rag_inference_api_client.rag_query_stream_async(
                                query_asking_request_model = rag_query_RM,
                                interrupt_flag = self.rag_interrupt_flag,
                                timeout = 120
                            )

            full_answer = ""
            was_interrupted = False
            async for chunk in response:
                # Vérifier si on a été interrompu entre les chunks
                if was_interrupted:
                    self.logger.info("Speech interrupted while processing RAG response")
                    break
                    
                full_answer += chunk
                self.logger.debug(f"Received chunk: << ... {chunk} ... >>")
                
                await self.outgoing_manager.enqueue_text(chunk)

            if full_answer:
                self.logger.info(f"Full answer received from RAG API: '{full_answer}'")
                state["history"].append(("AI", full_answer))
                #await self.studi_rag_inference_api_client.add_external_ai_message_to_conversation(state['agent_scratchpad']['conversation_id'], full_answer)

            return state
                
        except Exception as e:
            error_message = f"Je suis désolé, une erreur s'est produite lors de la communication avec le service."
            self.logger.error(f"Error in RAG API communication: {str(e)}")
            # Use enhanced text-to-speech for error messages too
            await self.outgoing_manager.enqueue_text(error_message)

        return state