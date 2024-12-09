from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import joinedload
#
from database_conversations.conversation_datacontext import ConversationDataContext
from common_tools.models.conversation import Conversation, Message
from database_conversations.entities import ConversationEntity, MessageEntity
from database_conversations.converter import ConversationConverter

class ConversationRepository:

    def __init__(self):
        self.data_context = ConversationDataContext()

    async def create_new_conversation_async(self, conversation: Conversation) -> bool:
        """Create a new conversation."""
        if await self.does_conversation_exists_async(conversation.id):
            raise ValueError(f"Conversation with ID {conversation.id} already exists in database.")
        try:
            conversation_entity = ConversationConverter.convert_conversation_model_to_entity(conversation)
            async with self.data_context.get_session_async() as session:
                session.add(conversation_entity)
            if not await self.does_conversation_exists_async(conversation.id):
                raise ValueError(f"Failed to retrieve created conversation with Id: {conversation.id}.")
            return True
        except Exception as e:
            print(f"Failed to create conversation: {e}")
            return False

    async def get_conversation_by_id_async(self, conversation_id: UUID) -> Optional[Conversation]:
        """Retrieve a conversation by its ID."""
        try:
            conversation_entity = await self._get_conversation_entity_by_id_async(conversation_id)
            if conversation_entity: 
                return ConversationConverter.convert_conversation_entity_to_model(conversation_entity)
            else:
                return None
        except Exception as e:
            print(f"Failed to retrieve conversation: {e}")
            return None
        
    async def _get_conversation_entity_by_id_async(self, conversation_id: UUID) -> Optional[ConversationEntity]:
        async with self.data_context.get_session_async() as session:
            result = await session.execute(
                select(ConversationEntity)
                #.options(joinedload(ConversationEntity.messages)) # Useless as messages are setup to be join loaded by default
                .where(ConversationEntity.id == conversation_id)
            )
            return result.scalars().first()


    async def does_conversation_exists_async(self, conversation_id: UUID) -> bool:
        """Check if a conversation with the given ID exists."""
        try:
            async with self.data_context.get_session_async() as session:
                result = await session.execute(
                    select(ConversationEntity.id)
                    .where(ConversationEntity.id == conversation_id)
                )
                return result.scalars().first() is not None
        except Exception as e:
            print(f"Failed to check conversation existence: {e}")
            return False

    async def add_message_to_conversation_async(self, conversation_id: UUID, message: Message) -> bool:
        """Add a message to an existing conversation."""
        try:
            async with self.data_context.get_session_async() as session:
                conversation_entity = await self._get_conversation_entity_by_id_async(conversation_id)
                if not conversation_entity: 
                    raise ValueError(f"Conversation with ID {conversation_id} not found in database.")
                
                new_message_entity = ConversationConverter.convert_message_model_to_entity(message)
                conversation_entity.messages.append(new_message_entity)

                session.add(conversation_entity)
            return True
        except Exception as e:
            print(f"Failed to add message to conversation: {e}")
            return False