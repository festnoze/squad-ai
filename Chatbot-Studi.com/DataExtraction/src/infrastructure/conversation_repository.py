from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import UUID
from common_tools.database.generic_datacontext import GenericDataContext
from common_tools.models.conversation import Conversation, Message
from common_tools.models.device_info import DeviceInfo
from src.database_conversations.entities import Base, ConversationEntity, MessageEntity, UserEntity, DeviceInfoEntity
from src.database_conversations.conversation_converters import ConversationConverters

class ConversationRepository:
    def __init__(self, db_path_or_url='database_conversations/conversation_database.db'):
        self.data_context = GenericDataContext(Base, db_path_or_url)

    async def create_new_conversation_empty_async(self, user_id:UUID) -> Optional[Conversation]:
        try:
            user_entity: UserEntity = await self.data_context.get_entity_by_id_async(UserEntity, user_id)
            conversation_entity = ConversationEntity(user_id= user_entity.id, user = user_entity, messages=[])
            conversation_entity = await self.data_context.add_entity_async(conversation_entity)
            return ConversationConverters.convert_conversation_entity_to_model(conversation_entity)
        
        except Exception as e:
            print(f"Failed to create conversation: {e}")
            return None
    
    async def add_message_to_existing_conversation_async(self, conversation_id: UUID, message: Message) -> bool:
        try:
            if not await self.does_exist_conversation_by_id_async(conversation_id):
                raise ValueError(f"Conversation with id: {conversation_id} does not exist.")
            new_message_entity = ConversationConverters.convert_message_model_to_entity(message, conversation_id)
            res = await self.data_context.add_entity_async(new_message_entity)
            return True
        except ValueError:
            raise
        except Exception as e:
            print(f"Failed to add message to conversation: {e}")
            return False
    
    async def does_exist_conversation_by_id_async(self, conversation_id: Optional[UUID]) -> bool:
        if conversation_id is None: 
            return False
        return await self.data_context.does_exist_entity_by_id_async(ConversationEntity, conversation_id)
            
    async def get_conversation_by_id_async(self, conversation_id: UUID, fails_if_not_found = True) -> Optional[Conversation]:
        conversation_entity = await self.data_context.get_entity_by_id_async(
                                            entity_class= ConversationEntity,
                                            entity_id= conversation_id,
                                            #to_join_list = [ConversationEntity.user, ConversationEntity.messages], 
                                            fails_if_not_found= fails_if_not_found)
        return ConversationConverters.convert_conversation_entity_to_model(conversation_entity)
    
    async def get_all_user_conversations_async(self, user_id: UUID) -> list[Conversation]:
        try:
            conversation_entities = await self.data_context.get_all_entities_async(
                entity_class=ConversationEntity,
                filters=[ConversationEntity.user_id == user_id]
            )
            return [ConversationConverters.convert_conversation_entity_to_model(entity) for entity in conversation_entities]
        except Exception as e:
            print(f"Failed to retrieve conversations for user id {user_id}: {e}")
            return []

    async def get_recent_conversations_count_by_user_id_async(self, user_id: UUID, during_last_hours: int = 24) -> int:
        try:
            limit_datetime = datetime.now(timezone.utc) - timedelta(hours=during_last_hours)
            recent_conversation_count = await self.data_context.count_entities_async(
                entity_class=ConversationEntity,
                filters=[
                    ConversationEntity.user_id == user_id,
                    ConversationEntity.created_at >= limit_datetime
                ]
            )
            return recent_conversation_count
        
        except Exception as e:
            print(f"Failed to count recent conversations for user id {user_id}: {e}")
            return 0