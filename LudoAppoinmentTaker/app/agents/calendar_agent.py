import os
import logging
import time
#
from datetime import datetime, timedelta
from langchain.tools import tool, BaseTool
from langchain.agents import AgentExecutor, create_tool_calling_agent, create_react_agent
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
#
from app.api_client.salesforce_api_client_interface import SalesforceApiClientInterface

class CalendarAgent:        
    salesforce_api_client: SalesforceApiClientInterface
    owner_id = None
    owner_name = None
    
    def __init__(self, llm_or_chain: any, salesforce_api_client: SalesforceApiClientInterface):
        self.logger = logging.getLogger(__name__)
        CalendarAgent.salesforce_api_client = salesforce_api_client
        # The agent now only exposes calendar-related tools – we removed contextual helpers that can be injected directly.
        self.tools = [self.get_appointments, self.schedule_new_appointment]
        self.llm = llm_or_chain
        self.prompt = self._load_prompt()
        self.prompts = ChatPromptTemplate.from_messages([
            ("system", self.prompt),
            MessagesPlaceholder(variable_name="chat_history"),
            ("human", "{input}"),
            MessagesPlaceholder(variable_name="agent_scratchpad"),
        ])
        self.agent = create_tool_calling_agent(self.llm, self.tools, self.prompts)
        self.agent_executor = AgentExecutor(agent=self.agent, tools=self.tools, verbose=True)
        # response = self.agent_executor.invoke({"input": "quel jour sommes nous ?", "chat_history": []})['output']

    @tool
    def get_owner_name() -> str:
        """Get the owner name"""
        return CalendarAgent.get_owner_name_tool()

    @staticmethod
    def get_owner_name_tool() -> str:
        return CalendarAgent.owner_name

    @tool
    def get_current_date() -> str:
        """Get the current date"""
        return CalendarAgent.get_current_date_tool()

    @staticmethod
    def get_current_date_tool() -> str:
        return datetime.now().strftime("%A %d %B %Y")

    @tool
    async def get_appointments(start_date: str, end_date: str) -> list[dict[str, any]]:
        """Get the existing appointments between the start and end dates for the owner"""
        # Get the existing appointments from Salesforce API
        #TODO: manage "CalendarAgent.owner_id" another way to allow multi-calls handling.
        taken_slots = await CalendarAgent.salesforce_api_client.get_scheduled_appointments_async(start_date, end_date, CalendarAgent.owner_id)
        
        # Log the result
        logger = logging.getLogger(__name__)
        logger.info(f"Called 'get_appointments' tool for owner {CalendarAgent.owner_id} between {start_date} and {end_date}.")
        if taken_slots:
            logger.info(f"Here is the list of the owner calendar taken slots: \n{'\n'.join(f'- De {slot.get('StartDateTime')} à {slot.get('EndDateTime')} - Sujet: {slot.get('Subject', '-')} - Description: {slot.get('Description', '-')} - Location: {slot.get('Location', '-')} - OwnerId: {slot.get('OwnerId', '-')} - WhatId: {slot.get('WhatId', '-')} - WhoId: {slot.get('WhoId', '-')}' for slot in taken_slots)}")
        else:
            logger.info("No appointments found for the owner between the specified dates.")
        return taken_slots

    @tool
    async def schedule_new_appointment(
            date_and_time: str,
            duration: int = 30,
            object: str | None = None,
            description: str | None = None
        ) -> dict[str, any]:
        """Schedule a new appointment with the owner at the specified date and time"""
        await CalendarAgent.schedule_new_appointment_tool_async(date_and_time, duration, object, description)

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
        with open("app/agents/calendar_agent_prompt.txt", "r", encoding="utf-8") as f:
            return f.read()

    def _load_classifier_prompt(self):
        with open("app/agents/calendar_agent_classifier_prompt.txt", "r", encoding="utf-8") as f:
            return f.read()

    def set_user_info(self, user_id, first_name, last_name, email, owner_id, owner_name):
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
        """
        if chat_history is None:
            chat_history = []

        # Re-format history the same way run_async expects
        formatted_history = []
        for message in chat_history:
            if "AI" in message:
                formatted_history.append(AIMessage(content=message["AI"]))
            elif "human" in message:
                formatted_history.append(HumanMessage(content=message["human"]))

        # Current contextual data to inject directly (no dedicated tools anymore)
        current_date_str = datetime.now().strftime("%A %d %B %Y")
        owner_name = CalendarAgent.owner_name or "le conseiller"

        classifier_prompt = self._load_classifier_prompt()\
                                .replace("{current_date_str}", current_date_str)\
                                .replace("{owner_name}", owner_name)

        messages = [SystemMessage(content=classifier_prompt)] + formatted_history + [HumanMessage(content=user_input)]

        try:
            # Use whichever async interface the provided LLM exposes.
            if hasattr(self.llm, "ainvoke"):
                resp = await self.llm.ainvoke({"messages": messages})
                return resp.content.strip() if hasattr(resp, "content") else str(resp).strip()
            elif hasattr(self.llm, "invoke"):
                resp = self.llm.invoke({"messages": messages})
                return resp.content.strip() if hasattr(resp, "content") else str(resp).strip()
            else:
                self.logger.error("LLM categorisation failed, fallback to heuristics: LLM does not have an async interface.")
                
        except Exception as e:
            self.logger.warning(f"LLM categorisation failed, fallback to heuristics: {e}")

        # ---- Heuristic fallback ----
        text = user_input.lower()
        if any(k in text for k in ["quels", "disponibilités", "jours", "heures"]):
            return "Demande des disponibilités"
        if any(k in text for k in ["confirme", "confirmation"]):
            return "Demande de confirmation du rendez-vous"
        if any(k in text for k in ["rendez-vous le", "propose", "réserver"]):
            return "Proposition de rendez-vous"
        if any(k in text for k in ["pris", "merci", "parfait"]):
            return "Rendez-vous confirmé"
        return "Proposition de créneaux"
    
    async def run_async(self, user_input: str, chat_history: list[dict[str, str]] = None) -> str:
        """High-level dispatcher orchestrating calendar actions according to the category."""
        if chat_history is None:
            chat_history = []

        category = await self.categorize_for_dispatch_async(user_input, chat_history)
        self.logger.info(f"Category detected: {category}")

        # === Category-specific handling ===
        if category == "Proposition de créneaux":
            # Determine search window: next two business days
            start_date = (datetime.now() + timedelta(days=1))
            end_date = (start_date + timedelta(days=2))

            appointments = await CalendarAgent.salesforce_api_client.get_scheduled_appointments_async(
                self._to_str(start_date),
                self._to_str(end_date),
                CalendarAgent.owner_id,
            )

            available = self.get_available_timeframes_from_scheduled_slots(start_date, end_date, appointments)

            if not available:
                return (
                    "Je suis désolé, aucun créneau n'est disponible entre le " + self._to_str(start_date) + " et le " + self._to_str(end_date) + " "
                    "Souhaitez-vous élargir la recherche ?"
                )

            # Propose the 3 first available times
            available_timeframes = self._get_french_from_timeframes(available[:3])
            return f"Je peux vous proposer les créneaux suivants :\n- {"\n- ".join(available_timeframes)}.\nLequel vous conviendrait ?"

        if category == "Demande des disponibilités":
            return "Quels jours et quelles heures de la journée vous conviennent le mieux ?"

        if category == "Proposition de rendez-vous":
            # Very naive extraction – in production we would parse date/time from user input.
            start_date = datetime.now().date()
            end_date = start_date + timedelta(days=0)
            taken = await self.get_appointments(str(start_date), str(end_date))
            if not taken:
                return "Souhaitez-vous réserver un rendez-vous le jeudi 5 mai à 18 heures ?"
            return "Ce créneau n'est pas disponible, souhaiteriez-vous un autre horaire ?"

        if category == "Demande de confirmation du rendez-vous":
            return "Veuillez confirmer le rendez-vous du xxx à xxx."

        if category == "Rendez-vous confirmé":
            now_slot = self._to_str(datetime.now()) #TODO: put the selected date and time
            success = await CalendarAgent.schedule_new_appointment_tool_async(now_slot)
            if success is not None:
                return "Votre rendez-vous est bien planinfié pour le xxx à xxx. Merci et au revoir"
            return "Je n'ai pas pu planifier le rendez-vous. Souhaitez-vous essayer un autre créneau ?"

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

    def _get_french_from_timeframes(self, slots: list[str]) -> str:
        results = []
        for slot in slots:
            results.append(self._get_french_from_timeframe(slot))
        return results

    def _get_french_from_timeframe(self, slot: str) -> str:
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
        return f"le {jour} {jour_num} {mois_nom} entre {int(debut_h)} heure {'' if debut_m == '00' else int(debut_m)} et {int(fin_h)} heure {'' if fin_m == '00' else int(fin_m)}"
    
    def _to_str(self, dt: datetime) -> str:
        return dt.strftime("%Y-%m-%dT%H:%M:%SZ")

    def get_available_timeframes_from_scheduled_slots(
        self,
        start_date_only: datetime,
        end_date: datetime,
        taken_slots: list[dict[str, any]],
        slot_duration_minutes: int = 30,
        max_weekday: int = 5,
        availability_timeframe: list[tuple[str, str]] = None,
    ) -> list[str]:
        """
        Return available appointment timeframes between start_date and end_date as consolidated ranges.
        
        Args:
            start_date: Start date for availability search
            end_date: End date for availability search
            taken_slots: List of occupied slots from Salesforce
            slot_duration_minutes: Duration of each slot in minutes
            max_weekday: Maximum weekday (0=Monday, 6=Sunday), default is 5 (only weekdays)
            availability_timeframe: List of tuples with opening hours [("09:00", "12:00"), ("13:00", "18:00")]
                                   Default is morning 9-12 and afternoon 13-18
        
        Returns:
            List of consolidated available time ranges in format "YYYY-MM-DD HH:MM-HH:MM"
        """
        # Set default availability timeframe if not provided
        if availability_timeframe is None:
            availability_timeframe = [("09:00", "12:00"), ("13:00", "18:00")]
            
        # Build list of occupied intervals
        occupied: list[tuple[datetime, datetime]] = []
        for slot in taken_slots or []:
            try:
                s = datetime.strptime(slot["StartDateTime"], "%Y-%m-%dT%H:%M:%SZ")
                e = datetime.strptime(slot["EndDateTime"], "%Y-%m-%dT%H:%M:%SZ")
                occupied.append((s, e))
            except Exception:
                continue

        # Initialize results
        available_ranges: list[str] = []
        delta = timedelta(minutes=slot_duration_minutes)
        
        # Process each day in the range
        start_date_only = start_date_only.date()
        end_date_only = end_date.date()
        
        while start_date_only <= end_date_only:
            # Skip weekends based on max_weekday
            if start_date_only.weekday() < max_weekday:
                # Process each availability timeframe for this day
                for timeframe in availability_timeframe:
                    start_time, end_time = timeframe
                    
                    # Parse timeframe hours
                    start_hour_dt = datetime.strptime(start_time, "%H:%M")
                    end_hour_dt = datetime.strptime(end_time, "%H:%M")
                    
                    # Create datetime objects for this timeframe
                    timeframe_start = datetime.combine(
                        start_date_only,
                        start_hour_dt.time()
                    )
                    timeframe_end = datetime.combine(
                        end_date_only,
                        end_hour_dt.time()
                    )
                    
                    # Find available slots within this timeframe
                    available_slots: list[datetime] = []
                    current_slot = timeframe_start
                    
                    while current_slot + delta <= timeframe_end:
                        slot_end = current_slot + delta
                        if not any(current_slot < occ_end and slot_end > occ_start for occ_start, occ_end in occupied):
                            available_slots.append(current_slot)
                        current_slot += delta
                    
                    # Consolidate consecutive slots into ranges
                    if available_slots:
                        ranges = []
                        range_start = available_slots[0]
                        prev_slot = available_slots[0]
                        
                        for slot in available_slots[1:] + [None]:  # Add None as sentinel
                            if slot is None or (slot - prev_slot) != delta:
                                # End of a consecutive range
                                range_end = prev_slot + delta
                                formatted_range = f"{range_start.strftime('%Y-%m-%d %H:%M')}-{range_end.strftime('%H:%M')}"
                                ranges.append(formatted_range)
                                if slot is not None:
                                    range_start = slot
                            prev_slot = slot if slot is not None else prev_slot
                        
                        available_ranges.extend(ranges)
            
            # Move to next day
            start_date_only += timedelta(days=1)

        return available_ranges