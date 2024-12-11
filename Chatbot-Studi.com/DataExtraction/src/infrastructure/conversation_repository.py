from typing import Optional
from uuid import UUID
from common_tools.database.generic_datacontext import GenericDataContext
from common_tools.models.conversation import Conversation, Message
from src.database_conversations.entities import Base, ConversationEntity, MessageEntity
from src.database_conversations.conversation_converters import ConversationConverters

class ConversationRepository:
    def __init__(self, db_path_or_url='database_conversations/conversation_database.db'):
        self.data_context = GenericDataContext(Base, db_path_or_url)

    async def create_new_conversation_async(self, conversation: Conversation) -> bool:
        if await self.does_exist_conversation_by_id_async(conversation.id):
            raise ValueError(f"Failed to create conversation as the id: {conversation.id} already exists.")
        try:            
            conversation_entity = ConversationConverters.convert_conversation_model_to_entity(conversation)
            await self.data_context.add_entity_async(conversation_entity)
            return True
        except Exception as e:
            print(f"Failed to create conversation: {e}")
            return False

    async def get_conversation_by_id_async(self, conversation_id: UUID, fails_if_not_found = True) -> Optional[Conversation]:
        conversation_entity = await self.data_context.get_entity_by_id_async(
                                            entity_class= ConversationEntity,
                                            entity_id= conversation_id,
                                            #to_join_list = [ConversationEntity.user, ConversationEntity.messages], 
                                            fails_if_not_found= fails_if_not_found)
        return ConversationConverters.convert_conversation_entity_to_model(conversation_entity)

    async def does_exist_conversation_by_id_async(self, conversation_id: Optional[UUID]) -> bool:
        if conversation_id is None: 
            return False
        return await self.data_context.does_exist_entity_by_id_async(ConversationEntity, conversation_id)

    async def add_message_to_conversation_async(self, conversation_id: UUID, message: Message) -> bool:
        if not await self.does_exist_conversation_by_id_async(conversation_id):
            raise ValueError(f"Conversation with id: {conversation_id} does not exist.")
        try:
            new_message_entity = ConversationConverters.convert_message_model_to_entity(message, conversation_id)
            new_message_entity.conversation = await self.get_conversation_by_id_async(conversation_id)
            await self.data_context.add_entity_async(new_message_entity)
            return True
        except Exception as e:
            print(f"Failed to add message to conversation: {e}")
            return False