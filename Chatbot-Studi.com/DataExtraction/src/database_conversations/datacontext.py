import asyncio
from contextlib import asynccontextmanager
import os
from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.future import select
from sqlalchemy.orm import sessionmaker
from uuid import UUID

from database_conversations.models import Base, ConversationEntity, MessageEntity  # Import SQLAlchemy database models
from common_tools.models.conversation import Conversation
from common_tools.helpers.txt_helper import txt
from common_tools.helpers.file_helper import file


class DataContextConversations:
    def __init__(self, db_path_or_url='database_conversations/conversation_database.db'):
        if ':' not in db_path_or_url:
            source_path = os.environ.get("PYTHONPATH").split(';')[-1]
            db_path_or_url = os.path.join(source_path, db_path_or_url)
        if 'http' not in db_path_or_url and not file.file_exists(db_path_or_url):
            txt.print(f"/!\\ Conversations Database file not found at path: {db_path_or_url}")
            self.create_database(db_path_or_url)

        sqlite_db_path = f'sqlite+aiosqlite:///{db_path_or_url}'
        self.engine = create_async_engine(sqlite_db_path, echo=True)
        self.SessionLocal = sessionmaker(
                                bind=self.engine,
                                expire_on_commit=False,
                                class_=AsyncSession)

    def create_database(self, db_path):
        sqlite_db_path_sync = f'sqlite:///{db_path}'
        sync_engine = create_engine(sqlite_db_path_sync, echo=True)
        with sync_engine.begin() as conn:
            Base.metadata.create_all(bind=conn)
        txt.print(">>> Conversations Database and tables created successfully.")

    @asynccontextmanager
    async def get_session_async(self):
        session = self.SessionLocal()
        try:
            yield session
            await session.commit()
        except Exception as e:
            await session.rollback()
            raise
        finally:
            await session.close()

    async def add_conversation_async(self, user_name: str, conversation_entity: ConversationEntity):
        async with self.get_session_async() as session:
            try:
                # Add the conversation (with its related messages) to the session
                session.add(conversation_entity)
                return conversation_entity.id
            except Exception as e:
                txt.print(f"Failed to add conversation: {e}")
                raise

    async def get_conversation_by_id_async(self, conversation_id: UUID):
        async with self.get_session_async() as session:
            try:
                result = await session.execute(select(ConversationEntity).filter(ConversationEntity.id == conversation_id))
                conversation = result.scalars().first()
                return conversation
            except Exception as e:
                txt.print(f"Failed to retrieve conversation: {e}")
                raise

    async def get_all_conversations_async(self):
        async with self.get_session_async() as session:
            try:
                result = await session.execute(select(ConversationEntity))
                conversations = result.scalars().all()
                return conversations
            except Exception as e:
                txt.print(f"Failed to retrieve conversations: {e}")
                raise

    async def update_conversation_async(self, conversation_id: UUID, user_name: str = None, new_messages: list[dict] = None):
        async with self.get_session_async() as session:
            try:
                result = await session.execute(select(ConversationEntity).filter(ConversationEntity.id == conversation_id))
                conversation = result.scalars().first()

                if not conversation:
                    raise ValueError("Conversation not found")

                if user_name:
                    conversation.user_name = user_name

                if new_messages:
                    for msg in new_messages:
                        message = MessageEntity(
                            role=msg['role'],
                            content=msg['content'],
                            elapsed_seconds=msg.get('elapsed_seconds', 0),
                        )
                        conversation.messages.append(message)

                session.add(conversation)
            except Exception as e:
                txt.print(f"Failed to update conversation: {e}")
                raise

    async def delete_conversation_async(self, conversation_id: UUID):
        async with self.get_session_async() as session:
            try:
                result = await session.execute(select(ConversationEntity).filter(ConversationEntity.id == conversation_id))
                conversation = result.scalars().first()

                if conversation:
                    await session.delete(conversation)
                else:
                    raise ValueError("Conversation not found")
            except Exception as e:
                txt.print(f"Failed to delete conversation: {e}")
                raise

    async def add_message_to_conversation_async(self, conversation_id: UUID, role: str, content: str, elapsed_seconds: int = 0):
        async with self.get_session_async() as session:
            try:
                result = await session.execute(select(ConversationEntity).filter(ConversationEntity.id == conversation_id))
                conversation = result.scalars().first()

                if not conversation:
                    raise ValueError("Conversation not found")

                message = MessageEntity(
                    role=role,
                    content=content,
                    elapsed_seconds=elapsed_seconds,
                )
                conversation.messages.append(message)
                session.add(conversation)
            except Exception as e:
                txt.print(f"Failed to add message: {e}")
                raise

    async def update_message_async(self, message_id: int, new_role: str = None, new_content: str = None, new_elapsed_seconds: int = None):
        async with self.get_session_async() as session:
            try:
                result = await session.execute(select(MessageEntity).filter(MessageEntity.id == message_id))
                message = result.scalars().first()

                if not message:
                    raise ValueError("Message not found")

                if new_role:
                    message.role = new_role
                if new_content:
                    message.content = new_content
                if new_elapsed_seconds is not None:
                    message.elapsed_seconds = new_elapsed_seconds

                session.add(message)
            except Exception as e:
                txt.print(f"Failed to update message: {e}")
                raise
