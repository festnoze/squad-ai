import pytest
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4
from datetime import datetime, timezone

from database.conversation_service import ConversationService, QuotaOverloadException
from api_client.request_models.user_request_model import UserRequestModel, DeviceInfoRequestModel
from api_client.request_models.conversation_request_model import ConversationRequestModel, MessageRequestModel
from database.models.conversation import Conversation, Message
from database.models.user import User
from database.models.device_info import DeviceInfo


@pytest.fixture
async def conversation_service():
    """Create a ConversationService instance with mocked repository"""
    service = ConversationService()
    service.conversation_repository = AsyncMock()
    service.max_conversations_by_day = 10  # Set a limit for testing
    yield service


@pytest.fixture
def sample_user_id():
    """Sample user UUID for testing"""
    return uuid4()


@pytest.fixture
def sample_conversation_id():
    """Sample conversation UUID for testing"""
    return uuid4()


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
def sample_conversation(sample_conversation_id, sample_user_id):
    """Sample Conversation model for testing"""
    conversation = MagicMock(spec=Conversation)
    conversation.id = sample_conversation_id
    conversation.user_id = sample_user_id
    conversation.messages = []
    conversation.created_at = datetime.now(timezone.utc)
    conversation.add_new_message = MagicMock()
    conversation.last_message = MagicMock()
    return conversation


class TestConversationServiceIntegration:
    
    @pytest.mark.asyncio
    async def test_create_or_retrieve_user_async_success(self, conversation_service, sample_user_request):
        """Test successful user creation or retrieval"""
        # Act
        result = await conversation_service.create_or_retrieve_user_async(sample_user_request)
        
        # Assert
        assert isinstance(result, dict)
        assert "user_id" in result
        assert "name" in result
        assert "created" in result
        assert result["name"] == sample_user_request.user_name
        assert result["created"] is True

    @pytest.mark.asyncio
    async def test_create_new_conversation_async_success(self, conversation_service, sample_conversation_request, sample_conversation):
        """Test successful conversation creation"""
        # Arrange
        conversation_service.conversation_repository.get_recent_conversations_count_by_user_id_async.return_value = 5
        conversation_service.conversation_repository.create_new_conversation_empty_async.return_value = sample_conversation
        conversation_service.conversation_repository.get_conversation_by_id_async.return_value = sample_conversation
        conversation_service.conversation_repository.add_message_to_existing_conversation_async.return_value = True
        
        # Act
        result = await conversation_service.create_new_conversation_async(sample_conversation_request)
        
        # Assert
        assert isinstance(result, dict)
        assert "conversation_id" in result
        assert "user_id" in result
        assert "message_count" in result
        assert "created" in result
        assert result["created"] is True
        conversation_service.conversation_repository.create_new_conversation_empty_async.assert_called_once()
        sample_conversation.add_new_message.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_new_conversation_async_quota_exceeded(self, conversation_service, sample_conversation_request):
        """Test conversation creation when quota is exceeded"""
        # Arrange
        conversation_service.conversation_repository.get_recent_conversations_count_by_user_id_async.return_value = 15
        
        # Act & Assert
        with pytest.raises(QuotaOverloadException, match="You have reached the maximum number of conversations allowed per day."):
            await conversation_service.create_new_conversation_async(sample_conversation_request)

    @pytest.mark.asyncio
    async def test_create_new_conversation_async_no_quota_limit(self, conversation_service, sample_conversation_request, sample_conversation):
        """Test conversation creation when no quota limit is set"""
        # Arrange
        conversation_service.max_conversations_by_day = None  # No limit
        conversation_service.conversation_repository.get_recent_conversations_count_by_user_id_async.return_value = 100
        conversation_service.conversation_repository.create_new_conversation_empty_async.return_value = sample_conversation
        conversation_service.conversation_repository.get_conversation_by_id_async.return_value = sample_conversation
        
        # Act
        result = await conversation_service.create_new_conversation_async(
            ConversationRequestModel(user_id=sample_conversation_request.user_id, messages=[])
        )
        
        # Assert
        assert isinstance(result, dict)
        assert result["created"] is True

    @pytest.mark.asyncio
    async def test_get_user_last_conversation_async_with_conversations(self, conversation_service, sample_user_id, sample_conversation):
        """Test getting user's last conversation when conversations exist"""
        # Arrange
        conversations = [sample_conversation, sample_conversation]
        conversation_service.conversation_repository.get_all_user_conversations_async.return_value = conversations
        
        # Act
        result = await conversation_service.get_user_last_conversation_async(sample_user_id)
        
        # Assert
        assert isinstance(result, dict)
        assert "conversation_id" in result
        assert "user_id" in result
        assert "message_count" in result
        assert result["conversation_id"] == str(sample_conversation.id)

    @pytest.mark.asyncio
    async def test_get_user_last_conversation_async_no_conversations(self, conversation_service, sample_user_id):
        """Test getting user's last conversation when no conversations exist"""
        # Arrange
        conversation_service.conversation_repository.get_all_user_conversations_async.return_value = []
        
        # Act
        result = await conversation_service.get_user_last_conversation_async(sample_user_id)
        
        # Assert
        assert isinstance(result, dict)
        assert result["conversation_id"] is None
        assert result["user_id"] == str(sample_user_id)
        assert result["message_count"] == 0

    @pytest.mark.asyncio
    async def test_add_external_ai_message_to_conversation_async_success(self, conversation_service, sample_conversation_id, sample_conversation):
        """Test successful addition of external AI message to conversation"""
        # Arrange
        conversation_id_str = str(sample_conversation_id)
        message_content = "This is an AI response"
        conversation_service.conversation_repository.get_conversation_by_id_async.return_value = sample_conversation
        conversation_service.conversation_repository.add_message_to_existing_conversation_async.return_value = True
        
        # Act
        result = await conversation_service.add_external_ai_message_to_conversation_async(conversation_id_str, message_content)
        
        # Assert
        assert isinstance(result, dict)
        assert "conversation_id" in result
        assert "message_added" in result
        assert "message_content" in result
        assert "message_count" in result
        assert result["conversation_id"] == conversation_id_str
        assert result["message_added"] is True
        assert result["message_content"] == message_content
        sample_conversation.add_new_message.assert_called_once_with("assistant", message_content)

    @pytest.mark.asyncio
    async def test_add_external_ai_message_to_conversation_async_empty_message(self, conversation_service, sample_conversation_id, sample_conversation):
        """Test adding empty message to conversation"""
        # Arrange
        conversation_id_str = str(sample_conversation_id)
        empty_message = ""
        conversation_service.conversation_repository.get_conversation_by_id_async.return_value = sample_conversation
        
        # Act
        result = await conversation_service.add_external_ai_message_to_conversation_async(conversation_id_str, empty_message)
        
        # Assert
        assert isinstance(result, dict)
        assert result["message_added"] is True
        assert result["message_content"] == empty_message
        sample_conversation.add_new_message.assert_not_called()

    @pytest.mark.asyncio
    async def test_add_message_to_user_last_conversation_or_create_one_async_existing_conversation(
        self, conversation_service, sample_user_id, sample_conversation
    ):
        """Test adding message to user's last conversation when conversation exists"""
        # Arrange
        conversations = [sample_conversation]
        message_content = "Hello from user"
        conversation_service.conversation_repository.get_all_user_conversations_async.return_value = conversations
        conversation_service.conversation_repository.add_message_to_existing_conversation_async.return_value = True
        
        # Act
        result = await conversation_service.add_message_to_user_last_conversation_or_create_one_async(sample_user_id, message_content)
        
        # Assert
        assert result == sample_conversation
        sample_conversation.add_new_message.assert_called_once_with("user", message_content)

    @pytest.mark.asyncio
    async def test_add_message_to_user_last_conversation_or_create_one_async_create_new(
        self, conversation_service, sample_user_id, sample_conversation
    ):
        """Test adding message to user's last conversation when no conversation exists"""
        # Arrange
        message_content = "Hello from user"
        # First call returns empty list (no conversations), second call returns the created conversation
        conversation_service.conversation_repository.get_all_user_conversations_async.side_effect = [[], [sample_conversation]]
        conversation_service.conversation_repository.get_recent_conversations_count_by_user_id_async.return_value = 0
        conversation_service.conversation_repository.create_new_conversation_empty_async.return_value = sample_conversation
        conversation_service.conversation_repository.get_conversation_by_id_async.return_value = sample_conversation
        conversation_service.conversation_repository.add_message_to_existing_conversation_async.return_value = True
        
        # Act
        result = await conversation_service.add_message_to_user_last_conversation_or_create_one_async(sample_user_id, message_content)
        
        # Assert
        assert result == sample_conversation
        sample_conversation.add_new_message.assert_called_once_with("user", message_content)

    @pytest.mark.asyncio 
    async def test_interface_compliance(self, conversation_service):
        """Test that ConversationService properly implements ConversationPersistenceInterface"""
        from api_client.conversation_persistence_interface import ConversationPersistenceInterface

        assert issubclass(conversation_service.__class__, ConversationPersistenceInterface)
        
        # Check that all interface methods are implemented
        interface_methods = [
            'create_or_retrieve_user_async',
            'create_new_conversation_async', 
            'get_user_last_conversation_async',
            'add_external_ai_message_to_conversation_async'
        ]
        
        for method_name in interface_methods:
            assert hasattr(conversation_service, method_name)
            assert callable(getattr(conversation_service, method_name))

    @pytest.mark.asyncio
    async def test_conversation_service_with_message_models(self, conversation_service, sample_user_id):
        """Integration test with actual message models"""
        # Arrange
        message_request = MessageRequestModel(
            role="user",
            content="Integration test message",
            elapsed_seconds=3.0
        )
        conversation_request = ConversationRequestModel(
            user_id=sample_user_id,
            messages=[message_request]
        )
        
        sample_conversation = MagicMock(spec=Conversation)
        sample_conversation.id = uuid4()
        sample_conversation.messages = []
        sample_conversation.add_new_message = MagicMock()
        sample_conversation.last_message = MagicMock()
        
        conversation_service.conversation_repository.get_recent_conversations_count_by_user_id_async.return_value = 0
        conversation_service.conversation_repository.create_new_conversation_empty_async.return_value = sample_conversation
        conversation_service.conversation_repository.get_conversation_by_id_async.return_value = sample_conversation
        conversation_service.conversation_repository.add_message_to_existing_conversation_async.return_value = True
        
        # Act
        result = await conversation_service.create_new_conversation_async(conversation_request)
        
        # Assert
        assert isinstance(result, dict)
        assert result["created"]
        sample_conversation.add_new_message.assert_called_once_with("user", "Integration test message")