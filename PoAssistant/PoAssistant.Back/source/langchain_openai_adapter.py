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
from typing import List, Tuple, Union
import uuid
from datetime import datetime, timedelta
from enum import Enum
import concurrent.futures
import asyncio
# internal import
from misc import misc
import uuid
import time

from models.conversation import Conversation, Message


class lc:
    api_key = ""

    def set_api_key(openai_api_key):
        lc.api_key = openai_api_key

    def create_chat_langchain(model, timeout_seconds = 50, temperature = 0.7) -> ChatOpenAI:
        return ChatOpenAI(    
            name= f"assistant_{str(uuid.uuid4())}",
            model= model,
            timeout= timeout_seconds,
            temperature= temperature,
            api_key= lc.api_key,
        )
    
    def invoke_with_conversation(chat_model: ChatOpenAI, user_role: str, conversation: Conversation, instructions: List[str]) -> Message:
        exchanges = conversation.to_langchain_messages(user_role, instructions)
        answer, elapsed = lc.invoke(chat_model, exchanges)
        conversation.add_message(user_role, answer, elapsed)
        return conversation.messages[-1] #return the last conv msg which corresponds to the invoke answer
    
    def invoke(chat_model: ChatOpenAI, input) -> Tuple[str, float]:
        start_time = time.time()
        response = chat_model.invoke(input)
        end_time = time.time()
        elapsed = misc.get_elapsed_time_seconds(start_time, end_time)
        answer = response.content
        return (answer, elapsed)

    def create_assistant_langchain(model, instructions, file_ids = None):
        return OpenAIAssistantRunnable.create_assistant(    
            name= f"assistant_{str(uuid.uuid4())}",
            instructions= instructions,
            tools=[],
            model= model,
            file_ids = file_ids,
            api_key= lc.api_key
        ) 