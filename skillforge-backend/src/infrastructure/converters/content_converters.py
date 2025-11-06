from typing import Any

from infrastructure.entities.content_entity import ContentEntity
from models.content import Content


class ContentConverters:
    @staticmethod
    def _convert_ids_to_string_in_dict(data: dict[Any, Any] | list[Any] | str | int | None) -> dict[Any, Any] | list[Any] | str | int | None:
        """Recursively convert all ID fields to strings in a dictionary.

        This ensures consistent ID types in JSON fields (filter, context_metadata)
        regardless of whether they were passed as int or str in the request.

        Args:
            data: Dictionary, list, or primitive value potentially containing ID fields

        Returns:
            Data structure with all ID fields converted to strings
        """
        # Handle primitives and None
        if data is None or isinstance(data, (str, int, float, bool)):
            return data

        # Handle lists
        if isinstance(data, list):
            return [ContentConverters._convert_ids_to_string_in_dict(item) for item in data]

        # Handle dictionaries
        if isinstance(data, dict):
            result: dict[Any, Any] = {}
            id_field_names = [
                "parcours_id",
                "parcours_code",
                "promotion_id",
                "matiere_id",
                "module_id",
                "theme_id",
                "ressource_id",
                "ressource_object_id",
                "ressource_url",  # Keep this as string for URL comparisons
            ]

            for key, value in data.items():
                # Convert ID fields to string
                if key in id_field_names and value is not None:
                    result[key] = str(value)
                # Recursively process nested dictionaries
                elif isinstance(value, dict):
                    result[key] = ContentConverters._convert_ids_to_string_in_dict(value)
                # Process lists
                elif isinstance(value, list):
                    result[key] = [ContentConverters._convert_ids_to_string_in_dict(item) for item in value]
                else:
                    result[key] = value

            return result

        # This line should never be reached, but satisfy type checker
        return data  # pragma: no cover

    @staticmethod
    def convert_content_entity_to_model(content_entity: ContentEntity) -> Content:
        """Convert a ContentEntity to a Content model.

        Handles NULL values from database by converting them to empty strings.
        """
        return Content(
            id=content_entity.id,
            filter=content_entity.filter,
            context_metadata=content_entity.context_metadata,
            content_full=content_entity.content_full or "",
            content_html=content_entity.content_html or "",
            content_media=content_entity.content_media or {},
            content_summary_full=content_entity.content_summary_full or "",
            content_summary_light=content_entity.content_summary_light or "",
            content_summary_compact=content_entity.content_summary_compact or "",
            created_at=content_entity.created_at,
            updated_at=content_entity.updated_at,
            deleted_at=content_entity.deleted_at,
        )

    @staticmethod
    def convert_content_model_to_entity(content: Content) -> ContentEntity:
        """Convert a Content model to a ContentEntity.

        This method ensures all IDs in filter and context_metadata are converted to strings
        for consistent database storage and querying.
        """
        return ContentEntity(
            filter=ContentConverters._convert_ids_to_string_in_dict(content.filter),
            context_metadata=ContentConverters._convert_ids_to_string_in_dict(content.context_metadata),
            content_full=content.content_full,
            content_html=content.content_html or "",
            content_media=content.content_media or {},
            content_summary_full=content.content_summary_full or "",
            content_summary_light=content.content_summary_light or "",
            content_summary_compact=content.content_summary_compact or "",
            id=content.id,
            created_at=content.created_at,
            updated_at=content.updated_at,
            deleted_at=content.deleted_at,
        )
