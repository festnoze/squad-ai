import asyncio
from contextlib import asynccontextmanager
import os
from uuid import UUID
from typing import Optional, List

from sqlalchemy.sql.expression import BinaryExpression
from sqlalchemy import create_engine, delete, func, select
from sqlalchemy import Column, String, Integer, ForeignKey, Table, DateTime
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import relationship, declarative_base
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import sessionmaker, joinedload

from common_tools.helpers.txt_helper import txt
from common_tools.helpers.file_helper import file

class GenericDataContext:
    def __init__(self, base_entities, db_path_or_url='database.db', log_queries_to_terminal=False):
        if ':' not in db_path_or_url:
            source_path = os.environ.get("PYTHONPATH").split(';')[-1]
            db_path_or_url = os.path.join(source_path.replace('/', '\\'), db_path_or_url.replace('/', '\\'))
        
        self.base_entities = base_entities
        self.db_path_or_url = db_path_or_url
        self.sqlite_sync_db_path = f'sqlite:///{db_path_or_url}'
        self.sqlite_async_db_path = f'sqlite+aiosqlite:///{db_path_or_url}'

        if 'http' not in self.db_path_or_url and not file.exists(self.db_path_or_url):
            txt.print(f"/!\\ Database file not found at path: {self.db_path_or_url}")
            self.create_database()

        self.engine = create_async_engine(self.sqlite_async_db_path, echo=log_queries_to_terminal)
        self.SessionLocal = sessionmaker(
                                bind=self.engine,
                                expire_on_commit=False,
                                class_=AsyncSession)

    def create_database(self):
        sync_engine = create_engine(self.sqlite_sync_db_path, echo=True)
        with sync_engine.begin() as conn:
            self.base_entities.metadata.create_all(bind=conn)
        txt.print(">>> Database and tables created successfully.")

    @asynccontextmanager
    async def new_transaction_async(self):
        transaction = self.SessionLocal()
        try:
            yield transaction
            await transaction.commit()
        except Exception:
            await transaction.rollback()
            raise
        finally:
            await transaction.close()
    
    @asynccontextmanager
    async def read_db_async(self):
        async with self.SessionLocal() as session:
            try:
                yield session
            except Exception as e:
                raise RuntimeError(f"Error during read operation: {e}")

    # AVOID - As it doesn't automatically map ORM objects
    @asynccontextmanager
    async def low_level_db_async(self):
        async with self.engine.connect() as connection:
            try:
                yield connection
            except Exception as e:
                raise RuntimeError(f"Error during read operation: {e}")
            
    async def does_exist_entity_by_id_async(self, entity_class, entity_id) -> bool:
        id_from_db = await self.get_first_entity_async(entity_class, 
                                                filters=[entity_class.id == entity_id], 
                                                selected_columns=[entity_class.id], 
                                                fails_if_not_found=False) 
        return id_from_db is not None

    async def get_entity_by_id_async(self, entity_class, entity_id, selected_columns: Optional[List] = None, to_join_list: Optional[List] = None, fails_if_not_found=True):
        filters = [entity_class.id == entity_id]
        return await self.get_first_entity_async(entity_class=entity_class, filters=filters, selected_columns=selected_columns, to_join_list=to_join_list, fails_if_not_found=fails_if_not_found)
    
    async def get_first_entity_async(self, entity_class, filters: Optional[List[BinaryExpression]] = None, selected_columns: Optional[List] = None, to_join_list: Optional[List] = None, fails_if_not_found: bool = True):
        query = select(*selected_columns) if selected_columns else select(entity_class)
        
        if filters:
            for filter_condition in filters:
                query = query.filter(filter_condition)

        if to_join_list:
            query = query.options(*[joinedload(to_join) for to_join in to_join_list])

        async with self.read_db_async() as session:
            try:
                results = await session.execute(query)
                result = results.scalars().first()
                if fails_if_not_found and not result:
                    raise ValueError(f"No entity found for '{entity_class.__name__}' with the specified filters.")
                return result
            except Exception as e:
                txt.print(f"/!\\ Fails to retrieve first entity: {e}")
                raise

    async def get_all_entities_async(self, entity_class, filters: Optional[List[BinaryExpression]] = None):
        query = select(entity_class)
        if filters:
            for filter_condition in filters:
                query = query.filter(filter_condition)

        async with self.read_db_async() as session:
            try:
                results = await session.execute(query)
                return results.unique().scalars().all()
            except Exception as e:
                txt.print(f"/!\\ Fails to retrieve entities: {e}")
                raise
            
    async def count_entities_async(self, entity_class, filters: Optional[List[BinaryExpression]] = None):
        query = select(func.count())
        if filters:
            for filter_condition in filters:
                query = query.where(filter_condition)

        async with self.read_db_async() as session:
            try:
                results = await session.execute(query)
                return results.scalar()
            except Exception as e:
                txt.print(f"/!\\ Fails to count entities: {e}")
                return 0

    async def add_entity_async(self, entity) -> any:
        results = await self.add_entities_async(entity)
        return results[0]
    
    async def add_entities_async(self, *args) -> list:
        async with self.new_transaction_async() as transaction:
            try:
                # Add all entities provided in *args
                for entity in args:
                    transaction.add(entity)
                return list(args)
            except Exception as e:
                txt.print(f"/!\\ Fails to add entities: {e}")
                raise

    async def update_entity_async(self, entity_class, entity_id, **kwargs):
        async with self.new_transaction_async() as transaction:
            try:
                result = await transaction.execute(select(entity_class).filter(entity_class.id == entity_id))
                entity = result.scalars().first()
                if not entity: 
                    raise ValueError(f"{entity_class.__name__} with id: {str(entity_id)} not found")

                for key, value in kwargs.items():
                    if hasattr(entity, key):
                        setattr(entity, key, value)

                transaction.add(entity)
            except Exception as e:
                txt.print(f"/!\\ Fails to update entity: {e}")
                raise

    async def delete_entity_async(self, entity_class, entity_id):
        async with self.new_transaction_async() as transaction:
            try:
                result = await transaction.execute(select(entity_class).filter(entity_class.id == entity_id))
                entity = result.scalars().first()
                if entity:
                    await transaction.delete(entity)
                else:
                    raise ValueError(f"{entity_class.__name__} not found")
            except Exception as e:
                txt.print(f"/!\\ Fails to delete entity: {e}")
                raise

    async def empty_all_database_tables_async(self):
        async with self.new_transaction_async() as transaction:
            # Delete all tables records, tables in the reverse order to avoid foreign key integrity errors
            for table in reversed(self.base_entities.metadata.sorted_tables):
                await transaction.execute(delete(table))