import httpx
from uuid import UUID
from typing import Any, Dict, AsyncGenerator
from api_client.request_models.user_request_model import UserRequestModel
from api_client.request_models.conversation_request_model import ConversationRequestModel
from api_client.request_models.query_asking_request_model import QueryAskingRequestModel, QueryNoConversationRequestModel

class StudiRAGInferenceClient:
    """
    Async client for interacting with the /rag/inference endpoints.
    """
    def __init__(self, host_base_name: str | None = None, host_port: int | None = None, is_ssh: bool = False):
        # Read host and port from environment if not provided
        import os
        self.host_base_name = host_base_name or os.getenv("RAG_HOST", "localhost")
        self.host_port = host_port or int(os.getenv("RAG_PORT", "8281"))
        self.is_ssh = is_ssh
        #
        self.host_base_url = f"http{'s' if is_ssh else ''}://{self.host_base_name}:{self.host_port}"
        self.client = httpx.AsyncClient(base_url=self.host_base_url)

    async def reinitialize(self) -> None:
        """POST /rag/inference/reinitialize: Reinitialize the service."""
        try:
            resp = await self.client.post("/rag/inference/reinitialize")
            resp.raise_for_status()
        except httpx.ConnectError as exc:
            raise RuntimeError(f"Cannot connect to RAG inference server at {self.host_base_url}") from exc

    async def create_or_retrieve_user(self, user_request_model: UserRequestModel) -> Dict[str, Any]:
        """PATCH /rag/inference/user/sync: Create or retrieve a user."""
        try:
            resp = await self.client.patch("/rag/inference/user/sync", json=user_request_model.to_dict())
            resp.raise_for_status()
            return resp.json()
        except httpx.ConnectError as exc:
            raise RuntimeError(f"Cannot connect to RAG inference server at {self.host_base_url}") from exc

    async def create_new_conversation(self, conversation_request_model: ConversationRequestModel) -> Dict[str, Any]:
        """POST /rag/inference/conversation/create: Create a new conversation."""
        try:
            resp = await self.client.post("/rag/inference/conversation/create", json=conversation_request_model.to_dict())
            resp.raise_for_status()
            return resp.json()
        except httpx.ConnectError as exc:
            raise RuntimeError(f"Cannot connect to RAG inference server at {self.host_base_url}") from exc

    async def add_message_to_conversation(self, conversation_id: str, new_message: str) -> Dict[str, Any]:
        """POST /rag/inference/conversation/add-message: Add a message to a conversation."""
        try:
            request_model = QueryAskingRequestModel(conversation_id=UUID(conversation_id), user_query_content=new_message)
            resp = await self.client.post("/rag/inference/conversation/add-external-message", json=request_model.to_dict())
            resp.raise_for_status()
            return resp.json()
        except httpx.ConnectError as exc:
            raise RuntimeError(f"Cannot connect to RAG inference server at {self.host_base_url}") from exc

    async def rag_query_stream_async(self, query_asking_request_model: QueryAskingRequestModel) -> AsyncGenerator[str, None]:
        """POST /rag/inference/conversation/ask-question/stream: Stream RAG answer for a conversation."""
        try:
            async with self.client.stream(
                "POST", "/rag/inference/conversation/ask-question/stream", json=query_asking_request_model.to_dict()
            ) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if line:
                        yield line
        except httpx.ConnectError as exc:
            raise RuntimeError(f"Cannot connect to RAG inference server at {self.host_base_url}") from exc

    async def rag_query_no_conversation_async(self, query_no_conversation_request_model: QueryNoConversationRequestModel) -> Dict[str, Any]:
        """POST /rag/inference/no-conversation/ask-question: Get RAG answer without conversation (not streamed)."""
        try:
            resp = await self.client.post(
                "/rag/inference/no-conversation/ask-question",
                json=query_no_conversation_request_model.to_dict()
            )
            resp.raise_for_status()
            return resp.json()
        except httpx.ConnectError as exc:
            raise RuntimeError(f"Cannot connect to RAG inference server at {self.host_base_url}") from exc

    async def rag_query_no_conversation_streaming_async(self, query_no_conversation_request_model: QueryNoConversationRequestModel) -> AsyncGenerator[str, None]:
        """POST /rag/inference/no-conversation/ask-question/stream: Stream RAG answer without conversation."""
        try:
            async with self.client.stream(
                "POST", "/rag/inference/no-conversation/ask-question/stream", json=query_no_conversation_request_model.to_dict()
            ) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if line:
                        yield line
        except httpx.ConnectError as exc:
            raise RuntimeError(f"Cannot connect to RAG inference server at {self.host_base_url}") from exc

    async def aclose(self):
        await self.client.aclose()
