import os
import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch
#
from app.agents.calendar_agent import CalendarAgent
#
from llms.langchain_factory import LangChainFactory
from llms.llm_info import LlmInfo
from llms.langchain_adapter_type import LangChainAdapterType



@pytest.mark.parametrize(
    "user_input, chat_history, expected_category, expected_answer, await_exact_match",
    [
        # ===== SCENARIO A: STANDARD FLOW - ACCEPT FIRST PROPOSAL =====
        # A1: Initial contact - user wants to book an appointment
        (
            "Je voudrais prendre rendez-vous", 
            [], 
            "Proposition de créneaux",
            "Je vous propose le créneau du jeudi 20 juin entre 14 heures et 15 heures. Si ce créneau vous convient, merci de me confirmer afin de finaliser sa réservation.",
            False # Semantic matching
        ),

        # A2: User confirms the appointment
        (
            "Oui, réserve le premier créneau.", 
            [
                ("human", "Je voudrais prendre rendez-vous"), 
                ("AI", "Je vous propose les créneaux suivants : le jeudi 20 juin, de 9 heures à 12 heures ou de 14 heures à 15 heures, ou le vendredi 21 juin, de 16 heures à 17 heures. Avez-vous une préférence ?")
            ],
            "Demande de confirmation du rendez-vous",
            "Parfait. Votre rendez-vous sera planifié le jeudi 20 juin à 9 heures. Merci de confirmer ce rendez-vous pour le valider.",
            True # Exact match
        ),
        
        # A3: User confirms the appointment
        (
            "Je confirme", 
            [
                ("human", "Je voudrais prendre rendez-vous"), 
                ("AI", "Je vous propose le créneaux du jeudi 20 juin à 14 heures. Si ce créneau vous convient, merci de me confirmer afin de finaliser sa réservation."),
                ("human", "Oui, ce créneau me convient parfaitement"),
                ("AI", "Veuillez confirmer le rendez-vous du jeudi 20 juin à 14 heures.")
            ],
            "Rendez-vous confirmé",
            "Votre rendez-vous est bien planifié pour le jeudi 20 juin à 14 heures. Merci et au revoir.",
            True # Exact match
        ),
        
        # ===== SCENARIO B: ALTERNATIVE FLOW - REQUEST DIFFERENT SLOT =====
        # B1: User asks for different availability
        (
            "Quelles sont vos autres disponibilités ?", 
            [
                ("human", "Je voudrais prendre rendez-vous"), 
                ("AI", "Je vous propose le créneaux du jeudi 20 juin à 14 heures. Si ce créneau vous convient, merci de me confirmer afin de finaliser sa réservation.")
            ],
            "Demande des disponibilités", 
            "Quels jours ou quelles heures de la journée vous conviendraient le mieux ?",
            True # Exact match
        ),
        
        # B2: User refuses, but proposes a specific time ("Je préfère vendredi à 10h")
        (
            "Je préfère vendredi à 10h", 
            [
                ("human", "Je voudrais prendre rendez-vous"), 
                ("AI", "Je vous propose le créneaux du jeudi 20 juin à 14 heures. Si ce créneau vous convient, merci de me confirmer afin de finaliser sa réservation."),
                ("human", "Quelles sont vos autres disponibilités ?"),
                ("AI", "Quels jours ou quelles heures de la journée vous conviendraient le mieux ?")
            ],
            "Demande de confirmation du rendez-vous", 
            "Parfait. Votre rendez-vous sera planifié le vendredi 21 juin à 10 heures. Merci de confirmer ce rendez-vous pour le valider.",
            True # Exact match
        ),
        
        # B3: User refuses, but specify its availability ("Non, je ne serais dispo qu'à partir de lundi prochain")
        (
            "Je ne serais dispo qu'à partir de lundi prochain", 
            [
                ("human", "Je voudrais prendre rendez-vous"), 
                ("AI", "Je vous propose le créneaux du jeudi 20 juin à 14 heures. Si ce créneau vous convient, merci de me confirmer afin de finaliser sa réservation."),
                ("human", "Quelles sont vos autres disponibilités ?"),
                ("AI", "Quels jours ou quelles heures de la journée vous conviendraient le mieux ?")
            ],
            "Proposition de créneaux", 
            "Je vous propose les créneaux suivants : le lundi 24 juin, de 9 heures à 12 heures ou de 13 heures à 18 heures, ou le mardi 25 juin, de 9 heures à 12 heures. Avez-vous une préférence ?",
            True # Exact match
        ),
        
        # B4: User confirms the new appointment
        (
            "Oui, je confirme ce rendez-vous", 
            [
                ("human", "Je voudrais prendre rendez-vous"), 
                ("AI", "Je vous propose le créneaux du jeudi 20 juin à 14 heures. Si ce créneau vous convient, merci de me confirmer afin de finaliser sa réservation."),
                ("human", "Quelles sont vos autres disponibilités ?"),
                ("AI", "Quels jours ou quelles heures de la journée vous conviendraient le mieux ?"),
                ("human", "Je préfère vendredi à 10h"),
                ("AI", "Veuillez confirmer le rendez-vous du vendredi 21 juin à 10 heures.")
            ],
            "Rendez-vous confirmé", 
            "Votre rendez-vous est bien planifié pour le vendredi 21 juin à 10 heures. Merci et au revoir.", 
            True # Exact match
        ),
        
        # ===== SCENARIO C: REJECTION FLOW - NO AVAILABILITY =====
        # C1: No availability in the requested timeframe
        (
            "Je voudrais prendre rendez-vous la semaine prochaine", 
            [], 
            "Proposition de créneaux", # Agent indicates no slots
            "Je suis désolé, aucun créneau n'est disponible entre le 24 juin 2025 et le 27 juin 2025. Souhaitez-vous élargir la recherche ?",
            False # Semantic match
        ),
        
        # C2: User asks to expand search
        (
            "Oui, pouvez-vous regarder la semaine d'après ?", 
            [
                ("human", "Je voudrais prendre rendez-vous la semaine prochaine"), 
                ("AI", "Je suis désolé, aucun créneau n'est disponible entre le 24 juin et le 28 juin. Souhaitez-vous élargir la recherche ?")
            ],
            "Proposition de créneaux", # Agent will propose new slots
            "Je vous propose le créneaux du lundi 30 juin entre 10 heures et 11 heures. Si ce créneau vous convient, merci de me confirmer afin de finaliser sa réservation.",
            False # Semantic match
        ),
        
        # ===== SCENARIO D: DIRECT SLOT REQUEST =====
        # D1: User directly requests a specific slot ("Je voudrais prendre rendez-vous jeudi à 15h")
        (
            "Je voudrais prendre rendez-vous jeudi à 15h", 
            [], 
            "Demande de confirmation du rendez-vous",
            "Parfait. Votre rendez-vous sera planifié le jeudi 13 juin à 15 heures. Merci de confirmer ce rendez-vous pour le valider.",
            True # Exact match
        ),
        
        # ===== SCENARIO E: UNAVAILABLE SLOT PROPOSED BY USER =====
        # E1: User proposes a slot that is not available ("Je voudrais prendre rendez-vous lundi prochain à 9h")
        (
            "Je voudrais prendre rendez-vous lundi prochain à 9h", 
            [], 
            "Demande de confirmation du rendez-vous", # Agent indicates slot is not available and proposes alternatives
            "Je suis désolé, ce créneau n'est pas disponible. Voici d'autres créneaux disponibles: le mardi 25 juin entre 14 heures et 16 heures, le mercredi 26 juin entre 10 heures et 12 heures. Lequel vous conviendrait ?",
            False # Semantic match
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
        #     True # Exact match
        # ),
        
        # ===== SCENARIO G: RESCHEDULING REQUEST =====
        # G1: User wants to reschedule ("En fait je préfère vendredi matin")
        (
            "En fait je préfère vendredi matin", 
            [
                ("human", "Je voudrais prendre rendez-vous"), 
                ("AI", "Je vous propose le créneaux du jeudi 20 juin à 14 heures. Si ce créneau vous convient, merci de me confirmer afin de finaliser sa réservation."),
                ("human", "Oui, ce créneau me convient parfaitement"),
                ("AI", "Veuillez confirmer le rendez-vous du jeudi 20 juin à 14 heures.")
            ],
            "Proposition de créneaux", # Agent should ask for new preferences
            "Je vous propose le créneau suivant : le vendredi 21 juin, de 9 heures à 12 heures. Avez-vous une préférence ?",
            True # Exact match
        )
    ]
)
async def test_calendar_agent_integration_classification_plus_outputed_answer(sf_client_mock, llm_instance, similarity_evaluator, user_input, chat_history, expected_category, expected_answer, await_exact_match):
    """
    Tests the complete workflow of the calendar agent through different scenarios.
    This test verifies that the agent responds appropriately based on the conversation context.
    
    Parameters:
        await_exact_match: If True, expects an exact match between expected_answer and actual_response.
                          If False, uses semantic similarity evaluation.
    """
    # Create the agent with mocked dependencies
    agent = CalendarAgent(llm_instance, sf_client_mock)
    CalendarAgent.now = datetime(2025, 6, 19)
    agent._set_user_info("test_user_id", "Test", "User", "test@example.com", "test_owner_id", "TestOwnerName")
    
    # First, ensure the agent classifies the user input correctly
    actual_category = await agent.categorize_for_dispatch_async(user_input, chat_history)
    assert actual_category == expected_category, (
        f"Expected category '{expected_category}', but got '{actual_category}' for input '{user_input}'.")

    # Then, verify the agent's full response
    actual_response = await agent.run_async(user_input, chat_history)

    if await_exact_match:
        assert actual_response == expected_answer, (
            f"Expected exact response:\n{expected_answer}\nGot:\n{actual_response}")
    else:
        is_similar = await similarity_evaluator.is_semantically_similar(expected_answer, actual_response)
        assert is_similar, (
            f"Expected a response semantically similar to:\n{expected_answer}\nGot:\n{actual_response}")



async def test_complete_conversation_exchange(sf_client_mock, llm_instance, similarity_evaluator):
    """
    Tests a complete conversation flow from initial contact to appointment confirmation.
    This test simulates a realistic conversation between a user and the calendar agent.
    """
    # Create the agent with mocked dependencies
    agent = CalendarAgent(llm_instance, sf_client_mock)
    CalendarAgent.now = datetime(2025, 6, 19)
    agent._set_user_info("test_user_id", "Test", "User", "test@example.com", "test_owner_id", "TestOwnerName")
    
    # Define the conversation flow with expected categories and responses
    conversation_flow = [
        # Step 1: User initiates conversation
        {
            "user_input": "Bonjour, je voudrais prendre rendez-vous avec mon conseiller",
            "category": "Proposition de créneaux",
            "expected_response": "Je vous propose le créneau du jeudi 20 juin entre 14 heures et 15 heures. Si ce créneau vous convient, merci de me confirmer afin de finaliser sa réservation.",
            "await_exact_match": False
        },
        # Step 2: User asks for different availabilities
        {
            "user_input": "Avez-vous d'autres créneaux disponibles ?",
            "category": "Demande des disponibilités",
            "expected_response": "Quels jours ou quelles heures de la journée vous conviendraient le mieux ?",
            "await_exact_match": True
        },
        # Step 3: User specifies a preference
        {
            "user_input": "Je préférerais vendredi après-midi",
            "category": "Proposition de créneaux",
            "expected_response": "Je vous propose le créneau du vendredi 21 juin entre 14 heures et 15 heures. Si ce créneau vous convient, merci de me confirmer afin de finaliser sa réservation.",
            "await_exact_match": False
        },
        # Step 4: User accepts the proposed time
        {
            "user_input": "Parfait, ça me convient",
            "category": "Demande de confirmation du rendez-vous",
            "expected_response": "Parfait. Votre rendez-vous sera planifié le vendredi 21 juin à 13 heures. Merci de confirmer ce rendez-vous pour le valider.",
            "await_exact_match": True
        },
        # Step 5: User confirms the appointment
        {
            "user_input": "Je confirme le rendez-vous",
            "category": "Rendez-vous confirmé",
            "expected_response": "Votre rendez-vous du vendredi 21 juin à 14 heures a bien été confirmé. Merci et à bientôt !",
            "await_exact_match": False
        }
    ]
    
    # Execute the conversation flow
    chat_history = []
    for step in conversation_flow:
        # Mock the categorize_for_dispatch_async method to return our predefined category for this step
        with patch.object(agent, 'categorize_for_dispatch_async', return_value=step["category"]):
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
        llm = LangChainFactory.create_llm_from_info(LlmInfo(type=LangChainAdapterType.OpenAI, model="gpt-4o-mini", timeout=50, temperature=0.5, api_key=os.getenv("OPENAI_API_KEY")))
        prompt = "Compare the following two responses for semantic similarity: \nResponse 1: {expected} \nResponse 2: {actual} \nReturn 'True' if they are semantically similar, 'False' otherwise."

        return llm.invoke(prompt.format(expected=expected, actual=actual))

@pytest.fixture
def sf_client_mock():
    class _DummyClient:
        async def get_scheduled_appointments_async(start_datetime=None, end_datetime=None, *args, **kwargs):
            # Check if the specific date range is requested
            if (
                str(start_datetime)[:10] == "2025-06-24" and str(end_datetime)[:10] == "2025-06-27"
            ):
                # Return 3 appointments, each 9 hours long, one per day
                appointments = []
                for day in range(3):
                    start = datetime(2025, 6, 24) + timedelta(days=day)
                    end = start + timedelta(hours=9)
                    appointments.append({
                        "id": f"appt_{day+1}",
                        "start_datetime": start,
                        "end_datetime": end,
                        "subject": f"Mock Appointment {day+1}",
                    })
                return appointments
            return []
        
        async def schedule_new_appointment_async(start_datetime: datetime, end_datetime: datetime, *args, **kwargs):
            return {"Id": "001"}
        
    return _DummyClient()

@pytest.fixture
def llm_instance():
    return LangChainFactory.create_llm_from_info(LlmInfo(type=LangChainAdapterType.OpenAI, model="gpt-4.1", timeout=50, temperature=0.5, api_key=os.getenv("OPENAI_API_KEY")))

@pytest.fixture
def similarity_evaluator():
    return SimilarityEvaluator()
