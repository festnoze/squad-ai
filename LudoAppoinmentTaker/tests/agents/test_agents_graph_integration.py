import pytest
from unittest.mock import patch, MagicMock, AsyncMock
import asyncio
from app.agents.agents_graph import AgentsGraph
from app.agents.phone_conversation_state_model import PhoneConversationState
from app.managers.outgoing_manager import OutgoingManager
from app.api_client.studi_rag_inference_api_client import StudiRAGInferenceApiClient
from app.api_client.salesforce_api_client_interface import SalesforceApiClientInterface
from app.agents.calendar_agent import CalendarAgent

@pytest.mark.asyncio
class TestAgentsGraphIntegration:
    @pytest.mark.asyncio
    async def test_graph_init_conversation_and_welcome_message(self, agents_graph_mockings):
        """Test that without user input, we get a welcome message and conversation_id is set."""
        # Arrange
        # Create the graph with mocked dependencies but use the real graph implementation
        agents_graph = AgentsGraph(
            outgoing_manager=agents_graph_mockings["outgoing_manager"],
            studi_rag_client=agents_graph_mockings["studi_rag_client"],
            salesforce_client=agents_graph_mockings["salesforce_client"],
            call_sid=agents_graph_mockings["call_sid"]
        ).graph

        initial_state: PhoneConversationState = PhoneConversationState(
            call_sid=agents_graph_mockings["call_sid"],
            caller_phone=agents_graph_mockings["phone_number"],
            user_input="",
            history=[],
            agent_scratchpad={}
        )
    
        # Then invoke the graph with initial state to get the AI-generated welcome message
        updated_state: PhoneConversationState = await agents_graph.ainvoke(initial_state)
        
        # Assert
        assert "conversation_id" in updated_state["agent_scratchpad"]
        assert updated_state["agent_scratchpad"]["conversation_id"] == "39e81136-4525-4ea8-bd00-c22211110001"
        assert len(updated_state["history"]) >= 1

        welcome_text = """Bonjour, je suis Studia, l'assistante virtuelle de Studi.
        Merci de nous recontacter  Test User. 
        Je peux prendre un rendez-vous avec votre conseiller : Test Owner.
        Je peux aussi répondre à vos questions à propos de nos formations.
        Que souhaitez-vous faire ?"""

        first_history_msg = updated_state["history"][0][1].replace("\n\n", "\n")
        for awaited_line, received_line in zip(welcome_text.split("\n"), first_history_msg.split("\n")):
            assert awaited_line.strip() == received_line.strip()
        
        # Verify that the user and conversation creation methods were called
        agents_graph_mockings["studi_rag_client"].create_or_retrieve_user_async.assert_called_once()
        agents_graph_mockings["studi_rag_client"].create_new_conversation_async.assert_called_once()
        
        # Verify outgoing_manager was called with welcome message
        agents_graph_mockings["outgoing_manager"].enqueue_text.assert_called()
    
    @pytest.mark.asyncio
    async def test_query_response_about_courses(self, agents_graph_mockings):
        """Test that with a user input query about courses, the history contains the query and the answer."""
        # Arrange
        # Create the graph with mocked dependencies but use the real graph implementation
        agents_graph = AgentsGraph(
            outgoing_manager=agents_graph_mockings["outgoing_manager"],
            studi_rag_client=agents_graph_mockings["studi_rag_client"],
            salesforce_client=agents_graph_mockings["salesforce_client"],
            call_sid=agents_graph_mockings["call_sid"]
        ).graph
                        
        init_msg = "Welcome to Studi! How can I help you schedule an appointment today?"
        user_input = "Quels BTS en RH ?"
        # Create a state with conversation_id already set and user input about BTS in HR
        initial_state: PhoneConversationState = PhoneConversationState(
            call_sid=agents_graph_mockings["call_sid"],
            caller_phone=agents_graph_mockings["phone_number"],
            user_input=user_input,
            history=[("assistant", init_msg)],
            agent_scratchpad={"conversation_id": "39e81136-4525-4ea8-bd00-c22211110001"}
        )

        # Mock the add_external_ai_message_to_conversation method
        agents_graph_mockings["studi_rag_client"].add_external_ai_message_to_conversation = AsyncMock()
        
        # Set up the RAG client to return a response about BTS in HR
        bts_response = "Le BTS Gestion des Ressources Humaines (GRH) est une formation qui prépare aux métiers des ressources humaines. Cette formation de niveau Bac+2 vous permettra d'acquérir des compétences en gestion administrative du personnel, en recrutement, et en formation professionnelle."
        agents_graph_mockings["studi_rag_client"].query_rag_api.return_value = bts_response
        
         # Create an async generator that yields words from the response with a delay
        async def mock_stream_response(*args, **kwargs):
            words = bts_response.split()
            for i, word in enumerate(words):
                last_word = i == len(words) - 1
                await asyncio.sleep(0.01)  # 10ms delay
                yield word + (" " if not last_word else "")
        
        # Mock the rag_query_stream_async method to return the async generator
        # We need to return the generator function itself, not call it
        agents_graph_mockings["studi_rag_client"].rag_query_stream_async = mock_stream_response
        
        # Act
        updated_state: PhoneConversationState = await agents_graph.ainvoke(initial_state)
        
        # Assert
        assert len(updated_state["history"]) >= 3  # Welcome + user query + response
        assert updated_state["history"][-3][0] == "assistant"
        assert updated_state["history"][-3][1] == init_msg
        assert updated_state["history"][-2][0] == "user"
        assert updated_state["history"][-2][1] == user_input
        assert updated_state["history"][-1][0] == "assistant"
        assert updated_state["history"][-1][1] == bts_response

        # Verify outgoing_manager was called with the response
        agents_graph_mockings["outgoing_manager"].enqueue_text.assert_called()

    @pytest.mark.asyncio
    async def test_schedule_calendar_appointment(self, agents_graph_mockings):
        # Arrange

        # Create an instance of AgentsGraph with mocked dependencies
        agents = AgentsGraph(
            outgoing_manager=agents_graph_mockings["outgoing_manager"],
            studi_rag_client=agents_graph_mockings["studi_rag_client"],
            salesforce_client=agents_graph_mockings["salesforce_client"],
            call_sid=agents_graph_mockings["call_sid"]
        )
        
        # Add necessary attributes for streaming
        agents.graph.is_speaking = True
        agents.graph.start_time = 0
        agents.graph.rag_interrupt_flag = {"interrupted": False}
        
        # Set up mocks for calendar agent methods
        with patch.object(SalesforceApiClientInterface, 'get_scheduled_appointments_async', return_value=[{"date": "2025-4-2", "time": "15:00", "object": "test slot"}]) as mock_get_appointments, \
             patch.object(SalesforceApiClientInterface, 'schedule_new_appointment_async', return_value={}) as mock_schedule_new_appointment:
            
            # Set up initial state with a user query about scheduling an appointment
            init_msg = "Bonjour, je suis votre assistant Studi. Comment puis-je vous aider aujourd'hui ?"
            user_input = "Je voudrais prendre rendez-vous avec un conseiller pour discuter de mon inscription"
            
            # Create initial state                    
            initial_state: PhoneConversationState = PhoneConversationState(
                call_sid=agents_graph_mockings["call_sid"],
                caller_phone=agents_graph_mockings["phone_number"],
                user_input=user_input,
                history=[("assistant", init_msg)],
                agent_scratchpad={
                    "conversation_id": "39e81136-4525-4ea8-bd00-c22211110001", 
                    "sf_account_info": {
                        'attributes': {'type': 'Contact', 'url': '/services/data/v60.0/sobjects/Contact/003Aa00000jW2RBIA0'}, 
                        'Id': '003Aa00000jW2RBIA0', 
                        'Salutation': 'Mr.', 
                        'FirstName': 'jean', 
                        'LastName': 'dujardin', 
                        'Email': 'eti.mille@studi.fr', 
                        'Phone': None, 
                        'MobilePhone': '+33668422388', 
                        'Account': {'attributes': {'type': 'Account', 'url': '/services/data/v60.0/sobjects/Account/001Aa00001J8StVIAV'}, 'Id': '001Aa00001J8StVIAV', 'Name': 'jean dujardin'}, 
                        'Owner': {'attributes': {'type': 'User', 'url': '/services/data/v60.0/sobjects/User/005Aa00000K990ZIAR'}, 'Id': '005Aa00000K990ZIAR', 'Name': 'Etienne Millerioux'}
                    }
                }
            )

            agents.calendar_agent_instance.salesforce_api_client.get_scheduled_appointments_async = mock_get_appointments
            
            # Act
            updated_state: PhoneConversationState = await agents.graph.ainvoke(initial_state)
            
            # Assert
            assert len(updated_state["history"]) >= 3  # Welcome + user query + response
            assert updated_state["history"][-2][0] == "user"
            assert updated_state["history"][-2][1] == user_input
            assert updated_state["history"][-1][0] == "assistant"
            #assert updated_state["history"][-1][1] == "D'accord, je vais vous aider à prendre rendez-vous avec un conseiller."
        
            # Verify Salesforce client methods were called
            agents_graph_mockings["salesforce_client"].get_person_by_phone_async.assert_not_called()
            assert agents_graph_mockings["outgoing_manager"].enqueue_text.call_count >= 1
            
            # Verify called calendar agent 'tools'
            assert mock_get_appointments.call_count >= 1
            assert mock_schedule_new_appointment.call_count == 0


    @pytest.fixture
    def agents_graph_mockings(self):
        # Create mock dependencies
        mock_outgoing_manager = MagicMock(spec=OutgoingManager)
        mock_outgoing_manager.enqueue_text = AsyncMock()
        mock_outgoing_manager.queue_data = AsyncMock()
        
        # Create mock for StudiRAGInferenceApiClient with all necessary methods
        mock_studi_rag_client = MagicMock(spec=StudiRAGInferenceApiClient)
        mock_studi_rag_client.query_rag_api = AsyncMock()
        mock_studi_rag_client.query_rag_api.return_value = "This is a mock RAG response about BTS programs."
        
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
        
        # Create mock for SalesforceApiClientInterface with all necessary methods
        mock_salesforce_client = MagicMock(spec=SalesforceApiClientInterface)
        
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