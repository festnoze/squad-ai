import asyncio
import logging
import os
from asyncio import Task
from datetime import UTC, datetime, timedelta
from typing import Hashable
from uuid import UUID

from api_client.calendar_client_interface import CalendarClientInterface
from api_client.conversation_persistence_interface import ConversationPersistenceInterface
from api_client.rag_query_interface import RagQueryInterface
from api_client.request_models.conversation_request_model import ConversationRequestModel
from api_client.request_models.query_asking_request_model import QueryAskingRequestModel
from api_client.request_models.user_request_model import DeviceInfoRequestModel, UserRequestModel
from api_client.salesforce_api_client import SalesforceApiClient
from api_client.salesforce_user_client_interface import SalesforceUserClientInterface

# Clients
from api_client.studi_rag_inference_api_client import StudiRAGInferenceApiClient
from langchain_core.language_models.chat_models import BaseChatModel
from langgraph.graph import END, StateGraph
from langgraph.graph.state import CompiledStateGraph
from managers.consecutive_error_manager import ConsecutiveErrorManager
from managers.outgoing_audio_manager import OutgoingAudioManager
from managers.outgoing_manager import OutgoingManager
from services.outgoing_call_service import OutgoingCallService
from utils.envvar import EnvHelper
from utils.twilio_sid_converter import TwilioCallSidConverter

from agents.calendar_agent import CalendarAgent

# Models
from agents.phone_conversation_state_model import PhoneConversationState
from agents.text_registry import TextRegistry
from database.conversation_persistence_service_factory import ConversationPersistenceServiceFactory
from llms.langchain_adapter_type import LangChainAdapterType
from llms.langchain_factory import LangChainFactory
from llms.llm_info import LlmInfo
from services.analytics_service import AnalyticsService


class AgentsGraph:
    waiting_music_bytes = None
    thanks_to_come_back = "Merci de nous recontacter"

    def __init__(
        self,
        outgoing_manager: OutgoingManager,
        call_sid: str | None = None,
        salesforce_client: SalesforceUserClientInterface | None = None,
        calendar_client: CalendarClientInterface | None = None,
        conversation_persistence: ConversationPersistenceInterface | None = None,
        rag_query_service: RagQueryInterface | None = None,
    ):
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        )
        self.logger = logging.getLogger(__name__)
        self.calendar_speech_cannot_be_interupted: bool = False
        self.call_sid = call_sid
        self.logger.info(f"[{self.call_sid}] Agents graph initialization")
        self.available_actions: list[str] = EnvHelper.get_available_actions()
        self.consecutive_error_manager = ConsecutiveErrorManager(call_sid=call_sid)
        self.analytics_service = AnalyticsService()

        self.conversation_persistence_type = EnvHelper.get_conversation_persistence_type()
        # Who handles conversation history persistence? local/ studi_rag/ desactivated (fake)
        self.conversation_persistence: ConversationPersistenceInterface
        if conversation_persistence:
            self.conversation_persistence = conversation_persistence
        else:
            self.conversation_persistence = ConversationPersistenceServiceFactory.create_conversation_persistence_service(self.conversation_persistence_type, self.available_actions)

        self.rag_query_service = rag_query_service or StudiRAGInferenceApiClient()
        if not salesforce_client and not calendar_client:
            new_salesforce_client = SalesforceApiClient()
            salesforce_client = new_salesforce_client
            calendar_client = new_salesforce_client
        self.salesforce_api_client: SalesforceUserClientInterface = salesforce_client or SalesforceApiClient()
        self.calendar_api_client: CalendarClientInterface = calendar_client or SalesforceApiClient()
        self.outgoing_manager: OutgoingManager = outgoing_manager
        self.has_waiting_music_on_calendar: bool = EnvHelper.get_waiting_music_on_calendar()
        self.has_waiting_music_on_rag: bool = EnvHelper.get_waiting_music_on_rag()
        lid_config_file_path = os.path.join(os.path.dirname(__file__), "configs", "lid_api_config.yaml")
        self.logger.info(f"Initialize Lead Agent succeed with config: {lid_config_file_path}")
        openai_api_key = EnvHelper.get_openai_api_key()
        self.calendar_classifier_llm: BaseChatModel = LangChainFactory.create_llm_from_info(
            LlmInfo(
                type=LangChainAdapterType.OpenAI,
                model="gpt-4.1",
                timeout=30,
                temperature=0.1,
                api_key=openai_api_key,
            )
        )
        self.calendar_timeframes_llm: BaseChatModel = LangChainFactory.create_llm_from_info(
            LlmInfo(
                type=LangChainAdapterType.OpenAI,
                model="gpt-4.1-mini",
                timeout=50,
                temperature=0.1,
                api_key=openai_api_key,
            )
        )

        self.calendar_agent_instance = CalendarAgent(
            salesforce_api_client=self.salesforce_api_client,
            classifier_llm=self.calendar_classifier_llm,
            available_timeframes_llm=self.calendar_timeframes_llm,
            date_extractor_llm=self.calendar_timeframes_llm,
        )
        self.logger.info("Initialize Calendar Agent succeed")

        self.logger.info("Initialize SF Agent succeed")
        self.graph: CompiledStateGraph = self._build_graph()

    def _build_graph(self) -> CompiledStateGraph:
        workflow = StateGraph(PhoneConversationState)
        self.logger.info(f"[{self.call_sid}] Agents graph ongoing creation.")

        # Add nodes & fixed edges
        workflow.set_entry_point("router")
        workflow.add_node("router", self.router_node)
        workflow.add_node("begin_of_welcome_message", self.begin_of_welcome_message_node)
        workflow.add_edge("begin_of_welcome_message", "init_conversation")
        workflow.add_node("init_conversation", self.init_conversation_node)
        workflow.add_edge("init_conversation", "user_identification")
        workflow.add_node("user_identification", self.user_identification_node)
        workflow.add_node("user_identified", self.user_identified_node)
        workflow.add_edge("user_identified", END)
        workflow.add_node("user_new", self.user_new_node)
        workflow.add_edge("user_new", END)
        workflow.add_node("anonymous_user", self.anonymous_user_node)
        workflow.add_edge("anonymous_user", END)

        workflow.add_conditional_edges(
            "user_identification",
            self.user_identification_decide_next_step,
            {"user_identified": "user_identified", "user_new": "user_new", "anonymous_user": "anonymous_user", END: END},
        )

        workflow.add_node("wait_for_user_input", self.wait_for_user_input_node)
        workflow.add_edge("wait_for_user_input", END)

        if "schedule_appointement" in self.available_actions:
            workflow.add_node("calendar_agent", self.calendar_agent_node)

        if "ask_rag" in self.available_actions:
            workflow.add_node("rag_course_agent", self.query_rag_api_about_trainings_agent_node)

        workflow.add_node("other_inquery", self.other_inquery_node)
        workflow.add_node("no_appointment_requested", self.no_appointment_requested_node)
        workflow.add_node("max_consecutive_errors_reached", self.max_consecutive_errors_reached_node)

        router_paths: dict[Hashable, str] = {
            "begin_of_welcome_message": "begin_of_welcome_message",
            "other_inquery": "other_inquery",
            "wait_for_user_input": "wait_for_user_input",
            "user_identified": "user_identified",
            "user_new": "user_new",
            "no_appointment_requested": "no_appointment_requested",
            "max_consecutive_errors_reached": "max_consecutive_errors_reached",
            END: END,
        }

        if "schedule_appointement" in self.available_actions:
            router_paths["calendar_agent"] = "calendar_agent"
        if "create_lead" in self.available_actions:
            router_paths["lead_agent"] = "lead_agent"
        if "ask_rag" in self.available_actions:
            router_paths["rag_course_agent"] = "rag_course_agent"

        # Add conditional edges
        workflow.add_conditional_edges("router", self.router_decide_next_step, router_paths)

        if "schedule_appointement" in self.available_actions:
            workflow.add_edge("calendar_agent", END)
        if "create_lead" in self.available_actions:
            workflow.add_edge("lead_agent", END)
        if "ask_rag" in self.available_actions:
            workflow.add_edge("rag_course_agent", END)
        workflow.add_edge("other_inquery", END)
        workflow.add_edge("no_appointment_requested", END)

        # Add checkpointer if state needs to be persisted (e.g., using SQLite)
        # checkpointer = MemorySaver() # Example using in-memory checkpointer
        # app_graph = workflow.compile(checkpointer=checkpointer)

        app_graph = workflow.compile()  # Compile w/o checkpointer
        self.logger.info(f"[{self.call_sid}] Agents graph compiled successfully.")
        return app_graph

    async def ainvoke(self, *args, **kwargs):
        """Delegate ainvoke calls to the compiled graph."""
        return await self.graph.ainvoke(*args, **kwargs)

    def invoke(self, *args, **kwargs):
        """Delegate invoke calls to the compiled graph."""
        return self.graph.invoke(*args, **kwargs)

    async def router_node(self, state: PhoneConversationState) -> PhoneConversationState:
        if not state.get("agent_scratchpad", None):
            state["agent_scratchpad"] = {}

        # Check if we've reached maximum consecutive errors
        if self.consecutive_error_manager.is_max_consecutive_errors_reached(state):
            state["agent_scratchpad"]["next_agent_needed"] = "max_consecutive_errors_reached"
            return state

        user_input = state.get("user_input")
        if not state.get("agent_scratchpad", {}).get("conversation_id", None):
            state["agent_scratchpad"]["next_agent_needed"] = "begin_of_welcome_message"
            return state

        if not user_input:
            # Empty user input is an error - increment counter
            self.consecutive_error_manager.increment_consecutive_error_count(state)
            state["agent_scratchpad"]["next_agent_needed"] = "wait_for_user_input"
            return state

        # Single possible action: schedule new appointment
        if len(self.available_actions) == 1 and self.available_actions[0] == "schedule_appointement":
            # Verify if last assistant message was a consent request
            history = state.get("history", [])
            is_consent_asked, does_consent = await self._check_appointment_consent_request(user_input, history)

            if is_consent_asked:
                # Track appointment consent response
                call_sid = state.get("call_sid", "N/A")
                await self.analytics_service.track_appointment_consent_response_async(
                    call_sid=call_sid,
                    consent_given=does_consent,
                    user_input=user_input
                )

            if is_consent_asked and not does_consent:
                state["agent_scratchpad"]["next_agent_needed"] = "no_appointment_requested"
            else:
                # Successful routing to calendar agent - reset error counter
                self.consecutive_error_manager.reset_consecutive_error_count(state)
                state["agent_scratchpad"]["next_agent_needed"] = "calendar_agent"

        # Multiple possible actions: schedule appointment or ask RAG for training infos
        elif len(self.available_actions) >= 1:
            category = await self.analyse_user_input_for_dispatch_async(self.calendar_classifier_llm, user_input, state["history"])
            call_sid = state.get("call_sid", "N/A")

            if category == "schedule_calendar_appointment":
                # Successful routing to calendar agent - reset error counter
                self.consecutive_error_manager.reset_consecutive_error_count(state)
                state["agent_scratchpad"]["next_agent_needed"] = "calendar_agent"
                # Track agent dispatch
                await self.analytics_service.track_agent_dispatched_async(
                    call_sid=call_sid,
                    agent_type="calendar",
                    user_input_category=category
                )
            elif category == "training_course_query":
                # Successful routing to RAG agent - reset error counter
                self.consecutive_error_manager.reset_consecutive_error_count(state)
                state["agent_scratchpad"]["next_agent_needed"] = "rag_course_agent"
                # Track agent dispatch
                await self.analytics_service.track_agent_dispatched_async(
                    call_sid=call_sid,
                    agent_type="rag",
                    user_input_category=category
                )
            elif category == "others":
                # Going to other_inquery is considered an error - increment counter
                self.consecutive_error_manager.increment_consecutive_error_count(state)
                state["agent_scratchpad"]["next_agent_needed"] = "other_inquery"
        return state

    async def analyse_user_input_for_dispatch_async(self, llm: any, user_input: str, chat_history: list[dict[str, str]]) -> str:
        """Analyse the user input and dispatch to the right agent"""
        with open(
            "app/agents/prompts/analyse_user_general_classifier_prompt.txt",
            encoding="utf-8",
        ) as file:
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

        if "schedule_appointement" in self.available_actions:
            actions_names += ", 'schedule_calendar_appointment'"
            actions_descriptions += "\n'schedule_calendar_appointment' category matches if the user query is related to scheduling a calendar appointment."

        if "ask_rag" in self.available_actions:
            actions_names += ", 'training_course_query'"
            actions_descriptions += "\n'training_course_query' category matches if the user query is related to a training course or its informations, like access conditions, fundings, ..."

        prompt = prompt.format(
            user_input=user_input,
            chat_history=chat_history_str,
            actions_names=actions_names,
            actions_descriptions=actions_descriptions,
        )

        response = await llm.ainvoke(prompt)

        self.logger.info(f"#> Router Analysis decide to dispatch to: |###> {response.content} <###|")
        return response.content

    async def _check_appointment_consent_request(self, user_input: str, history: list) -> tuple[bool, bool]:
        """Check if the last assistant message was a consent request and analyze user response.

        Returns:
            tuple[bool, bool]: (is_consent_asked, does_consent)
            - is_consent_asked: True if last assistant message was asking for consent
            - consent_result: "oui" or "non" if consent was asked, None otherwise
        """
        if not history:
            return False, False

        # Look for last assistant message
        last_assistant_message = None
        for role, message in reversed(history):
            if role == "assistant":
                last_assistant_message = message
                break

        if last_assistant_message and last_assistant_message.endswith(TextRegistry.yes_no_consent_text):
            does_consent = await self._analyse_appointment_consent_async(user_input, history)
            return True, does_consent
        return False, False

    async def _analyse_appointment_consent_async(self, user_input: str, chat_history: list[dict[str, str]]) -> bool:
        """Analyse if user accepts or refuses the appointment proposal"""
        prompt = self._load_analyse_appointment_consent_prompt()
        chat_history_str = "\n".join([f"[{msg[0]}]: {msg[1][:1000]}..." for msg in chat_history])
        prompt = prompt.format(user_input=user_input, chat_history=chat_history_str)

        response = await self.calendar_classifier_llm.ainvoke(prompt)
        self.logger.info(f"#> Appointment Consent Analysis result: |###> {response.content} <###|")
        return response.content.strip().lower() == "oui"

    analyse_appointment_consent_prompt: str = ""

    def _load_analyse_appointment_consent_prompt(self) -> str:
        if not AgentsGraph.analyse_appointment_consent_prompt:
            with open(
                "app/agents/prompts/appointment_consent_classifier_prompt.txt",
                encoding="utf-8",
            ) as f:
                AgentsGraph.analyse_appointment_consent_prompt = f.read()
        return AgentsGraph.analyse_appointment_consent_prompt

    async def begin_of_welcome_message_node(self, state: PhoneConversationState) -> PhoneConversationState:
        """Send the begin of welcome message to the user"""
        await self.add_AI_response_message_to_conversation_async(TextRegistry.start_welcome_text, state, persist=False)
        self.logger.info(f"[{state.get('call_sid', '')}] Sent 'begin of welcome message' to {state.get('caller_phone', 'N/A')}")
        return state

    async def init_conversation_node(self, state: PhoneConversationState) -> PhoneConversationState:
        """Initializes the conversation in the backend API."""
        if state.get("agent_scratchpad", {}).get("conversation_id", None) is not None:
            return state

        self.logger.info(f"Start init. RAG API for caller (User and a new conversation): {state.get('caller_phone')}")

        try:
            await self.rag_query_service.test_client_connection_async()
        except Exception:
            self.logger.exception("/!\\ Error testing connection to RAG API.")
            await self.add_AI_response_message_to_conversation_async(TextRegistry.technical_error_text, state, persist=False)
            return state

        conversation_id = await self._init_user_and_new_conversation_in_backend_api_async(state.get("caller_phone"), state.get("call_sid"))
        if not conversation_id:
            self.logger.error(f"Error initializing conversation for phone: {state.get('caller_phone')}, call_sid: {state.get('call_sid')}. Conversation id is not defined.")
            await self.add_AI_response_message_to_conversation_async(TextRegistry.technical_error_text, state, persist=False)

        # Late persistence of welcome message (because it cannot have been persisted before, as conversation has not been created then)
        if conversation_id:
            self.logger.info(f"Init. conversation persistence for phone: {state.get('caller_phone')}, call_sid: {state.get('call_sid')}")
            await self.conversation_persistence.add_message_to_conversation_async(conversation_id, TextRegistry.start_welcome_text, "assistant")

        if state.get("agent_scratchpad") is None:
            state["agent_scratchpad"] = {}
        state["agent_scratchpad"]["conversation_id"] = conversation_id

        self.logger.info(f"Created conversation of id: {conversation_id}, sent welcome message.")
        return state

    async def _init_user_and_new_conversation_in_backend_api_async(self, calling_phone_number: str, call_sid: str) -> str | None:
        """Initialize the user session in the backend API: create user and conversation"""
        user_name_val = "Twilio incoming call " + (calling_phone_number or "Unknown User")
        ip_val = calling_phone_number or "Unknown IP"
        user_RM = UserRequestModel(
            user_id=None,
            user_name=user_name_val,
            IP=ip_val,
            device_info=DeviceInfoRequestModel(
                user_agent="twilio",
                platform="phone",
                app_version="",
                os="",
                browser="",
                is_mobile=True,
            ),
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
            self.logger.error(f"Error creating conversation: {e!s}")
            return None

    def _mapping_complete_contact_info_to_sf_account_info(self, complete_info: dict) -> dict:
        """
        Adapter method to convert the complete contact info structure to the expected sf_account_info structure.

        This maintains backward compatibility with existing downstream consumers while using the enhanced
        contact information that includes the most relevant user (from opportunity or contact owner).

        Args:
            complete_info: Result from get_complete_contact_info_by_phone_async

        Returns:
            Dictionary in the expected sf_account_info format with enhanced Owner information
        """
        if not complete_info:
            return {}

        contact_data = complete_info.get("contact", {})
        assigned_user = complete_info.get("assigned_user")
        user_source = complete_info.get("user_source")

        # Start with the original contact data structure
        adapted_info = contact_data.copy()

        # Override the Owner information with the assigned user from opportunity (if available)
        if assigned_user:
            adapted_info["Owner"] = {"Id": assigned_user.get("Id", ""), "Name": assigned_user.get("Name", "")}
            self.logger.info(f"Using enhanced Owner info from {user_source}: {assigned_user.get('Name')}")
        else:
            # Fallback to original Owner structure if no assigned user found
            if "Owner" not in adapted_info or not adapted_info.get("Owner"):
                adapted_info["Owner"] = {"Id": "", "Name": ""}

        return adapted_info

    async def user_identification_node(self, state: PhoneConversationState) -> PhoneConversationState:
        self.logger.info("Initializing SF Agent")
        call_sid = state.get("call_sid", "N/A")
        phone_number = state.get("caller_phone", "N/A")

        if phone_number == "anonymous":
            state.get("agent_scratchpad", {})["next_agent_needed"] = "anonymous_user"
            self.logger.warning(f"No phone number found for call SID: {call_sid}")
            return state

        # Try (and retry) to retrieve SalesForce prospect account with its associated CF owner, by opportunity or direct link
        complete_contact_info = await self.salesforce_api_client.get_complete_contact_info_by_phone_async(phone_number)

        # Retry upon failure to retrieve SalesForce account
        if not complete_contact_info:
            self.logger.info(f"[{call_sid}] No SalesForce account found for phone number: {phone_number}. Retry once to retrieve.")
            complete_contact_info = await self.salesforce_api_client.get_complete_contact_info_by_phone_async(phone_number)
            if not complete_contact_info:
                self.logger.warning(f"[{call_sid}] No SalesForce account found after retry for phone number: {phone_number}. New user: needs creation.")
                state.get("agent_scratchpad", {})["next_agent_needed"] = "user_new"
                return state

        # Keep the leads info call for backward compatibility (though the new method includes this logic)
        leads_info = await self.salesforce_api_client.get_leads_by_details_async(phone_number)

        # Adapt the complete contact info to the expected sf_account_info structure
        sf_account_info = self._mapping_complete_contact_info_to_sf_account_info(complete_contact_info)

        state["agent_scratchpad"]["sf_account_info"] = sf_account_info
        state["agent_scratchpad"]["sf_leads_info"] = leads_info[0] if leads_info else {}
        state["agent_scratchpad"]["sf_complete_info"] = complete_contact_info  # Store complete info for potential future use

        self.logger.info(f"[{call_sid}] Stored enhanced sf_account_info with {complete_contact_info.get('user_source', 'unknown')} user: {sf_account_info.get('Owner', {}).get('Name', 'N/A')} in agent_scratchpad")

        if complete_contact_info:
            state.get("agent_scratchpad", {})["next_agent_needed"] = "user_identified"
            # Track user identified as recognized
            await self.analytics_service.track_user_identified_async(
                call_sid=call_sid,
                is_recognized=True,
                user_id=sf_account_info.get("Id", ""),
                owner_name=sf_account_info.get("Owner", {}).get("Name", "")
            )
        else:
            state.get("agent_scratchpad", {})["next_agent_needed"] = "user_new"
            # Track user identified as not recognized
            await self.analytics_service.track_user_identified_async(
                call_sid=call_sid,
                is_recognized=False
            )
        return state

    async def user_identification_decide_next_step(self, state: PhoneConversationState) -> str | None:
        """Decide next step based on user identification"""
        return state.get("agent_scratchpad", {}).get("next_agent_needed")

    async def user_identified_node(self, state: PhoneConversationState) -> PhoneConversationState:
        """For existing user: User identity confirmation"""
        first_name = state["agent_scratchpad"]["sf_account_info"].get("FirstName", "").strip()
        middle_welcome_text = f"{self.thanks_to_come_back} {first_name}."

        salesman_first_name = state["agent_scratchpad"]["sf_account_info"].get("Owner", {}).get("Name", "en formation").split(" ")[0].strip()
        middle_welcome_text += f" votre conseiller, {salesman_first_name}, est actuellement indisponible."

        await self.add_AI_response_message_to_conversation_async(middle_welcome_text, state)

        # Ends call if user has an existing appointment (and single action available)
        if len(self.available_actions) == 1 and "schedule_appointement" in self.available_actions:
            existing_appointments = await self.get_existing_user_appointments_async(state)
            if any(existing_appointments):
                call_sid = state.get("call_sid", "N/A")
                self.logger.info(f"[{call_sid}] Found existing appointments for user")
                # User has existing appointments - ask for modify/cancel preference
                existing_appointment_text = await self._get_existing_appointment_text_async(existing_appointments[0])
                await self.add_AI_response_message_to_conversation_async(existing_appointment_text, state)
                await self.add_AI_response_message_to_conversation_async(TextRegistry.end_call_suffix_text, state)
                return state

        end_welcome_text = ""
        if "schedule_appointement" in self.available_actions:
            end_welcome_text += f" {TextRegistry.appointment_text}"

        if "ask_rag" in self.available_actions:
            if len(self.available_actions) > 1:
                end_welcome_text += f" {TextRegistry.also_questions_text}"
            else:
                end_welcome_text += f" {TextRegistry.questions_text}"

        if len(self.available_actions) > 1:
            end_welcome_text += f" {TextRegistry.select_action_text}"
        elif self.available_actions[0] == "schedule_appointement":
            end_welcome_text += f" {TextRegistry.yes_no_consent_text}"
        elif self.available_actions[0] == "ask_rag":
            end_welcome_text += f" {TextRegistry.ask_question_text}"

        await self.add_AI_response_message_to_conversation_async(end_welcome_text, state)
        return state

    async def get_existing_user_appointments_async(self, state: PhoneConversationState) -> list[dict]:
        """Check for existing appointments in next 30 days before scheduling new one"""
        call_sid = state.get("call_sid", "N/A")
        sf_account_info: dict = state.get("agent_scratchpad", {}).get("sf_account_info", {})
        user_id = sf_account_info.get("Id", "")

        if user_id:
            start_date_utc = (CalendarAgent.now - timedelta(minutes=30)).astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
            end_date_utc = (CalendarAgent.now + timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%SZ")

            self.logger.info(f"[{call_sid}] Checking for existing appointments for user {user_id} from {start_date_utc} to {end_date_utc}")
            existing_appointments = await self.calendar_api_client.get_scheduled_appointments_async(start_date_utc, end_date_utc, user_id=user_id)
            return existing_appointments
        return []

    async def user_new_node(self, state: PhoneConversationState) -> PhoneConversationState:
        """For new user: Case not handled. Ask the user to call during the opening hours"""
        await self.add_AI_response_message_to_conversation_async(TextRegistry.unavailability_for_new_prospect, state)
        await self.add_AI_response_message_to_conversation_async(TextRegistry.new_prospect_message, state)
        return state

    async def anonymous_user_node(self, state: PhoneConversationState) -> PhoneConversationState:
        """For new user: Case not handled. Ask the user to call during the opening hours"""
        await self.add_AI_response_message_to_conversation_async(TextRegistry.unavailability_for_new_prospect, state)
        await self.add_AI_response_message_to_conversation_async(TextRegistry.anonymous_prospect_message, state)
        return state

    async def wait_for_user_input_node(self, state: PhoneConversationState) -> PhoneConversationState:
        """Wait for user input"""
        return state

    async def calendar_agent_node(self, state: PhoneConversationState) -> PhoneConversationState:
        """Handles calendar operations using CalendarAgent."""
        call_sid = state.get("call_sid", "N/A")
        user_input = state.get("user_input", "")
        self.logger.info(f"[{call_sid}] Entering Calendar Agent node")

        # Get SF account info from scratchpad
        sf_account_info: dict = state.get("agent_scratchpad", {}).get("sf_account_info", {})

        if sf_account_info:
            try:
                # Initialize Calendar Agent with user info from SF
                self.calendar_agent_instance._set_user_info(
                    user_id=sf_account_info.get("Id", ""),
                    first_name=sf_account_info.get("FirstName", ""),
                    last_name=sf_account_info.get("LastName", ""),
                    email=sf_account_info.get("Email", ""),
                    owner_id=sf_account_info.get("Owner", {}).get("Id", ""),
                    owner_name=sf_account_info.get("Owner", {}).get("Name", ""),
                )
                chat_history = state.get("history", [])

                # Limit the history to the last 10 messages to avoid context overflow
                max_history_length = 10
                if len(chat_history) > max_history_length:
                    self.logger.info(f"[{call_sid[-1 * max_history_length :]}] Chat history has {len(chat_history)} messages. Truncating to the last {max_history_length}.")
                    chat_history = chat_history[-max_history_length:]

                if self.has_waiting_music_on_calendar:
                    waiting_music_task = await self._start_waiting_music_async()

                calendar_agent_answer = await self.calendar_agent_instance.process_to_schedule_new_appointement_async(user_input, chat_history)

                # Send confirmation SMS if new appointment has just been created
                has_appointment_been_created = calendar_agent_answer.startswith(TextRegistry.appointment_confirmed_prefix_text)
                if has_appointment_been_created:
                    appointement_date_str = calendar_agent_answer.split(TextRegistry.appointment_confirmed_prefix_text)[1].split(".")[0].strip()

                    # Track appointment scheduled event
                    user_id = sf_account_info.get("Id", "")
                    await self.analytics_service.track_appointment_scheduled_async(
                        call_sid=call_sid,
                        user_id=user_id,
                        appointment_date=appointement_date_str,
                        calendar_provider=EnvHelper.get_calendar_provider()
                    )

                    if EnvHelper.get_sms_appointment_confirmation_enabled():
                        await self.send_sms_for_appointment_confirmation_async(appointement_date_str, state)
                
                if self.calendar_speech_cannot_be_interupted:
                    self.outgoing_manager.can_speech_be_interupted = False

                await self.add_AI_response_message_to_conversation_async(calendar_agent_answer, state)

                # Calendar agent successful response - reset error counter
                self.consecutive_error_manager.reset_consecutive_error_count(state)

                if self.has_waiting_music_on_calendar:
                    await self._stop_waiting_music_async(waiting_music_task)
            except Exception as e:
                self.logger.error(f"[{call_sid[-4:]}] Error in Calendar Agent node: {e}", exc_info=True)
                self.consecutive_error_manager.increment_consecutive_error_count(state)
        return state
    
    async def send_sms_for_appointment_confirmation_async(self, appointement_date_str: str, state: PhoneConversationState):
        """Send an SMS to the owner to confirm the appointment."""
        outgoing_call_service = OutgoingCallService()
        user_firstname = state.get("agent_scratchpad", {}).get("sf_account_info", {}).get("FirstName", "")
        sales_firstname = state.get("agent_scratchpad", {}).get("sf_account_info", {}).get("Owner", {}).get("Name", "")
        user_phone_number = state.get("agent_scratchpad", {}).get("sf_account_info", {}).get("MobilePhone", None)\
                         or state.get("agent_scratchpad", {}).get("sf_account_info", {}).get("Phone", None)

        if not user_phone_number:
            call_sid = state.get("call_sid", "N/A")
            self.logger.error(f"[{call_sid[-4:]}] No phone number found for user {user_firstname} to send appointment confirmation SMS.")
            return
        sms_message = f"Bonjour {user_firstname}, \nVotre rendez-vous avec {sales_firstname},  votre conseiller en formation chez {EnvHelper.get_company_name()}, est confirmé pour le {appointement_date_str}.\n Merci de votre confiance et à très vite !\nL'équipe {EnvHelper.get_company_name()}."
        message_sid = await outgoing_call_service.send_sms_async(to_phone_number=user_phone_number, message=sms_message)

        # Track SMS sent event
        if message_sid:
            call_sid = state.get("call_sid", "N/A")
            await self.analytics_service.track_appointment_sms_sent_async(
                call_sid=call_sid,
                message_sid=message_sid,
                phone_number=user_phone_number
            )

        return message_sid
    
    async def router_decide_next_step(self, state: PhoneConversationState) -> str:
        """Determines the next node to visit based on the current state."""
        call_sid = state.get("call_sid", "N/A")
        self.logger.info(f"[~{call_sid[-4:]}] Deciding next step")

        # Check if next agent is explicitly specified
        next_agent = state.get("agent_scratchpad", {}).get("next_agent_needed")
        if next_agent:
            self.logger.info(f"[~{call_sid[-4:]}] Explicit routing to: {next_agent}")
            return next_agent

        # Check Lead Agent status
        lead_status = state.get("agent_scratchpad", {}).get("lead_last_status")
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
        if state.get("agent_scratchpad", {}).get("appointment_created"):
            self.logger.info(f"[~{call_sid[-4:]}] Appointment created, ending conversation.")
            return END

        # Default behavior
        self.logger.info(f"[~{call_sid[-4:]}] No specific routing condition met, ending graph run.")
        return END

    async def query_rag_api_about_trainings_agent_node(self, state: PhoneConversationState) -> PhoneConversationState | str:
        """Handle the course agent node."""
        call_sid = state.get("call_sid", "N/A")
        user_query = state.get("user_input", "")
        self.logger.info(f"> Ongoing RAG query on training course information. User request: '{user_query}' for: [{call_sid[-4:]}].")

        conversation_id = state.get("agent_scratchpad", {}).get("conversation_id", None)
        if not conversation_id:
            self.logger.error(f"[~{call_sid[-4:]}] No conversation ID found, ending graph run.")
            return END

        try:
            self.rag_interrupt_flag = {"interrupted": False}  # Reset the interrupt flag before starting new streaming

            rag_query_RM = QueryAskingRequestModel(
                conversation_id=UUID(conversation_id),
                user_query_content=user_query,
                display_waiting_message=False,
            )

            if self.has_waiting_music_on_rag:
                waiting_music_task: Task | None = await self._start_waiting_music_async()

            # Call but not await the RAG API to get the streaming response
            response = self.rag_query_service.rag_query_stream_async(
                query_asking_request_model=rag_query_RM,
                interrupt_flag=self.rag_interrupt_flag,
                timeout=120,
            )

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
                is_local_persistence = self.conversation_persistence_type == "local"
                # Add answer, but: Don't speak out the full answer (as its streaming has been), and persist only onto local persistence (RAG API has already handled full answer persistance)
                await self.add_AI_response_message_to_conversation_async(full_answer, state, speak_out_text=False, persist=is_local_persistence)
                # RAG agent successful response - reset error counter
                self.consecutive_error_manager.reset_consecutive_error_count(state)

                # Track RAG query
                await self.analytics_service.track_rag_query_async(
                    call_sid=call_sid,
                    query_length=len(user_query),
                    response_length=len(full_answer)
                )

            return state

        except Exception as e:
            self.logger.error(f"Error in RAG API communication: {e!s}")
            # RAG agent failure is an error - increment counter
            self.consecutive_error_manager.increment_consecutive_error_count(state)
            await self.add_AI_response_message_to_conversation_async(TextRegistry.rag_communication_error_text, state)
            return state

    async def other_inquery_node(self, state: PhoneConversationState) -> PhoneConversationState:
        """Handle other inquery"""
        call_sid = state.get("call_sid", "N/A")
        phone_number = state.get("caller_phone", "N/A")
        await self.add_AI_response_message_to_conversation_async(TextRegistry.ask_to_repeat_text, state)
        self.logger.info(f"[{call_sid}] Sent 'other' message to {phone_number}")
        return state

    async def no_appointment_requested_node(self, state: PhoneConversationState) -> PhoneConversationState:
        """Handle case where user refuses appointment"""
        call_sid = state.get("call_sid", "N/A")
        phone_number = state.get("caller_phone", "N/A")
        await self.add_AI_response_message_to_conversation_async(TextRegistry.no_appointment_requested_text, state)
        self.logger.info(f"[{call_sid}] User refused appointment, sent closure message to {phone_number}")
        return state

    async def max_consecutive_errors_reached_node(self, state: PhoneConversationState) -> PhoneConversationState:
        """Handle case where maximum consecutive errors have been reached"""
        call_sid = state.get("call_sid", "N/A")
        phone_number = state.get("caller_phone", "N/A")
        error_count = self.consecutive_error_manager.get_consecutive_error_count(state)
        max_errors = self.consecutive_error_manager.get_max_consecutive_errors_threshold()

        # Track consecutive errors event
        await self.analytics_service.track_consecutive_errors_async(
            call_sid=call_sid,
            error_count=error_count,
            error_type="max_threshold_reached"
        )

        await self.add_AI_response_message_to_conversation_async(TextRegistry.max_consecutive_errors_text, state)
        self.logger.warning(f"[{call_sid}] Max consecutive errors reached ({error_count}/{max_errors}). Sent technical difficulties message to {phone_number}")
        self.consecutive_error_manager.reset_consecutive_error_count(state)
        return state

    async def _get_existing_appointment_text_async(self, existing_appointment: dict) -> str:
        try:
            appointment_date = existing_appointment.get("StartDateTime", "")
            if not appointment_date:
                return ""
            from datetime import datetime

            dt = datetime.fromisoformat(appointment_date.replace("Z", ""))
            french_days = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
            french_months = ["", "janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre", "novembre", "décembre"]

            day_name = french_days[dt.weekday()]
            month_name = french_months[dt.month]
            appointment_date_formatted = f"{day_name} {dt.day} {month_name} à {dt.hour} heure{'s' if dt.hour != 1 else ''}"
            if dt.minute > 0:
                appointment_date_formatted += f" {dt.minute}"
        except Exception:
            pass

        return TextRegistry.existing_appointment_found_text + appointment_date_formatted + "."

    ### Helper methods ###

    async def add_AI_response_message_to_conversation_async(
        self,
        text: str,
        state: PhoneConversationState,
        speak_out_text: bool = True,
        persist: bool = True,
    ) -> PhoneConversationState:
        """Send the answer's text, add it to the state history and to the API for persistence"""
        state["history"].append(("assistant", text))

        if speak_out_text:
            await self.outgoing_manager.enqueue_text_async(text)

        if persist:
            conv_id = state["agent_scratchpad"].get("conversation_id", None)
            if not conv_id:
                self.logger.error("No conversation_id value setted in graph 'state' prior adding a new message to conversation.")
            else:
                await self.conversation_persistence.add_message_to_conversation_async(conv_id, text, "assistant")

        return state

    def _load_file_bytes(self, file_path: str) -> bytes:
        with open(file_path, "rb") as f:
            return f.read()

    async def _start_waiting_music_async(self) -> Task | None:
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
                    # Play the music chunk with progressive volume if enabled
                    success = await self.outgoing_manager.audio_sender.send_audio_chunk_async(
                        music_bytes,
                        progressive_volume_increase_duration=EnvHelper.get_waiting_music_increasing_volume_duration(),
                        sending_start_delay=EnvHelper.get_waiting_music_start_delay(),
                    )

                    # If sending failed or was interrupted, break the loop
                    if not success or self.outgoing_manager.audio_sender.streaming_interruption_asked:
                        break

                    # Small delay before restarting to avoid tight loop
                    await asyncio.sleep(0.1)

                except asyncio.CancelledError:
                    break  # Task was cancelled, exit cleanly

        except Exception as e:
            self.logger.error(f"Error in waiting music loop: {e}")
            # Don't re-raise non-cancellation exceptions to avoid disrupting the call

    async def _stop_waiting_music_async(self, waiting_music_task: Task | None):
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
