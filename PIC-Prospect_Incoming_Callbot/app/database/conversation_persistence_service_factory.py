from api_client.conversation_persistence_interface import ConversationPersistenceInterface
from api_client.studi_rag_inference_api_client import StudiRAGInferenceApiClient
from utils.envvar import EnvHelper

from database.conversation_persistence_local_service import ConversationPersistenceLocalService
from database.conversation_persistence_service_fake import ConversationPersistenceServiceFake


class ConversationPersistenceServiceFactory:
    @staticmethod
    def create_conversation_persistence_service(conversation_persistence_type: str | None = None, available_actions: list[str] | None = None) -> ConversationPersistenceInterface:
        """Factory method to create service for conversation persistence based on configuration"""

        # Use provided values or get from environment
        persistence_type = conversation_persistence_type or EnvHelper.get_conversation_persistence_type()
        actions = available_actions or EnvHelper.get_available_actions()

        # Check for inconsistent states
        if "ask_rag" not in actions:
            assert persistence_type != "studi_rag", f"when 'ask_rag' action is not available, conversation persistence type cannot be 'studi_rag' but is: {persistence_type}"

        # Create and return appropriate service instance
        if persistence_type == "local":
            return ConversationPersistenceLocalService()
        elif persistence_type == "studi_rag":
            return StudiRAGInferenceApiClient()
        else:
            return ConversationPersistenceServiceFake()
