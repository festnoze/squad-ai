import asyncio
from contextlib import asynccontextmanager
import os
from uuid import UUID

from common_tools.helpers.txt_helper import txt
from common_tools.helpers.file_helper import file

from sqlalchemy import create_engine, select
from sqlalchemy import Column, String, Integer, ForeignKey, Table, DateTime
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import relationship, declarative_base
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import sessionmaker

Base = declarative_base()

class GenericRepository:
    def __init__(self, db_path_or_url='database.db'):
        if ':' not in db_path_or_url:
            source_path = os.environ.get("PYTHONPATH").split(';')[-1]
            db_path_or_url = os.path.join(source_path, db_path_or_url)
        if 'http' not in db_path_or_url and not file.file_exists(db_path_or_url):
            txt.print(f"/!\\ Database file not found at path: {db_path_or_url}")
            self.create_database(db_path_or_url)

        sqlite_db_path = f'sqlite+aiosqlite:///{db_path_or_url}'
        self.engine = create_async_engine(sqlite_db_path, echo=True)
        self.SessionLocal = sessionmaker(
            bind=self.engine,
            expire_on_commit=False,
            class_=AsyncSession
        )

    def create_database(self, db_path):
        sqlite_db_path_sync = f'sqlite:///{db_path}'
        sync_engine = create_engine(sqlite_db_path_sync, echo=True)
        with sync_engine.begin() as conn:
            Base.metadata.create_all(bind=conn)
        txt.print(">>> Database and tables created successfully.")

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

    async def add_entity_async(self, entity):
        async with self.get_session_async() as session:
            try:
                session.add(entity)
            except Exception as e:
                txt.print(f"Failed to add entity: {e}")
                raise

    async def get_entity_by_id_async(self, entity_class, entity_id):
        async with self.get_session_async() as session:
            try:
                result = await session.execute(select(entity_class).filter(entity_class.id == entity_id))
                return result.scalars().first()
            except Exception as e:
                txt.print(f"Failed to retrieve entity: {e}")
                raise

    async def get_all_entities_async(self, entity_class):
        async with self.get_session_async() as session:
            try:
                result = await session.execute(select(entity_class))
                return result.scalars().all()
            except Exception as e:
                txt.print(f"Failed to retrieve entities: {e}")
                raise

    async def update_entity_async(self, entity_class, entity_id, **kwargs):
        async with self.get_session_async() as session:
            try:
                result = await session.execute(select(entity_class).filter(entity_class.id == entity_id))
                entity = result.scalars().first()
                if not entity:
                    raise ValueError(f"{entity_class.__name__} not found")

                for key, value in kwargs.items():
                    if hasattr(entity, key):
                        setattr(entity, key, value)

                session.add(entity)
            except Exception as e:
                txt.print(f"Failed to update entity: {e}")
                raise

    async def delete_entity_async(self, entity_class, entity_id):
        async with self.get_session_async() as session:
            try:
                result = await session.execute(select(entity_class).filter(entity_class.id == entity_id))
                entity = result.scalars().first()
                if entity:
                    await session.delete(entity)
                else:
                    raise ValueError(f"{entity_class.__name__} not found")
            except Exception as e:
                txt.print(f"Failed to delete entity: {e}")
                raise