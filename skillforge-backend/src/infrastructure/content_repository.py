from abc import ABC, abstractmethod
from sqlalchemy import select
from common_tools.database.generic_datacontext import GenericDataContext  # type: ignore[import-untyped]
from infrastructure.entities import Base
from infrastructure.entities.content_entity import ContentEntity
from infrastructure.converters.content_converters import ContentConverters
from models.content import Content
from envvar import EnvHelper


class ContentRepository(ABC):
    """Abstract base class for content repositories."""

    @abstractmethod
    async def aget_content_by_filter(self, filter: dict) -> Content | None:
        """Retrieve a content by its JSON content filter.

        Args:
            filter: Filter JSON dictionary to search Content by

        Returns:
            Content model if found, None otherwise
        """
        pass

    @abstractmethod
    async def apersist_content(self, content: Content) -> None:
        """Persist a content in the repository.

        Args:
            content: Content model to persist
        """
        pass


class ContentRepositoryStudi(ContentRepository):
    def __init__(self, db_path_or_url: str | None = None) -> None:
        if db_path_or_url:
            self.db_path_or_url = db_path_or_url
        else:
            username = EnvHelper.get_postgres_username()
            password = EnvHelper.get_postgres_password()
            host = EnvHelper.get_postgres_host()
            dbname = EnvHelper.get_postgres_database_name()
            self.db_path_or_url = f"postgresql://{username}:{password}@{host}/{dbname}"
        #
        self.data_context = GenericDataContext(Base, self.db_path_or_url)

    async def aget_content_by_filter(self, filter: dict) -> Content | None:
        """Retrieve a content by its JSON content filter. If not found, scrapes the content from URL.

        Args:
            filter: Filter JSON dictionary to search Content by
        Returns:
            Content model if found or scraped, None otherwise
        """
        try:
            async with self.data_context.get_session_async() as session:
                stmt = select(ContentEntity).where(ContentEntity.filter == filter)
                result = await session.execute(stmt)
                content_entity = result.unique().scalar_one_or_none()
                if content_entity:
                    return ContentConverters.convert_content_entity_to_model(content_entity)
            return None
        except Exception as e:
            print(f"Failed to get content by filter: {e}")
            return None

    async def apersist_content(self, content: Content) -> None:
        """Persist a content in the repository.

        Args:
            content: Content model to persist
        """
        try:
            content_entity: ContentEntity = ContentConverters.convert_content_model_to_entity(content)
            async with self.data_context.get_session_async() as session:
                session.add(content_entity)
                await session.commit()
        except Exception as e:
            print(f"Failed to persist content: {e}")
