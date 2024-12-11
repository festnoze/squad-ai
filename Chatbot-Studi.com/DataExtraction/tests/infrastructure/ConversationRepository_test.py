import os
import pytest
import asyncio
from uuid import uuid4
from datetime import datetime, timezone
from src.database_conversations.entities import ConversationEntity
from src.database_conversations.conversation_converters import ConversationConverters
from src.infrastructure.conversation_repository import ConversationRepository
from common_tools.models.conversation import Conversation, Message, User

#TMP

from sqlalchemy.sql.expression import BinaryExpression
from sqlalchemy import create_engine, select
from sqlalchemy import Column, String, Integer, ForeignKey, Table, DateTime
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import relationship, declarative_base, joinedload
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import sessionmaker

pytest_plugins = ["pytest_asyncio"]

class TestConversationRepository:
    db_path_or_url: str = "tests/infrastructure/conversations_test.db"

    def setup_method(self):
        if os.path.exists(self.db_path_or_url):
            try:
                os.remove(self.db_path_or_url) # Remove the existing test database if it exists
            except Exception as e:
                print(f"Error during setup: {e}")

        self.conversation_repository = ConversationRepository(db_path_or_url=self.db_path_or_url)

        self.sample_user = User(id=uuid4(), name="First User", ip="192.168.1.1", device_info="browser")
        asyncio.run(self.conversation_repository.data_context.add_entity_async(
                ConversationConverters.convert_user_model_to_entity(self.sample_user)))

        self.sample_conversation = Conversation(self.sample_user, [Message("role1", "content1", 0, uuid4(), None)], uuid4(), None)
        asyncio.run(self.conversation_repository.data_context.add_entity_async(
                ConversationConverters.convert_conversation_model_to_entity(self.sample_conversation)))

    def teardown_method(self):
        # Dispose of the database connection and remove the test database
        self.conversation_repository.data_context.engine.dispose()
        if os.path.exists(self.db_path_or_url):
            try:
                os.remove(self.db_path_or_url)
            except Exception as e:
                print(f"Error during teardown: {e}")

    @pytest.mark.asyncio
    async def test_create_new_conversation(self):
        new_conversation = Conversation(self.sample_user, [Message("role2", "content2", 1.2, uuid4(), None)], uuid4(), None)
        result = await self.conversation_repository.create_new_conversation_async(new_conversation)
        assert result is True

        # Verify that the new conversation exists in the database
        exists = await self.conversation_repository.does_exist_conversation_by_id_async(new_conversation.id)
        assert exists is True

    @pytest.mark.asyncio
    async def test_create_new_conversation_existing_id(self):
        # Attempt to create a conversation with an existing ID
        duplicate_conversation = Conversation(
            user=self.sample_user,
            messages=[],
            id=self.sample_conversation.id,            
        )
        with pytest.raises(ValueError) as exc_info:
            await self.conversation_repository.create_new_conversation_async(duplicate_conversation)
        assert f"Failed to create conversation as the id: {duplicate_conversation.id} already exists." in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_get_conversation_by_id(self):
        retrieved_conversation = await self.conversation_repository.get_conversation_by_id_async(self.sample_conversation.id)
        assert retrieved_conversation is not None
        assert retrieved_conversation.id == self.sample_conversation.id
        assert retrieved_conversation.title == self.sample_conversation.title
        assert len(retrieved_conversation.messages) == 1
        assert retrieved_conversation.messages[0].content == "Hello, World!"

        assert retrieved_conversation.user is not None
        assert retrieved_conversation.user.id == self.sample_user.id
        assert retrieved_conversation.user.name == self.sample_user.name
        assert retrieved_conversation.user.ip == self.sample_user.ip
        assert retrieved_conversation.user.device_info == self.sample_user.device_info

        assert retrieved_conversation.messages is not None

    @pytest.mark.asyncio
    async def test_get_conversation_by_nonexistent_id(self):
        non_existent_id = uuid4()
        conversation = await self.conversation_repository.get_conversation_by_id_async(non_existent_id, fails_if_not_found=False)
        assert conversation is None

    @pytest.mark.asyncio
    async def test_does_exist_conversation_by_id(self):
        # Existing conversation
        exists = await self.conversation_repository.does_exist_conversation_by_id_async(self.sample_conversation.id)
        assert exists is True

        # Non-existing conversation
        non_existent_id = uuid4()
        exists = await self.conversation_repository.does_exist_conversation_by_id_async(non_existent_id)
        assert exists is False


    @pytest.mark.asyncio
    async def test_add_message_to_existing_conversation(self):
        async with self.conversation_repository.data_context.read_db() as connection:
            query = select(ConversationEntity)
            results = await connection.execute(query)
            result = results.scalars().first()
            print(result) 

            query = select(ConversationEntity)#.filter(ConversationEntity.id == self.sample_conversation.id)
            #query = select(UserEntity).filter(UserEntity.id == user_id)
            compiled_query = query.compile(dialect=connection.dialect, compile_kwargs={"literal_binds": True})
            print(compiled_query)
            results = await connection.execute(query)
            result = results.scalars().first()
            print(result)
        new_message = Message(
            role="User2",
            content="This is a new message.",
            elapsed_seconds=2.1,
            id=uuid4(),
            created_at=datetime.now(timezone.utc),
        )
        result = await self.conversation_repository.add_message_to_conversation_async(self.sample_conversation.id, new_message)
        assert result is True

        # Retrieve the conversation and verify the new message is added
        updated_conversation = await self.conversation_repository.get_conversation_by_id_async(self.sample_conversation.id)
        assert len(updated_conversation.messages) == 2
        assert any(msg.id == new_message.id and msg.content == new_message.content for msg in updated_conversation.messages)

    @pytest.mark.asyncio
    async def test_add_message_to_nonexistent_conversation(self):
        new_message = Message(
            role="User3",
            content="This is a new message and conversation.",
            elapsed_seconds=0.5,
            id=uuid4(),
            created_at=datetime.now(timezone.utc),
        )
        non_existent_id = uuid4()
        with pytest.raises(ValueError) as exc_info:
            await self.conversation_repository.add_message_to_conversation_async(non_existent_id, new_message)
        assert f"Conversation with id: {non_existent_id} does not exist." in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_create_or_update_conversation_create(self):
        # Assuming a method `create_or_update_conversation_async` exists
        new_conversation = Conversation(
            id=uuid4(),
            title="Create Or Update Conversation",
            messages=[]
        )
        result = await self.conversation_repository.create_or_update_conversation_async(new_conversation)
        assert result is True

        # Verify creation
        exists = await self.conversation_repository.does_exist_conversation_by_id_async(new_conversation.id)
        assert exists is True

    @pytest.mark.asyncio
    async def test_create_or_update_conversation_update(self):
        # Assuming a method `create_or_update_conversation_async` exists
        updated_title = "Updated Conversation Title"
        updated_conversation = Conversation(
            id=self.sample_conversation.id,
            title=updated_title,
            messages=self.sample_conversation.messages
        )
        result = await self.conversation_repository.create_or_update_conversation_async(updated_conversation)
        assert result is True

        # Verify update
        retrieved_conversation = await self.conversation_repository.get_conversation_by_id_async(self.sample_conversation.id)
        assert retrieved_conversation.title == updated_title