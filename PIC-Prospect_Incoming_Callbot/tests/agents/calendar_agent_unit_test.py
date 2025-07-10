from unittest.mock import AsyncMock
import pytest
from datetime import datetime, timedelta
from langchain_core.runnables import Runnable
from langchain_core.messages import AIMessage
from app.agents.calendar_agent import CalendarAgent
from app.agents.agents_graph import LangChainFactory
from app.agents.agents_graph import LlmInfo
from app.agents.agents_graph import LangChainAdapterType
from app.agents.agents_graph import EnvHelper

LLM_SHOULD_FAIL = object()  # Marker object to indicate LLM failure in tests

class FakeLLM(Runnable):
    def __init__(self, fake_value_to_return: str = "fake llm response", raise_exception: bool = False):
        self._fake_value_to_return = fake_value_to_return
        self._raise_exception = raise_exception

    def bind_tools(self, _tools):
        return self

    async def ainvoke(self, _messages, create_task=True):
        if self._raise_exception:
            raise Exception("LLM ainvoke failed for test")
        return AIMessage(content=self._fake_value_to_return)

    def invoke(self, _messages, create_task=True):
        if self._raise_exception:
            raise Exception("LLM invoke failed for test")
        return AIMessage(content=self._fake_value_to_return)

@pytest.fixture
def sf_client_mock():
    class _DummyClient:
        get_scheduled_appointments_async = AsyncMock(return_value=[])
        schedule_new_appointment_async = AsyncMock(return_value={"Id": "001"})

    return _DummyClient()


@pytest.mark.parametrize(
    "user_input, chat_history, llm_behavior, expected_category",
    [
        # Test LLM path: LLM successfully returns a category
        ("Je veux un RDV", [], "Proposition de créneaux", "Proposition de créneaux"),
        ("Quelles sont vos disponibilités cette semaine ?", [], "Demande des disponibilités", "Demande des disponibilités"),
        ("Je voudrais réserver pour jeudi 10h", [], "Proposition de rendez-vous", "Proposition de rendez-vous"),
        ("Pouvez-vous confirmer notre RDV de demain ?", [], "Demande de confirmation du rendez-vous", "Demande de confirmation du rendez-vous"),
        ("Oui, c'est confirmé pour moi.", [], "Rendez-vous confirmé", "Rendez-vous confirmé"),

        # Default fallback to "Proposition de créneaux" when LLM fails and no strong heuristic matches
        ("Bonjour, comment allez-vous ?", [], LLM_SHOULD_FAIL, "Proposition de créneaux"),
        ("Une question d'ordre général.", [], LLM_SHOULD_FAIL, "Proposition de créneaux"),
    ]
)
async def test_calendar_agent_classification(sf_client_mock, user_input, chat_history, llm_behavior, expected_category):
    """Tests the categorize_for_dispatch_async method for both LLM and heuristic paths."""
    # Setup fake LLM based on llm_behavior parameter
    if llm_behavior is LLM_SHOULD_FAIL:
        llm_instance = FakeLLM(raise_exception=True)
    else:
        # llm_behavior is the category string the LLM should return
        llm_instance = FakeLLM(fake_value_to_return=llm_behavior)

    agent = CalendarAgent(sf_client_mock, llm_instance)
    # Set deterministic time for output
    CalendarAgent.now = datetime(2025, 6, 19)
    # User info is needed because categorize_for_dispatch_async formats a prompt with owner_name
    agent._set_user_info("test_user_id", "Test", "User", "test@example.com", "test_owner_id", "TestOwnerName")

    # Call the method under test
    actual_category = await agent.categorize_for_dispatch_async(user_input, chat_history)

    # Assert that the correct category is returned
    assert actual_category == expected_category


async def test_proposition_de_creneaux_calls_get_appointments(sf_client_mock):
    openai_api_key = EnvHelper.get_openai_api_key()
    calendar_timeframes_llm = LangChainFactory.create_llm_from_info(LlmInfo(type=LangChainAdapterType.OpenAI, model="gpt-4.1-mini", timeout=50, temperature=0.1, api_key=openai_api_key))
    agent = CalendarAgent(sf_client_mock, FakeLLM("Proposition de créneaux"), calendar_timeframes_llm)
    CalendarAgent.now = datetime(2025, 6, 19)
    agent._set_user_info("uid", "John", "Doe", "john@ex.com", "ownerId", "Alice")

    await agent.run_async("Je voudrais un rendez-vous", [])
    
    sf_client_mock.get_scheduled_appointments_async.assert_awaited()


@pytest.mark.parametrize(
    "user_input, chat_history",
    [
        ("Parfait, c'est confirmé",
        [
            ("human", "Je voudrais prendre rendez-vous demain"),
            ("AI", "Bien sur, je peux vous proposer demain entre 9h et 11h ou entre 14h et 16h. Avez-vous une préférence ?"),
            ("human", "oui, demain à 10h"),
            ("AI", "Parfait, je vais planifier votre rendez-vous pour demain, mardi 10 juin de 10h à 10h30 concernant une demande de conseil en formation. Confirmez-vous ce rendez-vous ?")
        ])
    ])
async def test_user_confirmation_calls_schedule_new_appointment(sf_client_mock, user_input, chat_history):
    agent = CalendarAgent(sf_client_mock, FakeLLM("Rendez-vous confirmé"), FakeLLM(""), FakeLLM("2025-06-10T10:00:00Z"))
    CalendarAgent.now = datetime(2025, 6, 9)
    agent._set_user_info("uid", "John", "Doe", "john@ex.com", "ownerId", "Alice")
    await agent.run_async(user_input, chat_history)
    sf_client_mock.schedule_new_appointment_async.assert_awaited()