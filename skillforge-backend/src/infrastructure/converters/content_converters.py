from infrastructure.entities.content_entity import ContentEntity
from models.content import Content


class ContentConverters:
    @staticmethod
    def convert_content_entity_to_model(content_entity: ContentEntity) -> Content:
        """Convert a ContentEntity to a Content model"""
        return Content(
            id=content_entity.id,
            filter=content_entity.filter,
            context_metadata=content_entity.context_metadata,
            content_full=content_entity.content_full,
            content_html=content_entity.content_html,
            content_media=content_entity.content_media,
            created_at=content_entity.created_at,
            updated_at=content_entity.updated_at,
            deleted_at=content_entity.deleted_at,
        )

    @staticmethod
    def convert_content_model_to_entity(content: Content) -> ContentEntity:
        """Convert a Content model to a ContentEntity"""
        return ContentEntity(
            filter=content.filter,
            context_metadata=content.context_metadata,
            content_full=content.content_full,
            content_html=content.content_html,
            content_media=content.content_media,
            id=content.id,
            created_at=content.created_at,
            updated_at=content.updated_at,
            deleted_at=content.deleted_at,
        )
