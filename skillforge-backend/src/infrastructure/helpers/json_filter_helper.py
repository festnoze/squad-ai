"""Helper mixin for database-agnostic JSON filtering across repositories."""

from sqlalchemy import func, cast, String, and_
from common_tools.database.generic_datacontext import DatabaseType  # type: ignore[import-untyped]


class JsonFilterHelperMixin:
    """Mixin class providing database-agnostic JSON filtering capabilities.

    This mixin can be added to any repository class that has:
    - self.data_context: GenericDataContext instance
    - self.logger: logging.Logger instance

    Example:
        class MyRepository(JsonFilterHelperMixin):
            def __init__(self, db_path_or_url: str | None = None):
                self.logger = logging.getLogger(__name__)
                self.data_context = GenericDataContext(Base, db_path_or_url)

            async def get_by_metadata(self, metadata_filter: dict):
                filter_condition = self._build_json_containment_filter(
                    MyEntity.metadata_field,
                    metadata_filter
                )
                # Use filter_condition in query...
    """

    def _build_json_containment_filter(self, json_field, filter_dict: dict):
        """Build database-agnostic JSON containment filter for any JSON field.

        For PostgreSQL: Uses JSONB @> operator for efficient containment checks
        For SQLite: Uses JSON_EXTRACT function with string comparison for each key-value pair

        Args:
            json_field: SQLAlchemy column object representing the JSON field to filter
                       (e.g., Entity.json_column)
            filter_dict: JSON dictionary to filter by

        Returns:
            SQLAlchemy filter expression that can be used in WHERE clauses

        Example:
            # Filter by any JSON field
            filter_condition = self._build_json_containment_filter(
                MyEntity.metadata,
                {"course_id": 123, "user_id": 456}
            )

            # Use in query
            stmt = select(MyEntity).where(filter_condition)
        """
        if not hasattr(self, "data_context"):
            raise AttributeError("JsonFilterHelperMixin requires self.data_context to be set")

        if not hasattr(self, "logger"):
            raise AttributeError("JsonFilterHelperMixin requires self.logger to be set")

        if self.data_context.db_type == DatabaseType.POSTGRESQL:
            # PostgreSQL: Use JSONB containment operator (@>) for faster lookups
            return json_field.op("@>")(filter_dict)

        elif self.data_context.db_type == DatabaseType.SQLITE:
            # SQLite: Use json_extract() function for each key-value pair
            conditions = []
            for key, value in filter_dict.items():
                json_path = f"$.{key}"
                # json_extract returns the value as a string, so we compare as strings
                conditions.append(func.json_extract(json_field, json_path) == cast(str(value), String))

            # Combine all conditions with AND
            return and_(*conditions) if conditions else True

        else:
            # Fallback: direct equality (least efficient, but works)
            self.logger.warning(f"Using fallback equality filter for unknown database type: {self.data_context.db_type}")
            return json_field == filter_dict
