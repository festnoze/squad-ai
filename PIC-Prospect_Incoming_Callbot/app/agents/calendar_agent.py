import logging
import datetime
from datetime import datetime, timedelta, time
import pytz
from langchain.tools import tool, BaseTool
from langchain.agents import AgentExecutor, create_tool_calling_agent, create_react_agent
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.output_parsers import StrOutputParser
from langchain_core.messages import AIMessage, HumanMessage
#
from api_client.salesforce_api_client_interface import SalesforceApiClientInterface

class CalendarAgent:        
    salesforce_api_client: SalesforceApiClientInterface
    owner_id: str | None = None
    owner_name: str | None = None
    now: datetime | None = None
    
    # Static text responses for calendar operations
    availability_request_text = "Quels jours ou quelles heures de la journée vous conviendraient le mieux ?"
    no_timeframes_text = "Quand souhaitez-vous réserver un rendez-vous ?"
    slot_unavailable_text = "Ce créneau n'est pas disponible, souhaiteriez-vous un autre horaire ?"
    confirmation_prefix_text = "Récapitulons : votre rendez-vous sera planifié le "
    confirmation_suffix_text = "Merci de confirmer ce rendez-vous pour le valider."
    date_not_found_text = "Je n'ai pas trouvé la date et l'heure du rendez-vous. Veuillez me préciser la date et l'heure du rendez-vous souhaité."
    appointment_confirmed_prefix_text = "C'est confirmé ! Votre rendez-vous est maintenant planifié pour le "
    appointment_confirmed_suffix_text = "Merci et au revoir."
    appointment_failed_text = "Je n'ai pas pu planifier le rendez-vous. Souhaitez-vous essayer un autre créneau ?"
    modification_not_supported_text = "Je ne suis pas en mesure de gérer les modifications de rendez-vous."
    cancellation_not_supported_text = "Je ne suis pas en mesure de gérer les annulations de rendez-vous."
    
    def __init__(self, salesforce_api_client: SalesforceApiClientInterface, classifier_llm: any, available_timeframes_llm: any = None, date_extractor_llm: any = None):
        self.logger = logging.getLogger(__name__)
        self.classifier_llm = classifier_llm
        self.available_timeframes_llm = available_timeframes_llm if available_timeframes_llm else classifier_llm
        self.date_extractor_llm = date_extractor_llm if date_extractor_llm else self.available_timeframes_llm
        CalendarAgent.salesforce_api_client = salesforce_api_client
        CalendarAgent.now = datetime.now(tz=pytz.timezone('Europe/Paris'))

        # The global calendar scheduler agent with tools
        
        prompt = self._load_available_timeframes_prompt()
        prompts = ChatPromptTemplate.from_messages([
            ("system", prompt),
            MessagesPlaceholder(variable_name="agent_scratchpad"),
        ])
        tools_available_timeframes = [CalendarAgent.get_available_timeframes_async]
        agent = create_tool_calling_agent(self.available_timeframes_llm, tools_available_timeframes, prompts)
        self.available_timeframes_agent = AgentExecutor(agent=agent, tools=tools_available_timeframes, verbose=True)

        # self.tools = [self.get_appointments, self.schedule_new_appointment]
        # 
        # self.prompt = self._load_prompt()
        # self.prompts = ChatPromptTemplate.from_messages([
        #     ("system", self.prompt),
        #     MessagesPlaceholder(variable_name="chat_history"),
        #     ("human", "{input}"),
        #     MessagesPlaceholder(variable_name="agent_scratchpad"),
        # ])
        # self.agent = create_tool_calling_agent(self.date_extractor_llm, self.tools, self.prompts)
        # self.agent_executor = AgentExecutor(agent=self.agent, tools=self.tools, verbose=True)
        # response = self.agent_executor.invoke({"input": "quel jour sommes nous ?", "chat_history": []})['output']

    async def run_async(self, user_input: str, chat_history: list[dict] = None) -> str:
        """High-level dispatcher orchestrating calendar actions according to the category.
        
        Args:
            user_input: The user's message to process
            chat_history: Optional list of previous messages in the conversation
            
        Returns:
            A response string based on the user's input and category
        """
        if chat_history is None:
            chat_history = []

        category = await self.categorize_for_dispatch_async(user_input, chat_history)
        self.logger.info(f"Category detected: {category}")

        # === Category-specific handling ===
        if category == "Proposition de créneaux":            
            if chat_history is None: 
                chat_history = []
            formatted_history = []
            for message in chat_history:
                formatted_history.append(f"{message[0]}: {message[1]}")

            available_timeframes_answer = await self.available_timeframes_agent.ainvoke({
                "current_date_str": self._to_french_date(CalendarAgent.now, include_weekday=True, include_year=True, include_hour=True),
                "owner_name": CalendarAgent.owner_name,
                "user_input": user_input,
                "chat_history": "- " + "\n- ".join(formatted_history)
            })
            
            return available_timeframes_answer["output"]

        if category == "Demande des disponibilités":
            return self.availability_request_text

        if category == "Proposition de rendez-vous":
            start_date = CalendarAgent.now.date()
            end_date = start_date + timedelta(days=2)
            appointments = await CalendarAgent.get_appointments_async(str(start_date), str(end_date))
            available_timeframes = CalendarAgent.get_available_timeframes_from_scheduled_slots(str(start_date), str(end_date), appointments)

            if not available_timeframes:
                return self.no_timeframes_text
            return self.slot_unavailable_text

        if category == "Demande de confirmation du rendez-vous":
            # extract date and time from user_input + chat history
            date_and_time: datetime | None = await self._extract_appointment_selected_date_and_time_async(user_input, chat_history)
            
            if date_and_time:
                return self.confirmation_prefix_text + self._to_french_date(date_and_time, include_weekday=True, include_year=False, include_hour=True) + ". " + self.confirmation_suffix_text
            else:
                return self.date_not_found_text

        if category == "Rendez-vous confirmé":
            appointment_slot_datetime: datetime = await self._extract_appointment_selected_date_and_time_async(user_input, chat_history)
            appointment_slot_datetime_str = self._to_str_iso(appointment_slot_datetime)
            success = await CalendarAgent.schedule_new_appointment_tool_async(appointment_slot_datetime_str)
            if success is not None:
                return self.appointment_confirmed_prefix_text + self._to_french_date(appointment_slot_datetime, include_weekday=True, include_year=False, include_hour=True) + ". " + self.appointment_confirmed_suffix_text
            else:
                return self.appointment_failed_text

        if category == "Demande de modification":
            return self.modification_not_supported_text

        if category == "Demande d'annulation":
            return self.cancellation_not_supported_text

        # Fallback – delegate to original agent behaviour (no change to signature)
        formatted_history = []
        for message in chat_history:
            if "AI" in message:
                formatted_history.append(AIMessage(content=message["AI"]))
            elif "human" in message:
                formatted_history.append(HumanMessage(content=message["human"]))
        try:
            response = await self.agent_executor.ainvoke({
                "input": user_input,
                "chat_history": formatted_history
            })
            return response.get("output", "") if response else ""
        except Exception as e:
            self.logger.error(f"/!\\ Error executing calendar agent with tools: {e}")
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

    @tool
    async def get_appointments_async(start_date: str, end_date: str) -> list[dict[str, any]]:
        """Get the existing appointments between the start and end dates for the owner.
        
        Args:
            start_date: Start date for appointment search
            end_date: End date for appointment search
            
        Returns:
            List of appointments for the owner between the specified dates
        """
        # Get the existing appointments from Salesforce API
        #TODO: manage "CalendarAgent.owner_id" another way to allow multi-calls handling.
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
        if len(start_date) == 10: start_date += " 00:00:00"
        if ' ' in start_date: start_date = start_date.replace(' ', 'T')
        if not start_date.endswith("Z"): start_date += "Z"
        
        if len(end_date) == 10: end_date += " 00:00:00"
        if ' ' in end_date: end_date = end_date.replace(' ', 'T')
        if not end_date.endswith("Z"): end_date += "Z"

        scheduled_slots = await CalendarAgent.salesforce_api_client.get_scheduled_appointments_async(start_date, end_date, CalendarAgent.owner_id)
        return CalendarAgent.get_available_timeframes_from_scheduled_slots(start_date, end_date, scheduled_slots)

    @tool
    async def schedule_new_appointment(
            date_and_time: str,
            duration: int = 30,
            object: str | None = None,
            description: str | None = None
        ) -> dict[str, any]:
        """Schedule a new appointment with the owner at the specified date and time.
        
        Args:
            date_and_time: Date and time for the new appointment
            duration: Duration of the appointment in minutes
            object: Optional subject for the appointment
            description: Optional description for the appointment
            
        Returns:
            The scheduled appointment details
        """
        return await CalendarAgent.schedule_new_appointment_tool_async(date_and_time, duration, object, description)

    async def schedule_new_appointment_tool_async(
            date_and_time: str,
            duration: int = 30,
            object: str | None = None,
            description: str | None = None
        ) -> dict[str, any]:
        object = object if object else "Demande de conseil en formation prospect"
        description = description if description else "RV pris par l'IA après appel entrant du prospect"
        if not date_and_time.endswith("Z"):
            date_and_time += "Z"

        logger = logging.getLogger(__name__)
        logger.info(f"########### Called 'schedule_new_appointment' tool for {CalendarAgent.owner_id} at: {date_and_time}.")

        #TODO: manage "CalendarAgent.*" variables another way for multi-calls handling.
        return await CalendarAgent.salesforce_api_client.schedule_new_appointment_async(object, date_and_time, duration, description, owner_id= CalendarAgent.owner_id, who_id=CalendarAgent.user_id) 

    def _load_prompt(self):
        with open("app/agents/prompts/calendar_agent_prompt.txt", "r", encoding="utf-8") as f:
            return f.read()

    def _load_classifier_prompt(self):
        with open("app/agents/prompts/calendar_agent_classifier_prompt.txt", "r", encoding="utf-8") as f:
            return f.read()

    def _load_available_timeframes_prompt(self):
        with open("app/agents/prompts/calendar_agent_available_timeframes_prompt.txt", "r", encoding="utf-8") as f:
            return f.read()

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
        self.first_name = first_name
        self.last_name = last_name
        self.email = email
        
        CalendarAgent.user_id = user_id
        CalendarAgent.owner_id = owner_id
        CalendarAgent.owner_name = owner_name

    async def categorize_for_dispatch_async(self, user_input: str, chat_history: list[dict[str, str]] | None = None) -> str:
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
        current_date_str = self._to_french_date(CalendarAgent.now, include_weekday=True, include_year=True, include_hour=True)
        owner_name = CalendarAgent.owner_name or "le conseiller"

        classifier_prompt = self._load_classifier_prompt()\
                                .replace("{current_date_str}", current_date_str)\
                                .replace("{owner_name}", owner_name)\
                                .replace("{user_input}", user_input)\
                                .replace("{chat_history}", "- " + "\n- ".join(formatted_history))

        try:
            resp = await self.classifier_llm.ainvoke(classifier_prompt)
            llm_category = resp.content.strip() if hasattr(resp, "content") else str(resp).strip()
            return llm_category
        except Exception as e:
            self.logger.warning(f"CalendarAgent categorisation failed: {e}")
            return "Proposition de créneaux"
        
    def _get_french_slots(self, slots: list[str]) -> str:
        results = []
        for slot in slots:
            results.append(self._get_french_slot(slot))
        return results

    def _get_french_slot(self, slot: str) -> str:
        # Expects slot in "YYYY-MM-DD HH:MM-HH:MM"
        date_part, time_part = slot.split(" ")
        start_time, end_time = time_part.split("-")
        dt = datetime.strptime(date_part, "%Y-%m-%d")
        jours = [
            "lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"
        ]
        mois = [
            "", "janvier", "février", "mars", "avril", "mai", "juin",
            "juillet", "août", "septembre", "octobre", "novembre", "décembre"
        ]
        jour = jours[dt.weekday()]
        mois_nom = mois[dt.month]        
        jour_num = str(dt.day) # Remove leading zero for day
        debut_h, debut_m = start_time.split(":")
        fin_h, fin_m = end_time.split(":")
        debut_m_str = '' if debut_m == '00' else f' {debut_m}'
        fin_m_str = '' if fin_m == '00' else f' {fin_m}'
        return f"{jour} {jour_num} {mois_nom} entre {int(debut_h)} heure{'s' if int(debut_h) != 1 else ''}{debut_m_str} et {int(fin_h)} heure{'s' if int(fin_h) != 1 else ''}{fin_m_str}"

    def _to_french_date(self, dt: datetime, include_weekday: bool = True, include_year: bool = False, include_hour: bool = False) -> str:
        french_days = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
        french_months = ["", "janvier", "février", "mars", "avril", "mai", "juin", 
                         "juillet", "août", "septembre", "octobre", "novembre", "décembre"]
        french_date = ""
        if include_weekday: french_date += f"{french_days[dt.weekday()]} "
        french_date += f"{dt.day} {french_months[dt.month]}"
        if include_year: french_date += f" {dt.year}"
        if include_hour: french_date += f" à {self._to_french_time(dt)}"
        return french_date

    def _to_french_time(self, dt: datetime) -> str:
        minute_str = '' if dt.minute == 0 else f' {dt.minute}'
        return f"{dt.hour} heure{'s' if int(dt.hour) != 1 else ''}{minute_str}".strip()

    def get_available_timeframes_from_scheduled_slots(
        start_date: str,
        end_date: str,
        scheduled_slots: list[dict[str, any]],
        slot_duration_minutes: int = 30,
        max_weekday: int = 5,
        availability_timeframe: list[tuple[str, str]] = None,
        adjust_end_time: bool = False,
    ) -> list[str]:
        """
        Return available appointment timeframes between start_date and end_date as consolidated ranges.
        
        Args:
            start_date: Start date for availability search
            end_date: End date for availability search
            scheduled_slots: List of occupied slots from Salesforce
            slot_duration_minutes: Duration of each slot in minutes
            max_weekday: Maximum weekday (0=Monday, 6=Sunday), default is 5 (only weekdays)
            availability_timeframe: List of tuples with opening hours [("09:00", "12:00"), ("13:00", "18:00")]
                                   Default is morning 9-12 and afternoon 13-18
            adjust_end_time: If True, adjust the end time of each availability timeframe by subtracting
                               the slot duration to ensure the last appointment fits fully.
        """
        if availability_timeframe is None:
            availability_timeframe = [("09:00", "12:00"), ("13:00", "18:00")]

        # Parse start and end dates
        start_date_only = datetime.fromisoformat(start_date.replace('Z', '')).date()
        end_date_only = datetime.fromisoformat(end_date.replace('Z', '')).date()

        # Prepare occupied slots for quick lookup
        scheduled_slots_dt = []
        for slot in scheduled_slots:
            scheduled_slots_dt.append((
                datetime.fromisoformat(slot['StartDateTime'].replace('Z', '')),
                datetime.fromisoformat(slot['EndDateTime'].replace('Z', ''))
            ))

        delta = timedelta(minutes=slot_duration_minutes)
        available_ranges = []

        # Iterate through each day in the requested range
        while start_date_only <= end_date_only:
            # Skip weekends if max_weekday is set to 5 (Friday)
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
                import pytz
                french_tz = pytz.timezone('Europe/Paris')
                timeframe_start = french_tz.localize(datetime.combine(
                    start_date_only,
                    start_hour_dt.time()
                ))
                timeframe_end = french_tz.localize(datetime.combine(
                    start_date_only,
                    end_hour_dt.time()
                ))
                
                # If adjust_end_time is True, reduce the timeframe_end by slot_duration_minutes upfront.
                if adjust_end_time:
                    timeframe_end -= delta
                    # Special case: if after adjustment, start == end, return a single slot
                    if timeframe_start == timeframe_end:
                        formatted_range = f"{timeframe_start.strftime('%Y-%m-%d %H:%M')}-{timeframe_end.strftime('%H:%M')}"
                        available_ranges.append(formatted_range)
                        continue
            
                # Find available slots within this timeframe
                available_slots: list[datetime] = [] 
                current_slot = timeframe_start

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


    async def _extract_appointment_selected_date_and_time_async(self, user_input: str, chat_history: list[dict[str, str]]) -> datetime:
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
        response = await chain.ainvoke({
            "input": user_input,
            "chat_history": chat_history_str,
            "now": self._to_french_date(CalendarAgent.now, include_weekday=True, include_year=True, include_hour=True)
        })
        
        try:
            response = response.strip()
            if response == "not-found":
                return None
            else:
                return datetime.strptime(response, "%Y-%m-%dT%H:%M:%SZ")
        except ValueError:
            return None

    def _to_str_iso(self, dt: datetime) -> str:
        return dt.strftime("%Y-%m-%dT%H:%M:%SZ")