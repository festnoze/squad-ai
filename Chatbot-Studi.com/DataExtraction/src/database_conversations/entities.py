from sqlalchemy import Column, String, Integer, ForeignKey, Table, DateTime
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship, declarative_base
from datetime import datetime
import uuid

Base = declarative_base()

class UserEntity(Base):
    __tablename__ = 'users'

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String, nullable=False)
    ip = Column(String, nullable=False)
    device_info = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationship to Conversation
    conversations = relationship("ConversationEntity", back_populates="user", cascade="all, delete-orphan", lazy="select")

class ConversationEntity(Base):
    __tablename__ = 'conversations'

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey('users.id'), nullable=False)
    user = relationship("UserEntity", back_populates="conversations", lazy="joined")
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationship to Message
    messages = relationship("MessageEntity", back_populates="conversation", cascade="all, delete-orphan", lazy="joined")

    def __init__(self, user: UserEntity, messages: list = None):
        self.user = user
        self.messages = messages if messages is not None else []

class MessageEntity(Base):
    __tablename__ = 'messages'

    id = Column(Integer, primary_key=True, autoincrement=True)
    conversation_id = Column(UUID(as_uuid=True), ForeignKey('conversations.id'), nullable=False)
    role = Column(String, nullable=False)
    content = Column(String, nullable=False)
    elapsed_seconds = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationship to Conversation
    conversation = relationship("ConversationEntity", back_populates="messages")

    def __init__(self, role: str, content: str, elapsed_seconds: int = 0):
        self.role = role
        self.content = content
        self.elapsed_seconds = elapsed_seconds