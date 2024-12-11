import os
import pytest
import asyncio
from uuid import uuid4
from sqlalchemy import Column, String
from sqlalchemy.ext.declarative import declarative_base
#
from common_tools.database.generic_datacontext import GenericDataContext

pytest_plugins = ["pytest_asyncio"]

Base = declarative_base()

# Sample Entity for Testing
class SampleEntity(Base):
    __tablename__ = "sample_entities"

    id = Column(String, primary_key=True)
    name = Column(String, nullable=False)


class TestGenericDataContext:
    db_path_or_url = "tests/infrastructure/generic_test.db"

    def setup_method(self):
        self.data_context = GenericDataContext(Base, db_path_or_url=self.db_path_or_url)
        asyncio.run(self.data_context.empty_all_database_tables_async())

    def teardown_method(self):
        asyncio.run(self.data_context.empty_all_database_tables_async())
        self.data_context.engine.dispose()
        if os.path.exists(self.db_path_or_url):
            os.remove(self.db_path_or_url)

    @pytest.mark.asyncio
    async def test_add_entity(self):
        entity = SampleEntity(id=str(uuid4()), name="Test Entity")
        await self.data_context.add_entity_async(entity)

        result = await self.data_context.get_entity_by_id_async(SampleEntity, entity.id)
        assert result is not None
        assert result.id == entity.id
        assert result.name == entity.name

    @pytest.mark.asyncio
    async def test_get_entity_by_id(self):
        entity = SampleEntity(id=str(uuid4()), name="Test Entity")
        await self.data_context.add_entity_async(entity)

        result = await self.data_context.get_entity_by_id_async(SampleEntity, entity.id)
        assert result is not None
        assert result.id == entity.id

    @pytest.mark.asyncio
    async def test_get_all_entities(self):
        entities = [
            SampleEntity(id=str(uuid4()), name=f"Entity {i}") for i in range(3)
        ]
        for entity in entities:
            await self.data_context.add_entity_async(entity)

        results = await self.data_context.get_all_entities_async(SampleEntity)
        assert len(results) == len(entities)

    @pytest.mark.asyncio
    async def test_update_entity(self):
        entity = SampleEntity(id=str(uuid4()), name="Original Name")
        await self.data_context.add_entity_async(entity)

        await self.data_context.update_entity_async(
            SampleEntity, entity.id, name="Updated Name"
        )
        updated_entity = await self.data_context.get_entity_by_id_async(
            SampleEntity, entity.id
        )
        assert updated_entity.name == "Updated Name"

    @pytest.mark.asyncio
    async def test_delete_entity(self):
        entity = SampleEntity(id=str(uuid4()), name="Test Entity")
        await self.data_context.add_entity_async(entity)

        await self.data_context.delete_entity_async(SampleEntity, entity.id)
        result = await self.data_context.get_entity_by_id_async(
            SampleEntity, entity.id, fails_if_not_found=False
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_empty_all_database_tables(self):
        entities = [
            SampleEntity(id=str(uuid4()), name=f"Entity {i}") for i in range(5)
        ]
        for entity in entities:
            await self.data_context.add_entity_async(entity)

        await self.data_context.empty_all_database_tables_async()
        results = await self.data_context.get_all_entities_async(SampleEntity)
        assert len(results) == 0
