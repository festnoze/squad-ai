from abc import ABC, abstractmethod
from collections.abc import AsyncGenerator
from typing import Any

from api_client.request_models.query_asking_request_model import (
    QueryAskingRequestModel,
    QueryNoConversationRequestModel,
)


class RagQueryInterface(ABC):
    @abstractmethod
    async def rag_query_stream_async(
        self, query_asking_request_model: QueryAskingRequestModel, interrupt_flag: dict | None = None, timeout: int = 80
    ) -> AsyncGenerator[str, None]:
        """Stream RAG answer for a conversation.

        Args:
            query_asking_request_model: Model containing the query data
            interrupt_flag: Mutable object (like a dict {"interrupted": False}) with a modifiable value that can be externally changed to interrupt the streaming
            timeout: Request timeout in seconds

        Yields:
            String segments of the RAG response
        """
        pass

    @abstractmethod
    async def rag_query_no_conversation_async(
        self, query_no_conversation_request_model: QueryNoConversationRequestModel, timeout: int = 80
    ) -> dict[str, Any]:
        """Get RAG answer without conversation (not streamed).

        Args:
            query_no_conversation_request_model: The query request model for no-conversation queries
            timeout: Request timeout in seconds

        Returns:
            Dictionary containing the RAG response data
        """
        pass

    @abstractmethod
    async def rag_query_no_conversation_streaming_async(
        self,
        query_no_conversation_request_model: QueryNoConversationRequestModel,
        interrupt_flag: dict | None = None,
        timeout: int = 80,
    ) -> AsyncGenerator[str, None]:
        """Stream RAG answer without conversation.

        Args:
            query_no_conversation_request_model: The query request model for streaming no-conversation queries
            interrupt_flag: Optional interrupt flag (dictionary with "interrupted" key) to stop streaming
            timeout: Request timeout in seconds for the request

        Yields:
            String segments of the RAG response
        """
        pass

    @abstractmethod
    async def test_client_connection_async(self) -> bool:
        """Test the connection to the RAG inference server"""
        pass
