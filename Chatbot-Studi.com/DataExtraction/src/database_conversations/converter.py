from database_conversations.models import ConversationEntity, MessageEntity
from common_tools.models.conversation import Conversation, Message

class ConversationConverter:
    @staticmethod
    def convert_conversation_model_to_entity(conversation: Conversation):
        """Convert Conversation model to Conversation entity"""
        conversation_entity = ConversationEntity(
            id=conversation.id,
            user_name=conversation.user_name,
            messages=[
                MessageEntity(
                    role=message.role,
                    content=message.content,
                    elapsed_seconds=message.elapsed_seconds) 
                for message in conversation.messages
            ]
        )
        return conversation_entity
    
    @staticmethod
    def convert_conversation_entity_to_model(conversation_entity: ConversationEntity):
        """Convert Conversation entity to Conversation model"""
        conversation = Conversation(
            user_name=conversation_entity.user_name,
            messages=[
                Message(
                    role=message.role,
                    content=message.content,
                    elapsed_seconds=message.elapsed_seconds
                )
                for message in conversation_entity.messages
            ],
            id=conversation_entity.id
        )
        return conversation
    
    @staticmethod
    def convert_message_model_to_entity(message: Message):
        """Convert Message model to Message entity"""
        message_entity = MessageEntity(
            role=message.role,
            content=message.content,
            elapsed_seconds=message.elapsed_seconds
        )
        return message_entity