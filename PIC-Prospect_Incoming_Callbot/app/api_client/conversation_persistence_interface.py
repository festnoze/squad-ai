from abc import ABC, abstractmethod
from uuid import UUID
from typing import Any, Dict
from api_client.request_models.user_request_model import UserRequestModel
from api_client.request_models.conversation_request_model import ConversationRequestModel
from database.models.user import User
from database.models.conversation import Conversation

class ConversationPersistenceInterface(ABC):
    
    NoneUuid: str = "00000000-0000-0000-0000-000000000000"
    
    @abstractmethod
    async def create_or_retrieve_user_async(self, user_request_model: UserRequestModel, timeout: int = 10) -> UUID:
        """Create or retrieve a user.
        
        Args:
            user_request_model: The user request model containing user information
            timeout: Request timeout in seconds (default: 10)
            
        Returns:
            UUID of the created or retrieved user
        """
        pass

    @abstractmethod
    async def create_new_conversation_async(self, conversation_request_model: ConversationRequestModel, timeout: int = 10) -> UUID:
        """Create a new conversation.
        
        Args:
            conversation_request_model: The conversation request model containing conversation data
            timeout: Request timeout in seconds (default: 10)
            
        Returns:
            UUID of the created conversation
        """
        pass

    @abstractmethod
    async def get_user_last_conversation_async(self, user_id: UUID, timeout: int = 10) -> dict:
        """Get the last conversation for a user.
        
        Args:
            user_id: The UUID of the user to get the last conversation for
            timeout: Request timeout in seconds (default: 10)
            
        Returns:
            messages of the last conversation
        """
        pass

    @abstractmethod
    async def add_ai_message_to_conversation_async(self, conversation_id: str, new_message: str, timeout: int = 10) -> dict:
        """Add an external AI message to a conversation.
        
        Args:
            conversation_id: The ID of the conversation to add the message to
            new_message: The message content to add to the conversation
            timeout: Request timeout in seconds (default: 10)
            
        Returns:
            Dictionary containing the response from adding the message
        """
        pass