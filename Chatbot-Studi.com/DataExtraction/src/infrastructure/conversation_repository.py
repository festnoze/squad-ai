from typing import Optional
from uuid import UUID

from sqlalchemy import select
#
from database_conversations.datacontext import DataContextConversations
from common_tools.models.conversation import Conversation, Message
from database_conversations.models import ConversationEntity, MessageEntity
from database_conversations.converter import ConversationConverter

class ConversationRepository:

    def __init__(self):
        self.data_context = DataContextConversations()

    async def save_user_conversation_async(self, conversation: Conversation) -> bool:
        """Save a user conversation. Create or update depending on existence."""
        if await self.does_conversation_exists_async(conversation.id):
            return await self.update_existing_conversation_async(conversation)
        else:
            return await self.create_new_conversation_async(conversation)

    async def create_new_conversation_async(self, conversation: Conversation) -> bool:
        """Create a new conversation."""
        if await self.does_conversation_exists_async(conversation.id):
            raise ValueError(f"Conversation with ID {conversation.id} already exists in database.")
        try:
            conversation_entity = ConversationConverter.convert_conversation_model_to_entity(conversation)
            async with self.data_context.get_session_async() as session:
                session.add(conversation_entity)
            return True
        except Exception as e:
            print(f"Failed to create conversation: {e}")
            return False

    async def update_existing_conversation_async(self, conversation: Conversation) -> bool:
        """Update an existing conversation."""
        if not await self.does_conversation_exists_async(conversation.id):
            raise ValueError(f"Conversation with ID {conversation.id} not found in database.")
        try:
            async with self.data_context.get_session_async() as session:
                conversation_entity = await session.get(ConversationEntity, conversation.id)
                if not conversation_entity:
                    raise ValueError(f"Conversation with ID {conversation.id} not found.")
                # Update conversation's messages only
                conversation_entity.messages = [
                    ConversationConverter.convert_message_model_to_entity(message) for message in conversation.messages
                ]
                session.add(conversation_entity)
            return True
        except Exception as e:
            print(f"Failed to update conversation: {e}")
            return False

    async def get_conversation_by_id_async(self, conversation_id: UUID) -> Optional[Conversation]:
        """Retrieve a conversation by its ID."""
        try:
            async with self.data_context.get_session_async() as session:
                conversation_entity = await session.get(ConversationEntity, conversation_id)
                if conversation_entity: 
                    return ConversationConverter.convert_conversation_entity_to_model(conversation_entity)
                else:
                    return None
        except Exception as e:
            print(f"Failed to retrieve conversation: {e}")
            return None

    async def does_conversation_exists_async(self, conversation_id: UUID) -> bool:
        """Check if a conversation with the given ID exists."""
        try:
            async with self.data_context.get_session_async() as session:
                result = await session.execute(
                    select(ConversationEntity).where(ConversationEntity.id == conversation_id)
                )
                return result.scalars().first() is not None
        except Exception as e:
            print(f"Failed to check conversation existence: {e}")
            return False

    async def add_message_to_conversation_async(self, conversation_id: UUID, message: Message) -> bool:
        """Add a message to an existing conversation."""
        try:
            async with self.data_context.get_session_async() as session:
                conversation_entity = await self.get_conversation_by_id_async(conversation_id)
                if not conversation_entity: raise ValueError(f"Conversation with ID {conversation_id} not found in database.")
                message_entity = ConversationConverter.convert_message_model_to_entity(message)

                conversation_entity.messages.append(message_entity)
                session.add(conversation_entity)
            return True
        except Exception as e:
            print(f"Failed to add message to conversation: {e}")
            return False