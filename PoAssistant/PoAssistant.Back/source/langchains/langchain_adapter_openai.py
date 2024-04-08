from langchain_openai import ChatOpenAI
from langchain.agents.openai_assistant import OpenAIAssistantRunnable
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
from streaming import stream
from models.conversation import Conversation, Message
from langchains.langchain_adapter_interface import LangChainAdapter

class LangChainAdapterForOpenAI(LangChainAdapter):
    def __init__(self, llm_model_name: str, api_key: str):
        self.llm_model_name = llm_model_name
        self.api_key = api_key
        self.llm: ChatOpenAI = self.create_langchain_llm(llm_model_name)

    def create_langchain_llm(self, llm_model_name: str, timeout_seconds: int = 50, temperature:float = 0.1) -> ChatOpenAI:
        return ChatOpenAI(    
            name= f"chat_openai_{str(uuid.uuid4())}",
            model= llm_model_name,
            timeout= timeout_seconds,
            temperature= temperature,
            api_key= self.api_key,
        )
    
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
        content_stream = stream.get_llm_answer_stream_not_await_async(llm= self.llm, input= exchanges, full_stream= full_stream, display_console= True)
        await front_client.post_new_metier_or_pm_answer_as_stream(content_stream)
        end_time = time.time()
        elapsed = misc.get_elapsed_time_seconds(start_time, end_time)
        answer_message = Message(user_role, full_stream.content, elapsed)
        conversation.add_message(answer_message)
        front_client.post_update_last_metier_or_pm_answer(answer_message)
        return answer_message