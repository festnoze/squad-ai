from uuid import UUID

from api_client.conversation_persistence_interface import ConversationPersistenceInterface
from api_client.request_models.conversation_request_model import ConversationRequestModel
from api_client.request_models.user_request_model import UserRequestModel

from database.models.conversation import Conversation
from database.models.message import Message
from database.models.user import User


class QuotaOverloadException(Exception):
    pass


class ConversationPersistenceServiceFake(ConversationPersistenceInterface):
    def __init__(self):
        pass

    async def create_or_retrieve_user_async(self, user_request_model: UserRequestModel, timeout: int = 10) -> UUID:
        return UUID(ConversationPersistenceInterface.NoneUuid)

    async def create_new_conversation_async(
        self, conversation_request_model: ConversationRequestModel, timeout: int = 10
    ) -> UUID:
        return UUID(ConversationPersistenceInterface.NoneUuid)

    async def get_user_last_conversation_async(self, user_id: UUID, timeout: int = 10) -> dict:
        return {"conversation_id": None, "user_id": None, "message_count": 0}

    async def add_message_to_user_last_conversation_or_create_one_async(
        self, user_id: UUID, new_message: str
    ) -> Conversation:
        return Conversation(
            id=UUID(ConversationPersistenceInterface.NoneUuid),
            user=User(id=user_id),
            messages=[Message(role="user", content=new_message)],
        )

    async def add_message_to_conversation_async(
        self, conversation_id: str, new_message_content: str, role: str = "assistant", timeout: int = 10
    ) -> dict | None:
        conversation_uuid = UUID(conversation_id)
        return {"conversation_id": str(conversation_uuid), "user_id": None, "message_count": 1, "created_at": None}

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
        """Fake implementation - does nothing."""
        return True
