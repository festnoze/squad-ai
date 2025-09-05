import logging
import os
from contextlib import asynccontextmanager

from sqlalchemy import create_engine, delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import joinedload, sessionmaker
from sqlalchemy.sql.expression import BinaryExpression
from utils.envvar import EnvHelper

class GenericDataContext:
    def __init__(self, base_entities, db_path_or_url="database.db", log_queries_to_terminal=False):
        db_full_path_and_name = None
        if "http" not in db_path_or_url:
            source_path = EnvHelper.get_python_paths()[0]
            db_full_path_and_name = os.path.join(
                source_path.replace("\\", "/"), db_path_or_url.replace("\\", "/")
            ).replace("\\", "/")

        self.base_entities = base_entities
        self.db_path_or_url = db_full_path_and_name or db_path_or_url
        self.sqlite_sync_db_path = f"sqlite:///{self.db_path_or_url}"
        self.sqlite_async_db_path = f"sqlite+aiosqlite:///{self.db_path_or_url}"
        self.logger = logging.getLogger(__name__)

        if "http" not in self.db_path_or_url and not os.path.exists(self.db_path_or_url):
            self.logger.error(f"/!\\ Database file not found at path: {self.db_path_or_url}")
            self.create_database()

        self.engine = create_async_engine(self.sqlite_async_db_path, echo=log_queries_to_terminal)
        self.SessionLocal = sessionmaker(bind=self.engine, expire_on_commit=False, class_=AsyncSession)

    def create_database(self):
        self.logger.info(">>> Recreating full database & tables")
        if "http" not in self.db_path_or_url:
            parent_dir = os.path.dirname(self.db_path_or_url)
            if parent_dir and not os.path.exists(parent_dir):
                os.makedirs(parent_dir, exist_ok=True)
                self.logger.info(f"Created directory: {parent_dir}")

        sync_engine = create_engine(self.sqlite_sync_db_path, echo=True)
        with sync_engine.begin() as conn:
            self.base_entities.metadata.create_all(bind=conn)
        self.logger.info(">>> Database & tables creation completed successfully.")

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
        id_from_db = await self.get_first_entity_async(
            entity_class,
            filters=[entity_class.id == entity_id],
            selected_columns=[entity_class.id],
            fails_if_not_found=False,
        )
        return id_from_db is not None

    async def get_entity_by_id_async(
        self,
        entity_class,
        entity_id,
        selected_columns: list | None = None,
        to_join_list: list | None = None,
        fails_if_not_found=True,
    ):
        filters = [entity_class.id == entity_id]
        return await self.get_first_entity_async(
            entity_class=entity_class,
            filters=filters,
            selected_columns=selected_columns,
            to_join_list=to_join_list,
            fails_if_not_found=fails_if_not_found,
        )

    async def get_first_entity_async(
        self,
        entity_class,
        filters: list[BinaryExpression] | None = None,
        selected_columns: list | None = None,
        to_join_list: list | None = None,
        fails_if_not_found: bool = True,
    ):
        query = select(*selected_columns) if selected_columns else select(entity_class)

        if filters:
            for filter_condition in filters:
                query = query.filter(filter_condition)

        if to_join_list:
            query = query.options(*[joinedload(to_join) for to_join in to_join_list])

        async with self.read_db_async() as session:
            try:
                results = await session.execute(query)
                if selected_columns:
                    # If only one column selected, return scalar
                    if len(selected_columns) == 1:
                        result = results.scalars().first()
                    else:
                        # Multiple columns selected
                        row = results.first()
                        if row is not None:
                            result = row
                        else:
                            result = None
                else:
                    # If no columns are selected, return the entire entity
                    result = results.scalars().first()

                if fails_if_not_found and not result:
                    filters_str = "".join([str(filter) for filter in filters]) if filters else ""
                    raise ValueError(f"No entity found for '{entity_class.__name__}' with filters: '{filters_str}'.")
                return result
            except Exception as e:
                filters_str = "".join([str(filter) for filter in filters]) if filters else ""
                self.logger.error(f'/!\\ Fails to retrieve first entity with filters: "{filters_str}" - Error: {e}')
                raise

    async def get_all_entities_async(self, entity_class, filters: list[BinaryExpression] | None = None):
        query = select(entity_class)
        if filters:
            for filter_condition in filters:
                query = query.filter(filter_condition)

        async with self.read_db_async() as session:
            try:
                results = await session.execute(query)
                return results.unique().scalars().all()
            except Exception as e:
                self.logger.error(f"/!\\ Fails to retrieve entities: {e}")
                raise

    async def count_entities_async(self, entity_class, filters: list[BinaryExpression] | None = None):
        query = select(func.count())
        if filters:
            for filter_condition in filters:
                query = query.where(filter_condition)

        async with self.read_db_async() as session:
            try:
                results = await session.execute(query)
                return results.scalar()
            except Exception as e:
                self.logger.error(f"/!\\ Fails to count entities: {e}")
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
                await transaction.commit()
                return list(args)

            except Exception as e:
                self.logger.error(f"/!\\ Fails to add entities: {e}")
                raise

    async def update_entity_async(self, entity_class, entity_id, **kwargs):
        async with self.new_transaction_async() as transaction:
            try:
                result = await transaction.execute(select(entity_class).filter(entity_class.id == entity_id))
                entity = result.scalars().first()
                if not entity:
                    raise ValueError(f"{entity_class.__name__} with id: {entity_id!s} not found")

                for key, value in kwargs.items():
                    if hasattr(entity, key):
                        setattr(entity, key, value)

                transaction.add(entity)
                await transaction.commit()
            except Exception as e:
                self.logger.error(f"/!\\ Fails to update entity: {e}")
                raise

    async def delete_entity_async(self, entity_class, entity_id):
        async with self.new_transaction_async() as transaction:
            try:
                result = await transaction.execute(select(entity_class).filter(entity_class.id == entity_id))
                entity = result.scalars().first()
                if not entity:
                    raise ValueError(f"{entity_class.__name__} not found")

                await transaction.delete(entity)
                await transaction.commit()
            except Exception as e:
                self.logger.error(f"/!\\ Fails to delete entity: {e}")
                raise

    async def empty_all_database_tables_async(self):
        async with self.new_transaction_async() as transaction:
            # Delete all tables records, tables in the reverse order to avoid foreign key integrity errors
            for table in reversed(self.base_entities.metadata.sorted_tables):
                await transaction.execute(delete(table))
            await transaction.commit()

    async def close_async(self):
        """Close the async database engine and cleanup resources"""
        try:
            if hasattr(self, "engine") and self.engine:
                await self.engine.dispose()
                self.logger.info("Database engine closed successfully")
        except Exception as e:
            self.logger.error(f"Error closing database engine: {e}")
            raise
