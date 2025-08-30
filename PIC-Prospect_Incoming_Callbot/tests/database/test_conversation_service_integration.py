import pytest
import os
import tempfile
from uuid import uuid4, UUID
from datetime import datetime, timezone

from database.conversation_persistence_local_service import ConversationPersistenceLocalService, QuotaOverloadException
from database.conversation_repository import ConversationRepository
from database.user_repository import UserRepository
from api_client.request_models.user_request_model import UserRequestModel, DeviceInfoRequestModel
from api_client.request_models.conversation_request_model import ConversationRequestModel, MessageRequestModel
from database.models.conversation import Conversation, Message
from database.models.user import User
from database.models.device_info import DeviceInfo
from api_client.conversation_persistence_interface import ConversationPersistenceInterface


@pytest.fixture
async def test_db_path():
    """Create a temporary database file for testing"""
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as temp_file:
        db_path = temp_file.name
    
    yield db_path
    
    # Cleanup: Remove the test database file
    try:
        os.unlink(db_path)
    except OSError:
        pass  # File might already be deleted


@pytest.fixture
async def conversation_service(test_db_path):
    """Create a ConversationPersistenceLocalService instance with real repositories"""
    service = ConversationPersistenceLocalService()
    
    # Use real repositories with test database
    service.conversation_repository = ConversationRepository(test_db_path)
    service.user_repository = UserRepository(test_db_path)
    service.max_conversations_by_day = 10  # Set a limit for testing
    
    # Ensure database tables are created
    service.conversation_repository.data_context.create_database()
    
    yield service
    
    # Cleanup: Close database connections
    await service.conversation_repository.data_context.close_async()
    await service.user_repository.data_context.close_async()


@pytest.fixture
def sample_user_id():
    """Sample user UUID for testing"""
    return UUID('3d71c265-5291-48db-8378-000001111133')


@pytest.fixture
def sample_conversation_id():
    """Sample conversation UUID for testing"""
    return UUID('3d71c265-5291-48db-8378-000001111122')


@pytest.fixture
def sample_device_info_request():
    """Sample DeviceInfoRequestModel for testing"""
    return DeviceInfoRequestModel(
        user_agent="Mozilla/5.0 Test",
        platform="Windows",
        app_version="1.0.0",
        os="Windows 10",
        browser="Chrome",
        is_mobile=False
    )


@pytest.fixture
def sample_user_request(sample_user_id, sample_device_info_request):
    """Sample UserRequestModel for testing"""
    return UserRequestModel(
        user_id=sample_user_id,
        user_name="Test User",
        IP="192.168.1.100",
        device_info=sample_device_info_request
    )


@pytest.fixture
def sample_message_request():
    """Sample MessageRequestModel for testing"""
    return MessageRequestModel(
        role="user",
        content="Hello, this is a test message",
        elapsed_seconds=2.5
    )


@pytest.fixture
def sample_conversation_request(sample_user_id, sample_message_request):
    """Sample ConversationRequestModel for testing"""
    return ConversationRequestModel(
        user_id=sample_user_id,
        messages=[sample_message_request]
    )


@pytest.fixture
async def test_user(conversation_service, sample_user_request):
    """Create a test user in the database"""
    user_id = await conversation_service.create_or_retrieve_user_async(sample_user_request)
    return user_id


@pytest.fixture
async def test_conversation(conversation_service, sample_user_request):
    """Create a test conversation in the database"""
    # First create a user
    user_id = await conversation_service.create_or_retrieve_user_async(sample_user_request)
    
    # Create a conversation for that user
    conversation_request = ConversationRequestModel(
        user_id=user_id,
        messages=[]
    )
    conversation_id = await conversation_service.create_new_conversation_async(conversation_request)
    
    # Get the conversation object
    conversation = await conversation_service.conversation_repository.get_conversation_by_id_async(conversation_id)
    return conversation


class TestConversationServiceIntegration:
    
    @pytest.mark.asyncio
    async def test_create_or_retrieve_user_async_success(self, conversation_service, sample_user_request):
        """Test successful user creation or retrieval"""
        # Act
        user_id = await conversation_service.create_or_retrieve_user_async(sample_user_request)
        
        # Assert
        assert isinstance(user_id, UUID)
        
        # Verify the user was actually created/retrieved in the database
        user = await conversation_service.user_repository.get_user_by_id_async(user_id)
        assert user is not None
        assert user.name == sample_user_request.user_name

    @pytest.mark.asyncio
    async def test_create_new_conversation_async_success(self, conversation_service, sample_user_request, sample_message_request):
        """Test successful conversation creation"""
        # Arrange - First create a user to ensure they exist in the database
        user_id = await conversation_service.create_or_retrieve_user_async(sample_user_request)
        
        conversation_request = ConversationRequestModel(
            user_id=user_id,
            messages=[sample_message_request]
        )
        
        # Act
        conv_id = await conversation_service.create_new_conversation_async(conversation_request)
        
        # Assert
        assert isinstance(conv_id, UUID)
        
        # Verify the conversation was actually created in the database
        conversation = await conversation_service.conversation_repository.get_conversation_by_id_async(conv_id)
        assert conversation is not None
        assert conversation.user.id == user_id
        assert len(conversation.messages) == 1
        assert conversation.messages[0].content == sample_message_request.content

    @pytest.mark.asyncio
    async def test_create_new_conversation_async_quota_exceeded(self, conversation_service, sample_user_request):
        """Test conversation creation when quota is exceeded"""
        # Arrange - Create a user and set quota to 1
        user_id = await conversation_service.create_or_retrieve_user_async(sample_user_request)
        conversation_service.max_conversations_by_day = 1
        
        # Create first conversation (should succeed)
        conversation_request_1 = ConversationRequestModel(user_id=user_id, messages=[])
        conv_id_1 = await conversation_service.create_new_conversation_async(conversation_request_1)
        assert conv_id_1 is not None
        
        # Try to create second conversation (should fail due to quota)
        conversation_request_2 = ConversationRequestModel(user_id=user_id, messages=[])
        
        # Act & Assert
        with pytest.raises(QuotaOverloadException, match="You have reached the maximum number of conversations allowed per day."):
            await conversation_service.create_new_conversation_async(conversation_request_2)

    @pytest.mark.asyncio
    async def test_create_new_conversation_async_no_quota_limit(self, conversation_service, sample_user_request):
        """Test conversation creation when no quota limit is set"""
        # Arrange
        conversation_service.max_conversations_by_day = None  # No limit
        user_id = await conversation_service.create_or_retrieve_user_async(sample_user_request)
        
        # Create multiple conversations to test no quota limit
        conversation_ids = []
        for i in range(5):  # Create 5 conversations
            conversation_request = ConversationRequestModel(user_id=user_id, messages=[])
            conv_id = await conversation_service.create_new_conversation_async(conversation_request)
            conversation_ids.append(conv_id)
        
        # Assert - All conversations should be created successfully
        assert len(conversation_ids) == 5
        for conv_id in conversation_ids:
            assert isinstance(conv_id, UUID)
            # Verify each conversation exists in database
            conversation = await conversation_service.conversation_repository.get_conversation_by_id_async(conv_id)
            assert conversation is not None
            assert conversation.user.id == user_id

    @pytest.mark.asyncio
    async def test_get_user_last_conversation_async_with_conversations(self, conversation_service, sample_user_request):
        """Test getting user's last conversation when conversations exist"""
        # Arrange - Create user and multiple conversations
        user_id = await conversation_service.create_or_retrieve_user_async(sample_user_request)
        
        # Create multiple conversations
        conv_ids = []
        for i in range(3):
            conversation_request = ConversationRequestModel(user_id=user_id, messages=[])
            conv_id = await conversation_service.create_new_conversation_async(conversation_request)
            conv_ids.append(conv_id)
        
        # Act
        result = await conversation_service.get_user_last_conversation_async(user_id)
        
        # Assert
        assert isinstance(result, dict)
        assert "conversation_id" in result
        assert "user_id" in result
        assert "message_count" in result
        assert result["user_id"] == str(user_id)
        # The last conversation should be the most recent one
        assert UUID(result["conversation_id"]) in conv_ids

    @pytest.mark.asyncio
    async def test_get_user_last_conversation_async_no_conversations(self, conversation_service, sample_user_request):
        """Test getting user's last conversation when no conversations exist"""
        # Arrange - Create user but no conversations
        user_id = await conversation_service.create_or_retrieve_user_async(sample_user_request)
        
        # Act
        result = await conversation_service.get_user_last_conversation_async(user_id)
        
        # Assert
        assert isinstance(result, dict)
        assert result["conversation_id"] is None
        assert result["user_id"] == str(user_id)
        assert result["message_count"] == 0

    @pytest.mark.asyncio
    async def test_add_message_to_conversation_async_success(self, conversation_service: ConversationPersistenceInterface, test_conversation: Conversation):
        """Test successful addition of external AI message to conversation"""
        # Arrange
        conversation_id_str = str(test_conversation.id)
        message_content = "This is an AI response"
        
        # Act
        result = await conversation_service.add_message_to_conversation_async(conversation_id_str, message_content)
        
        # Assert
        assert isinstance(result, dict)
        assert "id" in result  # The conversation ID
        assert "messages" in result
        assert result["id"] == conversation_id_str
        
        # Verify the AI message was added
        messages = result["messages"]
        ai_messages = [msg for msg in messages if msg.get("role") == "assistant"]
        assert len(ai_messages) >= 1
        assert any(msg.get("content") == message_content for msg in ai_messages)
        
        # Verify the message was actually added to the database
        updated_conversation = await conversation_service.conversation_repository.get_conversation_by_id_async(test_conversation.id)
        # Find the AI message in the conversation
        db_ai_messages = [msg for msg in updated_conversation.messages if msg.role == "assistant"]
        assert len(db_ai_messages) >= 1
        assert any(msg.content == message_content for msg in db_ai_messages)

    @pytest.mark.asyncio
    async def test_add_message_to_conversation_async_empty_message(self, conversation_service, test_conversation):
        """Test adding empty message to conversation"""
        # Arrange
        conversation_id_str = str(test_conversation.id)
        empty_message = ""
        
        # Act
        result = await conversation_service.add_message_to_conversation_async(conversation_id_str, empty_message)
        
        # Assert
        assert isinstance(result, dict)
        assert "id" in result
        assert "messages" in result
        
        # Verify no new AI message was added to the database for empty content
        updated_conversation = await conversation_service.conversation_repository.get_conversation_by_id_async(test_conversation.id)
        # Should have the same number of messages as before (empty messages shouldn't be added)
        assert len(updated_conversation.messages) == len(test_conversation.messages)

    @pytest.mark.asyncio
    async def test_add_message_to_user_last_conversation_or_create_one_async_existing_conversation(
        self, conversation_service, test_conversation
    ):
        """Test adding message to user's last conversation when conversation exists"""
        # Arrange
        message_content = "Hello from user"
        user_id = test_conversation.user.id
        
        # Act
        result = await conversation_service.add_message_to_user_last_conversation_or_create_one_async(user_id, message_content)
        
        # Assert
        assert result is not None
        assert result.id == test_conversation.id
        assert result.user.id == user_id
        
        # Verify the message was actually added to the database
        updated_conversation = await conversation_service.conversation_repository.get_conversation_by_id_async(test_conversation.id)
        user_messages = [msg for msg in updated_conversation.messages if msg.role == "user"]
        assert any(msg.content == message_content for msg in user_messages)

    @pytest.mark.asyncio
    async def test_add_message_to_user_last_conversation_or_create_one_async_create_new(
        self, conversation_service, sample_user_request
    ):
        """Test adding message to user's last conversation when no conversation exists"""
        # Arrange - Create a user but no conversations
        user_id = await conversation_service.create_or_retrieve_user_async(sample_user_request)
        message_content = "Hello from user"
        
        # Act - This should create a new conversation since none exists
        result = await conversation_service.add_message_to_user_last_conversation_or_create_one_async(user_id, message_content)
        
        # Assert
        assert result is not None
        assert result.user.id == user_id
        
        # Verify the conversation was created and message was added
        conversations = await conversation_service.conversation_repository.get_all_user_conversations_async(user_id)
        assert len(conversations) == 1
        created_conversation = conversations[0]
        assert created_conversation.id == result.id
        
        # Verify the message was added
        user_messages = [msg for msg in created_conversation.messages if msg.role == "user"]
        assert any(msg.content == message_content for msg in user_messages)

    @pytest.mark.asyncio 
    async def test_interface_compliance(self, conversation_service):
        """Test that ConversationPersistenceLocalService properly implements ConversationPersistenceInterface"""
        from api_client.conversation_persistence_interface import ConversationPersistenceInterface

        assert issubclass(conversation_service.__class__, ConversationPersistenceInterface)
        
        # Check that all interface methods are implemented
        interface_methods = [
            'create_or_retrieve_user_async',
            'create_new_conversation_async', 
            'get_user_last_conversation_async',
            'add_message_to_conversation_async'
        ]
        
        for method_name in interface_methods:
            assert hasattr(conversation_service, method_name)
            assert callable(getattr(conversation_service, method_name))

    @pytest.mark.asyncio
    async def test_conversation_service_with_message_models(self, conversation_service, sample_user_request):
        """Integration test with actual message models"""
        # Arrange
        user_id = await conversation_service.create_or_retrieve_user_async(sample_user_request)
        
        message_request = MessageRequestModel(
            role="user",
            content="Integration test message",
            elapsed_seconds=3.0
        )
        conversation_request = ConversationRequestModel(
            user_id=user_id,
            messages=[message_request]
        )
        
        # Act
        conv_id = await conversation_service.create_new_conversation_async(conversation_request)
        
        # Assert
        assert isinstance(conv_id, UUID)
        
        # Verify the conversation was created with the message
        conversation = await conversation_service.conversation_repository.get_conversation_by_id_async(conv_id)
        assert conversation is not None
        assert conversation.user.id == user_id
        assert len(conversation.messages) == 1
        assert conversation.messages[0].content == "Integration test message"
        assert conversation.messages[0].role == "user"