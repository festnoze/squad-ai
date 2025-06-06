import httpx
import asyncio
from uuid import UUID
from typing import Any, Dict, AsyncGenerator, Optional
from app.api_client.request_models.user_request_model import UserRequestModel
from app.api_client.request_models.conversation_request_model import ConversationRequestModel
from app.api_client.request_models.query_asking_request_model import QueryAskingRequestModel, QueryNoConversationRequestModel

class StudiRAGInferenceApiClient:
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

    async def get_user_last_conversation(self, user_id: UUID) -> Dict[str, Any]:
        """GET /rag/inference/conversation/last/user/{user_id}: Get the last conversation for a user."""
        try:
            resp = await self.client.get(f"/rag/inference/conversation/last/user/{str(user_id)}")
            resp.raise_for_status()
            return resp.json()
        except httpx.ConnectError as exc:
            raise RuntimeError(f"Cannot connect to RAG inference server at {self.host_base_url}") from exc

    async def add_external_ai_message_to_conversation(self, conversation_id: str, new_message: str) -> Dict[str, Any]:
        """POST /rag/inference/conversation/add-message: Add a message to a conversation."""
        try:
            request_model = QueryAskingRequestModel(conversation_id=UUID(conversation_id), user_query_content=new_message, display_waiting_message=False)
            resp = await self.client.post("/rag/inference/conversation/add-external-message", json=request_model.to_dict())
            resp.raise_for_status()
            return resp.json()
        except httpx.ConnectError as exc:
            raise RuntimeError(f"Cannot connect to RAG inference server at {self.host_base_url}") from exc

    async def rag_query_stream_async(self, query_asking_request_model: QueryAskingRequestModel, timeout: int = 60, interrupt_flag=None) -> AsyncGenerator[str, None]:
        """
        POST /rag/inference/conversation/ask-question/phone/stream: Stream RAG answer for a conversation.
        
        Args:
            query_asking_request_model: Model containing the query data
            timeout: Request timeout in seconds
            interrupt_flag: Mutable object (like a dict {"interrupted": False}) that can be modified externally
                            to interrupt the streaming
        """
        try:
            async with self.client.stream(
                "POST", 
                "/rag/inference/conversation/ask-question/phone/stream", 
                json=query_asking_request_model.to_dict(),
                timeout=httpx.Timeout(timeout)
            ) as resp:
                resp.raise_for_status()
                async for segment in self.stream_by_segment(resp, interrupt_flag):
                    yield segment

        except httpx.ReadTimeout:
            yield "Je suis désolé, mais je n'ai pas pu obtenir une réponse à temps. Pouvez-vous reformuler votre question?"
        except httpx.ConnectError as exc:
            yield f"Désolé, je ne peux pas me connecter au serveur de réponses pour le moment."
        except Exception as e:
            yield f"Une erreur s'est produite lors de la récupération de la réponse: {str(e)}"

    @staticmethod
    async def stream_by_segment(response_stream: httpx.Response, interrupt_flag: Optional[Dict[str, bool]] = None):
        """Process the response stream byte by byte and yield segments"""
        text_buffer = ""
        async for chunk in response_stream.aiter_bytes():
            is_interupted = interrupt_flag and interrupt_flag.get("interrupted", False)
            # First check if streaming should be interrupted
            if is_interupted:
                break
                
            if chunk:
                text = chunk.decode("utf-8", errors="ignore")
                text_buffer += text
                # Yield when we have a complete thought or enough words
                if len(text_buffer.split()) > 10 or len(text_buffer) > 100:
                    yield text_buffer
                    text_buffer = ""
        
        # Only yield remaining text if not interrupted and there's something to yield
        if text_buffer and not is_interupted:
            yield text_buffer

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

    async def rag_query_no_conversation_streaming_async(self, query_no_conversation_request_model: QueryNoConversationRequestModel, timeout: int = 60, pause_duration_between_chunks_ms: int = 0) -> AsyncGenerator[str, None]:
        """POST /rag/inference/no-conversation/ask-question/stream: Stream RAG answer without conversation.
        
        Args:
            query_no_conversation_request_model: Le modèle de requête
            timeout: Délai d'expiration en secondes pour la requête
            pause_duration_between_chunks_ms: Durée de pause en millisecondes entre chaque chunk retourné (0 = pas de pause)
        """
        try:
            async with self.client.stream(
                "POST", 
                "/rag/inference/no-conversation/ask-question/stream", 
                json=query_no_conversation_request_model.to_dict(),
                timeout=httpx.Timeout(timeout)
            ) as resp:
                resp.raise_for_status()
                async for segment in self.stream_by_segment(resp, pause_duration_between_chunks_ms):
                    yield segment
        except httpx.ReadTimeout:
            yield "Je suis désolé, mais je n'ai pas pu obtenir une réponse à temps. Pouvez-vous reformuler votre question?"
        except httpx.ConnectError as exc:
            yield f"Désolé, je ne peux pas me connecter au serveur de réponses pour le moment."
        except Exception as e:
            yield f"Une erreur s'est produite lors de la récupération de la réponse: {str(e)}"

    async def aclose(self):
        await self.client.aclose()
