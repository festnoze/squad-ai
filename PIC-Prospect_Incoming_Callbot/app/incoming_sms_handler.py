import logging
from uuid import UUID

from api_client.request_models.conversation_request_model import ConversationRequestModel
from api_client.request_models.query_asking_request_model import QueryAskingRequestModel
from api_client.request_models.user_request_model import DeviceInfoRequestModel, UserRequestModel


class IncomingSMSHandler:
    def __init__(self):
        self.logger = logging.getLogger(__name__)

    async def init_user_and_conversation_upon_incoming_sms(self, phone_number: str) -> str | None:
        """Initialize the user session: retrieve or create user and conversation and send a welcome message"""
        user_RM = UserRequestModel(
            user_id=None,
            user_name="Twilio SMS in " + (phone_number or "Unknown User"),
            IP=phone_number or "Unknown IP",
            device_info=DeviceInfoRequestModel(
                user_agent="twilio", platform="phone", app_version="", os="", browser="", is_mobile=True
            ),
        )
        try:
            user = await self.studi_rag_inference_api_client.create_or_retrieve_user_async(user_RM)
            user_id = user["id"]
            if isinstance(user_id, str):
                user_id = UUID(user_id)

            last_conversation = await self.studi_rag_inference_api_client.get_user_last_conversation_async(user_id)

            if last_conversation["id"] is not None:
                self.logger.info(f"Retrieved existing conversation {last_conversation['id']} for user: {user_id}")
                return last_conversation["id"]
            else:  # Create the conversation if none already exists
                self.logger.info(f"Creating new conversation for user: {user_id}")
                conversation_model = ConversationRequestModel(user_id=user_id)
                new_conversation = await self.studi_rag_inference_api_client.create_new_conversation_async(
                    conversation_model
                )
                return new_conversation["id"]

        except Exception as e:
            self.logger.error(f"Error retrieving user's last conversation or creating it: {e!s}")
            return None

    async def get_rag_response_to_sms_query_async(self, conversation_id: str, incoming_message: str) -> str:
        """Main method: handle a full audio conversation with I/O Twilio streams on a WebSocket."""
        rag_query_RM = QueryAskingRequestModel(
            conversation_id=conversation_id, user_query_content=incoming_message, display_waiting_message=False
        )
        response = self.studi_rag_inference_api_client.rag_query_stream_async(rag_query_RM, timeout=60)

        full_rag_answer = ""
        async for chunk in response:
            full_rag_answer += chunk
        self.logger.info(f'AI full answer to incoming SMS: "{full_rag_answer}"')
        return full_rag_answer
