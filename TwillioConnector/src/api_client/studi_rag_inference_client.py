import httpx
from typing import Any, Dict, AsyncGenerator
from api_client.request_models.user_request_model import UserRequestModel
from api_client.request_models.conversation_request_model import ConversationRequestModel
from api_client.request_models.query_asking_request_model import QueryAskingRequestModel, QueryNoConversationRequestModel

class StudiRAGInferenceClient:
    """
    Async client for interacting with the /rag/inference endpoints.
    """
    def __init__(self, host_base_name: str = "localhost", host_port: int = 8281, is_ssh: bool = False):
        self.host_base_name = host_base_name
        self.host_port = host_port
        self.is_ssh = is_ssh
        #
        self.host_base_url = f"http{'s' if is_ssh else ''}://{host_base_name}:{host_port}"
        self.client = httpx.AsyncClient(base_url=self.host_base_url)

    async def reinitialize(self) -> None:
        """POST /rag/inference/reinitialize: Reinitialize the service."""
        resp = await self.client.post("/rag/inference/reinitialize")
        resp.raise_for_status()

    async def create_or_retrieve_user(self, user_request_model: UserRequestModel) -> Dict[str, Any]:
        """PATCH /rag/inference/user/sync: Create or retrieve a user."""
        resp = await self.client.patch("/rag/inference/user/sync", json=user_request_model.to_dict())
        resp.raise_for_status()
        return resp.json()

    async def create_new_conversation(self, conversation_request_model: ConversationRequestModel) -> Dict[str, Any]:
        """POST /rag/inference/conversation/create: Create a new conversation."""
        resp = await self.client.post("/rag/inference/conversation/create", json=conversation_request_model.to_dict())
        resp.raise_for_status()
        return resp.json()

    async def rag_query_stream_async(self, query_asking_request_model: QueryAskingRequestModel) -> AsyncGenerator[str, None]:
        """POST /rag/inference/conversation/ask-question/stream: Stream RAG answer for a conversation."""
        async with self.client.stream(
            "POST", "/rag/inference/conversation/ask-question/stream", json=query_asking_request_model.to_dict()
        ) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if line:
                    yield line

    async def rag_query_no_conversation_async(self, query_no_conversation_request_model: QueryNoConversationRequestModel) -> Dict[str, Any]:
        """POST /rag/inference/no-conversation/ask-question: Get RAG answer without conversation (not streamed)."""
        resp = await self.client.post(
            "/rag/inference/no-conversation/ask-question",
            json=query_no_conversation_request_model.to_dict()
        )
        resp.raise_for_status()
        return resp.json()

    async def rag_query_no_conversation_streaming_async(self, query_no_conversation_request_model: QueryNoConversationRequestModel) -> AsyncGenerator[str, None]:
        """POST /rag/inference/no-conversation/ask-question/stream: Stream RAG answer without conversation."""
        async with self.client.stream(
            "POST", "/rag/inference/no-conversation/ask-question/stream", json=query_no_conversation_request_model.to_dict()
        ) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if line:
                    yield line

    async def aclose(self):
        await self.client.aclose()
