from abc import ABC, abstractmethod
from typing import Any, List, Tuple
# internal import
from models.conversation import Conversation, Message

class LangChainAdapter(ABC):
    api_key: str = None        
    llm: Any = None

    @abstractmethod
    def create_langchain_llm(self, llm_model_name: str, timeout_seconds: int = 50, temperature:float = 0.1):
        pass

    @abstractmethod
    def invoke_with_conversation(self, user_role: str, conversation: Conversation, instructions: List[str]) -> Message:
        pass

    @abstractmethod
    def invoke_with_elapse_time(self, input) -> Tuple[str, float]:
        pass

    @abstractmethod
    async def ask_llm_new_pm_business_message_streamed_to_front_async(self, user_role: str, conversation: Conversation, instructions: List[str]) -> Message:
        pass