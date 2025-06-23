from unittest.mock import AsyncMock
import pytest
from datetime import datetime, timedelta
from langchain_core.runnables import Runnable
from langchain_core.messages import AIMessage
from app.agents.calendar_agent import CalendarAgent

LLM_SHOULD_FAIL = object()  # Marker object to indicate LLM failure in tests

class DummyLLM(Runnable):
    """Very small async mock suitable for our unit tests, can simulate success or failure."""

    def __init__(self, category_to_return: str = "DefaultCategory", raise_exception: bool = False):
        self._category_to_return = category_to_return
        self._raise_exception = raise_exception

    def bind_tools(self, _tools):
        return self

    async def ainvoke(self, _messages):
        if self._raise_exception:
            raise Exception("LLM ainvoke failed for test")
        return AIMessage(content=self._category_to_return)

    def invoke(self, _messages):
        if self._raise_exception:
            raise Exception("LLM invoke failed for test")
        return AIMessage(content=self._category_to_return)

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
    # Setup DummyLLM based on llm_behavior parameter
    if llm_behavior is LLM_SHOULD_FAIL:
        llm_instance = DummyLLM(raise_exception=True)
    else:
        # llm_behavior is the category string the LLM should return
        llm_instance = DummyLLM(category_to_return=llm_behavior)

    agent = CalendarAgent(llm_instance, sf_client_mock)
    # Set deterministic time for output
    CalendarAgent.now = datetime(2025, 6, 19)
    # User info is needed because categorize_for_dispatch_async formats a prompt with owner_name
    agent._set_user_info("test_user_id", "Test", "User", "test@example.com", "test_owner_id", "TestOwnerName")

    # Call the method under test
    actual_category = await agent.categorize_for_dispatch_async(user_input, chat_history)

    # Assert that the correct category is returned
    assert actual_category == expected_category


async def test_proposition_de_creneaux_calls_get_appointments(sf_client_mock):
    agent = CalendarAgent(DummyLLM("Proposition de créneaux"), sf_client_mock)
    CalendarAgent.now = datetime(2025, 6, 19)
    agent._set_user_info("uid", "John", "Doe", "john@ex.com", "ownerId", "Alice")

    await agent.run_async("Je voudrais un rendez-vous", [])
    
    sf_client_mock.get_scheduled_appointments_async.assert_awaited()


@pytest.mark.parametrize(
    "user_input, chat_history",
    [
        ("Parfait, c'est confirmé",
        [
            {'role': 'human', 'content': 'Je voudrais prendre rendez-vous demain'},
            {'role': 'AI', 'content': 'Bien sur, je peux vous proposer demain entre 9h et 11h ou entre 14h et 16h. Avez-vous une préférence ?'},
            {'role': 'human', 'content': 'oui, demain à 10h'},
            {'role': 'AI', 'content': 'Parfait, je vais planifier votre rendez-vous pour demain, mardi 10 juin de 10h à 10h30 concernant une demande de conseil en formation. Confirmez-vous ce rendez-vous ?'}
        ])
    ])
async def test_rendez_vous_confirme_calls_schedule(sf_client_mock, user_input, chat_history):
    agent = CalendarAgent(DummyLLM("Rendez-vous confirmé"), sf_client_mock)
    CalendarAgent.now = datetime(2025, 6, 19)
    agent._set_user_info("uid", "John", "Doe", "john@ex.com", "ownerId", "Alice")
    await agent.run_async(user_input, chat_history)
    sf_client_mock.schedule_new_appointment_async.assert_awaited()