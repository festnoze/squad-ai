from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


class UserEntity(Base):
    __tablename__ = "users"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    name = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.now(UTC), nullable=False)

    conversations = relationship(
        "ConversationEntity", back_populates="user", cascade="all, delete-orphan", lazy="select"
    )
    device_infos = relationship(
        "DeviceInfoEntity",
        back_populates="user",
        cascade="all, delete-orphan",
        lazy="joined",  # Ensures DeviceInfos are loaded with the user
    )


class DeviceInfoEntity(Base):
    __tablename__ = "device_infos"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id = Column(PG_UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    ip = Column(String, nullable=False)
    user_agent = Column(String, nullable=False)
    platform = Column(String, nullable=False)
    app_version = Column(String, nullable=False)
    os = Column(String, nullable=False)
    browser = Column(String, nullable=False)
    is_mobile = Column(Boolean, nullable=False)
    created_at = Column(DateTime, default=datetime.now(UTC), nullable=False)

    user = relationship("UserEntity", back_populates="device_infos")


class ConversationEntity(Base):
    __tablename__ = "conversations"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id = Column(PG_UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.now(UTC), nullable=False)

    user = relationship("UserEntity", back_populates="conversations", lazy="joined")
    messages = relationship("MessageEntity", back_populates="conversation", cascade="all, delete-orphan", lazy="joined")
    llm_operations = relationship(
        "LlmOperationEntity", back_populates="conversation", cascade="all, delete-orphan", lazy="select"
    )


class MessageEntity(Base):
    __tablename__ = "messages"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    conversation_id = Column(PG_UUID(as_uuid=True), ForeignKey("conversations.id"), nullable=False)
    role = Column(String, nullable=False)
    content = Column(String, nullable=False)
    elapsed_seconds = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.now(UTC), nullable=False)

    conversation = relationship("ConversationEntity", back_populates="messages")
    llm_operations = relationship(
        "LlmOperationEntity", back_populates="message", cascade="all, delete-orphan", lazy="select"
    )


class LlmOperationTypeEntity(Base):
    __tablename__ = "llm_operation_types"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    name = Column(String, nullable=False, unique=True)
    created_at = Column(DateTime, default=datetime.now(UTC), nullable=False)

    llm_operations = relationship(
        "LlmOperationEntity", back_populates="operation_type", cascade="all, delete-orphan", lazy="select"
    )


class LlmOperationEntity(Base):
    __tablename__ = "llm_operations"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    llm_operation_type_id = Column(PG_UUID(as_uuid=True), ForeignKey("llm_operation_types.id"), nullable=False)
    conversation_id = Column(PG_UUID(as_uuid=True), ForeignKey("conversations.id"), nullable=True)
    message_id = Column(PG_UUID(as_uuid=True), ForeignKey("messages.id"), nullable=True)
    tokens_or_duration = Column(Float, nullable=False)
    provider = Column(String, nullable=False)
    model = Column(String, nullable=False)
    price_per_unit = Column(Float, nullable=False)
    cost_dollar_cents = Column(Float, nullable=False)
    stream_id = Column(String, nullable=True)
    call_sid = Column(String, nullable=True)
    phone_number = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.now(UTC), nullable=False)

    operation_type = relationship("LlmOperationTypeEntity", back_populates="llm_operations")
    conversation = relationship("ConversationEntity", back_populates="llm_operations")
    message = relationship("MessageEntity", back_populates="llm_operations")
