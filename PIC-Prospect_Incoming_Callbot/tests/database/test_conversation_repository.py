import os
from datetime import UTC, datetime
from uuid import uuid4

import pytest

from database.conversation_repository import ConversationRepository
from database.entities import DeviceInfoEntity, UserEntity
from database.models.conversation import Conversation, Message


@pytest.fixture
async def conversation_repository():
    """Create a ConversationRepository instance with concrete file database"""
    # Create a temporary database file
    db_path = f'tests/database/test_conversation_{uuid4()}.db'
    if not os.path.exists(db_path):
        try:
            # Create repository with real database
            repo = ConversationRepository(db_path)
            yield repo
        except Exception as e:
            print(f"Failed to create conversation repository: {e}")
            raise
        finally:
            # Cleanup: close data context and delete the database file
            if hasattr(repo, 'data_context') and repo.data_context:
                await repo.data_context.close_async()
            if os.path.exists(db_path):
                os.remove(db_path)

@pytest.fixture
async def sample_user(conversation_repository):
    """Create a real user in the database for testing"""
    user_id = uuid4()
    device_info = DeviceInfoEntity(
        id=uuid4(),
        ip="192.168.1.100",
        user_agent="Mozilla/5.0 Test",
        platform="Windows",
        app_version="1.0.0",
        os="Windows 10",
        browser="Chrome",
        is_mobile=False,
        created_at=datetime.now(UTC)
    )
    
    user_entity = UserEntity(
        id=user_id,
        name="Test User",
        device_infos=[device_info],
        created_at=datetime.now(UTC)
    )
    
    await conversation_repository.data_context.add_entity_async(user_entity)
    return user_entity


@pytest.fixture
def sample_user_id():
    """Sample user UUID for testing"""
    return uuid4()


@pytest.fixture
def sample_conversation_id():
    """Sample conversation UUID for testing"""
    return uuid4()




@pytest.fixture
def sample_message():
    """Sample Message for testing"""
    return Message(
        role="user",
        content="Hello, this is a test message",
        elapsed_seconds=2.5
    )


class TestConversationRepositoryIntegration:
    
    @pytest.mark.asyncio
    async def test_create_new_conversation_empty_async_success(self, conversation_repository, sample_user):
        """Test successful creation of an empty conversation"""
        # Act
        result = await conversation_repository.create_new_conversation_empty_async(sample_user.id)
        
        # Assert
        assert result is not None
        assert isinstance(result, Conversation)
        assert result.user.id == sample_user.id
        assert len(result.messages) == 0
        
        # Verify conversation exists in database
        retrieved_conversation = await conversation_repository.get_conversation_by_id_async(result.id, fails_if_not_found=False)
        assert retrieved_conversation is not None
        assert retrieved_conversation.id == result.id

    @pytest.mark.asyncio
    async def test_create_new_conversation_empty_async_failure(self, conversation_repository):
        """Test failure in creating a new conversation with non-existent user"""
        # Arrange - use a non-existent user ID
        non_existent_user_id = uuid4()
        
        # Act
        result = await conversation_repository.create_new_conversation_empty_async(non_existent_user_id)
        
        # Assert
        assert result is None

    @pytest.mark.asyncio
    async def test_add_message_to_existing_conversation_async_success(self, conversation_repository, sample_user, sample_message):
        """Test successful addition of a message to existing conversation"""
        # Arrange - create a real conversation first
        conversation = await conversation_repository.create_new_conversation_empty_async(sample_user.id)
        assert conversation is not None
        
        # Act
        result = await conversation_repository.add_message_to_existing_conversation_async(conversation.id, sample_message)
        
        # Assert
        assert result is True
        
        # Verify message was added to conversation
        updated_conversation = await conversation_repository.get_conversation_by_id_async(conversation.id)
        assert len(updated_conversation.messages) == 1
        assert updated_conversation.messages[0].content == sample_message.content
        assert updated_conversation.messages[0].role == sample_message.role

    @pytest.mark.asyncio
    async def test_add_message_to_existing_conversation_async_conversation_not_exists(self, conversation_repository, sample_message):
        """Test adding message to non-existing conversation raises ValueError"""
        # Arrange - use a non-existent conversation ID
        non_existent_conversation_id = uuid4()
        
        # Act & Assert
        with pytest.raises(ValueError, match=f"Conversation with id: {non_existent_conversation_id} does not exist."):
            await conversation_repository.add_message_to_existing_conversation_async(non_existent_conversation_id, sample_message)


    @pytest.mark.asyncio
    async def test_does_exist_conversation_by_id_async_exists(self, conversation_repository, sample_user):
        """Test checking if conversation exists - returns True"""
        # Arrange - create a real conversation
        conversation = await conversation_repository.create_new_conversation_empty_async(sample_user.id)
        assert conversation is not None
        
        # Act
        result = await conversation_repository.does_exist_conversation_by_id_async(conversation.id)
        
        # Assert
        assert result is True

    @pytest.mark.asyncio
    async def test_does_exist_conversation_by_id_async_none_id(self, conversation_repository):
        """Test checking if conversation exists with None ID - returns False"""
        # Act
        result = await conversation_repository.does_exist_conversation_by_id_async(None)
        
        # Assert
        assert result is False
        
    @pytest.mark.asyncio
    async def test_does_exist_conversation_by_id_async_not_exists(self, conversation_repository):
        """Test checking if conversation exists - returns False for non-existent ID"""
        # Arrange - use a non-existent conversation ID
        non_existent_id = uuid4()
        
        # Act
        result = await conversation_repository.does_exist_conversation_by_id_async(non_existent_id)
        
        # Assert
        assert result is False

    @pytest.mark.asyncio
    async def test_get_conversation_by_id_async_success(self, conversation_repository, sample_user):
        """Test successful retrieval of conversation by ID"""
        # Arrange - create a real conversation
        created_conversation = await conversation_repository.create_new_conversation_empty_async(sample_user.id)
        assert created_conversation is not None
        
        # Act
        result = await conversation_repository.get_conversation_by_id_async(created_conversation.id)
        
        # Assert
        assert result is not None
        assert isinstance(result, Conversation)
        assert result.id == created_conversation.id
        assert result.user.id == sample_user.id

    @pytest.mark.asyncio
    async def test_get_all_user_conversations_async_success(self, conversation_repository, sample_user):
        """Test successful retrieval of all user conversations"""
        # Arrange - create multiple conversations for the user
        conversation1 = await conversation_repository.create_new_conversation_empty_async(sample_user.id)
        conversation2 = await conversation_repository.create_new_conversation_empty_async(sample_user.id)
        assert conversation1 is not None
        assert conversation2 is not None
        
        # Act
        result = await conversation_repository.get_all_user_conversations_async(sample_user.id)
        
        # Assert
        assert len(result) == 2
        assert all(isinstance(conv, Conversation) for conv in result)
        conversation_ids = [conv.id for conv in result]
        assert conversation1.id in conversation_ids
        assert conversation2.id in conversation_ids

    @pytest.mark.asyncio
    async def test_get_all_user_conversations_async_no_conversations(self, conversation_repository, sample_user):
        """Test retrieving conversations when user has no conversations"""
        # Act - user exists but has no conversations
        result = await conversation_repository.get_all_user_conversations_async(sample_user.id)
        
        # Assert
        assert result == []

    @pytest.mark.asyncio
    async def test_get_recent_conversations_count_by_user_id_async_success(self, conversation_repository, sample_user):
        """Test successful retrieval of recent conversation count"""
        # Arrange - create some conversations
        conversation1 = await conversation_repository.create_new_conversation_empty_async(sample_user.id)
        conversation2 = await conversation_repository.create_new_conversation_empty_async(sample_user.id)
        assert conversation1 is not None
        assert conversation2 is not None
        
        # Act
        result = await conversation_repository.get_recent_conversations_count_by_user_id_async(sample_user.id, 24)
        
        # Assert
        assert result == 2

    @pytest.mark.asyncio
    async def test_get_recent_conversations_count_by_user_id_async_no_conversations(self, conversation_repository, sample_user):
        """Test counting recent conversations when user has no conversations"""
        # Act
        result = await conversation_repository.get_recent_conversations_count_by_user_id_async(sample_user.id)
        
        # Assert
        assert result == 0
        
    @pytest.mark.asyncio
    async def test_full_workflow_integration(self, conversation_repository, sample_user, sample_message):
        """Test a full workflow: create conversation, add messages, retrieve"""
        # Create conversation
        conversation = await conversation_repository.create_new_conversation_empty_async(sample_user.id)
        assert conversation
        
        # Add multiple messages
        message1 = Message(role="user", content="First message", elapsed_seconds=1.0)
        message2 = Message(role="assistant", content="Assistant response", elapsed_seconds=2.0)
        
        assert await conversation_repository.add_message_to_existing_conversation_async(conversation.id, message1)
        assert await conversation_repository.add_message_to_existing_conversation_async(conversation.id, message2)
        
        # Retrieve and verify
        updated_conversation = await conversation_repository.get_conversation_by_id_async(conversation.id)
        assert len(updated_conversation.messages) == 2
        assert updated_conversation.messages[0].role == message1.role
        assert updated_conversation.messages[0].content == message1.content
        assert updated_conversation.messages[1].role == message2.role
        assert updated_conversation.messages[1].content == message2.content
        
        # Verify in user's conversations list
        user_conversations = await conversation_repository.get_all_user_conversations_async(sample_user.id)
        assert len(user_conversations) >= 1
        assert user_conversations[-1].id == conversation.id
        assert len(user_conversations[-1].messages) == 2
        
        # Verify count
        recent_count = await conversation_repository.get_recent_conversations_count_by_user_id_async(sample_user.id)
        assert recent_count == 1
