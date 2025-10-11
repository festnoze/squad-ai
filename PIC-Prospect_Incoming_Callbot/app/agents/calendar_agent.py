import datetime
import logging
from datetime import datetime, timedelta
from uuid import UUID

import pytz

#
from api_client.calendar_client_interface import CalendarClientInterface
from api_client.conversation_persistence_interface import ConversationPersistenceInterface
from langchain.agents import AgentExecutor, create_tool_calling_agent
from langchain.tools import tool
from langchain_core.language_models import BaseLanguageModel
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from utils.business_hours_config import BusinessHoursConfig, ValidationResult
from utils.envvar import EnvHelper

from agents.text_registry import TextRegistry


class CalendarAgent:
    salesforce_api_client: CalendarClientInterface
    owner_id: str | None = None
    owner_name: str | None = None
    now: datetime = datetime.now(tz=pytz.timezone("Europe/Paris"))
    business_hours_config: BusinessHoursConfig
    logger = logging.getLogger(__name__)

    def __init__(
        self,
        salesforce_api_client: CalendarClientInterface,
        classifier_llm: BaseLanguageModel,
        available_timeframes_llm: BaseLanguageModel | None = None,
        date_extractor_llm: BaseLanguageModel | None = None,
        conversation_persistence: ConversationPersistenceInterface | None = None,
    ):
        self.logger = CalendarAgent.logger
        self.classifier_llm = classifier_llm
        self.available_timeframes_llm = available_timeframes_llm if available_timeframes_llm else classifier_llm
        self.date_extractor_llm = date_extractor_llm if date_extractor_llm else self.available_timeframes_llm
        self.conversation_persistence = conversation_persistence
        CalendarAgent.salesforce_api_client = salesforce_api_client
        CalendarAgent.now = datetime.now(tz=pytz.timezone("Europe/Paris"))

        # Initialize business hours configuration (both instance and class level)
        self.business_hours_config = BusinessHoursConfig()
        CalendarAgent.business_hours_config = self.business_hours_config

        # Init. calendar agent to retrieve available timeframes
        available_timeframes_prompt = self._load_available_timeframes_prompt()
        available_timeframes_prompts = ChatPromptTemplate.from_messages(
            [
                ("system", available_timeframes_prompt),
                MessagesPlaceholder(variable_name="agent_scratchpad"),
            ]
        )
        tools_available_timeframes = [CalendarAgent.get_available_timeframes_async]
        agent = create_tool_calling_agent(self.available_timeframes_llm, tools_available_timeframes, available_timeframes_prompts)
        self.available_timeframes_agent = AgentExecutor(agent=agent, tools=tools_available_timeframes, verbose=True)

    async def process_to_schedule_new_appointement_async(self, user_input: str, chat_history: list[dict] | None = None) -> str:
        """High-level dispatcher orchestrating calendar actions according to the category.

        Args:
            user_input: The user's message to process
            chat_history: Optional list of previous messages in the conversation

        Returns:
            A response string based on the user's input and category
        """
        if chat_history is None:
            chat_history = []
        category = await self.categorize_request_for_dispatch_async(user_input, chat_history)
        self.logger.info(f"Category detected: {category}")

        # Check if user is requesting a valid date
        requested_date: datetime | None = await self._extract_appointment_selected_date_and_time_async(user_input, chat_history)
        if requested_date:
            validation_result = self.validate_appointment_time_async(requested_date)
            if validation_result != "valid":
                return self._get_text_time_validation_error(validation_result)
    
        # === Category-specific handling === #
        if category == "Proposition de créneaux":
            formatted_history = []
            for message in chat_history:
                formatted_history.append(f"{message[0]}: {message[1]}")

            available_timeframes_answer = await self.available_timeframes_agent.ainvoke(
                {
                    "current_date_str": self._to_french_date(CalendarAgent.now, include_weekday=True, include_year=True, include_hour=True),
                    "owner_name": CalendarAgent.owner_name,
                    "user_input": user_input,
                    "chat_history": "- " + "\n- ".join(formatted_history),
                    "business_hours_display": self.business_hours_config.get_business_hours_display(),
                }
            )

            return available_timeframes_answer["output"]

        if category == "Demande des disponibilités":
            return TextRegistry.availability_request_text

        if category == "Proposition de rendez-vous":
            start_date = CalendarAgent.now.date()
            end_date = start_date + timedelta(days=2)
            appointments = await CalendarAgent.get_appointments_async.ainvoke({"start_date": str(start_date), "end_date": str(end_date)})
            available_timeframes = CalendarAgent.get_available_timeframes_from_scheduled_slots(str(start_date), str(end_date), appointments, business_hours_config=self.business_hours_config)

            if not available_timeframes:
                return TextRegistry.no_timeframes_text
            return TextRegistry.slot_unavailable_text

        if category == "Demande de confirmation du rendez-vous":
            if requested_date:
                existing_event_id = await self.salesforce_api_client.verify_appointment_existance_async(event_id=None, start_datetime=requested_date.isoformat(), duration_minutes=30, owner_id=CalendarAgent.owner_id)
                if existing_event_id:
                    available_timeframes_answer = await self.available_timeframes_agent.ainvoke(
                        {
                            "current_date_str": self._to_french_date(CalendarAgent.now, include_weekday=True, include_year=True, include_hour=True),
                            "owner_name": CalendarAgent.owner_name,
                            "user_input": "Quels sont les prochains crénaux disponibles ?",
                            "chat_history": "",
                            "business_hours_display": self.business_hours_config.get_business_hours_display(),
                        }
                    )
                    available_slots_text = available_timeframes_answer["output"]
                    return TextRegistry.appointment_unavailable_slot_text + available_slots_text

                french_date = self._to_french_date(requested_date, include_weekday=True, include_year=False, include_hour=True)
                return TextRegistry.confirmation_prefix_text + french_date + ". " + TextRegistry.confirmation_suffix_text
            else:
                return TextRegistry.date_not_found_text

        if category == "Rendez-vous confirmé":
            if requested_date:
                validation_result = self.validate_appointment_time_async(requested_date)
                if validation_result != "valid":
                    return self._get_text_time_validation_error(validation_result)

                confirmed_date_str = self._to_str_iso(requested_date)
                success = await CalendarAgent.schedule_new_appointment_async(confirmed_date_str)
                if success:
                    return TextRegistry.appointment_confirmed_prefix_text + self._to_french_date(requested_date, include_weekday=True, include_year=False, include_hour=True) + ". " + TextRegistry.end_call_suffix_text
            return TextRegistry.appointment_failed_text

        if category == "Demande de modification":
            return TextRegistry.modification_not_supported_text

        if category == "Demande d'annulation":
            return TextRegistry.cancellation_not_supported_text

        return TextRegistry.ask_to_repeat_text

    def _get_text_time_validation_error(self, validation_result: str) -> str:
        if validation_result.startswith("outside_hours:"):
            business_hours = validation_result.split(":", 1)[1]
            return TextRegistry.appointment_outside_hours_text.format(business_hours=business_hours)
        elif validation_result == "weekend":
            return TextRegistry.appointment_weekend_text
        elif validation_result == "in_past":
            return TextRegistry.appointment_in_past_text
        elif validation_result == "holiday":
            return TextRegistry.appointment_holiday_text
        elif validation_result.startswith("too_far_future:"):
            return TextRegistry.appointment_too_far_text
        return ""

    @tool
    def get_owner_name() -> str:
        """Get the owner name for the current calendar agent."""
        return CalendarAgent.get_owner_name_tool()

    @staticmethod
    def get_owner_name_tool() -> str:
        return CalendarAgent.owner_name

    @tool
    def get_current_date() -> str:
        """Get the current date formatted in French style."""
        return CalendarAgent.get_current_date_tool()

    @staticmethod
    def get_current_date_tool() -> str:
        return CalendarAgent._to_french_date(CalendarAgent.now, include_weekday=True, include_year=True, include_hour=True)

    @staticmethod
    async def get_appointments_async(start_date: str, end_date: str) -> list[dict[str, any]]:
        """Get the existing appointments between the start and end dates for the owner.

        Args:
            start_date: Start date for appointment search
            end_date: End date for appointment search

        Returns:
            List of appointments for the owner between the specified dates
        """
        # Get the existing appointments from Salesforce API
        # TODO: manage "CalendarAgent.owner_id" another way to allow multi-calls handling.
        scheduled_slots = await CalendarAgent.salesforce_api_client.get_scheduled_appointments_async(start_date, end_date, CalendarAgent.owner_id)

        # Log the result
        logger = logging.getLogger(__name__)
        logger.info(f"Called 'get_appointments' tool for owner {CalendarAgent.owner_id} between {start_date} and {end_date}.")
        if scheduled_slots:
            slot_details = []
            for slot in scheduled_slots:
                slot_detail = f"- De {slot.get('StartDateTime')} à {slot.get('EndDateTime')} - Sujet: {slot.get('Subject', '-')} - Description: {slot.get('Description', '-')} - Location: {slot.get('Location', '-')} - OwnerId: {slot.get('OwnerId', '-')} - WhatId: {slot.get('WhatId', '-')} - WhoId: {slot.get('WhoId', '-')}"
                slot_details.append(slot_detail)
            logger.info(f"Here is the list of the owner calendar taken slots: \n{chr(10).join(slot_details)}")
        else:
            logger.info("No appointments found for the owner between the specified dates.")
        return scheduled_slots

    @tool
    async def get_available_timeframes_async(start_date: str, end_date: str) -> list[str]:
        """Get available appointment timeframes between start_date and end_date.

        Args:
            start_date: Start date for availability search in format "YYYY-MM-DD"
            end_date: End date for availability search in format "YYYY-MM-DD"

        Returns:
            List of available time ranges in format "YYYY-MM-DD HH:MM-HH:MM"
        """
        if len(start_date) == 10:
            start_date += " 00:00:00"
        if " " in start_date:
            start_date = start_date.replace(" ", "T")
        if not start_date.endswith("Z"):
            start_date += "Z"

        if len(end_date) == 10:
            end_date += " 23:59:59"
        if " " in end_date:
            end_date = end_date.replace(" ", "T")
        if not end_date.endswith("Z"):
            end_date += "Z"

        scheduled_slots = await CalendarAgent.salesforce_api_client.get_scheduled_appointments_async(start_date, end_date, CalendarAgent.owner_id)
        return CalendarAgent.get_available_timeframes_from_scheduled_slots(start_date, end_date, scheduled_slots, business_hours_config=CalendarAgent.business_hours_config)

    @staticmethod
    async def schedule_new_appointment_async(date_and_time: str, duration: int = 30, user_subject: str | None = None, description: str | None = None) -> str | None:
        subject = "RDV Callbot - " + CalendarAgent.first_name + " " + CalendarAgent.last_name
        if user_subject:
            subject += ": " + user_subject
        description = description if description else "Rendez-vous pris directement par l'IA lors d'un appel entrant du lead en dehors des heures ouvrées."
        if not date_and_time.endswith("Z"):
            date_and_time += "Z"

        # TODO: manage "CalendarAgent.*" variables another way for multi-calls handling.
        try:
            return await CalendarAgent.salesforce_api_client.schedule_new_appointment_async(subject, date_and_time, duration, description, owner_id=CalendarAgent.owner_id, who_id=CalendarAgent.user_id)
        except Exception as e:
            CalendarAgent.logger.error(f"Error scheduling appointment: {e!s}")
            return None

    def _set_user_info(self, user_id, first_name, last_name, email, owner_id, owner_name):
        """
        Initialize the Calendar Agent with user information and configuration.

        Args:
            user_id: Customer's ID
            last_name: Customer's last name
            email: Customer's email
            owner_id: Owner's (advisor) ID
            owner_name: Owner's (advisor) name
        """
        self.logger.info(f"Setting user info for CalendarAgent to: {first_name} {last_name} {email}, for owner: {owner_name}")
        CalendarAgent.first_name = first_name
        CalendarAgent.last_name = last_name
        CalendarAgent.email = email
        CalendarAgent.user_id = user_id
        CalendarAgent.owner_id = owner_id
        CalendarAgent.owner_name = owner_name

    async def categorize_request_for_dispatch_async(self, user_input: str, chat_history: list[dict[str, str]] | None = None) -> str:
        """Classify the user's request into one of the rendez-vous workflow categories.

        The categorisation relies primarily on the underlying LLM but falls back to
        deterministic heuristics when the LLM is unavailable (e.g. during unit tests).

        Args:
            user_input: The user's message to classify
            chat_history: Optional list of previous messages in the conversation

        Returns:
            A category string representing the intent of the user's message
        """
        if chat_history is None:
            chat_history = []

        formatted_history = []
        for message in chat_history:
            if isinstance(message, dict):
                formatted_history.append(f"{message['role']}: {message['content']}")
            elif isinstance(message, tuple):
                formatted_history.append(f"{message[0]}: {message[1]}")
            else:
                raise ValueError(f"Unsupported message type: {type(message)}")

        # Current contextual data to inject directly (no dedicated tools anymore)
        current_date_str = self._to_french_date(
            CalendarAgent.now,
            include_weekday=True,
            include_year=True,
            include_hour=True,
        )
        owner_name = CalendarAgent.owner_name or "le conseiller"

        classifier_prompt = (
            self._load_classifier_prompt()
            .replace("{current_date_str}", current_date_str)
            .replace("{owner_name}", owner_name)
            .replace("{user_input}", user_input)
            .replace("{chat_history}", "- " + "\n- ".join(formatted_history))
        )

        try:
            resp = await self.classifier_llm.ainvoke(classifier_prompt)
            llm_category = resp.content.strip() if hasattr(resp, "content") else str(resp).strip()

            # Log LLM operation cost for classification (if enabled)
            if EnvHelper.get_track_llm_operations_cost():
                response_content = resp.content if hasattr(resp, "content") else str(resp)
                await self._log_calendar_classification_llm_operation_async(classifier_prompt, response_content)

            return llm_category
        except Exception as e:
            self.logger.warning(f"CalendarAgent categorisation failed: {e}")
            return "Proposition de créneaux"

    def _to_french_date(self, dt: datetime, include_weekday: bool = True, include_year: bool = False, include_hour: bool = False) -> str:
        french_days = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
        french_months = ["", "janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre", "novembre", "décembre"]
        french_date = ""
        if include_weekday:
            french_date += f"{french_days[dt.weekday()]} "
        french_date += f"{dt.day} {french_months[dt.month]}"
        if include_year:
            french_date += f" {dt.year}"
        if include_hour:
            french_date += f" à {self._to_french_time(dt)}"
        return french_date

    def _to_french_time(self, dt: datetime) -> str:
        minute_str = "" if dt.minute == 0 else f" {dt.minute}"
        return f"{dt.hour} heure{'s' if int(dt.hour) != 1 else ''}{minute_str}".strip()

    @staticmethod
    def get_available_timeframes_from_scheduled_slots(
        start_date: str,
        end_date: str,
        scheduled_slots: list[dict],
        slot_duration_minutes: int = 30,
        max_weekday: int = 5,
        availability_timeframe: list[tuple[str, str]] | None = None,
        business_hours_config=None,
    ) -> list[str]:
        """
        Return available appointment timeframes between start_date and end_date as consolidated ranges.
        The end time of each timeframe is automatically adjusted to exclude the last slot, ensuring
        users can only book appointments that fit completely within the available hours.

        Args:
            start_date: Start date for availability search
            end_date: End date for availability search
            scheduled_slots: List of occupied slots from Salesforce
            slot_duration_minutes: Duration of each slot in minutes
            max_weekday: Maximum weekday (0=Monday, 6=Sunday), default is 5 (only weekdays)
            availability_timeframe: List of tuples with opening hours [("09:00", "12:00"), ("13:00", "16:00")]
                                   Default is morning 9-12 and afternoon 13-18.
                                   End times are adjusted by slot_duration_minutes to provide valid start hours only.
            business_hours_config: BusinessHoursConfig instance for centralized configuration
        """
        # Use business hours config if provided, otherwise fall back to parameters or defaults
        if business_hours_config is not None:
            # Always use business config appointment duration
            slot_duration_minutes = business_hours_config.appointment_duration

            # Override availability_timeframe if:
            # 1. No availability_timeframe was provided (None), OR
            # 2. Business config has non-default time_slots (explicitly configured)
            default_time_slots = [("09:00", "12:00"), ("13:00", "16:00")]
            if availability_timeframe is None or business_hours_config.time_slots != default_time_slots:
                availability_timeframe = business_hours_config.time_slots

            # Note: max_weekday is not used when business_hours_config is provided
            # We use business_hours_config.allowed_weekdays instead

        # Fall back to legacy defaults if still None
        if availability_timeframe is None:
            availability_timeframe = [("09:00", "12:00"), ("13:00", "16:00")]

        # Parse start and end dates
        start_date_only = datetime.fromisoformat(start_date.replace("Z", "")).date()
        end_date_only = datetime.fromisoformat(end_date.replace("Z", "")).date()

        # Prepare occupied slots for quick lookup
        scheduled_slots_dt = []
        for slot in scheduled_slots:
            scheduled_slots_dt.append((datetime.fromisoformat(slot["StartDateTime"].replace("Z", "")), datetime.fromisoformat(slot["EndDateTime"].replace("Z", ""))))

        delta = timedelta(minutes=slot_duration_minutes)
        available_ranges = []

        # Iterate through each day in the requested range
        while start_date_only <= end_date_only:
            # Check if this day should be included based on business hours config or max_weekday
            if business_hours_config is not None:
                # Use business hours config for weekday filtering
                if start_date_only.weekday() not in business_hours_config.allowed_weekdays:
                    start_date_only += timedelta(days=1)
                    continue
            else:
                # Legacy behavior: skip weekends if max_weekday is set to 5 (Friday)
                if start_date_only.weekday() >= max_weekday:
                    start_date_only += timedelta(days=1)
                    continue

            # For each availability timeframe
            for timeframe in availability_timeframe:
                start_hour_str, end_hour_str = timeframe
                start_hour_dt = datetime.strptime(start_hour_str, "%H:%M")
                end_hour_dt = datetime.strptime(end_hour_str, "%H:%M")

                # Combine date with time to create full datetime objects for the timeframe
                # Add timezone info (Europe/Paris) to make them compatible with occ_start and occ_end
                french_tz = pytz.timezone("Europe/Paris")
                timeframe_start = french_tz.localize(datetime.combine(start_date_only, start_hour_dt.time()))
                timeframe_end = french_tz.localize(datetime.combine(start_date_only, end_hour_dt.time()))

                # Always adjust the end time by subtracting slot_duration_minutes to exclude the last slot
                timeframe_end -= delta

                # Skip if the timeframe becomes invalid after adjustment
                if timeframe_start >= timeframe_end:
                    continue

                # Build a list of free intervals within the timeframe, excluding taken slots
                free_intervals = []
                interval_start = timeframe_start
                # Sort taken slots for the day and timeframe
                day_slots = [s for s in scheduled_slots_dt if s[0].date() == start_date_only]
                day_slots = sorted(day_slots, key=lambda x: x[0])
                for occ_start, occ_end in day_slots:
                    if occ_start.tzinfo is None:
                        occ_start = french_tz.localize(occ_start)
                    if occ_end.tzinfo is None:
                        occ_end = french_tz.localize(occ_end)

                    # If the taken slot is outside the current timeframe, skip
                    if occ_end <= timeframe_start or occ_start >= timeframe_end:
                        continue
                    # If there is free time before this taken slot, add it
                    if interval_start < occ_start:
                        free_start = max(interval_start, timeframe_start)
                        free_end = min(occ_start, timeframe_end)
                        if free_start < free_end:
                            formatted_range = f"{free_start.strftime('%Y-%m-%d %H:%M')}-{free_end.strftime('%H:%M')}"
                            free_intervals.append(formatted_range)
                    interval_start = max(interval_start, occ_end)
                # Add remaining free time after last taken slot
                if interval_start < timeframe_end:
                    formatted_range = f"{interval_start.strftime('%Y-%m-%d %H:%M')}-{timeframe_end.strftime('%H:%M')}"
                    free_intervals.append(formatted_range)
                available_ranges.extend(free_intervals)

            # Move to next day
            start_date_only += timedelta(days=1)

        # Remove duplicates while preserving order
        seen = set()
        unique_ranges = []
        for timeframe in available_ranges:
            if timeframe not in seen:
                seen.add(timeframe)
                unique_ranges.append(timeframe)

        return unique_ranges

    async def _extract_appointment_selected_date_and_time_async(self, user_input: str, chat_history: list[dict]) -> datetime | None:
        prompt = ChatPromptTemplate.from_template("""
        Extract the exact date and time specified by the user for the appointment from the following conversation.
        Only return the date and time in the following format: YYYY-MM-DDTHH:MM:SSZ.
        The now date and time is: {now}
        Note that the appointment date and time can only be in the future, and in the near future (less than 2 months from now).

        Current conversation:
        {chat_history}

        Latest user input: {input}

        Extract only the date and time in ISO format, nothing else.
        If no clear date/time is mentioned, return 'not-found'.
        """)

        chain = prompt | self.date_extractor_llm | StrOutputParser()
        chat_history_str = "- " + "\n- ".join((msg[0] + ": " + msg[1]) for msg in chat_history)
        response = await chain.ainvoke(
            {
                "input": user_input,
                "chat_history": chat_history_str,
                "now": self._to_french_date(CalendarAgent.now, include_weekday=True, include_year=True, include_hour=True),
            }
        )

        try:
            response = response.strip()
            if response == "not-found":
                return None
            else:
                return datetime.strptime(response, "%Y-%m-%dT%H:%M:%SZ")
        except ValueError:
            return None

    def _to_str_iso(self, dt: datetime | None) -> str:
        if not dt:
            return "not-found"
        return dt.strftime("%Y-%m-%dT%H:%M:%SZ")

    calendar_agent_prompt: str = ""

    def _load_calendar_agent_prompt(self):
        if not CalendarAgent.calendar_agent_prompt:
            with open("app/agents/prompts/calendar_agent_prompt.txt", encoding="utf-8") as f:
                CalendarAgent.calendar_agent_prompt = f.read()
        return CalendarAgent.calendar_agent_prompt

    classifier_prompt: str = ""

    def _load_classifier_prompt(self):
        if not CalendarAgent.classifier_prompt:
            with open("app/agents/prompts/calendar_agent_classifier_prompt.txt", encoding="utf-8") as f:
                CalendarAgent.classifier_prompt = f.read()
        return CalendarAgent.classifier_prompt

    available_timeframes_prompt: str = ""

    def _load_available_timeframes_prompt(self):
        if not CalendarAgent.available_timeframes_prompt:
            with open("app/agents/prompts/calendar_agent_available_timeframes_prompt.txt", encoding="utf-8") as f:
                CalendarAgent.available_timeframes_prompt = f.read()
        return CalendarAgent.available_timeframes_prompt

    def validate_appointment_time_async(self, requested_datetime: datetime) -> str:
        """
        Validate if the requested appointment time is within business hours and return appropriate response.

        Args:
            requested_datetime: The datetime for the requested appointment

        Returns:
            String indicating validation result or error message
        """
        if not self.business_hours_config:
            # Fall back to basic validation if no config
            return "valid"

        validation_result = self.business_hours_config.validate_appointment_time(requested_datetime, CalendarAgent.now)

        if validation_result == ValidationResult.VALID:
            return "valid"
        elif validation_result == ValidationResult.OUTSIDE_HOURS:
            business_hours_display = self.business_hours_config.get_business_hours_display()
            return f"outside_hours:{business_hours_display}"
        elif validation_result == ValidationResult.WEEKEND:
            return "weekend"
        elif validation_result == ValidationResult.TOO_FAR_FUTURE:
            max_days = self.business_hours_config.max_days_ahead
            return f"too_far_future:{max_days}"
        elif validation_result == ValidationResult.IN_PAST:
            return "in_past"
        elif validation_result == ValidationResult.HOLIDAY:
            return "holiday"
        else:
            return "invalid"

    async def _log_calendar_classification_llm_operation_async(
        self,
        prompt: str,
        response_content: str,
    ) -> None:
        """
        Log LLM operation cost for calendar classification to the database.

        Args:
            prompt: The input prompt sent to the LLM
            response_content: The response content from the LLM
        """
        try:
            # Estimate input tokens (rough approximation: ~4 characters per token)
            input_tokens = len(prompt) / 4
            # Estimate output tokens
            output_tokens = len(response_content) / 4
            total_tokens = input_tokens + output_tokens

            # GPT-4.1 pricing (hardcoded for now): $0.03 per 1K input tokens, $0.06 per 1K output tokens
            input_cost = (input_tokens / 1000) * 0.03
            output_cost = (output_tokens / 1000) * 0.06
            total_cost_usd = input_cost + output_cost

            # Price per token (blended rate for simplicity)
            price_per_token = total_cost_usd / total_tokens if total_tokens > 0 else 0

            if self.conversation_persistence:
                # Note: We don't have conversation_id or call_sid available in CalendarAgent context
                await self.conversation_persistence.add_llm_operation_async(
                    operation_type_name="classification",
                    provider="openai",
                    model="gpt-4.1",
                    tokens_or_duration=total_tokens,
                    price_per_unit=price_per_token,
                    cost_usd=total_cost_usd,
                    conversation_id=None,
                    message_id=None,
                    stream_id=None,
                    call_sid=None,
                    phone_number=None,
                )
        except Exception as e:
            self.logger.error(f"Failed to log calendar classification LLM operation: {e}")
