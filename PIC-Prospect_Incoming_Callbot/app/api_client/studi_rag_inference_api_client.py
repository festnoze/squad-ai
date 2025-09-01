from collections.abc import AsyncGenerator
from typing import Any
from uuid import UUID

import httpx
from api_client.conversation_persistence_interface import ConversationPersistenceInterface
from api_client.rag_query_interface import RagQueryInterface
from api_client.request_models.conversation_request_model import ConversationRequestModel
from api_client.request_models.query_asking_request_model import (
    QueryAskingRequestModel,
    QueryNoConversationRequestModel,
)
from api_client.request_models.user_request_model import UserRequestModel
from speech.text_processing import ProcessText
from utils.envvar import EnvHelper

from database.models.conversation import Conversation
from database.models.message import Message
from database.models.user import User


class StudiRAGInferenceApiClient(ConversationPersistenceInterface, RagQueryInterface):
    """
    Async client for interacting with the /rag/inference endpoints.
    """

    def __init__(
        self,
        host_base_name: str | None = None,
        host_port: int | None = None,
        is_ssh: bool | None = None,
        connect_timeout: float = 5.0,
        read_timeout: float = 60.0,
    ):
        # Read host and port from environment if not provided
        self.host_base_name = host_base_name or EnvHelper.get_rag_api_host()
        self.host_port = host_port or int(EnvHelper.get_rag_api_port())
        self.is_ssh = is_ssh or EnvHelper.get_rag_api_is_ssh()
        self.connect_timeout = connect_timeout
        self.read_timeout = read_timeout
        self.timeout = httpx.Timeout(
            connect=self.connect_timeout, read=self.read_timeout, write=self.read_timeout, pool=self.connect_timeout
        )

        self.host_base_url = f"http{'s' if self.is_ssh else ''}://{self.host_base_name}:{self.host_port}"
        self.client = httpx.AsyncClient(base_url=self.host_base_url, timeout=self.timeout)

    async def test_client_connection_async(self):
        # Test client connection
        try:
            short_timeout = httpx.Timeout(connect=3, read=3, write=3, pool=3)
            resp = await self.client.get("/ping", timeout=short_timeout)
            assert resp.status_code == 200
            assert resp.content == b'"pong"'
            return True
        except httpx.ConnectError as ex:
            raise RuntimeError(f"Cannot connect to RAG inference server at {self.host_base_url}: {ex!s}") from ex

    async def reinitialize_async(self) -> None:
        """POST /rag/inference/reinitialize: Reinitialize the service."""
        try:
            resp = await self.client.post("/rag/inference/reinitialize")
            resp.raise_for_status()
        except httpx.ConnectError as exc:
            raise RuntimeError(f"Cannot connect to RAG inference server at {self.host_base_url}") from exc
        except httpx.TimeoutException as exc:
            raise RuntimeError(f"Timeout connecting to RAG inference server at {self.host_base_url}") from exc

    async def create_or_retrieve_user_async(self, user_request_model: UserRequestModel, timeout: int = 10) -> UUID:
        """PATCH /rag/inference/user/sync: Create or retrieve a user."""
        try:
            user_request_model_dict = user_request_model.to_dict()
            resp = await self.client.patch(
                "/rag/inference/user/sync", json=user_request_model_dict, timeout=self.timeout
            )
            resp.raise_for_status()
            return UUID(resp.json().get("id", ConversationPersistenceInterface.NoneUuid))
        except httpx.ConnectError as exc:
            raise RuntimeError(f"Cannot connect to RAG inference server at {self.host_base_url}") from exc

    async def create_new_conversation_async(
        self, conversation_request_model: ConversationRequestModel, timeout: int = 10
    ) -> UUID:
        """POST /rag/inference/conversation/create: Create a new conversation."""
        try:
            resp = await self.client.post(
                "/rag/inference/conversation/create", json=conversation_request_model.to_dict(), timeout=self.timeout
            )
            resp.raise_for_status()
            return UUID(resp.json().get("id", ConversationPersistenceInterface.NoneUuid))
        except httpx.ConnectError as exc:
            raise RuntimeError(f"Cannot connect to RAG inference server at {self.host_base_url}") from exc

    async def get_user_last_conversation_async(self, user_id: UUID, timeout: int = 10) -> dict:
        """GET /rag/inference/conversation/last/user/{user_id}: Get the last conversation for a user."""
        try:
            resp = await self.client.get(f"/rag/inference/conversation/last/user/{user_id!s}", timeout=self.timeout)
            resp.raise_for_status()
            return resp.json()
        except httpx.ConnectError as exc:
            raise RuntimeError(f"Cannot connect to RAG inference server at {self.host_base_url}") from exc

    async def add_message_to_conversation_async(
        self, conversation_id: str, new_message_content: str, role: str = "assistant", timeout: int = 10
    ) -> dict | None:
        """POST /rag/inference/conversation/add-message: Add a message to a conversation."""
        try:
            # Validate conversation_id to create UUID
            if not conversation_id or conversation_id == ConversationPersistenceInterface.NoneUuid:
                raise ValueError("conversation_id is required and cannot be NoneUuid")
            conversation_uuid = UUID(conversation_id)
            request_model = QueryAskingRequestModel(
                conversation_id=conversation_uuid,
                user_query_content=new_message_content,
                role=role,
                display_waiting_message=False,
            )
            resp = await self.client.post(
                "/rag/inference/conversation/add-external-message", json=request_model.to_dict(), timeout=self.timeout
            )
            resp.raise_for_status()
            return resp.json()
        except ValueError as exc:
            raise exc
        except httpx.ConnectError as exc:
            raise RuntimeError(f"Cannot connect to RAG inference server at {self.host_base_url}") from exc
        except httpx.TimeoutException as exc:
            raise RuntimeError(f"Timeout connecting to RAG inference server at {self.host_base_url}") from exc

    async def add_message_to_user_last_conversation_or_create_one_async(
        self, user_id: UUID, new_message: str
    ) -> "Conversation":
        """Add a user message to the user's last conversation or create a new one.

        Args:
            user_id: The UUID of the user to add the message to
            new_message: The message content to add to the conversation

        Returns:
            Conversation object containing the added message
        """
        try:
            # Get user's last conversation
            last_conversation = await self.get_user_last_conversation_async(user_id)

            # If user has a conversation, add message to it
            if last_conversation and last_conversation.get("id"):
                conversation_id = last_conversation["id"]
                await self.add_message_to_conversation_async(str(conversation_id), new_message, role="user")

                # Return a Conversation object - we need to import it
                from database.models.conversation import Conversation

                return Conversation(
                    id=conversation_id,
                    user=User(id=user_id),
                    messages=last_conversation.get("messages", []) + [{"content": new_message, "role": "user"}],
                )
            else:
                # Create new conversation and add message
                from api_client.request_models.conversation_request_model import ConversationRequestModel

                conversation_request = ConversationRequestModel(user_id=user_id)
                conversation_id = await self.create_new_conversation_async(conversation_request)

                # Add the message to the new conversation
                await self.add_message_to_conversation_async(str(conversation_id), new_message, role="user")

                # Return a Conversation object
                from database.models.conversation import Conversation

                return Conversation(
                    id=conversation_id, user=User(id=user_id), messages=[Message(content=new_message, role="user")]
                )

        except httpx.ConnectError as exc:
            raise RuntimeError(f"Cannot connect to RAG inference server at {self.host_base_url}") from exc
        except httpx.TimeoutException as exc:
            raise RuntimeError(f"Timeout connecting to RAG inference server at {self.host_base_url}") from exc

    async def rag_query_stream_async(
        self, query_asking_request_model: QueryAskingRequestModel, interrupt_flag: dict | None = None, timeout: int = 80
    ) -> AsyncGenerator[str, None]:
        """
        POST /rag/inference/conversation/ask-question/phone/stream: Stream RAG answer for a conversation.

        Args:
            query_asking_request_model: Model containing the query data
            interrupt_flag: Mutable object (like a dict {"interrupted": False}) with a modifiable value that can be externally changed to interrupt the streaming
            timeout: Request timeout in seconds
        """
        try:
            # Set separate timeouts for connect and read operations
            # custom_timeout = httpx.Timeout(connect=self.connect_timeout, read=timeout, write=timeout, pool=self.connect_timeout)
            json = query_asking_request_model.to_dict()
            async with self.client.stream(
                "POST",
                "/rag/inference/conversation/ask-question/phone/stream",
                json=json,
                # timeout=custom_timeout
            ) as resp:
                resp.raise_for_status()
                async for segment in self._stream_by_sentence(resp, interrupt_flag):
                    yield segment

        except httpx.ReadTimeout:
            yield "Je suis désolé, mais je n'ai pas pu obtenir une réponse à temps. Pouvez-vous reformuler votre question?"
        except httpx.ConnectTimeout:
            yield "Désolé, je ne peux pas me connecter au serveur de réponses pour le moment. Veuillez vérifier votre connexion réseau."
        except httpx.ConnectError:
            yield "Désolé, je ne peux pas me connecter au serveur de réponses pour le moment."
        except TimeoutError:
            yield "Je suis désolé, mais la connexion a pris trop de temps. Veuillez réessayer plus tard."
        except Exception as e:
            yield f"Une erreur s'est produite lors de la récupération de la réponse: {e!s}"

    async def rag_query_no_conversation_async(
        self, query_no_conversation_request_model: QueryNoConversationRequestModel, timeout: int = 80
    ) -> dict[str, Any]:
        """POST /rag/inference/no-conversation/ask-question: Get RAG answer without conversation (not streamed)."""
        try:
            resp = await self.client.post(
                "/rag/inference/no-conversation/ask-question",
                json=query_no_conversation_request_model.to_dict(),
                timeout=self.timeout,
            )
            resp.raise_for_status()
            return resp.json()
        except httpx.ConnectError as exc:
            raise RuntimeError(f"Cannot connect to RAG inference server at {self.host_base_url}") from exc

    async def rag_query_no_conversation_streaming_async(
        self,
        query_no_conversation_request_model: QueryNoConversationRequestModel,
        interrupt_flag: dict | None = None,
        timeout: int = 80,
    ) -> AsyncGenerator[str, None]:
        """POST /rag/inference/no-conversation/ask-question/stream: Stream RAG answer without conversation.

        Args:
            query_no_conversation_request_model: Le modèle de requête
            interrupt_flag: Drapeau d'interruption (dictionnaire avec clé "interrupted")
            timeout: Délai d'expiration en secondes pour la requête
        """
        try:
            async with self.client.stream(
                "POST",
                "/rag/inference/no-conversation/ask-question/stream",
                json=query_no_conversation_request_model.to_dict(),
                timeout=self.timeout,
            ) as resp:
                resp.raise_for_status()
                async for segment in self._stream_by_sentence(resp, interrupt_flag):
                    yield segment
        except httpx.ReadTimeout:
            yield "Je suis désolé, mais je n'ai pas pu obtenir une réponse à temps. Pouvez-vous reformuler votre question?"
        except httpx.ConnectTimeout:
            yield "Désolé, je ne peux pas me connecter au serveur de réponses pour le moment. Veuillez vérifier votre connexion réseau."
        except httpx.ConnectError:
            yield "Désolé, je ne peux pas me connecter au serveur de réponses pour le moment."
        except TimeoutError:
            yield "Je suis désolé, mais la connexion a pris trop de temps. Veuillez réessayer plus tard."
        except Exception as e:
            yield f"Une erreur s'est produite lors de la récupération de la réponse: {e!s}"

    async def close_client_async(self):
        await self.client.aclose()

    ### TOOLS ###

    @staticmethod
    async def _stream_by_sentence(response_stream: httpx.Response, interrupt_flag: dict[str, bool] | None = None):
        """Process the response stream byte by byte and yield segments"""
        text_buffer = ""

        async for chunk in response_stream.aiter_bytes():
            is_interrupted = interrupt_flag and interrupt_flag.get("interrupted", False)
            # First check if streaming should be interrupted
            if is_interrupted:
                break

            if chunk:
                text = chunk.decode("utf-8", errors="ignore")
                text_buffer += text
                # Yield when we have a complete sentence or too much characters
                if (
                    any(separator in text_buffer for separator in ProcessText.split_separators)
                    or len(text_buffer.split()) > 20
                    or len(text_buffer) > 100
                ):
                    yield text_buffer
                    text_buffer = ""

        # Only yield remaining text if not interrupted and there's something to yield
        if text_buffer and not (interrupt_flag and interrupt_flag.get("interrupted", False)):
            yield text_buffer
