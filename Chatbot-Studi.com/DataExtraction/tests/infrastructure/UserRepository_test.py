import os
import pytest
import asyncio
pytest_plugins = ["pytest_asyncio"]
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from src.database_conversations.conversation_converters import ConversationConverters
from src.database_conversations.entities import UserEntity
from src.infrastructure.user_repository import UserRepository
from common_tools.models.user import User

class TestUserRepository:
    db_path_or_url:str = "tests/infrastructure/conversations_test.db"

    def setup_method(self):
        if os.path.exists(self.db_path_or_url):
            try:
                os.remove(self.db_path_or_url) # remove previous DB if it wasn't done by the previous test 
            except Exception as e:
                print(f"Error during startup: {e}") 

        self.sample_user = User(id=uuid4(), name="First User", ip="192.168.1.1", device_info="browser")
        self.user_repository = UserRepository(db_path_or_url=self.db_path_or_url)
        asyncio.run(self.user_repository.data_context.add_entity_async(ConversationConverters.convert_user_model_to_entity(self.sample_user)))

    def teardown_method(self):
        self.user_repository.data_context.engine.dispose()
        if os.path.exists(self.db_path_or_url):
            try:
                os.remove(self.db_path_or_url)
            except Exception as e:
                print(f"Error during teardown: {e}")

    @pytest.mark.asyncio
    async def test_create_new_user(self):
        user_entity = User(id=uuid4(), name="First User", ip=str(uuid4()), device_info="browser")
        await self.user_repository.create_new_user_async(user_entity)
        assert await self.user_repository.data_context.does_exist_entity_by_id_async(UserEntity, user_entity.id) is True

    @pytest.mark.asyncio
    async def test_get_user_by_id(self):
        user = await self.user_repository.get_user_by_id_async(self.sample_user.id)        
        assert user == self.sample_user

    @pytest.mark.asyncio
    async def test_does_exist_user_by_id(self):
        exists = await self.user_repository.does_exist_user_async(self.sample_user)
        assert exists is True

    @pytest.mark.asyncio
    async def test_does_exist_user_by_ip(self):
        exists = await self.user_repository.does_exist_user_async(self.sample_user)
        assert exists is True

    @pytest.mark.asyncio
    async def test_update_user(self):
        user_id = await self.user_repository.update_user_async(self.sample_user)
        assert user_id == self.sample_user.id

    @pytest.mark.asyncio
    async def test_create_or_update_user_create(self):        
        user_id = await self.user_repository.create_or_update_user_async(self.sample_user)
        assert user_id == self.sample_user.id

    @pytest.mark.asyncio
    async def test_create_or_update_user_update(self):       
        user_id = await self.user_repository.create_or_update_user_async(self.sample_user)
        assert user_id == self.sample_user.id
