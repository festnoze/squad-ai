from datetime import datetime
from unittest.mock import AsyncMock

import pytest
import pytz
from langchain_core.language_models import BaseLanguageModel
from langchain_core.messages import AIMessage

from app.agents.agents_graph import EnvHelper, LangChainAdapterType, LangChainFactory, LlmInfo
from app.agents.calendar_agent import CalendarAgent
from app.agents.text_registry import TextRegistry

LLM_SHOULD_FAIL = object()  # Marker object to indicate LLM failure in tests


class FakeLLM(BaseLanguageModel):
    def __init__(self, fake_value_to_return: str = "fake llm response", raise_exception: bool = False):
        self._fake_value_to_return = fake_value_to_return
        self._raise_exception = raise_exception

    def _check_exception(self, method_name: str):
        """Check if exception should be raised for this method."""
        if self._raise_exception:
            raise Exception(f"LLM {method_name} failed for test")

    def _get_text_response(self, method_name: str) -> str:
        """Get text response, checking for exceptions first."""
        self._check_exception(method_name)
        return self._fake_value_to_return

    def _get_message_response(self, method_name: str) -> AIMessage:
        """Get AIMessage response, checking for exceptions first."""
        self._check_exception(method_name)
        return AIMessage(content=self._fake_value_to_return)

    def bind_tools(self, _tools):
        return self

    async def ainvoke(self, _messages, create_task=True):
        return self._get_message_response("ainvoke")

    def invoke(self, _messages, create_task=True):
        return self._get_message_response("invoke")

    async def astream(self, _messages, create_task=True):
        return self._get_message_response("astream")

    def stream(self, _messages, create_task=True):
        return self._get_message_response("stream")

    async def agenerate_prompt(self, _messages, create_task=True):
        return self._get_message_response("agenerate_prompt")

    def generate_prompt(self, _messages, create_task=True):
        return self._get_message_response("generate_prompt")

    async def apredict(self, text, **kwargs):
        return self._get_text_response("apredict")

    async def apredict_messages(self, messages, **kwargs):
        return self._get_message_response("apredict_messages")

    def predict(self, text, **kwargs):
        return self._get_text_response("predict")

    def predict_messages(self, messages, **kwargs):
        return self._get_message_response("predict_messages")


@pytest.fixture
def sf_client_mock():
    class _DummyClient:
        get_scheduled_appointments_async = AsyncMock(return_value=[])
        schedule_new_appointment_async = AsyncMock(return_value={"Id": "001"})
        verify_appointment_existance_async = AsyncMock(return_value=None)  # No existing appointment

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
    ],
)
async def test_calendar_agent_classification(sf_client_mock, user_input, chat_history, llm_behavior, expected_category):
    """Tests the categorize_request_for_dispatch_async method for both LLM and heuristic paths."""
    # Setup fake LLM based on llm_behavior parameter
    if llm_behavior is LLM_SHOULD_FAIL:
        llm_instance = FakeLLM(raise_exception=True)
    else:
        # llm_behavior is the category string the LLM should return
        llm_instance = FakeLLM(fake_value_to_return=llm_behavior)

    agent = CalendarAgent(sf_client_mock, llm_instance)
    # Set deterministic time for output
    CalendarAgent.now = datetime(2025, 6, 19, tzinfo=pytz.timezone("Europe/Paris"))
    # User info is needed because categorize_request_for_dispatch_async formats a prompt with owner_name
    agent._set_user_info("test_user_id", "Test", "User", "test@example.com", "test_owner_id", "TestOwnerName")

    # Call the method under test
    actual_category = await agent.categorize_request_for_dispatch_async(user_input, chat_history)

    # Assert that the correct category is returned
    assert actual_category == expected_category


async def test_proposition_de_creneaux_calls_get_appointments(sf_client_mock):
    openai_api_key = EnvHelper.get_openai_api_key()
    calendar_timeframes_llm = LangChainFactory.create_llm_from_info(LlmInfo(type=LangChainAdapterType.OpenAI, model="gpt-4.1", timeout=50, temperature=0.1, api_key=openai_api_key))
    agent = CalendarAgent(sf_client_mock, FakeLLM("Proposition de créneaux"), calendar_timeframes_llm)
    CalendarAgent.now = datetime(2025, 6, 19, tzinfo=pytz.timezone("Europe/Paris"))
    agent._set_user_info("uid", "John", "Doe", "john@ex.com", "ownerId", "Alice")

    await agent.process_to_schedule_new_appointement_async("Je voudrais un rendez-vous", [])

    sf_client_mock.get_scheduled_appointments_async.assert_awaited()


@pytest.mark.parametrize(
    "user_input, chat_history",
    [
        (
            "Parfait, c'est confirmé",
            [
                ("human", "Je voudrais prendre rendez-vous demain"),
                ("AI", "Bien sur, je peux vous proposer demain entre 9h et 11h ou entre 14h et 16h. Avez-vous une préférence ?"),
                ("human", "oui, demain à 10h"),
                ("AI", "Parfait, je vais planifier votre rendez-vous pour demain, mardi 10 juin de 10h à 10h30 concernant une demande de conseil en formation. Confirmez-vous ce rendez-vous ?"),
            ],
        )
    ],
)
async def test_user_confirmation_calls_schedule_new_appointment(sf_client_mock, user_input, chat_history):
    # Arrange
    agent = CalendarAgent(sf_client_mock, FakeLLM("Rendez-vous confirmé"), FakeLLM(""), FakeLLM("2025-06-10T10:00:00Z"))

    # Set hard-coded now / business opening days & hours / user infos, for the test consistency
    CalendarAgent.now = datetime(2025, 6, 9, tzinfo=pytz.timezone("Europe/Paris"))
    agent._set_user_info("uid", "John", "Doe", "john@ex.com", "ownerId", "Alice")
    agent.business_hours_config.time_slots = [("09:00", "12:00"), ("13:00", "16:00")]
    agent.business_hours_config.allowed_weekdays = [0, 1, 2, 3, 4]
    
    # Act
    await agent.process_to_schedule_new_appointement_async(user_input, chat_history)

    # Assert
    sf_client_mock.schedule_new_appointment_async.assert_awaited()


@pytest.mark.parametrize(
    "user_input, chat_history, requested_date, category, expected_result",
    [
        # Test "Proposition de créneaux" category
        ("Je voudrais un rendez-vous dans 2 semaines", [], "2025-07-05T10:00:00Z", "Proposition de créneaux", "normal_flow"),
        ("Je voudrais un rendez-vous dans 30 jours", [], "2025-07-19T10:00:00Z", "Proposition de créneaux", "normal_flow"),
        ("Je voudrais un rendez-vous dans un mois et demi", [], "2025-07-20T10:00:00Z", "Proposition de créneaux", "too_far"),
        ("Je voudrais un rendez-vous en septembre", [], "2025-09-15T10:00:00Z", "Proposition de créneaux", "too_far"),
        # Test "Proposition de rendez-vous" category
        ("Je voudrais réserver pour dans 2 semaines", [], "2025-07-05T10:00:00Z", "Proposition de rendez-vous", "normal_flow"),
        ("Je voudrais réserver pour dans 30 jours", [], "2025-07-19T10:00:00Z", "Proposition de rendez-vous", "normal_flow"),
        ("Je voudrais réserver pour dans un mois et demi", [], "2025-07-20T10:00:00Z", "Proposition de rendez-vous", "too_far"),
        ("Je voudrais réserver pour septembre", [], "2025-09-15T10:00:00Z", "Proposition de rendez-vous", "too_far"),
        # Test "Demande de confirmation du rendez-vous" category
        ("Oui, confirmé pour dans 2 semaines", [], "2025-07-05T10:00:00Z", "Demande de confirmation du rendez-vous", "normal_flow"),
        ("Oui, confirmé pour dans 30 jours", [], "2025-07-19T10:00:00Z", "Demande de confirmation du rendez-vous", "normal_flow"),
        ("Oui, confirmé pour dans un mois et demi", [], "2025-07-20T10:00:00Z", "Demande de confirmation du rendez-vous", "too_far"),
        ("Oui, confirmé pour septembre", [], "2025-09-15T10:00:00Z", "Demande de confirmation du rendez-vous", "too_far"),
        # Test "Rendez-vous confirmé" category
        ("Parfait, dans 2 semaines", [], "2025-07-05T10:00:00Z", "Rendez-vous confirmé", "normal_flow"),
        ("Parfait, dans 30 jours", [], "2025-07-19T10:00:00Z", "Rendez-vous confirmé", "normal_flow"),
        ("Parfait, dans un mois et demi", [], "2025-07-20T10:00:00Z", "Rendez-vous confirmé", "too_far"),
        ("Parfait, en septembre", [], "2025-09-15T10:00:00Z", "Rendez-vous confirmé", "too_far"),
    ],
)
async def test_appointment_too_far_validation(sf_client_mock, user_input, chat_history, requested_date, category, expected_result):
    """Test that appointments requested more than 30 days in the future are rejected across all relevant categories."""
    # Set up fake LLMs
    classifier_llm = FakeLLM(category)  # Classify as the category we want to test
    date_extractor_llm = FakeLLM(requested_date)  # Return the date we want to test

    agent = CalendarAgent(sf_client_mock, classifier_llm, None, date_extractor_llm)

    # Set hard-coded now / business opening days & hours / user infos, for the test consistency
    agent.business_hours_config.time_slots = [("09:00", "12:00"), ("13:00", "16:00")]
    agent.business_hours_config.allowed_weekdays = [0, 1, 2, 3, 4]
    CalendarAgent.now = datetime(2025, 6, 19, tzinfo=pytz.timezone("Europe/Paris"))
    agent._set_user_info("uid", "John", "Doe", "john@ex.com", "ownerId", "Alice")

    # Call run_async with the test input
    result = await agent.process_to_schedule_new_appointement_async(user_input, chat_history)

    # Validate the result based on expected behavior
    if expected_result == "too_far":
        assert result == TextRegistry.appointment_too_far_text
    elif expected_result == "normal_flow":
        assert result != TextRegistry.appointment_too_far_text
    else:
        assert result == ""
