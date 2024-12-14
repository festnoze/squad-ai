import os
import pytest
import asyncio

from sqlalchemy import delete
pytest_plugins = ["pytest_asyncio"]
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from src.database_conversations.conversation_converters import ConversationConverters
from src.database_conversations.entities import UserEntity, DeviceInfoEntity
from src.infrastructure.user_repository import UserRepository
from common_tools.models.user import User

class TestUserRepository:
    db_path_or_url:str = "tests/infrastructure/conversations_test.db"

    def setup_method(self):
        self.sample_user = User(id=uuid4(), name="First User", device_info="browser")
        self.user_repository = UserRepository(db_path_or_url=self.db_path_or_url)        
        asyncio.run(self.user_repository.data_context.empty_all_database_tables_async())
        asyncio.run(self.user_repository.data_context.add_entity_async(ConversationConverters.convert_user_model_to_entity(self.sample_user)))

    def teardown_method(self):
        asyncio.run(self.user_repository.data_context.empty_all_database_tables_async())
        self.user_repository.data_context.engine.dispose()
        if os.path.exists(self.db_path_or_url):
            try:
                os.remove(self.db_path_or_url)
            except Exception:
                pass

    @pytest.mark.asyncio
    async def test_create_new_user(self):
        user_entity = User(name="First User", device_info="browser", id=uuid4())
        await self.user_repository.create_new_user_with_device_info_async(user_entity)
        assert await self.user_repository.data_context.does_exist_entity_by_id_async(UserEntity, user_entity.id) is True

    @pytest.mark.asyncio
    async def test_get_user_by_id(self):
        user = await self.user_repository.get_user_by_id_async(self.sample_user.id)        
        
        assert user.id == self.sample_user.id
        assert user.ip == self.sample_user.ip
        assert user.name == self.sample_user.name
        assert user.device_info == self.sample_user.device_info

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
