from typing import Optional
from uuid import UUID
#
from database_conversations.entities import Base, UserEntity, DeviceInfoEntity
from database_conversations.conversation_converters import ConversationConverters
#
from common_tools.database.generic_datacontext import GenericDataContext
from common_tools.models.conversation import User
from common_tools.models.device_info import DeviceInfo

class UserRepository:
    def __init__(self, db_path_or_url='database_conversations/conversation_database.db'):
        self.data_context = GenericDataContext(Base, db_path_or_url)

    async def get_all_users_async(self) -> list[User]:
        user_entities = await self.data_context.get_all_entities_async(UserEntity)
        return [ConversationConverters.convert_user_entity_to_model(user_entity) for user_entity in user_entities] 
    
    async def get_user_by_id_async(self, user_id: UUID) -> Optional[User]:
        user_entity = await self.data_context.get_entity_by_id_async(UserEntity, user_id)
        return ConversationConverters.convert_user_entity_to_model(user_entity)
    
    async def get_user_by_name_async(self, user_name: str) -> Optional[User]:
        user_entity = await self.data_context.get_first_entity_async(UserEntity, filters=[UserEntity.name == user_name])
        return ConversationConverters.convert_user_entity_to_model(user_entity)

    async def does_exist_user_async(self, user: User) -> bool:
        return await self.get_user_id_if_exists_async(user) is not None

    async def get_user_id_if_exists_async(self, user: User) -> Optional[UUID]:
        # Search user by id
        if user and user.id:
            if await self.data_context.does_exist_entity_by_id_async(UserEntity, user.id):
                return user.id
        
        # Search user by IP
        if user.device_info and isinstance(user.device_info, DeviceInfo) and user.device_info.ip:
            user_id_with_IP = await self.get_device_info_by_IP_async(user.device_info.ip, [DeviceInfoEntity.user_id])
            return user_id_with_IP
        
        # Search user by name & device info's platform
        if user.name and isinstance(user.device_info, DeviceInfo) and user.device_info and user.device_info.user_agent:
            user_entity = await self.data_context.get_first_entity_async(
                UserEntity,
                filters=[
                    UserEntity.name == user.name,
                    DeviceInfoEntity.platform == user.device_info.platform
                ],
                selected_columns=[UserEntity.id],
                fails_if_not_found=False
            )
            if user_entity:
                return user_entity.id
        
        return None
    
    async def get_device_info_by_IP_async(self, IP_to_look_up: str, selected_columns: Optional[list] = None) -> Optional[DeviceInfo]:
        if not IP_to_look_up: return None
        device_info = await self.data_context.get_first_entity_async(
                                                DeviceInfoEntity, 
                                                filters=[DeviceInfoEntity.ip == IP_to_look_up],
                                                selected_columns=selected_columns,
                                                fails_if_not_found=False)
        if selected_columns:
            return device_info
        else:
            return ConversationConverters.convert_device_info_entity_to_model(device_info)
    
    async def create_new_user_with_device_info_async(self, user: User) -> UUID:
        if await self.does_exist_user_async(user):
            raise ValueError(f"Cannot create user as a user with id: {user.id} already exists in database.")
        try:
            user_entity = ConversationConverters.convert_user_model_to_entity(user)
            device_info_entity = ConversationConverters.convert_device_info_model_to_entity(user.device_info)
            device_info_entity.user = user_entity
            user_entity, device_info_entity = await self.data_context.add_entities_async(user_entity, device_info_entity)
            return user_entity.id
        
        except Exception as e:
            print(f"Failed to create user: {e}")
            raise e
        
    async def update_user_async(self, user: User) -> UUID:
        """Update user details."""
        #user_entity = ConversationConverters.convert_user_model_to_entity(user)
        user_id_to_update = await self.get_user_id_if_exists_async(user)

        if not user_id_to_update:
            raise ValueError(f"User with id: {user.id} or IP: {user.device_info.ip if user.device_info else ''} does not exist.")
        try:
            user_entity: UserEntity = await self.data_context.get_entity_by_id_async(UserEntity, user_id_to_update)

            # Add new device info to user if device infos are different from the user's last one
            if (user.device_info and 
                (not any(user_entity.device_infos) or
                (user_entity.device_infos[-1].ip != user.device_info.ip 
                or user_entity.device_infos[-1].user_agent != user.device_info.user_agent
                or user_entity.device_infos[-1].platform != user.device_info.platform
                or user_entity.device_infos[-1].app_version != user.device_info.app_version
                or user_entity.device_infos[-1].os != user.device_info.os
                or user_entity.device_infos[-1].browser != user.device_info.browser
                or user_entity.device_infos[-1].is_mobile != user.device_info.is_mobile))):
                    new_device_info_entity = ConversationConverters.convert_device_info_model_to_entity(user.device_info)
                    new_device_info_entity.user_id = user_id_to_update
                    await self.data_context.add_entity_async(new_device_info_entity)
            
            # Update user if user infos are different from the existing ones
            if (user_entity.name != user.name):
                await self.data_context.update_entity_async(UserEntity, user_entity.id, name = user.name)

            return user_id_to_update
        
        except Exception as e:
            print(f"Failed to update user: {e}")
            raise e
        
    async def create_or_update_user_async(self, user: User) -> UUID:
        if await self.does_exist_user_async(user):
            user_id = await self.update_user_async(user)
        else:            
            user_id = await self.create_new_user_with_device_info_async(user)
        return user_id
    
    async def delete_user_by_id_async(self, user_id: UUID) -> None:
        user_entity = await self.data_context.get_entity_by_id_async(UserEntity, user_id)
        if not user_entity:
            raise ValueError(f"User with id {user_id} not found.")
        device_info_entities = getattr(user_entity, "device_infos", None)
        
        # Manually remove device infos first (Don't rely on cascading delete)
        if device_info_entities:
            for device_info_entity in device_info_entities:
                await self.data_context.delete_entity_async(device_info_entity)
        # If must done manually, we must delete all conversations (and theirs messages) related to the user first too!

        # Remove user
        await self.data_context.delete_entity_async(user_entity)