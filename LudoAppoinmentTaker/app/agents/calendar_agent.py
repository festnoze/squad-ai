import os
from datetime import datetime, timedelta
from langchain.tools import tool, BaseTool
from langchain.agents import AgentExecutor, create_tool_calling_agent, create_react_agent
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from app.api_client.salesforce_api_client import SalesforceApiClient
import logging

class CalendarAgent:        
    salesforce_api_client = SalesforceApiClient()
    owner_id = None
    
    def __init__(self, llm_or_chain: any):
        self.logger = logging.getLogger(__name__)
        self.tools = [self.get_current_date, self.get_appointments, self.schedule_new_appointment]
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
    def get_current_date() -> str:
        """Get the current date"""
        return CalendarAgent.get_current_date_tool()

    @staticmethod
    def get_current_date_tool() -> str:
        return datetime.now().strftime("%A, %B %d, %Y")

    @tool
    async def get_appointments(start_date: str, end_date: str) -> list[dict[str, any]]:
        """Get the existing appointments between the start and end dates for the owner"""
        # Handle different input formats for dates (w/ or w/o: time, 'T' / 'Z' chars)
        start_date_formated = start_date if "T" in start_date else f"{start_date}T"
        end_date_formated = end_date if "T" in end_date else f"{end_date}T"
        #
        if start_date_formated.endswith("T"): start_date_formated += "00:00:00"
        if end_date_formated.endswith("T"): end_date_formated += "23:59:59"
        #
        if not start_date_formated.endswith("Z"): start_date_formated += "Z"
        if not end_date_formated.endswith("Z"): end_date_formated += "Z"

        # Get the existing appointments from Salesforce API
        #TODO: manage "CalendarAgent.owner_id" another way to allow multi-calls handling.
        taken_slots = await CalendarAgent.salesforce_api_client.get_scheduled_appointments_async(start_date_formated, end_date_formated, CalendarAgent.owner_id)
        
        # Log the result
        logger = logging.getLogger(__name__)
        logger.info(f"Called 'get_appointments' tool for owner {CalendarAgent.owner_id} between {start_date} and {end_date}.")
        if taken_slots:
            logger.info(f"Here is the list of the owner calendar taken slots: \n{'\n'.join(f'- De {slot['StartDateTime']} à {slot['EndDateTime']} - Sujet: {slot['Subject']} - Description: {slot['Description']}' for slot in taken_slots)}")
        else:
            logger.info("No appointments found for the owner between the specified dates.")
        return taken_slots

    @tool
    async def schedule_new_appointment(
            user_id: str,
            date_and_time: str,
            object: str | None = None,
            description: str | None = None,
            duration: int = 30
        ) -> dict[str, any]:
        """Schedule a new appointment with the owner at the specified date and time"""
        object = object if object else "Demande de conseil en formation prospect"
        description = description if description else "RV pris par l'IA après appel entrant du prospect"
        if not date_and_time.endswith("Z"):
            date_and_time += "Z"

        logger = logging.getLogger(__name__)
        logger.info(f"########### Called 'schedule_new_appointment' tool for {CalendarAgent.owner_id} at: {date_and_time}.")

        return await CalendarAgent.salesforce_api_client.schedule_new_appointment_async(user_id, CalendarAgent.owner_id, date_and_time, object, description, duration) #TODO: manage "CalendarAgent.owner_id" another way to allow multi-calls handling.

    def _load_prompt(self):
        with open("app/agents/calendar_prompt.txt", "r", encoding="utf-8") as f:
            return f.read()

    def set_user_info(self, first_name, last_name, email, owner_id, owner_name):
        """
        Initialize the Calendar Agent with user information and configuration.
        
        Args:
            first_name: Customer's first name
            last_name: Customer's last name
            email: Customer's email
            owner_id: Owner's (advisor) ID
            owner_name: Owner's (advisor) name
        """
        self.logger.info(f"Setting user info for CalendarAgent to: {first_name} {last_name} {email}, for owner: {owner_name}")
        self.first_name = first_name
        self.last_name = last_name
        self.email = email
        CalendarAgent.owner_id = owner_id
        self.owner_name = owner_name        
        # self.calendar_service = self._init_google_calendar()
        # self.calendar_id = self.config["google_calendar"]["calendar_id"]

        # self.duration = self.config["appointments"].get("duration_minutes", 30)
        # self.max_slots = self.config["appointments"].get("max_slots", 3)
        
        # self.tz_name = "Europe/Paris"
        # self.tz = ZoneInfo(self.tz_name)
        # self.tz_offset = timezone(timedelta(hours=2))  # Adaptable si besoin
        
        # self.working_hours = self.config["appointments"]["working_hours"]
        # self.days_ahead = self.config["appointments"].get("days_ahead", 2)


    async def run_async(self, user_input: str, chat_history: list[dict[str, str]] = None) -> dict[str, any]:
        if chat_history is None:
            chat_history = []
        formatted_history = []
        for message in chat_history:
            if "AI" in message:
                formatted_history.append(AIMessage(content=message["AI"]))
            elif "human" in message:
                formatted_history.append(HumanMessage(content=message["human"]))
        try:
            # response = await self.agent_executor.ainvoke({"input": "quel jour sommes nous ?", "chat_history": []})
            # response = await self.agent_executor.ainvoke({"input": "Je voudrais prendre rendez-vous demain", "chat_history": []})
            response = await self.agent_executor.ainvoke({
                "input": user_input,
                "chat_history": formatted_history
            }) 
        except Exception as e:
            self.logger.error(f"/!\\ Error executing calendar agent with tools: {e}")
        return response["output"]