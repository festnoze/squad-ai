from infrastructure.entities.context_entity import ContextEntity
from models.context import Context


class ContextConverters:
    @staticmethod
    def convert_context_entity_to_model(context_entity: ContextEntity) -> Context:
        """Convert a ContextEntity to a Context model.

        Args:
            context_entity: The database entity to convert

        Returns:
            Context model instance
        """
        return Context(
            id=context_entity.id,
            context_filter=context_entity.context_filter,
            context_full=context_entity.context_full,
            created_at=context_entity.created_at,
            updated_at=context_entity.updated_at,
            deleted_at=context_entity.deleted_at,
        )

    @staticmethod
    def convert_context_model_to_entity(context: Context) -> ContextEntity:
        """Convert a Context model to a ContextEntity.

        Args:
            context: The Context model to convert

        Returns:
            ContextEntity instance
        """
        return ContextEntity(
            id=context.id,
            context_filter=context.context_filter,
            context_full=context.context_full,
            created_at=context.created_at,
            updated_at=context.updated_at,
            deleted_at=context.deleted_at,
        )
