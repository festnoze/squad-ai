import os
import pytest
import asyncio
pytest_plugins = ["pytest_asyncio"]
from uuid import uuid4

from src.database_conversations.conversation_converters import ConversationConverters
from src.infrastructure.user_repository import UserRepository
#
from common_tools.helpers.txt_helper import txt
from common_tools.models.user import User
from common_tools.models.device_info import DeviceInfo

class TestUserRepository:
    db_path_or_url:str = "tests/infrastructure/conversations_test.db"

    def setup_method(self):
        txt.activate_print = True
        self.delete_database()
        self.sample_device_info = DeviceInfo(ip="1.2.3.4", user_agent="Mozilla/5.0", platform="Windows", app_version="1.0", os="Windows", browser="Chrome", is_mobile=False)
        self.sample_user = User(id= uuid4(), name= "First User", device_info= self.sample_device_info)
        self.user_repository = UserRepository(db_path_or_url=self.db_path_or_url)
        asyncio.run(self.user_repository.data_context.empty_all_database_tables_async())
        asyncio.run(self.user_repository.data_context.add_entity_async(ConversationConverters.convert_user_model_to_entity(self.sample_user)))

    def teardown_method(self):
        asyncio.run(self.user_repository.data_context.empty_all_database_tables_async())
        self.user_repository.data_context.engine.dispose()
        self.delete_database()

    def delete_database(self):
        if os.path.exists(self.db_path_or_url):
            try:
                os.remove(self.db_path_or_url)
            except Exception as e:
                print(f"Error during database deletion: {e}")

    @pytest.mark.asyncio
    async def test_get_user_by_id(self):
        user = await self.user_repository.get_user_by_id_async(self.sample_user.id)        
        
        assert user.id == self.sample_user.id
        assert user.name == self.sample_user.name
        #assert user.device_info == self.sample_user.device_info

    @pytest.mark.asyncio
    async def test_get_all_users(self):
        users = await self.user_repository.get_all_users_async()
        assert users is not None
        assert len(users) >= 1
        #assert users.__contains__(self.sample_user)

    @pytest.mark.asyncio
    async def test_does_exist_user_by_id(self):
        exists = await self.user_repository.does_exist_user_async(self.sample_user)
        assert exists is True

    @pytest.mark.asyncio
    async def test_does_exist_user_by_ip(self):
        exists = await self.user_repository.does_exist_user_async(self.sample_user)
        assert exists is True

    @pytest.mark.asyncio
    async def test_create_new_user(self):
        # Arrange
        device_info_entity = DeviceInfo(ip="2.3.4.5", user_agent="Safari/5.0", platform="Mac OsX", app_version="2.0", os="Mac", browser="Safari", is_mobile=True)
        user_entity = User(name="First User", device_info=device_info_entity, id=uuid4())
        
        # Act
        new_user_id = await self.user_repository.create_new_user_with_device_info_async(user_entity)
        
        # Assert
        assert new_user_id == user_entity.id
        new_user = await self.user_repository.get_user_by_id_async(user_entity.id)
        #
        assert new_user is not None
        assert new_user.id == user_entity.id
        assert new_user.name == user_entity.name
        #
        assert new_user.device_info.id == user_entity.device_info.id
        assert new_user.device_info.ip == user_entity.device_info.ip
        assert new_user.device_info.user_agent == user_entity.device_info.user_agent
        assert new_user.device_info.platform == user_entity.device_info.platform
        assert new_user.device_info.app_version == user_entity.device_info.app_version
        assert new_user.device_info.os == user_entity.device_info.os
        assert new_user.device_info.browser == user_entity.device_info.browser
        assert new_user.device_info.is_mobile == user_entity.device_info.is_mobile

    @pytest.mark.asyncio
    async def test_update_user(self):
        # Arrange
        previous_name = self.sample_user.name
        self.sample_user.name = "Updated User Name"

        # Act
        user_id = await self.user_repository.update_user_async(self.sample_user)

        # Assert
        assert user_id == self.sample_user.id
        updated_user = await self.user_repository.get_user_by_id_async(self.sample_user.id)
        assert updated_user.name == self.sample_user.name

        # Tear down
        self.sample_user.name = previous_name

    @pytest.mark.asyncio
    async def test_create_or_update_user_create(self):        
        user_id = await self.user_repository.create_or_update_user_async(self.sample_user)
        assert user_id == self.sample_user.id

    @pytest.mark.asyncio
    async def test_create_or_update_user_update(self):       
        user_id = await self.user_repository.create_or_update_user_async(self.sample_user)
        assert user_id == self.sample_user.id
