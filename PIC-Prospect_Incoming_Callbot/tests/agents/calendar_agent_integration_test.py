import os
from datetime import datetime, timedelta
from unittest.mock import patch

import pytest

#
from agents.text_registry import TextRegistry

from app.agents.calendar_agent import CalendarAgent
from llms.langchain_adapter_type import LangChainAdapterType

#
from llms.langchain_factory import LangChainFactory
from llms.llm_info import LlmInfo


@pytest.mark.parametrize(
    "user_input, chat_history, expected_category, expected_answer, await_exact_match, exist_appointment",
    [
        # ===== SCENARIO A: STANDARD FLOW - ACCEPT FIRST PROPOSAL =====
        # A1: Initial contact - user wants to book an appointment
        (
            "Je voudrais prendre rendez-vous",
            [],
            "Proposition de créneaux",
            "Je vous propose les créneaux suivants : demain, jeudi 20 juin, de 9 heures à 11 heures 30, ou de 13 heures à 15 heures 30, ou vendredi 21 juin, de 9 heures à 11 heures 30. Avez-vous une préférence ?",
            True,  # Exact match
            False,  # exist_appointment
        ),
        # A2: User confirms the appointment
        (
            "Oui, réserve le premier créneau.",
            [
                ("human", "Je voudrais prendre rendez-vous"),
                (
                    "AI",
                    "Je vous propose les créneaux suivants : jeudi 20 juin, de 9 heures à 11 heures 30 ou de 14 heures à 14 heures 30. Avez-vous une préférence ?",
                ),
            ],
            "Demande de confirmation du rendez-vous",
            "Récapitulons : votre rendez-vous sera planifié le jeudi 20 juin à 9 heures. Merci de confirmer ce rendez-vous pour le valider.",
            True,  # Exact match
            False,  # exist_appointment
        ),
        # A3: User confirms the appointment
        (
            "Je confirme",
            [
                ("human", "Je voudrais prendre rendez-vous"),
                (
                    "AI",
                    "Je vous propose le créneaux du jeudi 20 juin à 14 heures. Si ce créneau vous convient, merci de me confirmer afin de finaliser sa réservation.",
                ),
                ("human", "Oui, ce créneau me convient parfaitement"),
                (
                    "AI",
                    "Veuillez confirmer le rendez-vous du jeudi 20 juin à 14 heures.",
                ),
            ],
            "Rendez-vous confirmé",
            "C'est confirmé, votre rendez-vous est maintenant planifié pour le jeudi 20 juin à 14 heures. Merci et au revoir.",
            True,  # Exact match
            False,  # exist_appointment
        ),
        # ===== SCENARIO B: ALTERNATIVE FLOW - REQUEST DIFFERENT SLOT =====
        # B0: User asks for different availability
        (
            "Quelles sont les dispo la semaine prochaine ?",
            [
                ("human", "Je voudrais prendre rendez-vous"),
                (
                    "AI",
                    "Je vous propose le créneaux du jeudi 20 juin à 14 heures. Si ce créneau vous convient, merci de me confirmer afin de finaliser sa réservation.",
                ),
            ],
            "Demande des disponibilités",
            TextRegistry.availability_request_text,
            False,  # Semantic matching
            False,  # exist_appointment
        ),
        # B1: User asks for different availability
        (
            "Quelles sont vos autres disponibilités ?",
            [
                ("human", "Je voudrais prendre rendez-vous"),
                (
                    "AI",
                    "Je vous propose le créneaux du jeudi 20 juin à 14 heures. Si ce créneau vous convient, merci de me confirmer afin de finaliser sa réservation.",
                ),
            ],
            "Demande des disponibilités",
            "Quels jours ou quelles heures de la journée vous conviendraient le mieux ?",
            True,  # Exact match
            True,  # exist_appointment
        ),
        # B2: User refuses, but proposes a specific time ("Je préfère vendredi à 10h")
        (
            "Je préfère vendredi à 10h",
            [
                ("human", "Je voudrais prendre rendez-vous"),
                (
                    "AI",
                    "Je vous propose le créneaux du jeudi 20 juin à 14 heures. Si ce créneau vous convient, merci de me confirmer afin de finaliser sa réservation.",
                ),
                ("human", "Quelles sont vos autres disponibilités ?"),
                (
                    "AI",
                    "Quels jours ou quelles heures de la journée vous conviendraient le mieux ?",
                ),
            ],
            "Demande de confirmation du rendez-vous",
            "Récapitulons : votre rendez-vous sera planifié le vendredi 21 juin à 10 heures. Merci de confirmer ce rendez-vous pour le valider.",
            True,  # Exact match
            False,  # exist_appointment
        ),
        # B3: User refuses, but specify its availability ("Non, je ne serais dispo qu'à partir de lundi prochain")
        (
            "Je ne serais dispo qu'à partir de lundi prochain",
            [
                ("human", "Je voudrais prendre rendez-vous"),
                (
                    "AI",
                    "Je vous propose le créneaux du jeudi 20 juin à 14 heures. Si ce créneau vous convient, merci de me confirmer afin de finaliser sa réservation.",
                ),
                ("human", "Quelles sont vos autres disponibilités ?"),
                (
                    "AI",
                    "Quels jours ou quelles heures de la journée vous conviendraient le mieux ?",
                ),
            ],
            "Proposition de créneaux",
            "Je vous propose les créneaux suivants : lundi 24 juin, de 9 heures à 11 heures 30, ou de 13 heures à 15 heures 30, ou mardi 25 juin, de 9 heures à 11 heures 30. Avez-vous une préférence ?",
            True,  # Exact match
            True,  # exist_appointment
        ),
        # B4: User confirms the new appointment
        (
            "Oui, je confirme ce rendez-vous",
            [
                ("human", "Je voudrais prendre rendez-vous"),
                (
                    "AI",
                    "Je vous propose le créneaux du jeudi 20 juin à 14 heures. Si ce créneau vous convient, merci de me confirmer afin de finaliser sa réservation.",
                ),
                ("human", "Quelles sont vos autres disponibilités ?"),
                (
                    "AI",
                    "Quels jours ou quelles heures de la journée vous conviendraient le mieux ?",
                ),
                ("human", "Je préfère vendredi à 10h"),
                (
                    "AI",
                    "Veuillez confirmer le rendez-vous du vendredi 21 juin à 10 heures.",
                ),
            ],
            "Rendez-vous confirmé",
            "C'est confirmé, votre rendez-vous est maintenant planifié pour le vendredi 21 juin à 10 heures. Merci et au revoir.",
            True,  # Exact match
            True,  # exist_appointment
        ),
        # ===== SCENARIO C: REJECTION FLOW - NO AVAILABILITY =====
        # C1: No availability in the requested timeframe
        (
            "Je voudrais prendre rendez-vous la semaine prochaine",
            [],
            "Proposition de créneaux",  # Agent indicates no slots
            "Je suis désolé, aucun créneau n'est disponible entre le 24 juin et le 28 juin. Souhaitez-vous regarder une autre date ?",
            False,  # Semantic match
            True,  # exist_appointment
        ),
        # C2: User asks to expand search
        (
            "Oui, pouvez-vous regarder la semaine d'après ?",
            [
                ("human", "Je voudrais prendre rendez-vous la semaine prochaine"),
                (
                    "AI",
                    "Je suis désolé, aucun créneau n'est disponible entre le 24 juin et le 28 juin. Souhaitez-vous élargir la recherche ?",
                ),
            ],
            "Proposition de créneaux",  # Agent will propose new slots
            "Je vous propose les créneaux suivants : lundi 1 juillet, de 9 heures à 11 heures 30, ou de 13 heures à 15 heures 30, ou mardi 2 juillet, de 9 heures à 11 heures 30. Avez-vous une préférence ?",
            False,  # Semantic match
            True,  # exist_appointment
        ),
        # ===== SCENARIO D: DIRECT SLOT REQUEST =====
        # D1: User directly requests a specific slot ("Je voudrais prendre rendez-vous jeudi à 15h")
        (
            "Je voudrais prendre rendez-vous jeudi à 15h",
            [],
            "Demande de confirmation du rendez-vous",
            "Récapitulons : votre rendez-vous sera planifié le jeudi 20 juin à 15 heures. Merci de confirmer ce rendez-vous pour le valider.",
            True,  # Exact match
            False,  # exist_appointment
        ),
        # ===== SCENARIO E: UNAVAILABLE SLOT PROPOSED BY USER =====
        # E1: User proposes a slot that is not available ("Je voudrais prendre rendez-vous lundi prochain à 9h")
        (
            "Je voudrais prendre rendez-vous lundi prochain à 9h",
            [],
            "Demande de confirmation du rendez-vous",  # Agent indicates slot is not available and proposes alternatives
            "Je suis désolé, ce créneau n'est pas disponible. A la place, Je vous propose les créneaux suivants : demain, le jeudi 20 juin, de 9 heures à 11 heures 30 ou de 13 heures à 15 heures 30, ou le vendredi 21 juin, de 9 heures à 11 heures 30. Avez-vous une préférence ?",
            False,  # Semantic match
            True,  # exist_appointment
        ),
        ### NOT HANDLED RIGHT NOW ###
        #############################
        # # ===== SCENARIO F: RESCHEDULING/CANCELLATION REQUEST =====
        # # F1: User wants to modify an appointment
        # (
        #     "Je souhaiterais changer l'heure de mon rendez-vous",
        #     [],
        #     "Demande de modification", # Agent asks for details of appointment to cancel
        #     "Je ne suis pas en mesure de gérer les modifications de rendez-vous.",
        #     True # Exact match
        # ),
        # # F2: User wants to cancel an appointment
        # (
        #     "Je souhaite annuler mon rendez-vous",
        #     [],
        #     "Demande d'annulation", # Agent asks for details of appointment to cancel
        #     "Je ne suis pas en mesure de gérer les annulations de rendez-vous.",
        #     True # Exact match
        # ),
        # # F3: User confirms cancellation with details
        # (
        #     "Oui, c'est le rendez-vous de jeudi à 14h",
        #     [
        #         ("human", "Je souhaite annuler mon rendez-vous"),
        #         ("AI", "Pourriez-vous me confirmer la date et l'heure du rendez-vous que vous souhaitez annuler ?")
        #     ],
        #     "Annulation confirmée",
        #     "Votre rendez-vous du jeudi 20 juin à 14 heures a bien été annulé. Souhaitez-vous en reprogrammer un autre ?",
        #     True, # Exact match
        #     True # exist_appointment
        # ),
        # ===== SCENARIO G: RESCHEDULING REQUEST =====
        # G1: User wants to reschedule ("En fait je préfère vendredi matin")
        (
            "En fait je préfère vendredi matin",
            [
                ("human", "Je voudrais prendre rendez-vous"),
                (
                    "AI",
                    "Je vous propose le créneaux du jeudi 20 juin à 14 heures. Si ce créneau vous convient, merci de me confirmer afin de finaliser sa réservation.",
                ),
                ("human", "Oui, ce créneau me convient parfaitement"),
                (
                    "AI",
                    "Veuillez confirmer le rendez-vous du jeudi 20 juin à 14 heures.",
                ),
            ],
            "Proposition de créneaux",  # Agent should ask for new preferences
            "Je vous propose les créneaux suivants : vendredi 21 juin, de 9 heures à 11 heures 30. Avez-vous une préférence ?",
            False,  # Semantic match
            True,  # exist_appointment
        ),
    ],
)
async def test_calendar_agent_integration_classification_plus_outputed_answer(
    sf_client_mock,
    llm_instance,
    similarity_evaluator,
    user_input,
    chat_history,
    expected_category,
    expected_answer,
    await_exact_match,
    exist_appointment,
):
    """
    Tests the complete workflow of the calendar agent through different scenarios.
    This test verifies that the agent responds appropriately based on the conversation context.

    Parameters:
        await_exact_match: If True, expects an exact match between expected_answer and actual_response.
                          If False, uses semantic similarity evaluation.
    """
    # Create the agent with mocked dependencies
    agent = CalendarAgent(sf_client_mock, llm_instance)
    CalendarAgent.now = datetime(2024, 6, 19, 19, 0)
    agent._set_user_info(
        "test_user_id",
        "Test",
        "User",
        "test@example.com",
        "test_owner_id",
        "TestOwnerName",
    )
    # Set the value returned by 'verify_appointment_existance_async' from SalesforceApiClient
    sf_client_mock.exist_appointment = exist_appointment

    # First, ensure the agent classifies the user input correctly
    actual_category = await agent.categorize_request_for_dispatch_async(user_input, chat_history)
    assert actual_category == expected_category, f"Expected category '{expected_category}', but got '{actual_category}' for input '{user_input}'."

    # Then, verify the agent's full response
    actual_response = await agent.run_async(user_input, chat_history)

    if await_exact_match:
        assert actual_response == expected_answer, f"Expected exact response:\n{expected_answer}\nGot:\n{actual_response}"
    else:
        is_similar = await similarity_evaluator.is_semantically_similar(expected_answer, actual_response)
        assert is_similar, f"Expected a response semantically similar to:\n{expected_answer}\nGot:\n{actual_response}"


async def test_complete_conversation_exchange(sf_client_mock, llm_instance, similarity_evaluator):
    """
    Tests a complete conversation flow from initial contact to appointment confirmation.
    This test simulates a realistic conversation between a user and the calendar agent.
    """
    # Create the agent with mocked dependencies
    agent = CalendarAgent(sf_client_mock, llm_instance)
    CalendarAgent.now = datetime(2024, 6, 19, 20, 0)
    agent._set_user_info(
        "test_user_id",
        "Test",
        "User",
        "test@example.com",
        "test_owner_id",
        "TestOwnerName",
    )

    # Define the conversation flow with expected categories and responses
    conversation_flow = [
        # Step 1: User initiates conversation
        {
            "user_input": "Bonjour, je voudrais prendre rendez-vous avec mon conseiller",
            "category": "Proposition de créneaux",
            "expected_response": "Je vous propose les créneaux suivants : demain, le jeudi 20 juin, de 9 heures à 11 heures 30 ou de 13 heures à 15 heures 30, ou vendredi 21 juin, de 9 heures à 11 heures 30. Avez-vous une préférence ?",
            "await_exact_match": True,
        },
        # Step 2: User asks for different availabilities
        {
            "user_input": "Avez-vous d'autres créneaux disponibles ?",
            "category": "Demande des disponibilités",
            "expected_response": "Quels jours ou quelles heures de la journée vous conviendraient le mieux ?",
            "await_exact_match": True,
        },
        # Step 3: User specifies a preference
        {
            "user_input": "Je préférerais vendredi après-midi",
            "category": "Proposition de créneaux",
            "expected_response": "Je vous propose le créneau suivant : vendredi, le 21 juin, de 13 heures à 15 heures 30. Avez-vous une préférence ?",
            "await_exact_match": False,
        },
        # Step 4: User specifies a slot
        {
            "user_input": "à 15 heures, c'est parfait.",
            "category": "Demande de confirmation du rendez-vous",
            "expected_response": "Récapitulons : votre rendez-vous sera planifié le vendredi 21 juin à 15 heures. Merci de confirmer ce rendez-vous pour le valider.",
            "await_exact_match": False,
        },
        # Step 5: User confirms the appointment
        {
            "user_input": "Je confirme le rendez-vous",
            "category": "Rendez-vous confirmé",
            "expected_response": "C'est confirmé, votre rendez-vous est maintenant planifié pour le vendredi 21 juin à 15 heures. Merci et au revoir.",
            "await_exact_match": True,
        },
    ]

    # Execute the conversation flow
    chat_history = []
    for step in conversation_flow:
        # Mock the categorize_request_for_dispatch_async method to return our predefined category for this step
        with patch.object(agent, "categorize_request_for_dispatch_async", return_value=step["category"]):
            # Call the method under test
            actual_response = await agent.run_async(step["user_input"], chat_history)

            # Verify the response using exact match or semantic similarity based on the parameter
            if step["await_exact_match"]:
                assert actual_response == step["expected_response"], f"Step {conversation_flow.index(step) + 1}: Expected: '{step['expected_response']}', Got: '{actual_response}'"
            else:
                is_similar = await similarity_evaluator.is_semantically_similar(step["expected_response"], actual_response)
                assert is_similar, f"Step {conversation_flow.index(step) + 1}: Expected a response similar to '{step['expected_response']}', but got '{actual_response}'"

            # Update chat history for the next step
            chat_history.append(("human", step["user_input"]))
            chat_history.append(("AI", actual_response))


class SimilarityEvaluator:
    @staticmethod
    async def is_semantically_similar(expected: str, actual: str) -> bool:
        llm = LangChainFactory.create_llm_from_info(
            LlmInfo(
                type=LangChainAdapterType.OpenAI,
                model="gpt-4o-mini",
                timeout=50,
                temperature=0.5,
                api_key=os.getenv("OPENAI_API_KEY") or "-- no openai key found --",
            )
        )
        prompt = "Compare the following two responses for semantic similarity: \nResponse 1: {expected} \nResponse 2: {actual} \nReturn 'True' if they are semantically similar, 'False' otherwise."

        response = await llm.ainvoke(prompt.format(expected=expected, actual=actual))
        return response.content == "True"


@pytest.fixture
def sf_client_mock():
    class _DummyClient:
        exist_appointment = False

        async def get_scheduled_appointments_async(self, start_datetime=None, end_datetime=None, *args, **kwargs) -> list:
            # Check if the specific date range is requested
            if str(start_datetime)[:10] == "2024-06-24" and str(end_datetime)[:10] == "2024-06-28":
                # Return 3 appointments, each 9 hours long, one per day
                appointments = []
                for day in range(5):
                    start = datetime(2024, 6, 24, 9, 0, 0) + timedelta(days=day)
                    end = start + timedelta(hours=9)
                    appointments.append(
                        {
                            "Id": f"appt_{day + 1}",
                            "StartDateTime": start.isoformat() + "Z",
                            "EndDateTime": end.isoformat() + "Z",
                            "Subject": f"Mock Appointment {day + 1}",
                            "Description": f"Mock Appointment {day + 1}",
                            "Location": f"Mock Appointment {day + 1}",
                            "OwnerId": "test_owner_id",
                            "WhatId": "test_what_id",
                            "WhoId": "test_who_id",
                        }
                    )
                return appointments
            return []

        async def schedule_new_appointment_async(self, *args, **kwargs) -> str | None:
            return "001"

        async def verify_appointment_existance_async(
            self,
            event_id: str | None = None,
            expected_subject: str | None = None,
            start_datetime: str = "",
            duration_minutes: int = 30,
        ) -> str | None:
            return "001" if self.exist_appointment else None

    return _DummyClient()


@pytest.fixture
def llm_instance():
    return LangChainFactory.create_llm_from_info(
        LlmInfo(
            type=LangChainAdapterType.OpenAI,
            model="gpt-4.1",
            timeout=50,
            temperature=0.5,
            api_key=os.getenv("OPENAI_API_KEY"),
        )
    )


@pytest.fixture
def similarity_evaluator():
    return SimilarityEvaluator()
