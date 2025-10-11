from uuid import UUID

from database.entities import Base, LlmOperationEntity, LlmOperationTypeEntity
from database.generic_datacontext import GenericDataContext


class LlmOperationRepository:
    def __init__(self, db_path_or_url="database/conversation_database.db"):
        self.data_context = GenericDataContext(Base, db_path_or_url)

    async def get_or_create_operation_type_async(self, operation_type_name: str) -> UUID:
        """
        Get or create an LLM operation type by name.

        Args:
            operation_type_name: Name of the operation type (e.g., "STT", "TTS")

        Returns:
            UUID of the operation type
        """
        try:
            # Try to get existing operation type
            operation_type_entity = await self.data_context.get_first_entity_async(
                LlmOperationTypeEntity,
                filters=[LlmOperationTypeEntity.name == operation_type_name],
                fails_if_not_found=False,
            )

            if operation_type_entity:
                return operation_type_entity.id

            # Create new operation type if it doesn't exist
            new_operation_type = LlmOperationTypeEntity(name=operation_type_name)
            created_entity = await self.data_context.add_entity_async(new_operation_type)
            return created_entity.id

        except Exception as e:
            print(f"Failed to get or create operation type '{operation_type_name}': {e}")
            raise

    async def add_llm_operation_async(
        self,
        operation_type_name: str,
        provider: str,
        model: str,
        tokens_or_duration: float,
        price_per_unit: float,
        cost_usd: float,
        conversation_id: UUID | None = None,
        message_id: UUID | None = None,
        stream_id: str | None = None,
        call_sid: str | None = None,
        phone_number: str | None = None,
    ) -> bool:
        """
        Add a new LLM operation to the database.

        Args:
            operation_type_name: Type of operation ("STT", "TTS", etc.)
            provider: Provider name (e.g., "google", "openai")
            model: Model name used
            tokens_or_duration: Number of tokens/characters or duration in seconds
            price_per_unit: Price per unit in USD
            cost_usd: Total cost in USD
            conversation_id: Optional conversation ID
            message_id: Optional message ID
            stream_id: Optional stream ID for tracking
            call_sid: Optional Twilio call SID
            phone_number: Optional phone number

        Returns:
            True if successful, False otherwise
        """
        try:
            # Get or create operation type
            operation_type_id = await self.get_or_create_operation_type_async(operation_type_name)

            # Convert cost to dollar cents
            cost_dollar_cents = cost_usd * 100

            # Create operation entity
            llm_operation = LlmOperationEntity(
                llm_operation_type_id=operation_type_id,
                conversation_id=conversation_id,
                message_id=message_id,
                tokens_or_duration=tokens_or_duration,
                provider=provider,
                model=model,
                price_per_unit=price_per_unit,
                cost_dollar_cents=cost_dollar_cents,
                stream_id=stream_id,
                call_sid=call_sid,
                phone_number=phone_number,
            )

            await self.data_context.add_entity_async(llm_operation)
            return True

        except Exception as e:
            print(f"Failed to add LLM operation: {e}")
            return False

    async def get_operations_by_conversation_async(self, conversation_id: UUID) -> list[LlmOperationEntity]:
        """Get all LLM operations for a specific conversation."""
        try:
            operations = await self.data_context.get_all_entities_async(
                entity_class=LlmOperationEntity,
                filters=[LlmOperationEntity.conversation_id == conversation_id]
            )
            return operations
        except Exception as e:
            print(f"Failed to retrieve LLM operations for conversation {conversation_id}: {e}")
            return []

    async def get_total_cost_by_conversation_async(self, conversation_id: UUID) -> float:
        """
        Get the total cost (in USD) for all LLM operations in a conversation.

        Returns:
            Total cost in USD
        """
        operations = await self.get_operations_by_conversation_async(conversation_id)
        total_cents = sum(op.cost_dollar_cents for op in operations)
        return total_cents / 100  # Convert cents to dollars
