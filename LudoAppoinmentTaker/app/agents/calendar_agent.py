import os
from datetime import datetime, timedelta
from langchain.tools import tool, BaseTool
from langchain.agents import AgentExecutor, create_tool_calling_agent, create_react_agent
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from app.api_client.salesforce_api_client import SalesforceApiClient
from uuid import UUID
import logging

class CalendarAgent:
    def __init__(self, llm_or_chain: any, salesforce_client: SalesforceApiClient):
        self.logger = logging.getLogger(__name__)
        self.tools = [self.get_current_date, self.get_appointments, self.schedule_new_appointment]
        self.salesforce_client = salesforce_client
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
        return datetime.now().strftime("%A, %B %d, %Y")

    @tool
    def get_appointments(start_date: datetime, end_date: datetime, owner_id: UUID) -> list[dict[str, any]]:
        """Get the existing appointments between the start and end dates for the owner"""
        salesforce_client = SalesforceApiClient()
        return salesforce_client.get_scheduled_appointments_async(str(start_date), str(end_date), str(owner_id))

    @tool
    def schedule_new_appointment(
            user_id: UUID,
            owner_id: UUID,
            date_and_time: datetime,
            object: str | None = None,
            description: str | None = None,
            duration: int = 30
        ) -> dict[str, any]:
        """Schedule a new appointment with the owner at the specified date and time"""
        object = object if object else "Demande de conseil en formation prospect"
        description = description if description else "RV pris par l'IA après appel entrant du prospect"
        salesforce_client = SalesforceApiClient()
        return salesforce_client.schedule_new_appointment_async(str(user_id), str(owner_id), object, description, str(date_and_time), duration)

    def _load_prompt(self):
        with open("app/agents/calendar_prompt.txt", "r", encoding="utf-8") as f:
            return f.read()

    def set_user_info(self, first_name, last_name, email, owner_name):
        """
        Initialize the Calendar Agent with user information and configuration.
        
        Args:
            first_name: Customer's first name
            last_name: Customer's last name
            email: Customer's email
            owner_name: Owner's (advisor) name
        """
        self.logger.info(f"Setting user info for CalendarAgent to: {first_name} {last_name} {email}, for owner: {owner_name}")
        self.first_name = first_name
        self.last_name = last_name
        self.email = email
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
        response = await self.agent_executor.ainvoke({
            "input": user_input,
            "chat_history": formatted_history
        })
        return {
            "output": response["output"],
            "intermediate_steps": response.get("intermediate_steps", [])
        }