from abc import ABC, abstractmethod
from typing import List, Tuple
# internal import
from models.conversation import Conversation, Message

class LangChainAdapter(ABC):
    @abstractmethod
    def set_api_key(openai_api_key: str)-> None:
        pass

    @abstractmethod
    def create_chat_langchain(model: str, timeout_seconds: int = 50, temperature:float = 0.7):
        pass

    @abstractmethod
    def invoke_with_conversation(chat_model, user_role: str, conversation: Conversation, instructions: List[str]) -> Message:
        pass

    @abstractmethod
    def invoke(chat_model, input) -> Tuple[str, float]:
        pass

    @abstractmethod
    async def ask_llm_new_pm_business_message_streamed_to_front_async(chat_model, user_role: str, conversation: Conversation, instructions: List[str]) -> Message:
        pass

    @abstractmethod
    def perform_task(self, data):
        pass