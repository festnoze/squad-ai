from langchain_openai import ChatOpenAI
from langchain_community.chat_models import ChatOllama
from langchain_groq import ChatGroq
from langchain_core.language_models import BaseChatModel
from langchains.langchain_adapter_type import LangChainAdapterType
import uuid

class LangChainFactory():

    @staticmethod
    def create_llm(adapter_type: LangChainAdapterType, llm_model_name: str, timeout_seconds: int = 50, temperature: float = 0.1, api_key: str = None) -> BaseChatModel:
        llm: BaseChatModel = None
        if adapter_type == LangChainAdapterType.OpenAI:
            llm = LangChainFactory.create_llm_openai(llm_model_name, api_key, timeout_seconds, temperature)
        elif adapter_type == LangChainAdapterType.Ollama:
            llm = LangChainFactory.create_llm_ollama(llm_model_name, timeout_seconds, temperature)
        elif adapter_type == LangChainAdapterType.Groq:
            llm = LangChainFactory.create_llm_groq(llm_model_name, api_key, timeout_seconds, temperature)
        else:
            raise ValueError(f"Unknown adapter type: {adapter_type}")
        return llm 
 
    @staticmethod
    def create_llm_openai(llm_model_name: str, api_key: str, timeout_seconds: int = 50, temperature:float = 0.1) -> ChatOpenAI:
        return ChatOpenAI(    
            name= f"chat_openai_{str(uuid.uuid4())}",
            model= llm_model_name,
            timeout= timeout_seconds,
            temperature= temperature,
            api_key= api_key,
        )
    
    @staticmethod
    def create_llm_ollama(llm_model_name: str, timeout_seconds: int = 50, temperature:float = 0.1) -> ChatOllama:
        return ChatOllama(    
            name= f"ollama_{str(uuid.uuid4())}",
            model= llm_model_name,
            timeout= timeout_seconds,
            temperature= temperature
        )
        
    @staticmethod     
    def create_llm_groq(self, llm_model_name: str, api_key: str, timeout_seconds: int = 50, temperature:float = 0.1) -> ChatGroq:
        return ChatGroq(    
            name= f"chat_groq_{str(uuid.uuid4())}",
            model_name= llm_model_name,
            timeout= timeout_seconds,
            temperature= temperature,
            groq_api_key= api_key,
        )