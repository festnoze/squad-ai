from sqlalchemy import Column, String, Integer, ForeignKey, Table, DateTime
from sqlalchemy.orm import relationship, declarative_base
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from uuid import UUID
import uuid
from datetime import datetime, timezone

Base = declarative_base()

class UserEntity(Base):
    __tablename__ = 'users'

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String, nullable=False)
    ip = Column(String, nullable=False)
    device_info = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.now(timezone.utc), nullable=False)

    conversations = relationship("ConversationEntity", back_populates="user", cascade="all, delete-orphan", lazy="select")

    def __init__(self, id: UUID, name: str, ip: str, device_info: str, created_at: datetime = None):
        self.id = id or uuid.uuid4()
        self.name = name
        self.ip = ip
        self.device_info = device_info
        self.created_at = created_at or datetime.now(timezone.utc)


class ConversationEntity(Base):
    __tablename__ = 'conversations'

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(PG_UUID(as_uuid=True), ForeignKey('users.id'), nullable=False)
    created_at = Column(DateTime, default=datetime.now(timezone.utc), nullable=False)
    user = relationship("UserEntity", back_populates="conversations", lazy="select")
    messages = relationship("MessageEntity", back_populates="conversation", cascade="all, delete-orphan", lazy="select")

    def __init__(self, id: UUID, user_id: UUID, created_at: datetime = None):
        self.id = id or uuid.uuid4()
        self.user_id = user_id
        self.created_at = created_at or datetime.now(timezone.utc)
        self.messages = []


class MessageEntity(Base):
    __tablename__ = 'messages'

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    conversation_id = Column(PG_UUID(as_uuid=True), ForeignKey('conversations.id'), nullable=False)
    role = Column(String, nullable=False)
    content = Column(String, nullable=False)
    elapsed_seconds = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.now(timezone.utc), nullable=False)

    conversation = relationship("ConversationEntity", back_populates="messages")

    def __init__(self, id: UUID, conversation_id: UUID, role: str, content: str, elapsed_seconds: int = 0, created_at: datetime = None):
        self.id = id or uuid.uuid4()
        self.conversation_id = conversation_id
        self.role = role
        self.content = content
        self.elapsed_seconds = elapsed_seconds
        self.created_at = created_at or datetime.now(timezone.utc)