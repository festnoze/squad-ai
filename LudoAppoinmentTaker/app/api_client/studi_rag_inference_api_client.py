import os
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
    def __init__(self, host_base_name: str | None = None, host_port: int | None = None, is_ssh: bool = False,
                 connect_timeout: float = 5.0, read_timeout: float = 60.0):
        # Read host and port from environment if not provided
        self.host_base_name = host_base_name or os.getenv("RAG_HOST", "localhost")
        self.host_port = host_port or int(os.getenv("RAG_PORT", "8281"))
        self.is_ssh = is_ssh
        self.connect_timeout = connect_timeout
        self.read_timeout = read_timeout
        
        self.host_base_url = f"http{'s' if is_ssh else ''}://{self.host_base_name}:{self.host_port}"
        self.client = httpx.AsyncClient(
            base_url=self.host_base_url,
            timeout=httpx.Timeout(connect=self.connect_timeout, read=self.read_timeout, write=self.read_timeout, pool=self.connect_timeout)
        )

    async def test_client_connection_async(self):
        #Test client connection
        try:
            resp = await self.client.get("/ping")
            assert resp.status_code == 200
            assert resp.content == b'"pong"'
            return True
        except httpx.ConnectError:
            return False

    async def reinitialize_async(self) -> None:
        """POST /rag/inference/reinitialize: Reinitialize the service."""
        try:
            resp = await self.client.post("/rag/inference/reinitialize")
            resp.raise_for_status()
        except httpx.ConnectError as exc:
            raise RuntimeError(f"Cannot connect to RAG inference server at {self.host_base_url}") from exc
        except httpx.TimeoutException as exc:
            raise RuntimeError(f"Timeout connecting to RAG inference server at {self.host_base_url}") from exc

    async def create_or_retrieve_user_async(self, user_request_model: UserRequestModel, timeout: int = 10) -> Dict[str, Any]:
        """PATCH /rag/inference/user/sync: Create or retrieve a user."""
        try:
            user_request_model_dict = user_request_model.to_dict()
            resp = await self.client.patch("/rag/inference/user/sync", json=user_request_model_dict, timeout=httpx.Timeout(timeout))
            resp.raise_for_status()
            return resp.json()
        except httpx.ConnectError as exc:
            raise RuntimeError(f"Cannot connect to RAG inference server at {self.host_base_url}") from exc

    async def create_new_conversation_async(self, conversation_request_model: ConversationRequestModel, timeout: int = 10) -> Dict[str, Any]:
        """POST /rag/inference/conversation/create: Create a new conversation."""
        try:
            resp = await self.client.post("/rag/inference/conversation/create", json=conversation_request_model.to_dict(), timeout=httpx.Timeout(timeout))
            resp.raise_for_status()
            return resp.json()
        except httpx.ConnectError as exc:
            raise RuntimeError(f"Cannot connect to RAG inference server at {self.host_base_url}") from exc

    async def get_user_last_conversation_async(self, user_id: UUID, timeout: int = 10) -> Dict[str, Any]:
        """GET /rag/inference/conversation/last/user/{user_id}: Get the last conversation for a user."""
        try:
            resp = await self.client.get(f"/rag/inference/conversation/last/user/{str(user_id)}", timeout=httpx.Timeout(timeout))
            resp.raise_for_status()
            return resp.json()
        except httpx.ConnectError as exc:
            raise RuntimeError(f"Cannot connect to RAG inference server at {self.host_base_url}") from exc

    async def add_external_ai_message_to_conversation_async(self, conversation_id: str, new_message: str, timeout: int = 10) -> Dict[str, Any]:
        """POST /rag/inference/conversation/add-message: Add a message to a conversation."""
        try:
            request_model = QueryAskingRequestModel(conversation_id=UUID(conversation_id), user_query_content=new_message, display_waiting_message=False)
            resp = await self.client.post("/rag/inference/conversation/add-external-message", json=request_model.to_dict(), timeout=httpx.Timeout(timeout))
            resp.raise_for_status()
            return resp.json()
        except httpx.ConnectError as exc:
            raise RuntimeError(f"Cannot connect to RAG inference server at {self.host_base_url}") from exc

    async def rag_query_stream_async(self, query_asking_request_model: QueryAskingRequestModel, interrupt_flag: dict | None = None, timeout: int = 80) -> AsyncGenerator[str, None]:
        """
        POST /rag/inference/conversation/ask-question/phone/stream: Stream RAG answer for a conversation.
        
        Args:
            query_asking_request_model: Model containing the query data
            interrupt_flag: Mutable object (like a dict {"interrupted": False}) with a modifiable value that can be externally changed to interrupt the streaming
            timeout: Request timeout in seconds
        """
        try:
            # Set separate timeouts for connect and read operations
            custom_timeout = httpx.Timeout(connect=min(10.0, timeout), read=timeout)
            
            async with self.client.stream(
                "POST", 
                "/rag/inference/conversation/ask-question/phone/stream", 
                json=query_asking_request_model.to_dict(),
                timeout=custom_timeout
            ) as resp:
                resp.raise_for_status()
                async for segment in self._stream_by_segment(resp, interrupt_flag):
                    yield segment

        except httpx.ReadTimeout:
            yield "Je suis désolé, mais je n'ai pas pu obtenir une réponse à temps. Pouvez-vous reformuler votre question?"
        except httpx.ConnectTimeout:
            yield f"Désolé, je ne peux pas me connecter au serveur de réponses pour le moment. Veuillez vérifier votre connexion réseau."
        except httpx.ConnectError as exc:
            yield f"Désolé, je ne peux pas me connecter au serveur de réponses pour le moment."
        except asyncio.TimeoutError:
            yield "Je suis désolé, mais la connexion a pris trop de temps. Veuillez réessayer plus tard."
        except Exception as e:
            yield f"Une erreur s'est produite lors de la récupération de la réponse: {str(e)}"

    async def rag_query_no_conversation_async(self, query_no_conversation_request_model: QueryNoConversationRequestModel, timeout: int = 80) -> Dict[str, Any]:
        """POST /rag/inference/no-conversation/ask-question: Get RAG answer without conversation (not streamed)."""
        try:
            resp = await self.client.post(
                "/rag/inference/no-conversation/ask-question",
                json=query_no_conversation_request_model.to_dict(),
                timeout=httpx.Timeout(timeout)
            )
            resp.raise_for_status()
            return resp.json()
        except httpx.ConnectError as exc:
            raise RuntimeError(f"Cannot connect to RAG inference server at {self.host_base_url}") from exc

    async def rag_query_no_conversation_streaming_async(self, query_no_conversation_request_model: QueryNoConversationRequestModel, interrupt_flag: dict | None = None, timeout: int = 80) -> AsyncGenerator[str, None]:
        """POST /rag/inference/no-conversation/ask-question/stream: Stream RAG answer without conversation.
        
        Args:
            query_no_conversation_request_model: Le modèle de requête
            interrupt_flag: Drapeau d'interruption (dictionnaire avec clé "interrupted")
            timeout: Délai d'expiration en secondes pour la requête
        """
        try:
            # Set separate timeouts for connect and read operations
            custom_timeout = httpx.Timeout(connect=min(10.0, timeout), read=timeout)
            
            async with self.client.stream(
                "POST", 
                "/rag/inference/no-conversation/ask-question/stream", 
                json=query_no_conversation_request_model.to_dict(),
                timeout=custom_timeout
            ) as resp:
                resp.raise_for_status()
                async for segment in self._stream_by_segment(resp, interrupt_flag):
                    yield segment
        except httpx.ReadTimeout:
            yield "Je suis désolé, mais je n'ai pas pu obtenir une réponse à temps. Pouvez-vous reformuler votre question?"
        except httpx.ConnectTimeout:
            yield f"Désolé, je ne peux pas me connecter au serveur de réponses pour le moment. Veuillez vérifier votre connexion réseau."
        except httpx.ConnectError as exc:
            yield f"Désolé, je ne peux pas me connecter au serveur de réponses pour le moment."
        except asyncio.TimeoutError:
            yield "Je suis désolé, mais la connexion a pris trop de temps. Veuillez réessayer plus tard."
        except Exception as e:
            yield f"Une erreur s'est produite lors de la récupération de la réponse: {str(e)}"

    async def close_client_async(self):
        await self.client.aclose()

    
    ### TOOLS ###
    
    @staticmethod
    async def _stream_by_segment(response_stream: httpx.Response, interrupt_flag: Optional[dict[str, bool]] = None):
        """Process the response stream byte by byte and yield segments"""
        text_buffer = ""
        # Set a timeout for each individual chunk read
        chunk_timeout = 10  # 10 seconds per chunk timeout
        
        try:
            async for chunk in asyncio.wait_for(response_stream.aiter_bytes().__aiter__(), chunk_timeout):
                is_interrupted = interrupt_flag and interrupt_flag.get("interrupted", False)
                # First check if streaming should be interrupted
                if is_interrupted:
                    break
                    
                if chunk:
                    text = chunk.decode("utf-8", errors="ignore")
                    text_buffer += text
                    # Yield when we have a complete thought or enough words
                    if len(text_buffer.split()) > 10 or len(text_buffer) > 100:
                        yield text_buffer
                        text_buffer = ""
            
            # Only yield remaining text if not interrupted and there's something to yield
            if text_buffer and not (interrupt_flag and interrupt_flag.get("interrupted", False)):
                yield text_buffer
                
        except asyncio.TimeoutError:
            # If we have any buffered text, yield it before raising the timeout
            if text_buffer:
                yield text_buffer
            yield "Le serveur prend trop de temps à répondre. La communication a été interrompue."
