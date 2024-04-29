import time
from typing import Any, List, Tuple, Union
from langchain_openai import ChatOpenAI
from langchain.llms.ollama  import Ollama
import uuid
# internal imports
from models.conversation import Conversation, Message
from langchains.langchain_adapter_type import LangChainAdapterType
from models.stream_container import StreamContainer
from front_client import front_client
from misc import misc
from langchains.langchain_factory import LangChainFactory

# from langchain.callbacks.manager import CallbackManager
# from langchain.callbacks.streaming_stdout import StreamingStdOutCallbackHandler

# from langchain.prompts import PromptTemplate
# from langchain.schema.messages import HumanMessage, SystemMessage
# from langchain_core.prompts.chat import (
#     ChatPromptTemplate,
#     HumanMessagePromptTemplate,
# )
# from langchain.chains import ConversationChain
# from langchain_core.prompts.chat import MessagesPlaceholder
# from langchain.memory import ConversationBufferMemory
# from langchain_core.messages.base import BaseMessage, BaseMessageChunk

class LangChainAdapter():
    api_key: str = None
    adapter_type: LangChainAdapterType = None
    llm: Any = None

    def __init__(self, adapter_type: LangChainAdapterType, llm_model_name: str, timeout_seconds: int = 50, temperature: float = 0.1, api_key: str = None):
        self.adapter_type = adapter_type
        self.api_key = api_key
        self.llm = LangChainFactory.create_llm(adapter_type, llm_model_name, timeout_seconds, temperature, api_key)
    
    def invoke_with_conversation(self, user_role: str, conversation: Conversation, instructions: List[str]) -> Message:
        exchanges = conversation.to_langchain_messages(user_role, instructions)
        answer, elapsed = self.invoke_with_elapse_time(llm= self.llm, input= exchanges)        
        answer_message = Message(user_role, answer, elapsed)
        conversation.add_message(answer_message)
        return answer_message
    
    def invoke_with_elapse_time(self, input) -> Tuple[str, float]:
        start_time = time.time()
        response = self.llm.invoke(input)
        end_time = time.time()
        elapsed = misc.get_elapsed_time_seconds(start_time, end_time)
        answer = response.content
        return (answer, elapsed)
    
    async def ask_llm_new_pm_business_message_streamed_to_front_async(self, user_role: str, conversation: Conversation, instructions: List[str]) -> Message:
        exchanges = conversation.to_langchain_messages(user_role, instructions)            
        full_stream = StreamContainer()
        start_time = time.time()
        content_stream = self.get_llm_answer_stream_not_await_async(input= exchanges, full_stream= full_stream, display_console= True)
        await front_client.post_new_metier_or_pm_answer_as_stream(content_stream)
        end_time = time.time()
        elapsed = misc.get_elapsed_time_seconds(start_time, end_time)
        answer_message = Message(user_role, full_stream.content, elapsed)
        conversation.add_message(answer_message)
        front_client.post_update_last_metier_or_pm_answer(answer_message)
        return answer_message

    async def get_llm_answer_stream_not_await_async(self, input, full_stream: StreamContainer, display_console: bool = True):
        new_line_for_stream = "\\/%*/\\"
        async for chunk in self.llm.astream(input):
            
            # Handle both OpenAI & Ollama streams struct:
            # stream's chunks content are in a 'content' property on OpenAI LLM but are direct on Ollama LLMs
            if self.adapter_type == LangChainAdapterType.OpenAI:
                content = chunk.content
            elif self.adapter_type == LangChainAdapterType.Ollama:
                content = chunk
            else:
                raise ValueError(f"Unknown adapter type: {self.adapter_type}")
            
            if display_console:
                print(content, end= "", flush= True)
            full_stream.add_content(content)
            content = content.replace('\r\n', '\n').replace('\n', new_line_for_stream)
            yield content.encode('utf-8')