import logging
import os
import uuid
from uuid import UUID
import random
import asyncio
from langgraph.graph import StateGraph, END
from langchain_core.language_models.chat_models import BaseChatModel

# Models
from agents.phone_conversation_state_model import PhoneConversationState
from api_client.request_models.user_request_model import UserRequestModel, DeviceInfoRequestModel
from api_client.request_models.conversation_request_model import ConversationRequestModel
from api_client.request_models.query_asking_request_model import QueryAskingRequestModel

# Agents
from agents.lead_agent import LeadAgent
from agents.calendar_agent import CalendarAgent
from agents.sf_agent import SFAgent

# Clients
from api_client.studi_rag_inference_api_client import StudiRAGInferenceApiClient
from api_client.salesforce_api_client import SalesforceApiClient
from api_client.salesforce_api_client_interface import SalesforceApiClientInterface
from api_client.rag_query_interface import RagQueryInterface
from api_client.conversation_persistence_interface import ConversationPersistenceInterface
from database.conversation_persistence_service import ConversationLocalPersistenceService
from database.conversation_persistence_service_fake import ConversationPersistenceServiceFake

from managers.outgoing_manager import OutgoingManager
from managers.outgoing_audio_manager import OutgoingAudioManager
#
from llms.llm_info import LlmInfo
from llms.langchain_factory import LangChainFactory
from llms.langchain_adapter_type import LangChainAdapterType
from utils.envvar import EnvHelper
from utils.twilio_sid_converter import TwilioCallSidConverter
from agents.text_registry import AgentTexts

class AgentsGraph:
    waiting_music_bytes = None

    def __init__(self, outgoing_manager: OutgoingManager, call_sid: str = None, salesforce_client: SalesforceApiClientInterface = None, conversation_persistence: ConversationPersistenceInterface = None, rag_query_service: RagQueryInterface = None):
        logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        self.logger = logging.getLogger(__name__)
        self.calendar_speech_cannot_be_interupted : bool = False
        self.call_sid = call_sid
        self.logger.info(f"[{self.call_sid}] Agents graph initialization")
        
        # Who handles conversation history persistence? local/ studi_rag/ desactivated (fake)
        self.conversation_persistence: ConversationPersistenceInterface | None = None
        if conversation_persistence:
            self.conversation_persistence = conversation_persistence
        else:
            conversation_persistence_type = EnvHelper.get_conversation_persistence_type()
            if conversation_persistence_type == "local":
                self.conversation_persistence = ConversationLocalPersistenceService()
            elif conversation_persistence_type == "studi_rag":
                self.conversation_persistence = StudiRAGInferenceApiClient()
            else:
                self.conversation_persistence = ConversationPersistenceServiceFake()
        
        self.rag_query_service = rag_query_service or StudiRAGInferenceApiClient()
        
        self.salesforce_api_client: SalesforceApiClientInterface = salesforce_client or SalesforceApiClient()
        self.outgoing_manager: OutgoingManager = outgoing_manager
        
        self.has_waiting_music_on_calendar: bool = EnvHelper.get_waiting_music_on_calendar()
        self.has_waiting_music_on_rag: bool = EnvHelper.get_waiting_music_on_rag()
        self.available_actions: bool = EnvHelper.get_available_actions()

        lid_config_file_path = os.path.join(os.path.dirname(__file__), 'configs', 'lid_api_config.yaml')
        self.lead_agent_instance = LeadAgent(config_path=lid_config_file_path)
        self.logger.info(f"Initialize Lead Agent succeed with config: {lid_config_file_path}")
        
        openai_api_key = EnvHelper.get_openai_api_key()
        self.calendar_classifier_llm: BaseChatModel = LangChainFactory.create_llm_from_info(LlmInfo(type=LangChainAdapterType.OpenAI, model="gpt-4.1", timeout=30, temperature=0.1, api_key=openai_api_key))
        self.calendar_timeframes_llm: BaseChatModel = LangChainFactory.create_llm_from_info(LlmInfo(type=LangChainAdapterType.OpenAI, model="gpt-4.1-mini", timeout=50, temperature=0.1, api_key=openai_api_key))
        
        self.calendar_agent_instance = CalendarAgent(salesforce_api_client=self.salesforce_api_client, classifier_llm=self.calendar_classifier_llm, available_timeframes_llm=self.calendar_timeframes_llm, date_extractor_llm=self.calendar_timeframes_llm)
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
        workflow.add_node("begin_of_welcome_message", self.begin_of_welcome_message_node)
        workflow.add_edge("begin_of_welcome_message", "init_conversation")
        workflow.add_node("init_conversation", self.init_conversation_node)
        workflow.add_edge("init_conversation", "user_identification")
        workflow.add_node("user_identification", self.user_identification_node)
        workflow.add_node("user_identified", self.user_identified_node)
        workflow.add_edge("user_identified", END)
        workflow.add_node("user_new", self.user_new_node)        
        workflow.add_edge("user_new", END)
        
        workflow.add_conditional_edges(
            "user_identification",
            self.user_identification_decide_next_step,
            {
                "user_identified": "user_identified",
                "user_new": "user_new",
                END: END
            })

        workflow.add_node("wait_for_user_input", self.wait_for_user_input_node)
        workflow.add_edge("wait_for_user_input", END)

        if 'create_lead' in self.available_actions: 
            workflow.add_node("lead_agent", self.lead_agent_node)

        if 'schedule_appointement' in self.available_actions: 
            workflow.add_node("calendar_agent", self.calendar_agent_node)

        if 'ask_rag' in self.available_actions: 
            workflow.add_node("rag_course_agent", self.query_rag_api_about_trainings_agent_node)

        workflow.add_node("other_inquery", self.other_inquery_node)

        router_paths = {
            "begin_of_welcome_message": "begin_of_welcome_message",
            "other_inquery": "other_inquery",
            "wait_for_user_input": "wait_for_user_input",
            END: END
        }

        if 'schedule_appointement' in self.available_actions:
            router_paths["calendar_agent"] = "calendar_agent"
        if 'create_lead' in self.available_actions:
            router_paths["lead_agent"] = "lead_agent"
        if 'ask_rag' in self.available_actions:
            router_paths["rag_course_agent"] = "rag_course_agent"
            
        # Add conditional edges
        workflow.add_conditional_edges(
            "router",
            self.router_decide_next_step,
            router_paths
        )

        if 'schedule_appointement' in self.available_actions:
            workflow.add_edge("calendar_agent", END)
        if 'create_lead' in self.available_actions:
            workflow.add_edge("lead_agent", END)        
        if 'ask_rag' in self.available_actions: 
            workflow.add_edge("rag_course_agent", END)
        workflow.add_edge("other_inquery", END)

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
            state['agent_scratchpad']["next_agent_needed"] = "begin_of_welcome_message"
            return state

        if user_input:            
            if len(self.available_actions) == 1 and self.available_actions[0] == 'schedule_appointement':
                state['agent_scratchpad']["next_agent_needed"] = "calendar_agent"
                return state
            
            if len(self.available_actions) >= 1:                
                category = await self.analyse_user_input_for_dispatch_async(self.calendar_classifier_llm, user_input, state["history"])
                state["history"].append(("user", user_input))
                if category == "schedule_calendar_appointment":
                    state['agent_scratchpad']["next_agent_needed"] = "calendar_agent"
                elif category == "training_course_query":
                    state['agent_scratchpad']["next_agent_needed"] = "rag_course_agent"
                elif category == "others":
                    state['agent_scratchpad']["next_agent_needed"] = "other_inquery"
                return state
        state['agent_scratchpad']["next_agent_needed"] = "wait_for_user_input"
        return state

    async def analyse_user_input_for_dispatch_async(self, llm: any, user_input: str, chat_history: list[dict[str, str]]) -> str:
        """Analyse the user input and dispatch to the right agent"""  
        with open("app/agents/prompts/analyse_user_general_classifier_prompt.txt", 'r', encoding='utf-8') as file:
            prompt = file.read()
        
        # TODO: to improve using langchain history summarization, or our own existing in the RAG API.
        chat_history_str = "\n".join([f"[{msg[0]}]: {msg[1][:1000]}..." for msg in chat_history])
        
        # Reduce to max_history_chars and to max_msg_count total messages to avoid exceeding the context window length of the LLM.
        max_msg_chars = 16000 
        max_msg_count = 8
        if len(chat_history_str) > max_msg_chars:
            chat_history_str = "\n".join([f"[{msg[0]}]: {msg[1][:1000]}..." for msg in chat_history[-max_msg_count:]])
            chat_history_str = "... " + chat_history_str[-max_msg_chars:]
        
        actions_names = ""
        actions_descriptions = ""

        if 'schedule_appointement' in self.available_actions:
            actions_names += ", 'schedule_calendar_appointment'"
            actions_descriptions += "\n'schedule_calendar_appointment' category matches if the user query is related to scheduling a calendar appointment."

        if 'ask_rag' in self.available_actions:
            actions_names += ", 'training_course_query'"
            actions_descriptions += "\n'training_course_query' category matches if the user query is related to a training course or its informations, like access conditions, fundings, ..."

        prompt = prompt.format(user_input=user_input, chat_history=chat_history_str, actions_names=actions_names, actions_descriptions=actions_descriptions)
        
        response = await llm.ainvoke(prompt)
        
        self.logger.info(f"#> Router Analysis decide to dispatch to: |###> {response.content} <###|")
        return response.content

    async def begin_of_welcome_message_node(self, state: PhoneConversationState) -> dict:
        """Send the begin of welcome message to the user"""     
        await self._add_ai_answer_async(AgentTexts.start_welcome_text, state, persist=False)
        self.logger.info(f"[{state.get('call_sid', '')}] Sent 'begin of welcome message' to {state.get('caller_phone', 'N/A') }")
        return state

    async def init_conversation_node(self, state: PhoneConversationState) -> dict:
        """Initializes the conversation in the backend API."""
        if state.get('agent_scratchpad', {}).get('conversation_id', None) is not None:
            return state
        
        self.logger.info(f"Start init. RAG API for caller (User and a new conversation): {state.get('caller_phone')}") 
        
        try:
            await self.rag_query_service.test_client_connection_async()
        except Exception as e:
            self.logger.error(f"/!\\ Error testing connection to RAG API : {str(e)}")
            await self._add_ai_answer_async(AgentTexts.technical_error_text, state)    
            return state
        
        conversation_id = await self._init_user_and_new_conversation_in_backend_api_async(state.get('caller_phone'), state.get('call_sid'))
        if not conversation_id:
            await self._add_ai_answer_async(AgentTexts.technical_error_text, state, persist=False)    
        self.logger.info(f"Init. conversation persistence for phone: {state.get('caller_phone')}, call_sid: {state.get('call_sid')}")

        # Late persistence of welcome message (cannot persist before conversation has been created)
        if conversation_id:
            await self.conversation_persistence.add_ai_message_to_conversation_async(conversation_id, AgentTexts.start_welcome_text)

        if state.get('agent_scratchpad') is None: state['agent_scratchpad'] = {}
        state['agent_scratchpad']['conversation_id'] = conversation_id

        self.logger.info(f"Created conversation of id: {conversation_id}, sent welcome message.")
        return state

    async def _init_user_and_new_conversation_in_backend_api_async(self, calling_phone_number: str, call_sid: str) -> str | None:
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
            user_id = await self.conversation_persistence.create_or_retrieve_user_async(user_RM)
            # Use Twilio call Sid as uuid for conversation (converted with 'TwilioCallSidConverter') 
            call_sid_uuid = TwilioCallSidConverter.call_sid_to_uuid(call_sid)
            new_conversation_RM = ConversationRequestModel(user_id=user_id, messages=[], conversation_id=call_sid_uuid)
            self.logger.info(f"Creating new conversation for user: {user_id}")
            new_conv_id = await self.conversation_persistence.create_new_conversation_async(new_conversation_RM)
            return str(new_conv_id)

        except Exception as e:
            self.logger.error(f"Error creating conversation: {str(e)}")
            return None

    async def user_identification_node(self, state: PhoneConversationState) -> dict:        
        self.logger.info(f"Initializing SF Agent")
        call_sid = state.get('call_sid', 'N/A')
        phone_number = state.get('caller_phone', 'N/A')
        #accounts = await self.salesforce_api_client.get_persons_async()
        sf_account_info = await self.salesforce_api_client.get_person_by_phone_async(phone_number)

        # Single retry upon failure to retrieve SalesForce account
        if not sf_account_info:
            self.logger.info(f"[{call_sid}] No SalesForce account found for phone number: {phone_number}. Retry once to retrieve.")       
            sf_account_info = await self.salesforce_api_client.get_person_by_phone_async(phone_number)
            if not sf_account_info: self.logger.warning(f"[{call_sid}] No SalesForce account found after retry for phone number: {phone_number}. New user: needs LID creation.")
        leads_info = await self.salesforce_api_client.get_leads_by_details_async(phone_number)

        state['agent_scratchpad']['sf_account_info'] = sf_account_info.get('data', {}) if sf_account_info else {}
        state['agent_scratchpad']['sf_leads_info'] = leads_info[0] if leads_info else {}
        self.logger.info(f"[{call_sid}] Stored sf_account_info: {sf_account_info.get('data', {}) if sf_account_info else "-no SF account found-"} in agent_scratchpad")

        state.get('agent_scratchpad', {})['next_agent_needed'] = "user_identified" if sf_account_info else "user_new"
        return state

    async def user_identification_decide_next_step(self, state: PhoneConversationState) -> dict:
        """Decide next step based on user identification"""
        return state.get('agent_scratchpad', {}).get('next_agent_needed')

    async def user_identified_node(self, state: PhoneConversationState) -> dict:
        """For existing user: User identity confirmation"""        
        end_welcome_text = AgentTexts.unavailability_for_returning_prospect

        first_name = state['agent_scratchpad']['sf_account_info'].get('FirstName', '').strip()
        end_welcome_text += f"{AgentTexts.thanks_to_come_back} {first_name}."

        if 'schedule_appointement' in self.available_actions:
            end_welcome_text += f"{AgentTexts.appointment_text}"# {owner_first_name}."
        if 'ask_rag' in self.available_actions:
            end_welcome_text += f"\n{AgentTexts.questions_text}"
            
        if len(self.available_actions) > 1:
            end_welcome_text += f"\n{AgentTexts.select_action_text}"
        elif self.available_actions[0] == 'schedule_appointement':
            end_welcome_text += f"\n{AgentTexts.yes_no_consent_text}"
        elif self.available_actions[0] == 'ask_rag':
            end_welcome_text += f"\n{AgentTexts.ask_question_text}"

        await self._add_ai_answer_async(end_welcome_text, state)
        return state

    async def user_new_node(self, state: PhoneConversationState) -> dict:
        """For new user: Case not handled. Ask the user to call during the opening hours"""
        await self._add_ai_answer_async(AgentTexts.unavailability_for_new_prospect, state)
        return state

    async def send_end_of_welcome_message_node(self, state: PhoneConversationState) -> dict:
        """Send the end of welcome message to the user"""
        call_sid = state.get('call_sid', 'N/A')
        phone_number = state.get('caller_phone', 'N/A')

        sf_account = state.get('agent_scratchpad', {}).get('sf_account_info', {})
        leads_info = state.get('agent_scratchpad', {}).get('sf_leads_info', {})
        
        # Message signaling: sales unavailability
        if sf_account:
            await self._add_ai_answer_async(AgentTexts.unavailability_for_returning_prospect)
        else:
            await self._add_ai_answer_async(AgentTexts.unavailability_for_new_prospect)

        # Message signaling: available actions
        if sf_account:
            civility = sf_account.get('Salutation', '')
            if civility:
                civility = civility.replace("Mme", "Madame").replace("Melle", "Mademoiselle").replace("Mr.", "Monsieur").replace("Ms.", "Madame").strip()
            else:
                civility = ''
            first_name = sf_account.get('FirstName', '').strip()
            last_name = sf_account.get('LastName', '').strip()
            owner_first_name = sf_account.get('Owner', {}).get('Name', '').strip()
            
            end_welcome_text = f"{AgentTexts.thanks_to_come_back} {civility} {first_name} {last_name}."
            if 'schedule_appointement' in self.available_actions:
                end_welcome_text += f"{AgentTexts.appointment_text}"# {owner_first_name}."
            if 'ask_rag' in self.available_actions:
                end_welcome_text += f"\n{AgentTexts.questions_text}"
                
            if len(self.available_actions) > 1:
                end_welcome_text += f"\n{AgentTexts.select_action_text}"
            elif self.available_actions[0] == 'schedule_appointement':
                end_welcome_text += f"\n{AgentTexts.yes_no_consent_text}"
            elif self.available_actions[0] == 'ask_rag':
                end_welcome_text += f"\n{AgentTexts.ask_question_text}"
        else:
            end_welcome_text = "Pour votre premier appel, je vais vous demander quelques informations, afin de planifier un rendez-vous avec un conseiller en formation."
                
        await self._add_ai_answer_async(end_welcome_text)

        self.logger.info(f"[{call_sid}] Sent 'end of welcome message' to {phone_number}")
        return state
    
    async def wait_for_user_input_node(self, state: PhoneConversationState) -> dict:
        """Wait for user input"""
        return state

    async def lead_agent_node(self, state: PhoneConversationState) -> dict:
        """Handles lead qualification and information gathering using LeadAgent."""
        call_sid = state.get('call_sid', 'N/A')
        self.logger.info(f"[{call_sid}] Entering Lead Agent node")
        user_input = state['user_input']
        # Retrieve previously extracted info from scratchpad if continuing interaction
        current_extracted_info = state.get('agent_scratchpad', {}).get('lead_extracted_info', {})

        if not self.lead_agent_instance:
            self.logger.error(f"[{call_sid}] LeadAgent not initialized. Cannot process.")
            await self._add_ai_answer_async(AgentTexts.lead_agent_error_text)
            return {"history": [("user", user_input), ("assistant", AgentTexts.lead_agent_error_text)], "agent_scratchpad": {"error": "LeadAgent not initialized"}}

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
                "history": [("user", user_input), ("assistant", response_text)],
                "agent_scratchpad": updated_scratchpad
            }

        except Exception as e:
            self.logger.error(f"[{call_sid[-4:]}] Error in Lead Agent node: {e}", exc_info=True)
            response_text = "Je rencontre un problème pour traiter votre demande."
            # Include the error in the scratchpad for debugging if needed
            error_scratchpad = state.get('agent_scratchpad', {})
            error_scratchpad['error'] = str(e)
            return {"history": [("user", user_input), ("assistant", response_text)], "agent_scratchpad": error_scratchpad}

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
                self.calendar_agent_instance._set_user_info(
                    user_id=sf_account_info.get('Id', ''),
                    first_name=sf_account_info.get('FirstName', ''),
                    last_name=sf_account_info.get('LastName', ''),
                    email=sf_account_info.get('Email', ''),
                    owner_id=sf_account_info.get('Owner').get('Id', ''),
                    owner_name=sf_account_info.get('Owner').get('Name', '')
                )
                chat_history = state.get('history', [])

                # Limit the history to the last 10 messages to avoid context overflow
                max_history_length = 4
                if len(chat_history) > max_history_length:
                    self.logger.info(f"[{call_sid[-4:]}] Chat history has {len(chat_history)} messages. Truncating to the last {max_history_length}.")
                    chat_history = chat_history[-max_history_length:]

                if self.has_waiting_music_on_calendar:
                    waiting_music_task = await self._start_waiting_music_async()

                calendar_agent_answer = await self.calendar_agent_instance.run_async(user_input, chat_history)
                
                if self.calendar_speech_cannot_be_interupted:
                    self.outgoing_manager.can_speech_be_interupted = False

                await self._add_ai_answer_async(calendar_agent_answer)

                if self.has_waiting_music_on_calendar:
                    await self._stop_waiting_music_async(waiting_music_task)

                return state
                
            except Exception as e:
                self.logger.error(f"[{call_sid[-4:]}] Error in Calendar Agent node: {e}", exc_info=True)
                return state

    async def router_decide_next_step(self, state: PhoneConversationState) -> str:
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

            # waiting_messages = ["Je suis en train de chercher les informations pour répondre à votre demande.",
            #                     "Je recherche les éléments d'informations pour vous répondre.",
            #                     "Je recherche dans ma base de connaissances.",
            #                     "Un instant, je consulte mes sources d'informations.",
            #                     "Laissez-moi vérifier quelques détails.",
            #                     "Laissez-moi un instant pour trouver la meilleure réponse.",
            #                     "Je rassemble les informations nécessaires."]
            
            # await self._add_ai_answer_async(random.choice(waiting_messages))

            if self.has_waiting_music_on_rag:
                waiting_music_task = await self._start_waiting_music_async()

            # Call but not await the RAG API to get the streaming response
            response = self.rag_query_service.rag_query_stream_async(
                                query_asking_request_model = rag_query_RM,
                                interrupt_flag = self.rag_interrupt_flag,
                                timeout = 120)

            full_answer = ""
            was_interrupted = False

            async for chunk in response:
                if self.has_waiting_music_on_rag:
                    await self._stop_waiting_music_async(waiting_music_task)
                
                # Vérifier si on a été interrompu entre les chunks
                if was_interrupted:                    
                    if isinstance(self.outgoing_manager, OutgoingAudioManager):
                        self.outgoing_manager.audio_sender.streaming_interruption_asked = True
                    self.logger.info("Speech interrupted while processing RAG response")
                    break
                    
                full_answer += chunk
                self.logger.info(f"Received chunk: << ... {chunk} ... >>")
                
                await self.outgoing_manager.enqueue_text_async(chunk)

            if full_answer:
                self.logger.info(f"Full answer received from RAG API: '{full_answer}'")
                state["history"].append(("assistant", full_answer))
                await self.conversation_persistence.add_ai_message_to_conversation_async(state['agent_scratchpad']['conversation_id'], full_answer)

            return state
                
        except Exception as e:
            self.logger.error(f"Error in RAG API communication: {str(e)}")
            # Use enhanced text-to-speech for error messages too
            await self._add_ai_answer_async(AgentTexts.rag_communication_error_text, state)

        return state

    async def other_inquery_node(self, state: PhoneConversationState) -> dict:
        """Handle other inquery"""
        call_sid = state.get('call_sid', 'N/A')
        phone_number = state.get('caller_phone', 'N/A')
        await self._add_ai_answer_async(AgentTexts.ask_to_repeat_text, state)
        self.logger.info(f"[{call_sid}] Sent 'other' message to {phone_number}")
        return state

    ### Helper methods ###

    async def _add_ai_answer_async(self, answer_text: str, state: PhoneConversationState, persist: bool = True) -> dict:
        """Send the answer's text, add it to the state history and to the API for persistence"""
        conv_id = state['agent_scratchpad'].get('conversation_id', None)
        state["history"].append(("assistant", answer_text))

        await self.outgoing_manager.enqueue_text_async(answer_text)

        if persist:
            await self.conversation_persistence.add_ai_message_to_conversation_async(conv_id, answer_text)
        
        return state
    
    def _load_file_bytes(self, file_path: str) -> bytes:
        with open(file_path, "rb") as f:
            return f.read()

    async def _start_waiting_music_async(self):
        # Replace waiting message by a background music that loops
        if not self.waiting_music_bytes:
            self.waiting_music_bytes = self._load_file_bytes("static/internal/waiting_music.pcm")
        waiting_music_task = None
        if isinstance(self.outgoing_manager, OutgoingAudioManager):
            while self.outgoing_manager.audio_sender.is_sending:
                await asyncio.sleep(0.1) 
            waiting_music_task = asyncio.create_task(self._loop_waiting_music_async(self.waiting_music_bytes))
        return waiting_music_task

    async def _loop_waiting_music_async(self, music_bytes: bytes):
        """Continuously play waiting music until interrupted"""
        try:
            while not self.outgoing_manager.audio_sender.streaming_interruption_asked:
                try:
                    # Play the music chunk
                    success = await self.outgoing_manager.audio_sender.send_audio_chunk_async(music_bytes)
                    
                    # If sending failed or was interrupted, break the loop
                    if not success or self.outgoing_manager.audio_sender.streaming_interruption_asked:
                        break
                        
                    # Small delay before restarting to avoid tight loop
                    await asyncio.sleep(0.1)
                    
                except asyncio.CancelledError:
                    # Task was cancelled, exit cleanly
                    break
                    
        except Exception as e:
            self.logger.error(f"Error in waiting music loop: {e}")
            # Don't re-raise non-cancellation exceptions to avoid disrupting the call

    async def _stop_waiting_music_async(self, waiting_music_task: asyncio.Task):
        if waiting_music_task and not waiting_music_task.done():
            # Signal interruption
            self.outgoing_manager.audio_sender.streaming_interruption_asked = True
            
            # Wait for the audio sender to actually stop sending
            while self.outgoing_manager.audio_sender.is_sending:
                await asyncio.sleep(0.05)
            
            # Cancel the task and wait for it to complete
            waiting_music_task.cancel()
            try:
                await waiting_music_task
            except asyncio.CancelledError:
                pass  # Expected when cancelling a task
