from sqlalchemy import Column, String, Integer, ForeignKey, Table
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship, declarative_base
import uuid

Base = declarative_base()

class ConversationEntity(Base):
    __tablename__ = 'conversations'

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_name = Column(String, nullable=True)

    # Relationship to Message
    messages = relationship("MessageEntity", back_populates="conversation", cascade="all, delete-orphan", lazy="joined") # auto load conv messages too

    def __init__(self, id:UUID, user_name: str = None, messages: list = None):
        self.id = id
        self.user_name = user_name
        self.messages = messages if messages is not None else []


class MessageEntity(Base):
    __tablename__ = 'messages'

    id = Column(Integer, primary_key=True, autoincrement=True)
    conversation_id = Column(UUID(as_uuid=True), ForeignKey('conversations.id'), nullable=False)
    role = Column(String, nullable=False)
    content = Column(String, nullable=False)
    elapsed_seconds = Column(Integer, default=0)

    # Relationship to Conversation
    conversation = relationship("ConversationEntity", back_populates="messages")

    def __init__(self, role: str, content: str, elapsed_seconds: int = 0):
        self.role = role
        self.content = content
        self.elapsed_seconds = elapsed_seconds
