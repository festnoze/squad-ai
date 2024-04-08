from langchain.llms.ollama  import Ollama
from langchain.callbacks.manager import CallbackManager
from langchain.callbacks.streaming_stdout import StreamingStdOutCallbackHandler


from langchain.prompts import PromptTemplate
from langchain.schema.messages import HumanMessage, SystemMessage
from langchain_core.prompts.chat import (
    ChatPromptTemplate,
    HumanMessagePromptTemplate,
)
from langchain.chains import ConversationChain
from langchain_core.prompts.chat import MessagesPlaceholder
from langchain.memory import ConversationBufferMemory
from langchain_core.messages.base import BaseMessage, BaseMessageChunk
from typing import List, Tuple, Union
import uuid
import time
# internal import
from misc import misc
from front_client import front_client
from models.stream_container import StreamContainer
from langchain_adapter_interface import LangChainAdapter
from streaming import stream
from models.conversation import Conversation, Message

class LangChainOllamaAdapter(LangChainAdapter):
    def create_chat_langchain(self, model: str, timeout_seconds: int = 50, temperature:float = 0.7) -> Ollama:
        return Ollama(    
            name= f"ollama_{str(uuid.uuid4())}",
            model= model,
            timeout= timeout_seconds,
            temperature= temperature,
            callback_manager= CallbackManager([StreamingStdOutCallbackHandler()])
        )
    
    def invoke_with_conversation(self, chat_model: Ollama, user_role: str, conversation: Conversation, instructions: List[str]) -> Message:
        exchanges = conversation.to_langchain_messages(user_role, instructions)
        answer, elapsed = LangChainOllamaAdapter.invoke(chat_model, exchanges)        
        answer_message = Message(user_role, answer, elapsed)
        conversation.add_message(answer_message)
        return answer_message
    
    def invoke(self, chat_model: Ollama, input) -> Tuple[str, float]:
        start_time = time.time()
        response = chat_model.invoke(input)
        end_time = time.time()
        elapsed = misc.get_elapsed_time_seconds(start_time, end_time)
        answer = response.content
        return (answer, elapsed)
    
    async def ask_llm_new_pm_business_message_streamed_to_front_async(self, chat_model: Ollama, user_role: str, conversation: Conversation, instructions: List[str]) -> Message:
        exchanges = conversation.to_langchain_messages(user_role, instructions)            
        full_stream = StreamContainer()
        start_time = time.time()
        content_stream = stream.get_chat_answer_as_stream_not_await_async(chat= chat_model, input= exchanges, full_stream= full_stream, display_console= True)
        await front_client.post_new_metier_or_pm_answer_as_stream(content_stream)
        end_time = time.time()
        elapsed = misc.get_elapsed_time_seconds(start_time, end_time)
        answer_message = Message(user_role, full_stream.content, elapsed)
        conversation.add_message(answer_message)
        front_client.post_update_last_metier_or_pm_answer(answer_message)
        return answer_message