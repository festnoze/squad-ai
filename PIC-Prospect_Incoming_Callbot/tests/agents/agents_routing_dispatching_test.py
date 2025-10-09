from unittest.mock import AsyncMock, MagicMock

import pytest
from routers.callbot_router import change_env_var_values

from app.agents.agents_graph import AgentsGraph
from app.api_client.salesforce_user_client_interface import SalesforceUserClientInterface
from app.api_client.studi_rag_inference_api_client import StudiRAGInferenceApiClient
from app.managers.outgoing_manager import OutgoingManager


@pytest.mark.parametrize("awaited_dispatch, user_input, chat_history", [

    # Direct request from the user query
    ("training_course_query", "Quels BTS en ressources humaines ?", []),
    ("schedule_calendar_appointment", "Je souhaite prendre rendez-vous", []),
    ("others", "Quelle est la météo ?", []), # Hors-sujet
    ("greetings", "Salut", []), # Greeting
    ("greetings", "Excuse moi", []), # Interupting
    ("non-sense|greetings", "Je t'interomps", []), # Interupting
    ("non-sense", "je souhaiterais connaitre", []), # Incomplete query
    ("non-sense", "Elle formation vrai", []), # query with transcription error
    ("non-sense", "", []), # Empty query

    # Ambiguous request from the user query needing history to be dispatched to the right agent
    ("training_course_query", "oui", [("user", "Quels BTS en ressources humaines ?"), ("assistant", "Il existe deux BTS en ressources humaines : le BTS SIO et le BTS RNCP. souhaitez-vous plus d'informations à leur sujet ?")]),
    ("schedule_calendar_appointment", "oui", [("user", "Je souhaite prendre rendez-vous"), ("assistant", "Bien sûr, seriez-vous disponible demain matin ?")]),
    ("schedule_calendar_appointment", "Je souhaite prendre rendez-vous", [("user", "Quels BTS en ressources humaines ?"), ("assistant", "Il existe deux BTS en ressources humaines : le BTS SIO et le BTS RNCP. souhaitez-vous plus d'informations à leur sujet ?")]),
])
async def test_agents_dispatching(agents_graph_mockings, user_input: str, chat_history: list[tuple[str, str]], awaited_dispatch: str):
    """Test that the agents graph dispatch to the targeted agent."""

    # Arrange
    # Set available actions to schedule_calendar_appointment and ask rag
    await change_env_var_values({"AVAILABLE_ACTIONS": "schedule_appointement, ask_rag"})

    # Create an instance of AgentsGraph with mocked dependencies
    agents = AgentsGraph(
        outgoing_manager=agents_graph_mockings["outgoing_manager"],
        call_sid=agents_graph_mockings["call_sid"],
        salesforce_client=agents_graph_mockings["salesforce_client"],
        conversation_persistence=agents_graph_mockings["studi_rag_client"],
        rag_query_service= agents_graph_mockings["studi_rag_client"]
    )

    # Add necessary attributes for streaming
    agents.graph.is_speaking = True
    agents.graph.start_time = 0
    agents.graph.rag_interrupt_flag = {"interrupted": False}

    # Act
    result= await agents.analyse_user_input_for_dispatch_async(agents.calendar_classifier_llm, user_input, chat_history)
    # Assert
    if '|' in awaited_dispatch:
        assert result in awaited_dispatch.split('|')
    else:
        assert result == awaited_dispatch


### Fixture ###

@pytest.fixture
def agents_graph_mockings():
    # Create mock dependencies
    mock_outgoing_manager = MagicMock(spec=OutgoingManager)
    mock_outgoing_manager.enqueue_text = AsyncMock()
    mock_outgoing_manager.queue_data = AsyncMock()
    # Create mock for StudiRAGInferenceApiClient with all necessary methods
    mock_studi_rag_client = MagicMock(spec=StudiRAGInferenceApiClient)
    mock_studi_rag_client.rag_query_stream_async = AsyncMock()
    mock_studi_rag_client.rag_query_stream_async.return_value = "This is a mock RAG response about BTS programs."

    # Mock user creation/retrieval
    mock_studi_rag_client.create_or_retrieve_user_async  = AsyncMock()
    mock_studi_rag_client.create_or_retrieve_user_async .return_value = {
        "id": "39e81136-4525-4ea8-bd00-c22211110000",
        "user_name": "Test User",
        "created_at": "2025-06-01T00:00:00Z"
    }

    # Mock conversation creation
    mock_studi_rag_client.create_new_conversation_async = AsyncMock()
    mock_studi_rag_client.create_new_conversation_async.return_value = {
        "id": "39e81136-4525-4ea8-bd00-c22211110001",
        "user_id": "39e81136-4525-4ea8-bd00-c22211110000",
        "created_at": "2025-06-02T00:00:00Z"
    }

    # Mock adding messages to conversation
    mock_studi_rag_client.add_external_ai_message_to_conversation = AsyncMock()
    mock_studi_rag_client.add_external_ai_message_to_conversation.return_value = {
        "id": "39e81136-4525-4ea8-bd00-c22211110002",
        "conversation_id": "39e81136-4525-4ea8-bd00-c22211110001",
        "user_id": "39e81136-4525-4ea8-bd00-c22211110000",
        "content": "Message content",
        "created_at": "2025-06-02T00:10:00Z",
        "role": "assistant",
        "messages": [
            {
                "role": "assistant",
                "content": "Welcome message"
            }
        ]
    }

    # Create mock for SalesforceUserClientInterface with all necessary methods
    mock_salesforce_client = MagicMock(spec=SalesforceUserClientInterface)

    # Mock get_person_by_phone_async method
    mock_salesforce_client.get_person_by_phone_async = AsyncMock()
    mock_salesforce_client.get_person_by_phone_async.return_value = {
        'type': 'Lead',
        'data': {
            'Id': '00Q3X00001Gz7XYUAZ',
            'FirstName': 'Test',
            'LastName': 'User',
            'Email': 'test.user@example.com',
            'Phone': '+33123456789',
            'MobilePhone': '+33123456789',
            'Company': 'Test Company',
            'Status': 'Open',
            'Owner': {
                'Id': '0053X00000GzTYQA3',
                'Name': 'Test Owner'
            },
            'IsConverted': False
        }
    }

    # Mock get_leads_by_details_async method
    mock_salesforce_client.get_leads_by_details_async = AsyncMock()
    mock_salesforce_client.get_leads_by_details_async.return_value = [
        {
            'Id': '00Q3X00001Gz7XYUAZ',
            'FirstName': 'Test',
            'LastName': 'User',
            'Email': 'test.user@example.com',
            'Company': 'Test Company',
            'Status': 'Open',
            'Owner': {
                'Name': 'Test Owner'
            },
            'CreatedDate': '2025-06-01T00:00:00.000Z'
        }
    ]

    call_sid = "test_call_sid"
    phone_number = "+33123456789"

    return {
        "outgoing_manager": mock_outgoing_manager,
        "studi_rag_client": mock_studi_rag_client,
        "salesforce_client": mock_salesforce_client,
        "call_sid": call_sid,
        "phone_number": phone_number
    }
