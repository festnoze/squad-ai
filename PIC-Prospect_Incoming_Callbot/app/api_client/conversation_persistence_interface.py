from abc import ABC, abstractmethod
from uuid import UUID

from api_client.request_models.conversation_request_model import ConversationRequestModel
from api_client.request_models.user_request_model import UserRequestModel

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
    async def create_new_conversation_async(
        self, conversation_request_model: ConversationRequestModel, timeout: int = 10
    ) -> UUID:
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
    async def add_message_to_user_last_conversation_or_create_one_async(
        self, user_id: UUID, new_message: str
    ) -> Conversation:
        """Add a user message to the user's last conversation or create a new one.

        Args:
            user_id: The UUID of the user to add the message to
            new_message: The message content to add to the conversation

        Returns:
            Conversation object containing the added message
        """
        pass

    @abstractmethod
    async def add_message_to_conversation_async(
        self, conversation_id: str, new_message_content: str, role: str = "assistant", timeout: int = 10
    ) -> dict | None:
        """Add an external AI message to a conversation.

        Args:
            conversation_id: The ID of the conversation to add the message to
            new_message: The message content to add to the conversation
            role: The role of the message (default: "assistant")
            timeout: Request timeout in seconds (default: 10)

        Returns:
            Dictionary containing the response from adding the message
        """
        pass

    @abstractmethod
    async def add_llm_operation_async(
        self,
        operation_type_name: str,
        provider: str,
        model: str,
        tokens_or_duration: float,
        price_per_unit: float,
        cost_usd: float,
        conversation_id: UUID | None = None,
        message_id: UUID | None = None,
        stream_id: str | None = None,
        call_sid: str | None = None,
        phone_number: str | None = None,
    ) -> bool:
        """Add a new LLM operation (STT, TTS, etc.) to track costs.

        Args:
            operation_type_name: Type of operation ("STT", "TTS", etc.)
            provider: Provider name (e.g., "google", "openai")
            model: Model name used
            tokens_or_duration: Number of tokens/characters or duration in seconds
            price_per_unit: Price per unit in USD
            cost_usd: Total cost in USD
            conversation_id: Optional conversation ID
            message_id: Optional message ID
            stream_id: Optional stream ID for tracking
            call_sid: Optional Twilio call SID
            phone_number: Optional phone number

        Returns:
            True if operation was added successfully, False otherwise
        """
        pass
