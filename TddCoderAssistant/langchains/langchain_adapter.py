import time
from datetime import datetime
from langchain_core.language_models import BaseChatModel
from langchain_openai import ChatOpenAI
#from langchain.llms.ollama import Ollama
from langchain_community.chat_models import ChatOllama
from langchain_groq import ChatGroq
import uuid
# internal imports
from langchains.langchain_adapter_type import LangChainAdapterType

class LangChainAdapter():
    api_key: str = None
    adapter_type: LangChainAdapterType = None
    llm: BaseChatModel = None

    def __init__(self, adapter_type: LangChainAdapterType, llm_model_name: str, timeout_seconds: int = 50, temperature: float = 0.1, api_key: str = None):
        self.adapter_type = adapter_type
        self.api_key = api_key
        if adapter_type == LangChainAdapterType.OpenAI:
            self.llm = self.create_llm_openai(llm_model_name, timeout_seconds, temperature)
        elif adapter_type == LangChainAdapterType.Ollama:
            self.llm = self.create_llm_ollama(llm_model_name, timeout_seconds, temperature)
        elif adapter_type == LangChainAdapterType.Groq:
            self.llm = self.create_llm_groq(llm_model_name, timeout_seconds, temperature)
        else:
            raise ValueError(f"Unknown adapter type: {adapter_type}")
 
    def create_llm_ollama(self, llm_model_name: str, timeout_seconds: int = 50, temperature:float = 0.1) -> ChatOllama:
        return ChatOllama(    
            name= f"ollama_{str(uuid.uuid4())}",
            model= llm_model_name,
            timeout= timeout_seconds,
            temperature= temperature
        )
    
    def create_llm_openai(self, llm_model_name: str, timeout_seconds: int = 50, temperature:float = 0.1) -> ChatOpenAI:
        chat = ChatOpenAI(    
            name= f"chat_openai_{str(uuid.uuid4())}",
            model= llm_model_name,
            timeout= timeout_seconds,
            temperature= temperature,
            api_key= self.api_key,
            openai_api_key= self.api_key
        )
    
    def create_llm_groq(self, llm_model_name: str, timeout_seconds: int = 50, temperature:float = 0.1) -> ChatGroq:
        return ChatGroq(    
            name= f"chat_groq_{str(uuid.uuid4())}",
            model_name= llm_model_name,
            timeout= timeout_seconds,
            temperature= temperature,
            groq_api_key= self.api_key,
        )
    
    def invoke_with_elapse_time(self, input) -> tuple[str, float]:
        start_time = time.time()
        response = self.llm.invoke(input)
        end_time = time.time()
        elapsed = self.get_elapsed_time_seconds(start_time, end_time)
        
        if isinstance(response, str):
            answer = response
        elif hasattr(response, 'content'):
            answer = response.content
        else:
            raise ValueError("Unhandled response type")
        
        return (answer, elapsed)
    
    async def get_llm_answer_stream_not_await_async(self, input, display_console: bool = True):
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
            #full_stream.add_content(content)
            content = content.replace('\r\n', '\n').replace('\n', new_line_for_stream)
            yield content.encode('utf-8')

    def get_elapsed_time_seconds(self, began_at: datetime, ended_at: datetime) -> int:
        if not ended_at:
            return -1
        elapsed_time = ended_at - began_at
        return int(elapsed_time)