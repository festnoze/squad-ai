from sqlalchemy import Column, String, Integer, ForeignKey, DateTime
from sqlalchemy.orm import relationship, declarative_base
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from uuid import uuid4
from datetime import datetime, timezone

Base = declarative_base()

class UserEntity(Base):
    __tablename__ = 'users'

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    name = Column(String, nullable=False)
    ip = Column(String, nullable=False)
    device_info = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.now(timezone.utc), nullable=False)

    conversations = relationship("ConversationEntity", back_populates="user", cascade="all, delete-orphan", lazy="select")


class ConversationEntity(Base):
    __tablename__ = 'conversations'

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id = Column(PG_UUID(as_uuid=True), ForeignKey('users.id'), nullable=False)
    created_at = Column(DateTime, default=datetime.now(timezone.utc), nullable=False)

    user = relationship("UserEntity", back_populates="conversations", lazy="joined")
    messages = relationship("MessageEntity", back_populates="conversation", cascade="all, delete-orphan", lazy="joined")


class MessageEntity(Base):
    __tablename__ = 'messages'

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    conversation_id = Column(PG_UUID(as_uuid=True), ForeignKey('conversations.id'), nullable=False)
    role = Column(String, nullable=False)
    content = Column(String, nullable=False)
    elapsed_seconds = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.now(timezone.utc), nullable=False)

    conversation = relationship("ConversationEntity", back_populates="messages")