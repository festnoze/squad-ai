from typing import Optional
from uuid import UUID
#
from src.database_conversations.entities import Base, UserEntity
from src.database_conversations.conversation_converters import ConversationConverters
#
from common_tools.database.generic_datacontext import GenericDataContext
from common_tools.models.conversation import User

class UserRepository:
    def __init__(self, db_path_or_url='database_conversations/conversation_database.db'):
        self.data_context = GenericDataContext(Base, db_path_or_url)

    async def create_new_user_async(self, user: User) -> UUID:
        if await self.does_exist_user_async(user):
            raise ValueError(f"Cannot create user as the id: {user.id} already exists.")
        try:
            user_entity = ConversationConverters.convert_user_model_to_entity(user)
            await self.data_context.add_entity_async(user_entity)
            return user_entity.id
        except Exception as e:
            print(f"Failed to create user: {e}")
            raise e

    async def get_user_by_id_async(self, user_id: UUID) -> Optional[User]:
        user_entity = await self.data_context.get_entity_by_id_async(UserEntity, user_id)
        return ConversationConverters.convert_user_entity_to_model(user_entity)

    async def does_exist_user_async(self, user: User) -> bool:
        user_entity = ConversationConverters.convert_user_model_to_entity(user)
        if user_entity.id is None and user_entity.ip is None: 
            return False
        
        if await self.data_context.does_exist_entity_by_id_async(UserEntity, user_entity.id):
            return True
        
        if user_entity.ip:
            user_ip = await self.data_context.get_first_entity_async(UserEntity, 
                                                    filters=[UserEntity.ip == user_entity.ip], 
                                                    selected_columns=[UserEntity.ip], 
                                                    fails_if_not_found=False)
            return user_ip is not None
        return False
    
    async def get_user_if_exists_async(self, user: User) -> User:
        user_entity = ConversationConverters.convert_user_model_to_entity(user)
        if user_entity.id is None and user_entity.ip is None: 
            return None
        
        if await self.data_context.does_exist_entity_by_id_async(UserEntity, user_entity.id):
            return user
        
        if user_entity.ip:
            user_id = await self.data_context.get_first_entity_async(UserEntity, 
                                                filters=[UserEntity.ip == user_entity.ip], 
                                                selected_columns=[UserEntity.id],
                                                fails_if_not_found=False)
            if not user_id: return None
            return await self.get_user_by_id_async(user_id)
        return False

    async def update_user_async(self, user: User) -> UUID:
        """Update user details."""
        user_entity = ConversationConverters.convert_user_model_to_entity(user)
        if not await self.does_exist_user_async(user_entity):
            raise ValueError(f"User with id: {user_entity.id} or IP: {user_entity.ip} does not exist.")
        try:
            await self.data_context.update_entity_async(
                                            UserEntity, 
                                            user_entity.id, 
                                            name = user_entity.name,
                                            ip = user_entity.ip,
                                            device_info = user_entity.device_info)
            return user_entity.id
        except Exception as e:
            print(f"Failed to update user: {e}")
            raise e
        
    async def create_or_update_user_async(self, user: User) -> UUID:
        if await self.does_exist_user_async(user):
            user = await self.get_user_if_exists_async(user) # Allow getting the user by its IP (with the correct id)
            user_id = await self.update_user_async(user)
        else:            
            user_id = await self.create_new_user_async(user)
        return user_id