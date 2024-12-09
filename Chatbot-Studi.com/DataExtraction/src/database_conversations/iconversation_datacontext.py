from abc import ABC, abstractmethod
from uuid import UUID
from contextlib import AbstractAsyncContextManager
from sqlalchemy.ext.asyncio import AsyncSession
from contextlib import asynccontextmanager

class IConversationDataContext(ABC):
    @abstractmethod
    def create_database(self, db_path: str) -> None:
        pass

    @abstractmethod
    @asynccontextmanager
    async def get_session_async(self) -> AbstractAsyncContextManager[AsyncSession]:
        pass

    @abstractmethod
    async def add_conversation_async(self, user_name: str, conversation_entity: any) -> UUID:
        pass

    @abstractmethod
    async def get_conversation_by_id_async(self, conversation_id: UUID) -> any:
        pass

    @abstractmethod
    async def get_all_conversations_async(self) -> list:
        pass

    @abstractmethod
    async def update_conversation_async(self, conversation_id: UUID, user_name: str = None, new_messages: list[dict] = None) -> None:
        pass

    @abstractmethod
    async def delete_conversation_async(self, conversation_id: UUID) -> None:
        pass

    @abstractmethod
    async def add_message_to_conversation_async(self, conversation_id: UUID, role: str, content: str, elapsed_seconds: int = 0) -> None:
        pass

    @abstractmethod
    async def update_message_async(self, message_id: int, new_role: str = None, new_content: str = None, new_elapsed_seconds: int = None) -> None:
        pass
