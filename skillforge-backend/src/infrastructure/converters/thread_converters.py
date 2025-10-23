from infrastructure.entities.thread_entity import ThreadEntity
from infrastructure.converters.message_converters import MessageConverters
from models.thread import Thread


class ThreadConverters:
    @staticmethod
    def convert_thread_entity_to_model(thread_entity: ThreadEntity) -> Thread:
        """Convert a ThreadEntity to a Thread model.

        Args:
            thread_entity: The database entity to convert

        Returns:
            Thread model instance
        """
        return Thread(
            id=thread_entity.id,
            user_id=thread_entity.user_id,
            context_id=thread_entity.context_id,
            created_at=thread_entity.created_at,
            messages=[MessageConverters.convert_message_entity_to_model(msg) for msg in thread_entity.messages] if thread_entity.messages else [],
        )

    @staticmethod
    def convert_thread_model_to_entity(thread: Thread) -> ThreadEntity:
        """Convert a Thread model to a ThreadEntity.

        Args:
            thread: The Thread model to convert

        Returns:
            ThreadEntity instance
        """
        return ThreadEntity(
            id=thread.id,
            user_id=thread.user_id,
            context_id=thread.context_id,
            created_at=thread.created_at,
            messages=[MessageConverters.convert_message_model_to_entity(msg) for msg in thread.messages] if thread.messages else [],
        )
